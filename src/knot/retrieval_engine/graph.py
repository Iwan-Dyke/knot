"""Bounded graph traversal and evidence-package assembly."""

import copy
import re
from collections import defaultdict, deque

from pyoxigraph import Literal, NamedNode

from knot.graph.rdf import DERIVED, META, RDF_TYPE, VOCAB, one, values
from knot.retrieval_engine.evidence import _Evidence
from knot.retrieval_engine.policy import FRAMEWORK, GENERIC
from knot.retrieval_engine.response import _envelope, _measure, _prune
from knot.shared.vocabulary import local_name


def _iri(predicate):
    return predicate if ':' in predicate else VOCAB + predicate


def _include_assertion(trial, record, store, original, labels, types, evidence):
    aid = record['id']
    if aid in trial['assertions']:
        return
    triples = list(original.quads_for_pattern(None, None, None, NamedNode(aid)))
    if len(triples) != 1:
        raise ValueError(f'Invalid original assertion: {aid}')
    triple = triples[0]
    item = {
        'subject': record['subject']['id'],
        'predicate': record['predicate'],
        'object': record['object']['id'],
        'object_literal': record['object']['literal'],
        'source_subject': triple.subject.value,
        'source_object': triple.object.value,
        'status': record['status'],
        'origin': record['origin'],
        'lifecycle': 'Active',
        'kind': record['kind'],
        'rationale': record['rationale'],
        'role': 'association'
        if record['predicate'] == VOCAB + 'relatedTo'
        else 'framework'
        if record['framework']
        else 'substantive',
        'classification': record['classification']['status'],
        'sources': [],
        'identities': [],
    }
    if record.get('evidence_accounts'):
        item['evidence_accounts'] = copy.deepcopy(record['evidence_accounts'])
    if isinstance(triple.object, Literal):
        item['object_datatype'] = triple.object.datatype.value
        item['object_language'] = triple.object.language
    for end in ('subject', 'object'):
        entity = record[end]
        if not entity.get('literal'):
            trial['entities'][entity['id']] = {
                'labels': sorted(labels[entity['id']]),
                'types': sorted(types[entity['id']]),
            }
            if 'original_label' in entity:
                trial['entities'][entity['id']]['preferred_label'] = entity['label']
    for source in (triple.subject, triple.object):
        if isinstance(source, Literal):
            continue
        for quad in store.quads_for_pattern(None, NamedNode(VOCAB + 'sourceEntity'), source, META):
            mid = quad.subject.value
            if one(store, mid, VOCAB + 'reviewStatus').value != VOCAB + 'Accepted':
                continue
            receipt = {
                'source': source.value,
                'target': one(store, mid, VOCAB + 'entity').value,
                'status': 'Accepted',
            }
            for key in ('reviewer', 'time', 'rationale'):
                found = values(store, mid, VOCAB + key)
                receipt[key] = found[0].value if found else None
            trial['identities'][mid] = receipt
            item['identities'].append(mid)
    eids = sorted(v.value for v in values(store, aid, DERIVED))
    if not eids:
        raise ValueError('MissingEvidence')
    for eid in eids:
        quote, citation = evidence.citation(eid)
        pid = next((p for p, q in trial['passages'].items() if q == quote), None)
        if pid is None:
            pid = 'p' + str(len(trial['passages']) + 1)
            trial['passages'][pid] = quote
        trial['sources'][eid] = {**citation, 'passage': pid}
        item['sources'].append(eid)
    item['identities'] = sorted(set(item['identities']))
    trial['assertions'][aid] = item


