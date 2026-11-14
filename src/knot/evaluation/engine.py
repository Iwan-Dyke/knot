"""Evaluate direct support mappings without ranked retrieval or generated queries."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pyoxigraph import Literal, NamedNode

from knot.curating.evidence_accounts import annotate_accounts
from knot.evaluation.request import CoverageRequest
from knot.evaluation.snapshot import Evidence, Snapshot, canonical_hash
from knot.graph.query import identity_bindings, load_store
from knot.graph.rdf import ATTRIBUTED, DERIVED, META, RDF_TYPE, VOCAB, one, values
from knot.reviewing.state import fingerprint, read_events
from knot.writing.notes import REVISION
from knot.writing.sources import add_note_sources

DEFINITION = 'http://www.w3.org/2004/02/skos/core#definition'


def _candidate_assertions(store: Any, request: CoverageRequest) -> list[dict[str, Any]]:
    candidates = []
    for registered in store.quads_for_pattern(
        None, NamedNode(RDF_TYPE), NamedNode(VOCAB + 'Assertion'), META
    ):
        aid = registered.subject.value
        status = one(store, aid, VOCAB + 'reviewStatus').value
        lifecycle = one(store, aid, VOCAB + 'lifecycle').value
        if status != VOCAB + 'Accepted' or lifecycle != VOCAB + 'Active':
            continue
        triples = list(store.quads_for_pattern(None, None, None, NamedNode(aid)))
        if len(triples) != 1:
            raise ValueError(f'Invalid accepted assertion: {aid}')
        triple = triples[0]
        definition = (
            triple.predicate.value == DEFINITION
            and triple.subject.value in request.criteria
            and isinstance(triple.object, Literal)
            and NamedNode(VOCAB + 'FrameworkDefinition') in values(store, aid, VOCAB + 'recordKind')
            and values(store, aid, VOCAB + 'framework') == [NamedNode(request.framework)]
        )
        support = (
            triple.subject == NamedNode(request.subject)
            and triple.predicate == NamedNode(VOCAB + 'supports')
            and isinstance(triple.object, NamedNode)
            and triple.object.value in request.criteria
        )
        if definition or support:
            candidates.append({'id': aid, 'triple': triple, 'definition': definition})
    return sorted(candidates, key=lambda item: item['id'])


def _premise(
    store: Any,
    candidate: dict[str, Any],
    reader: Evidence,
    reviews: list[dict[str, Any]],
    meaning: str,
) -> dict[str, Any]:
    aid, triple = candidate['id'], candidate['triple']
    origin = one(store, aid, VOCAB + 'origin').value.removeprefix(VOCAB)
    if origin not in ('Explicit', 'Inferred'):
        raise ValueError('Invalid assertion origin')
    sources = []
    evidence = sorted(v.value for v in values(store, aid, DERIVED))
    if not evidence:
        raise ValueError('MissingEvidence')
    for eid in evidence:
        # The pilot requires exact locators, even for older records whose quotes
        # the exploratory reader can locate by searching the source.
        one(store, eid, VOCAB + 'characterOffset')
        one(store, eid, VOCAB + 'startLine')
        quote, citation = reader.citation(eid)
        sources.append({'id': eid, 'quote': quote, **citation})
    return {
        'subject': triple.subject.value,
        'predicate': triple.predicate.value,
        'object': triple.object.value,
        'object_literal': isinstance(triple.object, Literal),
        'meaning': meaning,
        'origin': origin,
        'status': 'Accepted',
        'lifecycle': 'Active',
        'rationale': one(store, aid, VOCAB + 'rationale').value,
        'attributed_to': sorted(v.value for v in values(store, aid, ATTRIBUTED)),
        'reviews': [
            {key: value for key, value in event.items() if key != 'store'} for event in reviews
        ],
        'sources': sources,
    }


def evaluate(root: Path, request: CoverageRequest, *, scope: Any = None) -> dict[str, Any]:
    """Fresh evaluation within an explicit grant, or owner-local access when omitted."""
    from knot.evaluation.access import ScopedSnapshot, _records_for_evaluation
    from knot.interfaces.access import AccessScope

    if scope is not None and not isinstance(scope, AccessScope):
        raise ValueError('Select an AccessScope or use owner-local evaluation')
    if not isinstance(request, CoverageRequest):
        raise TypeError('Supply a CoverageRequest')
    root = Path(root).resolve()
    snapshot = Snapshot(root) if scope is None else ScopedSnapshot(root, scope)
    scoped = scope is not None
    if scoped:
        store = snapshot.view.store
        scope = snapshot.view.scope
    else:
        store = load_store(root / 'graph', history=True, include_notes=False, allow_empty=True)
    restricted = scoped and not scope.whole_dataset
    reasons = []
    if request.as_of is not None:
        reasons.append('unsupported_temporal_scope')
    relevant = {request.subject, request.framework, *request.criteria}
    if any(
        source.value in relevant or target.value in relevant
        for source, target in identity_bindings(store).items()
    ):
        reasons.append('identity_resolution_not_supported')
    candidates = _candidate_assertions(store, request) if not reasons else []
    if len(candidates) > request.max_assertions:
        reasons.append('assertion_budget')
        candidates = []
    fingerprints = {
        candidate['id']: fingerprint(store, candidate['id']) for candidate in candidates
    }
    events = snapshot.view.events if scoped else read_events(root)
    records = (
        {
            record['id']: record
            for record in (snapshot.view.records if scoped else _records_for_evaluation(store))
        }
        if candidates
        else {}
    )
    reader = Evidence(snapshot, store, request.max_sources)
    assertions, exclusions = {}, {}
    definitions = {criterion: [] for criterion in request.criteria}
    support = {criterion: [] for criterion in request.criteria}
    unknown = {criterion: [] for criterion in request.criteria}
    try:
        for candidate in candidates:
            aid, triple = candidate['id'], candidate['triple']
            criterion = triple.subject.value if candidate['definition'] else triple.object.value
            revisions = {
                one(store, eid.value, VOCAB + 'revision').value
                for eid in values(store, aid, DERIVED)
            }
            if candidate['definition'] and revisions != {request.framework_revision}:
                continue
            reviews = [event for event in events if event['target'] == aid]
            if not reviews or reviews[-1]['action'] != 'accept':
                unknown[criterion].append('missing_acceptance_event')
                continue
            record = records.get(aid)
            if record is None:
                raise ValueError(f'Incomplete accepted assertion metadata: {aid}')
            authored = record.get('author_classification', {})
            kind = authored.get('kind', record['kind'])
            if not candidate['definition'] and kind not in ('Assessment', 'Unspecified'):
                exclusions[aid] = {'reason': 'kind_not_assessment', 'kind': kind}
                continue
            for revision in sorted(revisions):
                if not scoped and revision.startswith(REVISION):
                    add_note_sources(root, store, store, {}, note_revision=revision)
            meaning = 'Definition' if candidate['definition'] else 'Assessment'
            premise = _premise(store, candidate, reader, reviews, meaning)
            premise['classification'] = record['classification']
            premise['author_classification'] = authored
            qualified = annotate_accounts(root, store, [record], scope=scope, reader=reader)[0]
            premise['evidence_accounts'] = qualified.get('evidence_accounts', [])
            premise['evidence_account_sources'] = [
                {
                    **span,
                    'quote': reader.revision(span['revision'])[0][span['start'] : span['end']],
                }
                for span in qualified.get('_evidence_account_spans', [])
            ]
            assertions[aid] = premise
            (definitions if candidate['definition'] else support)[criterion].append(aid)
    except ValueError as error:
        if str(error) != 'SourceRevisionBudget':
            raise
        reasons.append('source_budget')
    rows = []
    for criterion in request.criteria:
        # Skipped or interrupted enumeration cannot establish a missing definition.
        missing = [] if definitions[criterion] or reasons else ['missing_reviewed_definition']
        row_reasons = sorted(set(reasons + unknown[criterion] + missing))
        if restricted and not support[criterion]:
            row_reasons.append('scope_limited')
        outcome = (
            'unknown'
            if row_reasons
            else 'support_found'
            if support[criterion]
            else 'no_qualifying_support'
        )
        rows.append(
            {
                'criterion': criterion,
                'outcome': outcome,
                'reasons': row_reasons,
                'definitions': definitions[criterion],
                'support': support[criterion],
                'steps': [
                    {
                        'check': 'reviewed_definition_at_requested_revision',
                        'assertions': definitions[criterion],
                    },
                    {
                        'check': 'direct_reviewed_supports_assessment',
                        'assertions': support[criterion],
                    },
                ],
            }
        )
    manifest = {
        'implementation': snapshot.implementation,
        **snapshot.manifest(),
        'assertion_fingerprints': fingerprints,
        'request': request.to_dict(),
        'access': 'granted-source-view'
        if restricted
        else 'whole-dataset'
        if scoped
        else 'owner-local-whole-dataset',
    }
    result = {
        'schema_version': 1,
        'request': request.to_dict(),
        'scope': 'Selected criteria only; direct supports assessments; current Active Accepted assertions; no temporal or identity inference.'
        + (
            ' Granted-source view only; missing support is unknown, not global absence.'
            if restricted
            else ''
        ),
        'complete': all(row['outcome'] != 'unknown' for row in rows),
        'enumeration_complete': not reasons,
        'reasons': sorted(set(reasons)),
        'criteria': rows,
        'assertions': assertions,
        'excluded_assertions': exclusions,
        'manifest': manifest,
    }
    snapshot.verify()
    result['receipt_sha256'] = canonical_hash(result)
    return result
