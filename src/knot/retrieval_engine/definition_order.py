"""Experimental title-specificity ordering of already verified definitions."""

from collections import defaultdict

from knot.retrieval_engine.ranking import tokens


def reorder(packages, question):
    if len(packages) > 128:
        raise ValueError('Definition ordering is bounded to 128 existing packages')
    query = tokens(question)
    groups, matched = defaultdict(list), {}
    for index, package in enumerate(packages):
        envelope = package['envelope']
        if len(envelope['sources']) != 1 or any(
            m['channel'] != 'text' for m in envelope['matches']
        ):
            continue
        source = next(iter(envelope['sources'].values()))
        note = source.get('native_note', {})
        derivation = note.get('derivation', {})
        origins = tuple(sorted({p['revision'] for p in derivation.get('sources', [])}))
        if (
            source.get('citation_status') != 'Verified'
            or note.get('kind') != 'Definition'
            or derivation.get('method') != 'faithful_restatement'
            or not origins
            or not note.get('title')
        ):
            continue
        matched[index] = tokens(note['title']) & query
        groups[origins].append(index)
    order = list(range(len(packages)))
    edges = []
    for positions in groups.values():
        predecessors = {i: {j for j in positions if matched[i] < matched[j]} for i in positions}
        edges.extend([j, i] for i in positions for j in sorted(predecessors[i]))
        pending, chosen = set(positions), []
        while pending:
            # Strict set inclusion cannot cycle. Stable ties retain existing rank;
            # incomparable framework facets are deliberately not interpreted.
            index = min(i for i in pending if not (predecessors[i] & pending))
            pending.remove(index)
            chosen.append(index)
        for position, index in zip(positions, chosen):
            order[position] = index
    return [packages[i] for i in order], {
        'method': 'definition-title-specificity-v1',
        'changed': order != list(range(len(packages))),
        'original_indices': order,
        'precedence_edges': edges,
    }
