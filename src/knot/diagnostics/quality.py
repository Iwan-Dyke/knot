"""Read-only integrity checks and heuristic curation warnings for the whole dataset."""

import argparse
import json
import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

from pyoxigraph import Literal, NamedNode, RdfFormat, Store

from knot.curating.entity_labels import apply_entity_labels
from knot.curating.evidence_accounts import annotate_accounts
from knot.curating.provenance import validate_sources
from knot.curating.rules import ACTOR_TYPES as ACTOR_TYPES
from knot.curating.rules import SPECIFIC_TYPES as SPECIFIC_TYPES
from knot.curating.rules import relationship_warnings, validate_relationship
from knot.graph.query import identity_bindings
from knot.graph.rdf import ATTRIBUTED, DERIVED, LABEL, META, RDF_TYPE, VOCAB, one, values
from knot.retrieval_engine.evidence import _Evidence
from knot.reviewing.state import apply_reviews, read_events
from knot.shared.datasets import cli_data_root
from knot.shared.storage import digest, managed_path
from knot.shared.vocabulary import TYPES
from knot.writing.notes import REVISION, _canonical_entities, _history, _registry
from knot.writing.sources import add_note_sources

GENERIC_NAMES = {'result', 'update', 'meeting', 'question', 'action', 'notes', 'untitled'}
NUMERIC_NAME = re.compile(r'[+-]?\d+(?:[.,]\d+)?(?:[eE][+-]?\d+)?')
CONTEXT_NAME = re.compile(
    r'^(?:built|reviewed|completed|delivered|implemented|selected|improved|resolved|'
    r'achieved|updated|suitable candidate selected|successfully|the team|this|that|it)(?:\W|$)',
    re.IGNORECASE,
)
AI_AUTHORS = {'codex', 'kiro', 'sage', 'chatgpt'}
CONVERSATIONAL = re.compile(
    r'\b(can you add|please add|add (?:an? |the )?(?:edge|link)|'
    r'add (?:this|that|some more)|needs? to be made|add to the graph|'
    r'separate (?:notes|entities)|separte (?:notes|entities))\b',
    re.IGNORECASE,
)
READ_ERRORS = (ValueError, OSError, SyntaxError, TypeError, KeyError)
REPORT_VERSION = 1
RULESET_VERSION = 'continuous-curation-v1'


def _classification(severity, code):
    if severity == 'errors':
        return 'integrity', 'repair'
    if code in {'label_collision', 'low_quality_entity_name'}:
        return 'historical_labels', 'informational'
    if code == 'missing_generation_date':
        return 'metadata_completeness', 'informational'
    if code in {'shared_source_bytes', 'repeated_source_span'}:
        return 'source_dependence', 'review'
    if code in {'conversational_note', 'missing_derivation', 'unsupported_curated_association'}:
        return 'note_curation', 'editorial'
    if code in {
        'decision_subject_needs_review',
        'actor_subject_needs_review',
        'decision_about_subject_needs_review',
        'relationship_object_type_needs_review',
        'self_relationship_needs_review',
        'claim_qualification_needs_review',
        'literal_entity_relation',
    }:
        return 'relationship_semantics', 'review'
    if code in {'duplicate_identity_bindings', 'current_name_collision'}:
        return 'identity_candidates', 'review'
    return 'entity_description', 'editorial'


def _finding_id(finding, severity):
    identity = {
        key: value
        for key, value in finding.items()
        if key not in {'id', 'detail', 'priority', 'category'}
    }
    # Older reports used detail as the actual alias value for this one rule.
    if finding['code'] == 'low_quality_entity_name':
        identity.setdefault('label', finding['detail'])
    identity['severity'] = severity
    return 'urn:knot:quality:' + digest(
        json.dumps(identity, sort_keys=True, ensure_ascii=False).encode()
    )