def _retrieve(root, seed, policy, store, original, records, labels):
    if seed not in labels:
        raise ValueError('Select an active canonical IRI using lookup first')
    # Count derived inputs within the graph traversal's existing work envelope.
    evidence = _Evidence(root, store, max_revisions=policy.max_expanded * policy.max_degree)
    adjacency, types = defaultdict(list), defaultdict(set)
    outgoing = list(policy.outgoing) + (list(FRAMEWORK) if policy.include_frameworks else [])
    incoming = list(policy.incoming)
    predicate_order = {_iri(p): i for i, p in enumerate(dict.fromkeys(outgoing + incoming))}
    for record in records:
        for end in ('subject', 'object'):
            entity = record[end]
            if not entity.get('literal'):
                types[entity['id']].update(entity['types'])
                types[entity['id']].update(
                    local_name(v.value) for v in values(store, entity['id'], RDF_TYPE)
                )
        if policy.accepted_only and record['status'] != 'Accepted':
            continue
        if record['framework'] and not policy.include_frameworks:
            continue
        for direction, predicates, start, end in [
            ('outgoing', outgoing, 'subject', 'object'),
            ('incoming', incoming, 'object', 'subject'),
        ]:
            if record['predicate'] not in map(_iri, predicates) or record[start].get('literal'):
                continue
            order = predicate_order[record['predicate']]
            adjacency[record[start]['id']].append(
                (order, direction, record['id'], record, record[end])
            )
    for edges in adjacency.values():
        edges.sort(key=lambda e: (e[0], e[1], e[2]))
    result = _envelope(seed, policy, outgoing, incoming)
    if _measure(result) > policy.max_chars:
        raise ValueError('Budget too small for a valid response envelope')
    queue, scheduled = deque([(seed, [])]), {seed}

    def omit(reason, count=1):
        result['omissions']['limits'][reason] = result['omissions']['limits'].get(reason, 0) + count
        result['omissions']['further_unknown'] = True

    def add(record, path):
        trial = copy.deepcopy(result)
        _include_assertion(trial, record, store, original, labels, types, evidence)
        if path not in trial['paths']:
            trial['paths'].append(path)
        trial['usage']['assertions'] = len(trial['assertions'])
        trial['usage']['passages'] = len(trial['passages'])
        if len(trial['assertions']) > policy.max_assertions:
            return 'assertions'
        if len(trial['passages']) > policy.max_passages:
            return 'passages'
        if _measure(trial) > policy.max_chars:
            return 'characters'
        result.clear()
        result.update(trial)
        return None

    while queue:
        if result['usage']['expanded'] >= policy.max_expanded:
            omit('expanded', len(queue))
            break
        entity, path = queue.popleft()
        used = {step['assertion'] for step in path}
        edges = [edge for edge in adjacency[entity] if edge[2] not in used]
        hub = bool(types[entity] & GENERIC) or len(adjacency[entity]) > policy.hub_degree
        if hub and entity != seed:
            result['omissions']['hubs'] += 1
            result['omissions']['further_unknown'] = True
            continue
        result['usage']['expanded'] += 1
        cap = min(policy.max_degree, policy.seed_hub_degree) if hub else policy.max_degree
        if len(edges) > cap:
            omit('degree', len(edges) - cap)
        for _, direction, aid, record, endpoint in edges[:cap]:
            new_path = path + [{'assertion': aid, 'direction': direction}]
            try:
                reason = add(record, new_path)
            except (ValueError, UnicodeError) as error:
                category = (
                    str(error) if re.fullmatch('[A-Za-z]+', str(error)) else 'InvalidMetadata'
                )
                omissions = result['omissions']
                omissions['invalid_citations'] += 1
                omissions['citation_errors'][category] = (
                    omissions['citation_errors'].get(category, 0) + 1
                )
                omissions['further_unknown'] = True
                continue
            if reason:
                omit(reason)
                continue
            if endpoint.get('literal') or not adjacency[endpoint['id']]:
                continue
            if len(new_path) >= policy.max_depth:
                # The reverse association already on the path is not further work.
                if any(
                    edge[2] not in {s['assertion'] for s in new_path}
                    for edge in adjacency[endpoint['id']]
                ):
                    omit('depth')
                continue
            if endpoint['id'] in scheduled:
                result['omissions']['alternate_routes'] += 1
                continue
            if len(queue) >= policy.max_frontier:
                omit('frontier')
                continue
            queue.append((endpoint['id'], new_path))
            scheduled.add(endpoint['id'])
            result['usage']['frontier_peak'] = max(result['usage']['frontier_peak'], len(queue))
    # Omission metadata and final traversal counters also consume the size budget.
    # Remove complete suffix packages until the final envelope fits.
    while _measure(result) > policy.max_chars and result['paths']:
        result['paths'].pop()
        _prune(result)
        omit('characters')
    if _measure(result) > policy.max_chars:
        raise ValueError('Budget too small for the final omission envelope')
    return result
