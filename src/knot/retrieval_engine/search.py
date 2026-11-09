"""Question-aware selection of existing graph paths and verified source sections."""

import copy
import heapq
import re
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path

from pyoxigraph import NamedNode

from knot.graph.rdf import DERIVED, META, RDF_TYPE, VOCAB, values
from knot.retrieval_engine.context import _prepare
from knot.retrieval_engine.evidence import _Evidence
from knot.retrieval_engine.graph import _include_assertion, _iri
from knot.retrieval_engine.policy import FRAMEWORK, GENERIC
from knot.retrieval_engine.ranking import CONCEPTS as CONCEPTS
from knot.retrieval_engine.ranking import INTENTS as INTENTS
from knot.retrieval_engine.ranking import NORMAL as NORMAL
from knot.retrieval_engine.ranking import STOP as STOP
from knot.retrieval_engine.ranking import _Question as _Question
from knot.retrieval_engine.ranking import tokens as tokens
from knot.retrieval_engine.response import _envelope, _measure
from knot.retrieval_engine.selection import QUALIFICATION, _select
from knot.shared.storage import digest
from knot.shared.text import segment_text
from knot.shared.vocabulary import local_name


@dataclass(frozen=True)
class Limits:
    max_source_revisions: int = 64
    max_source_sections: int = 1024
    max_candidates: int = 128
    max_revision_previews: int = 256
    max_preview_bytes: int = 8192

    def __post_init__(self):
        for key, value in asdict(self).items():
            if type(value) is not int or value < 1:
                raise ValueError(f'{key} must be a positive integer')


def _failure(result, error):
    if str(error) == 'SourceRevisionBudget':
        _omit(result, 'source_revisions')
        return
    category = str(error) if re.fullmatch('[A-Za-z]+', str(error)) else 'InvalidMetadata'
    omissions = result['omissions']
    omissions['invalid_citations'] += 1
    omissions['citation_errors'][category] = omissions['citation_errors'].get(category, 0) + 1
    omissions['further_unknown'] = True


def _omit(result, name, count=1):
    limits = result['omissions']['limits']
    limits[name] = limits.get(name, 0) + count
    result['omissions']['further_unknown'] = True


def _candidate_order(candidate):
    path = candidate.get('path', [])
    return (-candidate['ranking']['score'], len(path), str(path) if path else candidate['id'])


def _keep(candidates, candidate, cap, result):
    candidates.append(candidate)
    candidates.sort(key=_candidate_order)
    if len(candidates) > cap:
        candidates.pop()
        _omit(result, 'candidates')


