"""Ephemeral subject discovery and bounded collection through the existing retriever."""

import copy
from dataclasses import replace
from pathlib import Path

from knot.graph.query import identity_bindings
from knot.graph.rdf import DERIVED, VOCAB, one, values
from knot.retrieval_engine.context import _prepare
from knot.retrieval_engine.discovery_score import DiscoveryQuestion
from knot.retrieval_engine.evidence import _Evidence
from knot.retrieval_engine.policy import Policy
from knot.retrieval_engine.response import _envelope, _measure
from knot.retrieval_engine.search import Limits, _failure, _omit, _retrieve_ranked, _text_candidates
from knot.retrieval_engine.selection import QUALIFICATION, _select
from knot.shared.storage import digest

OBJECTIVES = {
    'relationships': 'Inspect recorded claims and existing relationships, preserving review states.',
    'context': 'Read original writing, including sources without structured assertions.',
    'qualifications': 'Inspect explicit limitations and changed accounts; do not infer contradictions.',
}


def prune_discovery(result):
    used = {ref for candidate in result['candidates'] for ref in candidate['support']}
    result['sources'] = {ref: source for ref, source in result['sources'].items() if ref in used}


def discover(
    root,
    question,
    *,
    max_chars=4000,
    limit=8,
    limits=None,
    scope=None,
    accepted_only=False,
    include_frameworks=False,
):
    if (
        not isinstance(question, str)
        or not question.strip()
        or type(limit) is not int
        or not 1 <= limit <= 20
        or type(max_chars) is not int
        or max_chars < 1
    ):
        raise ValueError('Supply a question, a positive context budget and 1–20 candidates')
    limits = limits or Limits()
    policy = Policy(
        max_chars=max_chars, accepted_only=accepted_only, include_frameworks=include_frameworks
    )
    store, original, records, labels = _prepare(root, scope=scope)
    canonical_targets = {node.value for node in identity_bindings(store).values()}
    records = [
        r
        for r in records
        if (include_frameworks or not r['framework'])
        and (not accepted_only or r['status'] == 'Accepted')
    ]
    reader, scorer = (
        _Evidence(root, store, max_revisions=limits.max_source_revisions),
        DiscoveryQuestion(question),
    )
    scorer.fit(' '.join(e['quote'] for e in r['evidence']) for r in records)
    stats = _envelope(None, policy, [], [])
    stats['ranking'] = {}
    stats['usage'].update(source_revisions=0, source_sections=0, candidates=0)
    text = _text_candidates(
        store, records, [], scorer, reader, policy, limits, limits.max_candidates, stats
    )
    cards, sources, reference_ids = {}, {}, {}

    def reference(quote, citation):
        full, _ = reader.revision(citation['revision'])
        offset = citation.get('locator', {}).get('characterOffset')
        if offset is None:
            if full.count(quote) != 1:
                raise ValueError('AmbiguousLocator')
            offset = full.index(quote)
        offset = int(offset)
        if full[offset : offset + len(quote)] != quote:
            raise ValueError('ChangedLocator')
        identity = (citation['revision'], offset, digest(quote.encode()))
        key = reference_ids.setdefault(identity, 's' + str(len(reference_ids) + 1))
        sources[key] = {
            k: citation[k] for k in ('revision', 'text_path', 'text_sha256', 'verification')
        }
        sources[key].update(
            locator={
                'character_offset': offset,
                'length': len(quote),
                'start_line': full[:offset].count('\n') + 1,
            },
            quote_sha256=digest(quote.encode()),
            claim_review=None,
        )
        if 'native_note' in citation:
            sources[key].update(
                native_note=citation['native_note']['id'],
                manifest_sha256=citation['manifest_sha256'],
                currentness=citation['native_note']['currentness'],
            )
        return key

    def add(ident, kind, names, score, ref, reason, status=None):
        if score['score'] <= 0:
            return
        if ident not in cards or score['score'] > cards[ident]['relevance']:
            cards[ident] = {
                'id': ident,
                'kind': kind,
                'identity_resolution': 'AcceptedBinding'
                if ident in canonical_targets
                else 'RecordedIRI',
                'labels': sorted(names),
                'support': [ref] if isinstance(ref, str) else list(dict.fromkeys(ref)),
                'review_statuses': sorted(
                    set(status if isinstance(status, list) else [status] if status else [])
                ),
                'claim_review': None,
                'relevance': score['score'],
                'reasons': [reason],
                'matched_terms': score['matched'],
            }

    for candidate in text:
        source, quote = candidate['citation'], candidate['quote']
        ref = reference(quote, source)
        native = source.get('native_note')
        ident = (
            native['id']
            if native
            else (
                source['revision']
                + '#knot-unit='
                + str(source['locator']['characterOffset'])
                + ':'
                + str(len(quote))
                + ':'
                + digest(quote.encode())
            )
        )
        heading = source['locator']['heading_path'][-1:] or [Path(source['snapshot']).name]
        names = [native['title']] if native and native['title'] else heading
        add(
            ident,
            'note' if native else 'source',
            names or [ident],
            candidate['ranking'],
            ref,
            {'method': 'OriginalSource', 'assertion': None, 'origin': None},
        )
        if native:
            for entity in native['navigation_entities']:
                add(
                    entity,
                    'entity',
                    labels.get(entity, [entity]),
                    candidate['ranking'],
                    ref,
                    {'method': 'AuthorDeclaredNavigation', 'note': native['id']},
                )

    # Prefer subjects with useful routing, rather than returning every leaf outcome
    # as an apparent new project. This never creates an edge to an unlinked source.
    routable = {r['subject']['id'] for r in records if not r['subject'].get('literal')}
    routable.update(
        r['object']['id']
        for r in records
        if r['predicate'] == VOCAB + 'relatedTo' and not r['object'].get('literal')
    )
    associations = {}
    for record in records:
        if record['predicate'] != VOCAB + 'relatedTo':
            continue
        for a, b in (('subject', 'object'), ('object', 'subject')):
            if not record[a].get('literal') and not record[b].get('literal'):
                associations.setdefault(record[a]['id'], []).append((record, record[b]))
    ranked = sorted(
        [
            (
                scorer.score(
                    ' '.join(e['quote'] for e in r['evidence']),
                    labels=' '.join(sorted(labels.get(r['subject']['id'], [r['subject']['label']])))
                    + ' '
                    + ' '.join(sorted(labels.get(r['object']['id'], [r['object']['label']]))),
                    predicate=r['predicate'],
                ),
                r,
            )
            for r in records
        ],
        key=lambda item: (-item[0]['score'], item[1]['id']),
    )
    routing_scores = {record['id']: score['score'] for score, record in ranked}
    for score, record in ranked[: limits.max_candidates]:
        if score['score'] <= 0:
            continue
        refs = []
        try:
            for eid in sorted(values(store, record['id'], DERIVED), key=lambda node: node.value):
                revision = one(store, eid.value, VOCAB + 'revision').value
                if (
                    revision not in reader.attempted
                    and len(reader.attempted) >= limits.max_source_revisions
                ):
                    _omit(stats, 'discovery_revisions')
                    break
                quote, citation = reader.citation(eid.value)
                refs.append(reference(quote, citation))
            else:
                for end in ('subject', 'object'):
                    entity = record[end]
                    if (
                        entity.get('literal')
                        or entity['id'] not in routable
                        or set(entity.get('types', [])) & {'Person', 'Theme', 'RoleGrade'}
                    ):
                        continue
                    for ref in refs:
                        add(
                            entity['id'],
                            'entity',
                            labels.get(entity['id'], [entity['label']]),
                            score,
                            ref,
                            {
                                'method': 'RecordedAssertion',
                                'assertion': record['id'],
                                'status': record['status'],
                                'origin': record['origin'],
                            },
                            record['status'],
                        )
                    # One verified association hop can expose a subject whose
                    # name never occurs in the question. Generic author/theme
                    # hubs cannot connect otherwise unrelated experiences.
                    edges = sorted(
                        associations.get(entity['id'], []),
                        key=lambda e: (-routing_scores[e[0]['id']], e[0]['id']),
                    )
                    if len(edges) > policy.max_degree:
                        _omit(stats, 'discovery_degree', len(edges) - policy.max_degree)
                    for link, neighbor in edges[: policy.max_degree]:
                        if set(neighbor.get('types', [])) & {'Person', 'Theme', 'RoleGrade'}:
                            continue
                        linked = []
                        for eid in sorted(
                            values(store, link['id'], DERIVED), key=lambda node: node.value
                        ):
                            revision = one(store, eid.value, VOCAB + 'revision').value
                            if (
                                revision not in reader.attempted
                                and len(reader.attempted) >= limits.max_source_revisions
                            ):
                                _omit(stats, 'discovery_revisions')
                                break
                            quote, citation = reader.citation(eid.value)
                            linked.append(reference(quote, citation))
                        else:
                            add(
                                neighbor['id'],
                                'entity',
                                labels.get(neighbor['id'], [neighbor['label']]),
                                score,
                                refs,
                                {
                                    'method': 'ExistingAssociation',
                                    'via': entity['id'],
                                    'assertions': [record['id'], link['id']],
                                    'origins': [record['origin'], link['origin']],
                                },
                                [record['status'], link['status']],
                            )
        except (ValueError, UnicodeError) as error:
            _failure(stats, error)
    if len(ranked) > limits.max_candidates:
        _omit(stats, 'discovery_assertions', len(ranked) - limits.max_candidates)
    ordered = sorted(
        cards.values(), key=lambda c: (-c['relevance'], c['id'] not in canonical_targets, c['id'])
    )
    # First show distinct source contexts; additional subjects in the same source
    # can follow. Similar labels remain distinct identities.
    first, later, seen = [], [], set()
    for card in ordered:
        card['labels'] = [
            name if len(name) <= 200 else name[:197] + '…' for name in card['labels'][:3]
        ]
        revisions = {sources[ref]['revision'] for ref in card['support']}
        (later if revisions <= seen else first).append(card)
        seen.update(revisions)
    result = {
        'method': 'scoped-subject-discovery-v1',
        'question': question,
        'objectives': [{'id': k, 'purpose': v} for k, v in OBJECTIVES.items()],
        'candidates': [],
        'sources': {},
        'truncated': False,
        'coverage': {
            'verified_revisions': len(reader.cache),
            'text_revision_catalogue': (
                stats['usage']['source_revisions']
                + stats['omissions']['limits'].get('source_revisions', 0)
            ),
            'attempted_revisions': len(reader.attempted),
            'unseen_in_scanned_sources': sorted(scorer.terms - scorer.idf.keys()),
            'eligible_assertions': len(records),
            'scanned_sections': stats['usage']['source_sections'],
            'source_selection': stats['ranking'].get('source_selection'),
        },
        'omissions': stats['omissions'],
        'uncertainty': 'Candidates indicate possible relevance, not truth, identity equivalence or a new relationship. Source context has no claim acceptance; coverage is bounded.',
        'usage': {'characters': 0, 'utf8_bytes': 0},
    }
    if _measure(result) > max_chars:
        raise ValueError('Budget too small for discovery envelope')
    for card in first + later:
        if len(result['candidates']) >= limit:
            _omit(result, 'discovery_candidates')
            result['truncated'] = True
            continue
        trial = copy.deepcopy(result)
        trial['candidates'].append(card)
        trial['sources'].update({ref: sources[ref] for ref in card['support']})
        if _measure(trial) <= max_chars - 64:
            result = trial
        else:
            _omit(result, 'characters')
            result['truncated'] = True
    while _measure(result) > max_chars and result['candidates']:
        result['candidates'].pop()
        result['truncated'] = True
        prune_discovery(result)
    if _measure(result) > max_chars:
        raise ValueError('Budget too small for discovery omissions')
    return result