def _diagnostics(result):
    priorities, categories = Counter(), Counter()
    for severity in ('errors', 'warnings'):
        for finding in result[severity]:
            finding['category'], finding['priority'] = _classification(severity, finding['code'])
            finding['id'] = _finding_id(finding, severity)
            priorities[finding['priority']] += 1
            categories[finding['category']] += 1
    result['schema_version'] = REPORT_VERSION
    result['ruleset_version'] = RULESET_VERSION
    result['counts']['findings_by_priority'] = dict(sorted(priorities.items()))
    result['counts']['findings_by_category'] = dict(sorted(categories.items()))
    return result


def compare_reports(current, baseline):
    """Compare diagnostics, without suppressing findings or deciding their meaning."""

    def index(report):
        if (
            not isinstance(report, dict)
            or report.get('schema_version', REPORT_VERSION) != REPORT_VERSION
        ):
            raise ValueError('Unsupported quality report schema version')
        indexed = {}
        for severity in ('errors', 'warnings'):
            findings = report.get(severity)
            if not isinstance(findings, list):
                raise ValueError('Quality baseline requires errors and warnings lists')
            if any(
                not isinstance(finding, dict)
                or any(
                    not isinstance(finding.get(key), str) for key in ('code', 'record', 'detail')
                )
                for finding in findings
            ):
                raise ValueError('Invalid quality baseline finding')
            indexed[severity] = {_finding_id(finding, severity) for finding in findings}
        return indexed

    now, before = index(current), index(baseline)
    result = {
        'baseline_schema_version': baseline.get('schema_version'),
        'baseline_ruleset_version': baseline.get('ruleset_version'),
        'same_ruleset': current.get('ruleset_version') == baseline.get('ruleset_version')
        and current.get('ruleset_version') is not None,
        'interpretation': 'Finding changes are diagnostics, not proof of data improvement or '
        'degradation; compare rule versions and original records.',
        'counts': {},
    }
    for state in ('new', 'resolved', 'persisting'):
        result[state] = {}
        for severity in ('errors', 'warnings'):
            ids = {
                'new': now[severity] - before[severity],
                'resolved': before[severity] - now[severity],
                'persisting': now[severity] & before[severity],
            }[state]
            result[state][severity] = sorted(ids)
        result['counts'][state] = {key: len(ids) for key, ids in result[state].items()}
    return result


def _normalise(label):
    return ' '.join(re.findall(r'\w+', unicodedata.normalize('NFKC', label).casefold()))


def _name_issues(label):
    """Conservative review prompts, not rules for rejecting natural language or identity."""
    issues = {}
    normalised = _normalise(label)
    if NUMERIC_NAME.fullmatch(label.strip()):
        issues['numeric_entity_name'] = (
            'Numeric-only referent: confirm whether this is a title/identifier or an attribute value'
        )
    if normalised in GENERIC_NAMES | {'team', 'project', 'work', 'outcome', 'event', 'activity'}:
        issues['generic_entity_name'] = 'Name lacks a distinguishing subject or scope'
    if CONTEXT_NAME.search(label.strip()):
        issues['context_dependent_entity_name'] = (
            'Claim-like or deictic phrase: identify its subject, activity or reported outcome'
        )
    words = normalised.split()
    if len(words) >= 20 or (
        len(words) >= 10
        and (
            label.rstrip().endswith(('.', '!', '?'))
            or re.search(r'\b(is|are|was|were|has|have|will|should|can|could)\b', normalised)
        )
    ):
        issues['sentence_like_entity'] = (
            'Sentence-like name: consider a note/assertion or a concise referent name'
        )
    if len(re.split(r'\s*[;|]\s*|\s+/\s+', label)) >= 3:
        issues['compound_entity_candidate'] = (
            'Several listed subjects may be independent referents; inspect granularity without splitting automatically'
        )
    return issues


def name_warnings(label):
    """Shared editorial prompts; a name cannot establish a referent's identity."""
    return [
        {'code': code, 'detail': detail, 'label': label}
        for code, detail in _name_issues(label).items()
    ]


@dataclass(frozen=True)
class _GraphAudit:
    store: Store
    evidence_claims: dict
    revision_claims: dict
    labels: dict
    types: dict
    endpoints: set[str]
    active_triples: list
    active_assertions: set[str]
    endpoint_labels: list
    literal_counts: Counter
    assertion_endpoints: dict