def _graph_candidates(seed, adjacency, scores, types, evidence, store, policy, cap, result):
    def hub(entity):
        return bool(types[entity] & GENERIC)

    # Bounded dynamic lookahead over the already eligible index. Generic nodes
    # never propagate routing scores; actual expansion still verifies every hop.
    lookahead = [{entity: 0 for entity in adjacency}]
    for _ in range(min(policy.max_depth, policy.max_expanded)):
        previous = lookahead[-1]
        lookahead.append(
            {
                entity: max(
                    (
                        previous.get(edge[3]['id'], 0)
                        if edge[1]['predicate'] == VOCAB + 'relatedTo'
                        else scores[edge[0]]['score']
                        for edge in edges
                    ),
                    default=0,
                )
                for entity, edges in adjacency.items()
                if not hub(entity)
            }
        )

    def priority(edge, remaining):
        aid, record, direction, endpoint = edge
        ahead = lookahead[min(remaining, len(lookahead) - 1)].get(endpoint['id'], 0)
        score = ahead if record['predicate'] == VOCAB + 'relatedTo' else scores[aid]['score']
        return (-score, -scores[aid]['score'], aid, direction)

    queue, scheduled, candidates = [(0, 0, seed, [])], {seed}, []
    while queue:
        if result['usage']['expanded'] >= policy.max_expanded:
            _omit(result, 'expanded', len(queue))
            break
        depth, _, entity, path = heapq.heappop(queue)
        if hub(entity) and entity != seed:
            result['omissions']['hubs'] += 1
            result['omissions']['further_unknown'] = True
            continue
        result['usage']['expanded'] += 1
        used = {s['assertion'] for s in path}
        remaining = max(0, policy.max_depth - depth - 1)
        edges = sorted(
            (e for e in adjacency[entity] if e[0] not in used),
            key=lambda edge: priority(edge, remaining),
        )
        if len(edges) > policy.hub_degree and not hub(entity):
            relevant = [edge for edge in edges if priority(edge, remaining)[0] < 0]
            if len(relevant) < len(edges):
                _omit(result, 'unranked_hub_edges', len(edges) - len(relevant))
            edges = relevant
        degree = (
            min(policy.max_degree, policy.seed_hub_degree) if hub(entity) else policy.max_degree
        )
        if len(edges) > degree:
            _omit(result, 'degree', len(edges) - degree)
        for edge in edges[:degree]:
            aid, record, direction, endpoint = edge
            try:
                eids = values(store, aid, DERIVED)
                if not eids:
                    raise ValueError('MissingEvidence')
                for eid in sorted(eids, key=lambda value: value.value):
                    evidence.citation(eid.value)
            except (ValueError, UnicodeError) as error:
                _failure(result, error)
                continue
            new_path = path + [{'assertion': aid, 'direction': direction}]
            if scores[aid]['score'] > 0 and record['predicate'] != VOCAB + 'relatedTo':
                _keep(
                    candidates,
                    {'channel': 'graph', 'path': new_path, 'ranking': scores[aid]},
                    cap,
                    result,
                )
            if endpoint.get('literal'):
                continue
            further = [e for e in adjacency[endpoint['id']] if e[0] not in used | {aid}]
            if not further:
                continue
            if len(new_path) >= policy.max_depth:
                _omit(result, 'depth')
            elif endpoint['id'] in scheduled:
                result['omissions']['alternate_routes'] += 1
            elif len(queue) >= policy.max_frontier:
                _omit(result, 'frontier')
            else:
                heapq.heappush(
                    queue, (depth + 1, priority(edge, remaining)[0], endpoint['id'], new_path)
                )
                scheduled.add(endpoint['id'])
                result['usage']['frontier_peak'] = max(result['usage']['frontier_peak'], len(queue))
    return candidates


def _sections(text, snapshot):
    format_name = Path(snapshot).suffix.lower().lstrip('.')
    offset, headings = 0, []
    for section in segment_text(text, format_name):
        first = section['text'].splitlines()[0] if section['text'] else ''
        heading = re.match(r'^(\*+|#{1,6})\s+', first)
        if heading:
            level = len(heading[1])
            headings = [(n, title) for n, title in headings if n < level]
            headings.append((level, section['title']))
        # These source notes explicitly separate observations from repeated
        # interview interpretation. Keep the entire observation body, including
        # all its caveats and attribution, rather than clipping at a size limit.
        boundary = re.search(r'^- (?:Why this matters:|Interview lens\b)', section['text'], re.M)
        cuts = [0]
        tail_qualification = boundary and re.search(
            r'\b(?:caveat|correlation|does not prove|not independent|not yet|still outstanding|unverified|not re-verified)\b',
            section['text'][boundary.start() :],
            re.I,
        )
        if (
            boundary
            and not tail_qualification
            and boundary.start() > 0
            and len(section['text']) > 1800
        ):
            cuts.append(boundary.start())
        cuts.append(len(section['text']))
        for index, (start, end) in enumerate(zip(cuts, cuts[1:])):
            yield (
                section['text'][start:end],
                {
                    'characterOffset': str(offset + start),
                    'startLine': str(section['start_line'] + section['text'][:start].count('\n')),
                    'endLine': str(
                        section['start_line']
                        + section['text'][:end].count('\n')
                        - (1 if section['text'][:end].endswith('\n') else 0)
                    ),
                    'heading_path': [title for _, title in headings],
                    'section_complete': len(cuts) == 2,
                    'document_complete': len(cuts) == 2 and len(section['text']) == len(text),
                    'evidence_role': 'interpretation' if index else 'source_record',
                },
            )
        offset += len(section['text'])