def gather(
    root, subjects, question, policy=None, *, limits=None, scope=None, objectives=None, exclude=()
):
    if (
        not isinstance(subjects, (list, tuple))
        or len(subjects) > 4
        or any(not isinstance(s, str) or not s for s in subjects)
        or not isinstance(question, str)
        or not question.strip()
        or not isinstance(exclude, (list, tuple))
        or len(exclude) > 128
        or any(not isinstance(e, str) for e in exclude)
    ):
        raise ValueError('Supply a question, up to four subjects and at most 128 exclusion handles')
    objectives = tuple(OBJECTIVES) if objectives is None else tuple(objectives)
    if not objectives or len(objectives) > 3 or set(objectives) - OBJECTIVES.keys():
        raise ValueError('Select relationships, context and/or qualifications')
    policy, limits = policy or Policy(max_chars=12000), limits or Limits()
    subjects = list(dict.fromkeys(subjects))
    prepared = _prepare(root, scope=scope)
    from knot.retrieval_engine.source_selection import source_unit

    for subject in subjects:
        unit = source_unit(subject)
        revision = unit[0] if unit else subject
        if subject not in prepared[3] and (
            ':' not in revision
            or revision.startswith('urn:knot:note-revision:')
            or not values(prepared[0], revision, VOCAB + 'snapshotPath')
        ):
            raise ValueError('Select an active canonical IRI or permitted source unit')
    reader = _Evidence(root, prepared[0], max_revisions=limits.max_source_revisions)
    count = min(
        max(1, len(subjects)),
        policy.max_expanded,
        limits.max_source_revisions,
        limits.max_source_sections,
        limits.max_candidates,
        limits.max_revision_previews,
    )
    selected = subjects[:count]
    per_limits = replace(
        limits,
        **{
            k: max(1, getattr(limits, k) // count)
            for k in (
                'max_source_revisions',
                'max_source_sections',
                'max_candidates',
                'max_revision_previews',
            )
        },
    )
    per_policy = replace(policy, max_expanded=max(1, policy.max_expanded // count))
    result, packages, weights = None, {}, {}
    for subject in selected or [None]:
        base, collected, terms = _retrieve_ranked(
            root,
            subject,
            question,
            per_policy,
            'hybrid',
            per_limits,
            prepared,
            collect=True,
            reader=reader,
        )
        if result is None:
            result = base
        else:
            for key, value in base['usage'].items():
                if key not in ('characters', 'utf8_bytes'):
                    result['usage'][key] += value
            for key, value in base['omissions']['limits'].items():
                _omit(result, key, value)
            for key in ('invalid_citations', 'hubs', 'alternate_routes'):
                result['omissions'][key] += base['omissions'][key]
            result['omissions']['further_unknown'] |= base['omissions']['further_unknown']
            for key, value in base['omissions']['citation_errors'].items():
                errors = result['omissions']['citation_errors']
                errors[key] = errors.get(key, 0) + value
        for term, value in terms.items():
            weights[term] = max(weights.get(term, 0), value)
        for package in collected:
            envelope, handle = package['envelope'], package['handle']
            match = envelope['matches'][0]
            graph = match['channel'] == 'graph'
            eligible = (
                'relationships' in objectives
                if graph
                else 'context' in objectives
                or (
                    'qualifications' in objectives
                    and any(QUALIFICATION.search(p) for p in envelope['passages'].values())
                )
            )
            if not eligible or handle in exclude:
                continue
            match['handle'] = handle
            if handle not in packages or package['relevance'] > packages[handle]['relevance']:
                packages[handle] = package
    result.update(
        seed=None,
        subjects=subjects,
        inspected_subjects=selected,
        mode='hybrid',
        objectives=[{'id': k, 'purpose': OBJECTIVES[k]} for k in objectives],
    )
    result['policy'] = {**result['policy'], 'max_expanded': policy.max_expanded}
    result['ranking']['terms'] = sorted(weights)
    result['usage']['revision_reads'] = len(reader.attempted)
    if len(selected) < len(subjects):
        _omit(result, 'subjects', len(subjects) - len(selected))
    return _select(result, list(packages.values()), policy, weights)