@dataclass(frozen=True)
class _NoteAudit:
    revisions: dict
    bodies: dict


@dataclass(frozen=True)
class _NameAudit:
    bindings: dict
    labels: dict
    types: dict
    current: dict


def _audit_graph(root, counts, report):
    store = Store()
    for path in sorted(managed_path(root, 'graph').glob('*.trig')):
        try:
            store.load(path=managed_path(root, path.relative_to(root)), format=RdfFormat.TRIG)
        except READ_ERRORS as error:
            report('errors', 'invalid_graph', str(path.relative_to(root)), error)
    # Fingerprints describe authoritative RDF. Replay before adding native view metadata.
    events = []
    try:
        apply_reviews(store, root, history=True)
        events = read_events(root)
        counts['review_events'] = len(events)
    except READ_ERRORS as error:
        report('errors', 'invalid_reviews', 'reviews/events', error)

    assertions = sorted(
        q.subject.value
        for q in store.quads_for_pattern(
            None, NamedNode(RDF_TYPE), NamedNode(VOCAB + 'Assertion'), META
        )
    )
    counts['assertions'] = len(assertions)
    evidence_claims, revision_claims = defaultdict(set), defaultdict(set)
    labels, types = defaultdict(set), defaultdict(set)
    for quad in store:
        if quad.predicate.value == LABEL:
            labels[quad.subject.value].add(quad.object.value)
        elif quad.predicate.value == RDF_TYPE:
            types[quad.subject.value].add(quad.object.value)
    endpoints, statuses, active_triples = set(), Counter(), []
    active_assertions = set()
    endpoint_labels = []
    literal_counts = Counter()
    assertion_endpoints = defaultdict(set)
    enums = {
        'reviewStatus': {'Accepted', 'Unreviewed', 'Rejected'},
        'origin': {'Explicit', 'Inferred'},
        'lifecycle': {'Active', 'Superseded'},
    }
    for assertion in assertions:
        triples = list(store.quads_for_pattern(None, None, None, NamedNode(assertion)))
        if len(triples) != 1:
            report(
                'errors', 'invalid_domain_triple', assertion, 'Expected exactly one domain triple'
            )
        for key in ('subjectLabel', 'objectLabel', 'rationale', *enums, ATTRIBUTED):
            try:
                term = one(store, assertion, key if ':' in key else VOCAB + key)
                if key in enums and (
                    not isinstance(term, NamedNode)
                    or term.value not in {VOCAB + v for v in enums[key]}
                ):
                    raise ValueError(f'Unknown {key}: {term.value}')
                if key == 'reviewStatus':
                    statuses[term.value.removeprefix(VOCAB)] += 1
            except READ_ERRORS as error:
                report('errors', 'invalid_assertion_metadata', assertion, error, field=key)
        if not values(store, assertion, VOCAB + 'generatedAt'):
            report(
                'warnings', 'missing_generation_date', assertion, 'Generating time is unspecified'
            )
        active = NamedNode(VOCAB + 'Active') in values(
            store, assertion, VOCAB + 'lifecycle'
        ) and any(
            NamedNode(VOCAB + status) in values(store, assertion, VOCAB + 'reviewStatus')
            for status in ('Accepted', 'Unreviewed')
        )
        if active:
            active_assertions.add(assertion)
        for triple in triples:
            try:
                validate_relationship(triple.subject, triple.predicate, triple.object)
            except ValueError as error:
                report(
                    'errors',
                    'invalid_relationship_structure',
                    assertion,
                    error,
                    predicate=triple.predicate.value,
                )
            if active:
                active_triples.append((assertion, triple))
            for end, node in (('subject', triple.subject), ('object', triple.object)):
                if isinstance(node, NamedNode):
                    endpoints.add(node.value)
                    assertion_endpoints[assertion].add(node.value)
                    labels[node.value].update(
                        v.value for v in values(store, assertion, VOCAB + end + 'Label')
                    )
                    if active:
                        names = sorted(
                            v.value for v in values(store, assertion, VOCAB + end + 'Label')
                        )
                        if names:
                            endpoint_labels.append((node.value, names[0]))
            if isinstance(triple.object, Literal):
                literal_counts['literal_occurrences'] += 1
                numeric = bool(NUMERIC_NAME.fullmatch(triple.object.value.strip()))
                literal_counts['numeric_literal_occurrences'] += numeric
                if active:
                    literal_counts['active_literal_occurrences'] += 1
                    literal_counts['active_numeric_literal_occurrences'] += numeric
        evidence = values(store, assertion, DERIVED)
        if not evidence:
            report('errors', 'missing_evidence', assertion, 'Assertion has no source evidence')
        for item in evidence:
            evidence_claims[item.value].add(assertion)
            for revision in values(store, item.value, VOCAB + 'revision'):
                revision_claims[revision.value].add(assertion)
    counts['statuses'] = dict(sorted(statuses.items()))
    corrections = [event for event in events if event['action'] == 'correct']
    counts['correction_events'] = len(corrections)
    counts['active_correction_replacements'] = sum(
        event.get('replacement_id') in active_assertions for event in corrections
    )
    counts['evidence_resources'] = len(evidence_claims)
    counts['citation_references'] = sum(map(len, evidence_claims.values()))

    for revision, targets in sorted(revision_claims.items()):
        if revision.startswith(REVISION) and any(
            len(values(store, revision, VOCAB + field)) != 1 for field in ('snapshotPath', 'sha256')
        ):
            report(
                'errors',
                'missing_native_registration',
                revision,
                'Cited native revision lacks authoritative snapshot/hash registration',
                assertions=sorted(targets),
            )

    return _GraphAudit(
        store=store,
        evidence_claims=evidence_claims,
        revision_claims=revision_claims,
        labels=labels,
        types=types,
        endpoints=endpoints,
        active_triples=active_triples,
        active_assertions=active_assertions,
        endpoint_labels=endpoint_labels,
        literal_counts=literal_counts,
        assertion_endpoints=assertion_endpoints,
    )