def _text_candidates(
    store, records, aliases, scorer, evidence, policy, limits, cap, result, *, seed=None
):
    if policy.accepted_only:
        result['omissions']['source_only_excluded'] = True
        return []
    revisions = {
        q.subject.value
        for q in store.quads_for_pattern(None, NamedNode(VOCAB + 'snapshotPath'), None, META)
    }
    framework, personal = set(), set()
    # Historical native citations can exist in factual RDF. Their provenance
    # remains available to graph paths, but they are not default note text heads.
    revisions = {
        r
        for r in revisions
        if not r.startswith('urn:knot:note-revision:')
        or any(v.value == 'true' for v in values(store, r, VOCAB + 'nativeTextEligible'))
    }
    for quad in store.quads_for_pattern(
        None, NamedNode(VOCAB + 'recordKind'), NamedNode(VOCAB + 'FrameworkDefinition'), META
    ):
        for eid in values(store, quad.subject.value, DERIVED):
            framework.update(r.value for r in values(store, eid.value, VOCAB + 'revision'))
    for record in records:
        target = framework if record['framework'] else personal
        for eid in values(store, record['id'], DERIVED):
            target.update(r.value for r in values(store, eid.value, VOCAB + 'revision'))
    if not policy.include_frameworks:
        revisions -= framework - personal
    revisions = sorted(revisions)
    from knot.retrieval_engine.source_selection import source_unit

    requested_unit = source_unit(seed)
    selected_revision = requested_unit[0] if requested_unit else seed
    direct_source = selected_revision in revisions
    if direct_source:
        revisions = [selected_revision]
    direct_note = seed is not None and any(
        NamedNode(seed) in values(store, revision, VOCAB + 'nativeNote') for revision in revisions
    )
    if direct_note:
        revisions = [
            revision
            for revision in revisions
            if NamedNode(seed) in values(store, revision, VOCAB + 'nativeNote')
        ]
    if len(revisions) > limits.max_source_revisions:
        _omit(result, 'source_revisions', len(revisions) - limits.max_source_revisions)
    from knot.retrieval_engine.source_selection import select_revisions

    revisions = select_revisions(
        revisions, store, records, scorer, evidence, limits, result, aliases
    )
    descriptors = {'account', 'framework', 'project'}
    alias_terms = [
        tokens(alias) - descriptors or tokens(alias) for alias in sorted(aliases) if tokens(alias)
    ]
    seed_evidence = [
        eid.value
        for record in records
        if not record['framework'] and seed in (record['subject']['id'], record['object']['id'])
        for eid in values(store, record['id'], DERIVED)
    ]
    verified, matched_documents = [], set()
    for revision in revisions[: limits.max_source_revisions]:
        result['usage']['source_revisions'] += 1
        try:
            text, citation = evidence.revision(revision)
        except (ValueError, UnicodeError) as error:
            _failure(result, error)
            continue
        document_terms = tokens(text)
        matched = (
            'LabelTermsInRevision'
            if any(terms <= document_terms for terms in alias_terms)
            else None
        )
        native = citation.get('native_note')
        if native:
            if seed == native['id']:
                matched = 'DirectNote'
            elif seed in native['navigation_entities']:
                matched = 'NoteEntityAssociation'
        if seed is None:
            matched = 'QuestionOnly'
        elif direct_source:
            matched = 'SelectedSourceRevision'
        if matched:
            matched_documents.update(citation['documents'])
        verified.append((text, citation, matched))
    verified_ids = {citation['revision'] for _, citation, _ in verified}
    seed_spans = defaultdict(list)
    valid_anchors = set()
    for eid in seed_evidence:
        if not verified_ids.intersection(r.value for r in values(store, eid, VOCAB + 'revision')):
            continue
        try:
            quote, citation = evidence.citation(eid)
        except (ValueError, UnicodeError) as error:
            _failure(result, error)
            continue
        valid_anchors.add(citation['revision'])
        text, _ = evidence.revision(citation['revision'])
        offset = citation['locator'].get('characterOffset')
        if offset is None and text.count(quote) == 1:
            offset = text.index(quote)
        if offset is not None:
            seed_spans[citation['revision']].append((int(offset), int(offset) + len(quote)))
    verified = [
        (
            text,
            citation,
            matched
            or ('EntityAssertionInRevision' if citation['revision'] in valid_anchors else None),
        )
        for text, citation, matched in verified
    ]
    matched_documents.update(
        document
        for _, citation, matched in verified
        if matched
        for document in citation['documents']
    )
    sections = []
    section_limit = False
    for text, citation, matched in verified:
        if not matched and not matched_documents.intersection(citation['documents']):
            continue
        native = citation.get('native_note')
        snapshot = (
            ('note.md' if native['format'] == 'markdown' else 'note.org')
            if native
            else citation['snapshot']
        )
        units = _sections(text, snapshot)
        if not scorer.terms and matched in ('DirectNote', 'NoteEntityAssociation'):
            units = [
                (
                    text,
                    {
                        'characterOffset': '0',
                        'startLine': '1',
                        'endLine': str(len(text.splitlines())),
                        'heading_path': [],
                        'section_complete': True,
                        'document_complete': True,
                        'evidence_role': 'source_record',
                    },
                )
            ]
        for quote, locator in units:
            if (
                requested_unit
                and (int(locator['characterOffset']), len(quote), digest(quote.encode()))
                != requested_unit[1:]
            ):
                continue
            if result['usage']['source_sections'] >= limits.max_source_sections:
                _omit(result, 'source_sections')
                section_limit = True
                break
            result['usage']['source_sections'] += 1
            sections.append((quote, locator, citation, matched))
        if section_limit:
            break
    scorer.fit(quote for quote, _, _, _ in sections)
    if requested_unit and verified and not sections:
        raise ValueError('UnknownSourceUnit')
    candidates = []
    for quote, locator, citation, matched in sections:
        body = re.sub(r'^\s*(?:[#:*]|:PROPERTIES:|:END:).*$', '', quote, flags=re.M).strip()
        if not body:
            continue
        heading_labels = ' '.join(locator['heading_path'])
        if getattr(scorer, 'include_source_titles', False):
            heading_labels += ' ' + (citation.get('native_note', {}).get('title') or '')
        ranking = scorer.score(quote, labels=heading_labels)
        if requested_unit or (
            not scorer.terms and matched in ('DirectNote', 'NoteEntityAssociation')
        ):
            # An exact discovery selection requests this complete verified unit,
            # even if its wording differs from the follow-up question.
            ranking['score'] = max(1, ranking['score'])
        start = int(locator['characterOffset'])
        local = (
            any(
                terms
                <= tokens(
                    ' '.join(locator['heading_path']) if 'measurement' in scorer.intents else quote
                )
                for terms in alias_terms
            )
            or any(
                a < start + len(quote) and start < b for a, b in seed_spans[citation['revision']]
            )
            or citation['verification'] == 'StoredTranscription'
            or matched
            in ('DirectNote', 'NoteEntityAssociation', 'QuestionOnly', 'SelectedSourceRevision')
        )
        ranking['seed_locality'] = 'Section' if local else 'Document'
        if not local:
            ranking['score'] = round(ranking['score'] * 0.65, 6)
        if locator['evidence_role'] == 'interpretation':
            ranking['score'] = round(ranking['score'] * 0.5, 6)
        if re.search(
            r'evidence scores|self.assess|\*\*Claimed:|Target:.*Score:', quote, re.I
        ) and not (scorer.terms & {'score', 'scores', 'assessment', 'self'}):
            ranking['score'] = round(ranking['score'] * 0.5, 6)
            ranking['self_assessment_penalty'] = True
        if ranking['score'] <= 0:
            continue
        eid = 'urn:knot:source-context:' + digest(
            (citation['revision'] + '\0' + locator['characterOffset'] + '\0' + quote).encode()
        )
        locator['locatorKind'] = {
            'SourceText': 'source_line',
            'ExtractedText': 'extracted_line',
            'StoredTranscription': 'transcription_line',
            'NativeNote': 'source_line',
        }[citation['verification']]
        _keep(
            candidates,
            {
                'channel': 'text',
                'id': eid,
                'quote': quote,
                'citation': {**citation, 'locator': locator},
                'seed_context': matched or 'LabelTermsInSameDocument',
                'ranking': ranking,
            },
            cap,
            result,
        )
    return candidates


def retrieve_ranked(
    root,
    seed,
    question,
    policy,
    *,
    mode='graph',
    limits=None,
    scope=None,
    note_revision=None,
    definition_order=False,
):
    if (
        not isinstance(question, str)
        or not question.strip()
        or mode not in ('graph', 'text', 'hybrid')
    ):
        raise ValueError('Supply a nonempty question and graph, text or hybrid mode')
    limits = limits or Limits()
    prepared = _prepare(root, scope=scope, note_revision=note_revision)
    if seed is None and note_revision is not None:
        from knot.graph.rdf import one

        seed = one(prepared[0], note_revision, VOCAB + 'nativeNote').value
    if (
        mode == 'graph'
        and seed is not None
        and any(
            q.object.value == seed
            for q in prepared[0].quads_for_pattern(
                None, NamedNode(VOCAB + 'nativeNote'), None, META
            )
        )
    ):
        mode = 'text'
    return _retrieve_ranked(
        root, seed, question, policy, mode, limits, prepared, definition_order=definition_order
    )


def _fuse(graph, text, store, evidence, scorer):
    """Fuse ranks using existing relevance and exact same-revision support."""
    supports = []
    for candidate in graph:
        aid = candidate['path'][-1]['assertion']
        supports.append([evidence.citation(e.value) for e in values(store, aid, DERIVED)])

    def contains(candidate, support):
        quote, source = support
        citation = candidate['citation']
        if citation['revision'] != source['revision']:
            return False
        offset = source['locator'].get('characterOffset')
        if offset is None:
            full_text, _ = evidence.revision(source['revision'])
            if full_text.count(quote) != 1:
                return False
            offset = full_text.index(quote)
        start = int(citation['locator']['characterOffset'])
        return start <= int(offset) and int(offset) + len(quote) <= start + len(candidate['quote'])

    def relevance(candidate):
        ranking = candidate['ranking']
        # General replacement regressed small-budget reading/engineering cases.
        # Keep the established fusion outside the new, explicit question intent.
        if 'measurement' in scorer.intents:
            return ranking['score']
        return sum(scorer.weights.get(term, 1) for term in ranking['matched']) + 0.25 * len(
            ranking.get('concepts', [])
        )

    graph_relevance = [relevance(c) for c in graph]
    text_relevance = [relevance(c) for c in text]
    overlaps = []
    for g, support in enumerate(supports):
        for t, candidate in enumerate(text):
            if any(contains(candidate, source) for source in support):
                overlaps.append((g, t))
                # The package builder requires this qualifying unit with the
                # claim. Score that complete account, not just its short quote.
                if 'measurement' in scorer.intents and QUALIFICATION.search(candidate['quote']):
                    graph_relevance[g] = max(graph_relevance[g], text_relevance[t])
    strongest = max(graph_relevance + text_relevance, default=1) or 1
    graph_scores = [value / strongest / (60 + i) for i, value in enumerate(graph_relevance, 1)]
    text_scores = [value / strongest / (60 + i) for i, value in enumerate(text_relevance, 1)]
    graph_bonus, text_bonus = [0.0] * len(graph), [0.0] * len(text)
    for g, t in overlaps:
        graph_bonus[g] = max(graph_bonus[g], text_scores[t])
        text_bonus[t] = max(text_bonus[t], graph_scores[g])
    candidates = [
        {**candidate, 'fusion_score': round(score + bonus, 9)}
        for channel, scores, bonuses in (
            (graph, graph_scores, graph_bonus),
            (text, text_scores, text_bonus),
        )
        for candidate, score, bonus in zip(channel, scores, bonuses)
    ]
    # On equal supporting ranks, prefer the complete source context over the
    # isolated assertion quote. It may contain qualifications absent from RDF.
    return sorted(
        candidates, key=lambda c: (-c['fusion_score'], c['channel'] == 'graph', _candidate_order(c))
    )