def _audit_notes(root, counts, report):
    revisions, bodies = {}, defaultdict(set)
    valid_derivations, conversational = set(), []
    try:
        registry = _registry(root)
    except READ_ERRORS as error:
        report('errors', 'invalid_note_registry', 'notes/registry.json', error)
        registry = {'notes': {}}
    counts['native_notes'] = len(registry['notes'])
    association_checks = set()
    for note in sorted(registry['notes']):
        try:
            history = _history(root, note, registry)
        except READ_ERRORS as error:
            report('errors', 'invalid_note_history', note, error)
            continue
        for saved in history:
            revision = saved['revision']
            revisions[revision] = saved
            bodies[saved['body_sha256']].add(revision)
            entities = tuple(saved['entities'])
            if entities not in association_checks:
                association_checks.add(entities)
                try:
                    _canonical_entities(root, entities)
                except READ_ERRORS as error:
                    report('errors', 'invalid_note_association', revision, error)
            derivation = saved.get('derivation')
            if derivation:
                try:
                    validate_sources(root, derivation['sources'])
                    valid_derivations.add(revision)
                except READ_ERRORS as error:
                    report('errors', 'invalid_derivation', revision, error)
        current = history[-1]
        if CONVERSATIONAL.search(current['body']):
            conversational.append(current)
        if not current.get('derivation') and (current['author'] or '').casefold() in AI_AUTHORS:
            report(
                'warnings',
                'missing_derivation',
                note,
                'AI-authored writing has no machine-readable derivation; inspect prose provenance',
            )
    counts['native_revisions'] = len(revisions)
    covered_captures = set()
    for revision in sorted(set(registry['notes'].values()) & valid_derivations):
        for pin in revisions[revision]['derivation']['sources']:
            source = revisions.get(pin['revision'])
            if source is not None:
                # Equal bytes in another logical note do not curate this source.
                covered_captures.add((source['note'], pin['sha256']))
    current_notes = [revisions[head] for head in registry['notes'].values() if head in revisions]
    source_notes = [saved for saved in current_notes if not saved.get('derivation')]
    curated = [saved for saved in current_notes if saved.get('derivation')]
    counts['current_note_heads_read'] = len(current_notes)
    counts['current_source_notes'] = len(source_notes)
    counts['current_curated_notes'] = len(curated)
    counts['current_valid_curated_notes'] = sum(
        saved['revision'] in valid_derivations for saved in curated
    )
    counts['current_source_notes_with_curation'] = sum(
        (saved['note'], saved['body_sha256']) in covered_captures for saved in source_notes
    )
    uncovered = [
        saved
        for saved in conversational
        if (saved['note'], saved['body_sha256']) not in covered_captures
    ]
    counts['conversational_source_captures'] = len(conversational)
    counts['conversational_captures_with_curation'] = len(conversational) - len(uncovered)
    counts['uncurated_conversational_captures'] = len(uncovered)
    for saved in uncovered:
        report(
            'warnings',
            'conversational_note',
            saved['note'],
            'Possible conversational instruction without a current verified curation of this '
            'source body; preserve the source and consider a curated note',
        )

    return _NoteAudit(revisions, bodies)