def _packages(base, candidates, records, store, original, labels, types, evidence):
    """Prepare each complete path once; selection never re-reads graph evidence."""
    by_id = {record['id']: record for record in records}
    account_spans = defaultdict(dict)
    for record in records:
        for span in record.get('_evidence_account_spans', []):
            source = tuple(span[key] for key in ('revision', 'sha256', 'text_sha256'))
            account_spans[source][(span['start'], span['end'], span['context']['id'])] = span
    envelopes = []
    for candidate in candidates:
        trial = copy.deepcopy(base)
        if candidate['channel'] == 'graph':
            try:
                for step in candidate['path']:
                    _include_assertion(
                        trial, by_id[step['assertion']], store, original, labels, types, evidence
                    )
            except (ValueError, UnicodeError) as error:
                _failure(base, error)
                envelopes.append(None)
                continue
            trial['paths'].append(candidate['path'])
            trial['matches'].append(
                {'channel': 'graph', 'path': 0, 'ranking': candidate['ranking']}
            )
        else:
            eid = candidate['id']
            trial['passages']['p1'] = candidate['quote']
            trial['sources'][eid] = {**candidate['citation'], 'passage': 'p1'}
            trial['source_context'][eid] = {
                'claim_review': None,
                'entity_link': 'AuthorDeclaredNavigation'
                if candidate['seed_context'] == 'NoteEntityAssociation'
                else 'LexicalOnly',
                'seed_context': candidate['seed_context'],
            }
            citation = candidate['citation']
            source = tuple(citation[key] for key in ('revision', 'sha256', 'text_sha256'))
            start = int(citation['locator']['characterOffset'])
            end = start + len(candidate['quote'])
            accounts = {
                span['context']['id']: span['context']
                for span in account_spans[source].values()
                if (start <= span['start'] and span['end'] <= end)
                or (span['start'] <= start and end <= span['end'])
            }
            if accounts:
                trial['source_context'][eid]['evidence_accounts'] = copy.deepcopy(
                    list(accounts.values())
                )
            trial['matches'].append(
                {'channel': 'text', 'source': eid, 'ranking': candidate['ranking']}
            )
        if 'fusion_score' in candidate:
            trial['matches'][0]['fusion_score'] = candidate['fusion_score']
        # Older assertions sometimes lack numeric locators. Only a unique verified
        # occurrence may supply one for storage sharing; ambiguity remains intact.
        for source in trial['sources'].values():
            if 'characterOffset' not in source['locator']:
                quote = trial['passages'][source['passage']]
                text, _ = evidence.revision(source['revision'])
                if text.count(quote) == 1:
                    source['locator'] = {
                        **source['locator'],
                        'characterOffset': str(text.index(quote)),
                    }
        envelopes.append(trial)
    maximum = (
        max((c.get('fusion_score', c['ranking']['score']) for c in candidates), default=1) or 1
    )
    packages = []
    for index, (candidate, envelope) in enumerate(zip(candidates, envelopes)):
        if envelope is None:
            continue
        if candidate['channel'] == 'graph':
            terminal = envelope['assertions'][candidate['path'][-1]['assertion']]
            contexts = {}
            for other, context in zip(candidates, envelopes):
                if other['channel'] != 'text' or context is None:
                    continue
                source = other['citation']
                start = int(source['locator']['characterOffset'])
                quote = other['quote']
                supported = [
                    eid
                    for eid in terminal['sources']
                    if (
                        envelope['sources'][eid]['revision'] == source['revision']
                        and envelope['sources'][eid]['locator'].get('characterOffset') is not None
                        and start <= int(envelope['sources'][eid]['locator']['characterOffset'])
                        and int(envelope['sources'][eid]['locator']['characterOffset'])
                        + len(envelope['passages'][envelope['sources'][eid]['passage']])
                        <= start + len(quote)
                    )
                ]
                covered = [
                    (
                        int(s['locator']['characterOffset']),
                        int(s['locator']['characterOffset'])
                        + len(envelope['passages'][s['passage']]),
                    )
                    for s in envelope['sources'].values()
                    if s['revision'] == source['revision']
                    and s['locator'].get('characterOffset') is not None
                ]
                if (
                    supported
                    and QUALIFICATION.search(quote)
                    and not any(a <= start and start + len(quote) <= b for a, b in covered)
                ):
                    for eid in supported:
                        previous = contexts.get(eid)
                        if previous is None or (len(quote), other['id']) < (
                            len(previous[0]['quote']),
                            previous[0]['id'],
                        ):
                            contexts[eid] = (other, context)
            chosen = {other['id']: (other, context) for other, context in contexts.values()}
            for other, context in chosen.values():
                eid = other['id']
                pid = 'p' + str(len(envelope['passages']) + 1)
                envelope['passages'][pid] = other['quote']
                envelope['sources'][eid] = {**context['sources'][eid], 'passage': pid}
                envelope['source_context'].update(context['source_context'])
                envelope['matches'][0].setdefault('context_sources', {}).update(
                    copy.deepcopy(context['source_context'])
                )
                envelope['matches'][0]['context_reason'] = 'SameSourceUnitQualificationCue'
        packages.append(
            {
                'envelope': envelope,
                'relevance': candidate.get('fusion_score', candidate['ranking']['score']) / maximum,
                'terms': candidate['ranking']['matched'],
                'key': str(index),
                'handle': candidate.get('id') or candidate['path'][-1]['assertion'],
            }
        )
    return packages