def _audit_evidence(root, graph, notes, counts, report):
    store, revisions, bodies = graph.store, notes.revisions, notes.bodies
    evidence_claims, active_assertions = graph.evidence_claims, graph.active_assertions
    # This is an owner-local audit; admitting historical sources here does not widen MCP grants.
    for revision in sorted(revisions):
        try:
            add_note_sources(root, store, store, {}, note_revision=revision)
        except READ_ERRORS as error:
            report('errors', 'invalid_native_source', revision, error)
    try:
        annotated = annotate_accounts(
            root, store, [{'id': assertion} for assertion in sorted(active_assertions)]
        )
        counts['active_evidence_account_members'] = sum(
            bool(record.get('evidence_accounts')) for record in annotated
        )
        counts['active_evidence_account_groups'] = len(
            {group['id'] for record in annotated for group in record.get('evidence_accounts', [])}
        )
    except READ_ERRORS as error:
        report('errors', 'invalid_evidence_accounts', 'curation/evidence-accounts.json', error)
    try:
        reader = _Evidence(root, store, verify_derivation=False)
    except READ_ERRORS as error:
        report('errors', 'invalid_evidence_index', 'migration/conversion.json', error)
        reader = None
    counts['verified_citations'] = 0
    quotes_by_assertion, repeated_spans = defaultdict(set), defaultdict(lambda: defaultdict(set))
    if reader is not None:
        for evidence in sorted(evidence_claims):
            try:
                quote, source = reader.citation(evidence)
                counts['verified_citations'] += 1
                active_targets = evidence_claims[evidence] & active_assertions
                for target in active_targets:
                    quotes_by_assertion[target].add(quote)
                # Short repeated phrases can be incidental; this remains a review
                # prompt even for longer spans, never an automatic account merge.
                if len(quote) >= 100 and active_targets:
                    repeated_spans[quote][source['revision']].update(active_targets)
            except READ_ERRORS as error:
                report('errors', 'invalid_citation', evidence, error)
        for quad in store.quads_for_pattern(None, NamedNode(VOCAB + 'snapshotPath'), None, META):
            revision = quad.subject.value
            try:
                sha = one(store, revision, VOCAB + 'sha256').value
                reader.read(quad.object.value, sha)
                bodies[sha].add(revision)
            except READ_ERRORS as error:
                report('errors', 'invalid_source_snapshot', revision, error, path=quad.object.value)
    repeated = {quote: spans for quote, spans in repeated_spans.items() if len(spans) > 1}
    counts['repeated_source_span_groups'] = len(repeated)
    for quote, spans in sorted(repeated.items()):
        report(
            'warnings',
            'repeated_source_span',
            digest(quote.encode()),
            'Identical quotations across revisions do not establish independent corroboration '
            'or prove the same account; inspect source dependence in context',
            revisions=sorted(spans),
            assertions=sorted(set().union(*spans.values())),
        )
    for sha, accounts in sorted(bodies.items()):
        if len(accounts) > 1:
            report(
                'warnings',
                'shared_source_bytes',
                sha,
                'Shared bytes or metadata revisions do not establish independent corroboration',
                revisions=sorted(accounts),
            )

    return quotes_by_assertion


def _audit_semantics(root, graph, quotes_by_assertion, counts, report):
    store, labels, types = graph.store, graph.labels, graph.types
    active_triples, endpoint_labels = graph.active_triples, graph.endpoint_labels
    bindings = {}
    try:
        bindings = {a.value: b.value for a, b in identity_bindings(store).items()}
    except READ_ERRORS as error:
        report('errors', 'invalid_identity_bindings', 'identity', error)
    accepted = defaultdict(list)
    for quad in store.quads_for_pattern(None, NamedNode(VOCAB + 'sourceEntity'), None, META):
        if NamedNode(VOCAB + 'Accepted') in values(
            store, quad.subject.value, VOCAB + 'reviewStatus'
        ):
            accepted[quad.object.value].append(quad.subject.value)
    for source, records in sorted(accepted.items()):
        if len(records) > 1:
            report(
                'warnings',
                'duplicate_identity_bindings',
                source,
                'Multiple accepted identity records target this source; inspect without merging',
                bindings=sorted(records),
            )
    canonical_labels, canonical_types = defaultdict(set), defaultdict(set)
    for entity, names in labels.items():
        canonical_labels[bindings.get(entity, entity)].update(names)
    for entity, kinds in types.items():
        canonical_types[bindings.get(entity, entity)].update(kinds)
    semantic_counts = Counter()
    semantic_metrics = {
        'decision_subject_needs_review': 'active_nonactor_claims',
        'actor_subject_needs_review': 'active_nonactor_claims',
        'decision_about_subject_needs_review': 'active_decision_about_type_warnings',
        'self_relationship_needs_review': 'active_projected_self_links',
        'claim_qualification_needs_review': 'active_qualification_warnings',
        'relationship_object_type_needs_review': 'active_relationship_object_type_warnings',
        'literal_entity_relation': 'active_literal_relation_warnings',
    }
    for assertion, triple in active_triples:
        subject = bindings.get(triple.subject.value, triple.subject.value)
        obj = (
            bindings.get(triple.object.value, triple.object.value)
            if isinstance(triple.object, NamedNode)
            else None
        )
        object_labels = [v.value for v in values(store, assertion, VOCAB + 'objectLabel')]
        for warning in relationship_warnings(
            triple.predicate.value,
            canonical_types[subject],
            object_types=canonical_types[obj] if obj else (),
            quotes=quotes_by_assertion[assertion],
            object_label=' '.join(object_labels),
            subject=subject,
            object=triple.object if isinstance(triple.object, Literal) else obj,
        ):
            code = warning.pop('code')
            detail = warning.pop('detail')
            if code == 'self_relationship_needs_review':
                warning['entity'] = subject
            if code == 'decision_about_subject_needs_review':
                warning.pop('predicate', None)  # Preserve finding identity in older audit reports.
            semantic_counts[semantic_metrics[code]] += 1
            report('warnings', code, assertion, detail, **warning)
    for key in sorted(set(semantic_metrics.values())):
        counts[key] = semantic_counts[key]
    profile_path = managed_path(root, 'curation/entity-labels.json')
    current_labels = {
        entity: sorted(names)[0] for entity, names in canonical_labels.items() if names
    }
    # The first current assertion label is the default display; an accepted identity
    # projection and verified preferred name take precedence over historical aliases.
    for entity, label in reversed(endpoint_labels):
        current_labels[bindings.get(entity, entity)] = label
    display_records = [
        {'subject': {'id': entity, 'label': label}, 'object': {'id': entity, 'label': label}}
        for entity, label in sorted(current_labels.items())
    ]
    try:
        display_records, canonical_labels = apply_entity_labels(
            root, store, display_records, canonical_labels
        )
        current_labels = {r['subject']['id']: r['subject']['label'] for r in display_records}
        if profile_path.exists():
            for profile in json.loads(profile_path.read_text())['profiles']:
                if bindings.get(profile['entity'], profile['entity']) not in canonical_labels:
                    report(
                        'warnings',
                        'unknown_label_profile_entity',
                        profile['entity'],
                        'Display profile has no visible existing entity; it cannot create an identity',
                    )
    except READ_ERRORS as error:
        report('errors', 'invalid_entity_labels', 'curation/entity-labels.json', error)
    return _NameAudit(bindings, canonical_labels, canonical_types, current_labels)