def _retrieve_ranked(
    root,
    seed,
    question,
    policy,
    mode,
    limits,
    prepared,
    *,
    collect=False,
    reader=None,
    definition_order=False,
):
    if type(definition_order) is not bool or (
        definition_order and (seed is not None or not question or mode == 'graph')
    ):
        raise ValueError('Definition ordering requires question-only text or hybrid retrieval')
    store, original, records, labels = prepared
    from knot.retrieval_engine.source_selection import source_unit

    unit = source_unit(seed)
    source_seed = unit[0] if unit else seed
    if seed is not None and seed not in labels:
        if (
            ':' in seed
            and not seed.startswith('urn:knot:note-revision:')
            and values(store, source_seed, VOCAB + 'snapshotPath')
        ):
            mode = 'text'
        else:
            raise ValueError('Select an active canonical IRI using lookup first')
    scorer = _Question(question, labels.get(seed, []))
    evidence, types, adjacency = (
        reader or _Evidence(root, store, max_revisions=limits.max_source_revisions),
        defaultdict(set),
        defaultdict(list),
    )
    outgoing = list(policy.outgoing) + (list(FRAMEWORK) if policy.include_frameworks else [])
    incoming = list(policy.incoming)
    scores = {}
    eligible = [
        record
        for record in records
        if not (
            (record['framework'] and not policy.include_frameworks)
            or (policy.accepted_only and record['status'] != 'Accepted')
        )
    ]
    scorer.fit(' '.join(e['quote'] for e in record['evidence']) for record in eligible)
    for record in records:
        for end in ('subject', 'object'):
            entity = record[end]
            if not entity.get('literal'):
                types[entity['id']].update(entity['types'])
                types[entity['id']].update(
                    local_name(t.value) for t in values(store, entity['id'], RDF_TYPE)
                )
        if (record['framework'] and not policy.include_frameworks) or (
            policy.accepted_only and record['status'] != 'Accepted'
        ):
            continue
        aid = record['id']
        scores[aid] = scorer.score(
            ' '.join(e['quote'] for e in record['evidence']),
            labels=record['subject']['label'] + ' ' + record['object']['label'],
            predicate=record['predicate'],
        )
        for direction, predicates, start, end in [
            ('outgoing', outgoing, 'subject', 'object'),
            ('incoming', incoming, 'object', 'subject'),
        ]:
            if not record[start].get('literal') and record['predicate'] in map(_iri, predicates):
                adjacency[record[start]['id']].append((aid, record, direction, record[end]))
    result = _envelope(seed, policy, outgoing, incoming)
    result.update(
        {
            'question': question,
            'mode': mode,
            'matches': [],
            'source_context': {},
            'ranking': {
                'method': 'lexical-intent-v2',
                'terms': sorted(scorer.terms),
                'intents': scorer.intents,
                'fusion': 'not applied: single text channel'
                if seed is None
                else 'reciprocal-rank with source overlap; text first on ties',
                'source_limits': {
                    k: v
                    for k, v in asdict(limits).items()
                    if k not in ('max_revision_previews', 'max_preview_bytes')
                },
            },
        }
    )
    result['omissions']['source_only_excluded'] = policy.accepted_only and mode != 'graph'
    result['usage'].update({'source_revisions': 0, 'source_sections': 0, 'candidates': 0})
    if mode == 'text' or seed is None:
        result['usage']['frontier_peak'] = 0
    if _measure(result) > policy.max_chars:
        raise ValueError('Budget too small for a valid question response envelope')
    graph_cap = limits.max_candidates if mode == 'graph' else max(1, limits.max_candidates // 2)
    graph = (
        _graph_candidates(
            seed, adjacency, scores, types, evidence, store, policy, graph_cap, result
        )
        if mode != 'text' and seed is not None
        else []
    )
    text = (
        _text_candidates(
            store,
            records,
            labels.get(seed, []),
            scorer,
            evidence,
            policy,
            limits,
            limits.max_candidates - len(graph),
            result,
            seed=seed,
        )
        if mode != 'graph'
        else []
    )
    result['usage']['candidates'] = len(graph) + len(text)
    # Question-only retrieval has no graph channel. Preserve its complete text
    # relevance scores instead of replacing them with cross-channel rank weights.
    candidates = (
        _fuse(graph, text, store, evidence, scorer)
        if mode == 'hybrid' and seed is not None
        else graph + text
    )
    packages = _packages(result, candidates, records, store, original, labels, types, evidence)
    result['usage']['source_revisions'] = len(evidence.attempted)
    for package in packages:
        package['envelope']['usage']['source_revisions'] = len(evidence.attempted)
    if collect:
        return result, packages, scorer.weights
    if definition_order:
        from knot.retrieval_engine.definition_order import reorder

        packages, _ = reorder(packages, question)
    return _select(
        result,
        packages,
        policy,
        scorer.weights,
        strategy='relevance_first' if seed is None else 'density',
    )