def _audit_associations(graph, notes, names, report):
    store, revisions = graph.store, notes.revisions
    revision_claims, assertion_endpoints = graph.revision_claims, graph.assertion_endpoints
    bindings, canonical_labels = names.bindings, names.labels
    source_entities = defaultdict(set)
    for revision, targets in revision_claims.items():
        for target in targets:
            if NamedNode(VOCAB + 'Rejected') not in values(
                store, target, VOCAB + 'reviewStatus'
            ) and NamedNode(VOCAB + 'Active') in values(store, target, VOCAB + 'lifecycle'):
                source_entities[revision].update(
                    bindings.get(entity, entity) for entity in assertion_endpoints[target]
                )
    for revision, saved in sorted(revisions.items()):
        derivation = saved.get('derivation')
        if not derivation:
            continue
        pins = derivation['sources']
        supported = set()
        for pin in pins:
            source = pin['revision']
            supported.update(source_entities[source])
            supported.update(
                bindings.get(entity, entity)
                for entity in revisions.get(source, {}).get('entities', [])
            )
        for declared in saved['entities']:
            entity = bindings.get(declared, declared)
            # A mention is only a navigation trace for the already-declared IRI.
            # It neither resolves another identity nor validates a substantive claim.
            mentioned = any(
                label.strip()
                and re.search(r'(?<!\w)' + re.escape(label) + r'(?!\w)', pin['quote'], re.I)
                for label in canonical_labels.get(entity, ())
                for pin in pins
            )
            if entity not in supported and not mentioned:
                report(
                    'warnings',
                    'unsupported_curated_association',
                    revision,
                    'No navigation trace in pinned source associations, assertion endpoints or '
                    'exact quotations; review this association',
                    entity=entity,
                    source_revisions=sorted({pin['revision'] for pin in pins}),
                )


def _audit_names(graph, names, counts, report):
    bindings, canonical_labels = names.bindings, names.labels
    canonical_types, current_labels = names.types, names.current
    endpoints, literal_counts = graph.endpoints, graph.literal_counts
    collisions = defaultdict(set)
    for entity, names in sorted(canonical_labels.items()):
        for label in sorted(names):
            normalised = _normalise(label)
            if not normalised or normalised in GENERIC_NAMES or label.startswith('urn:'):
                report(
                    'warnings',
                    'low_quality_entity_name',
                    entity,
                    label or 'Empty entity name',
                    label=label or 'Empty entity name',
                )
            if normalised:
                collisions[normalised].add(entity)
    for name, entities in sorted(collisions.items()):
        if len(entities) > 1:
            report(
                'warnings',
                'label_collision',
                name,
                'Shared current or historical names are search collisions, not identity equivalence',
                entities=sorted(entities),
            )
    entity_types = {VOCAB + kind for kind in TYPES - {'Entity'}} | {
        VOCAB + 'Competency',
        VOCAB + 'MasteryCriterion',
        VOCAB + 'Note',
    }
    canonical_endpoints = {bindings.get(e, e) for e in endpoints}
    # Source documents and independent notes need not become named knowledge entities.
    entity_referents = canonical_endpoints | {
        entity
        for entity, kinds in canonical_types.items()
        if kinds & ((entity_types - {VOCAB + 'Document', VOCAB + 'Note'}) | {VOCAB + 'Entity'})
    }
    current_collisions, name_issues = defaultdict(set), defaultdict(set)
    for entity in sorted(entity_referents):
        if not canonical_labels.get(entity):
            report('warnings', 'missing_entity_name', entity, 'No human-readable label found')
        if entity in canonical_endpoints and not canonical_types[entity] & entity_types:
            report('warnings', 'untyped_endpoint', entity, 'No specific entity type found')
        label = current_labels.get(entity)
        if label is None:
            continue
        normalised = _normalise(label)
        if normalised:
            current_collisions[normalised].add(entity)
        for code, detail in _name_issues(label).items():
            name_issues[code].add(entity)
            report('warnings', code, entity, detail, label=label)
    duplicate_groups = [ids for ids in current_collisions.values() if len(ids) > 1]
    for name, entities in sorted(current_collisions.items()):
        if len(entities) > 1:
            report(
                'warnings',
                'current_name_collision',
                name,
                'Distinct canonical identities share a current display name; confirm scope before any merge',
                entities=sorted(entities),
            )
    # Node counts use one current preferred name per canonical referent. Literal
    # counts are assertion occurrences (including history), not distinct values/entities.
    counts['current_name_nodes_audited'] = len(entity_referents & current_labels.keys())
    for key, code in (
        ('current_numeric_name_nodes', 'numeric_entity_name'),
        ('current_generic_name_nodes', 'generic_entity_name'),
        ('current_context_dependent_name_nodes', 'context_dependent_entity_name'),
    ):
        counts[key] = len(name_issues[code])
    counts['current_granularity_candidate_nodes'] = len(
        name_issues['sentence_like_entity'] | name_issues['compound_entity_candidate']
    )
    counts['current_name_duplicate_groups'] = len(duplicate_groups)
    counts['current_name_duplicate_nodes'] = sum(map(len, duplicate_groups))
    for key in (
        'literal_occurrences',
        'numeric_literal_occurrences',
        'active_literal_occurrences',
        'active_numeric_literal_occurrences',
    ):
        counts[key] = literal_counts[key]
    # Labels include documents, frameworks and other RDF resources; these are not
    # equivalent to an inventory of personal entities or substantive graph endpoints.
    counts['labelled_resources'] = len(canonical_labels)
    counts['domain_endpoints'] = len(canonical_endpoints)
    counts['labelled_or_typed_resources'] = len(set(canonical_labels) | entity_referents)


def audit(root):
    """Run ordered audit passes without writing data or accepting claims."""
    root = Path(root).resolve()
    result = {'counts': {}, 'errors': [], 'warnings': []}
    counts = result['counts']

    def report(severity, code, record, detail, **extra):
        result[severity].append({'code': code, 'record': record, 'detail': str(detail), **extra})

    # Evidence populates the verification view before identity and semantic checks.
    graph = _audit_graph(root, counts, report)
    notes = _audit_notes(root, counts, report)
    quotes = _audit_evidence(root, graph, notes, counts, report)
    names = _audit_semantics(root, graph, quotes, counts, report)
    _audit_associations(graph, notes, names, report)
    _audit_names(graph, names, counts, report)
    counts['errors'] = len(result['errors'])
    counts['warnings'] = len(result['warnings'])
    counts['warning_codes'] = dict(sorted(Counter(w['code'] for w in result['warnings']).items()))
    return _diagnostics(result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-root', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument(
        '--baseline', type=Path, help='Compare with a previous read-only quality report'
    )
    args = parser.parse_args()
    args.data_root = cli_data_root(parser, args.data_root)
    if args.output and args.output.resolve().is_relative_to(args.data_root.resolve()):
        parser.error(
            'Quality output must be outside the data root; the audit cannot overwrite data'
        )
    if args.output and args.baseline and args.output.resolve() == args.baseline.resolve():
        parser.error('Quality output must not overwrite its baseline')
    baseline = None
    if args.baseline:
        try:
            baseline = json.loads(args.baseline.read_text(encoding='utf-8'))
            compare_reports({'errors': [], 'warnings': []}, baseline)
        except (ValueError, OSError, TypeError) as error:
            parser.error(str(error))
    result = audit(args.data_root)
    if baseline is not None:
        result['comparison'] = compare_reports(result, baseline)
    text = json.dumps(result, indent=2, ensure_ascii=False) + '\n'
    if args.output:
        args.output.write_text(text, encoding='utf-8')
    else:
        print(text, end='')
    return int(bool(result['errors']))


if __name__ == '__main__':
    raise SystemExit(main())
