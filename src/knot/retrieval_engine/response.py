"""Evidence response encoding, exact wire budgets and package pruning."""

import json
from dataclasses import asdict


def serialise(result):
    """The complete wire representation, including its terminating newline."""
    return json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(',', ':')) + '\n'


def _quotation(result, source):
    passage = result['passages'][source['passage']]
    span = source.get('passage_span')
    if span is None:
        return passage
    if (
        not isinstance(span, list)
        or len(span) != 2
        or any(type(value) is not int for value in span)
        or not 0 <= span[0] < span[1] <= len(passage)
    ):
        raise ValueError('Invalid quotation range in shared passage')
    return passage[span[0] : span[1]]


def _coalesce(result):
    """Share containing passages only when revision and exact source offsets agree."""
    quotations = {eid: _quotation(result, source) for eid, source in result['sources'].items()}
    full = {}
    for eid, source in result['sources'].items():
        quote = quotations[eid]
        offset = source['locator'].get('characterOffset')
        if offset is not None:
            full[eid] = (source['revision'], int(offset), int(offset) + len(quote))
    passages = {}
    for eid, source in result['sources'].items():
        quote = quotations[eid]
        containing = [
            other
            for other, (revision, start, end) in full.items()
            if eid in full
            and revision == full[eid][0]
            and start <= full[eid][1]
            and full[eid][2] <= end
            and quotations[other][full[eid][1] - start : full[eid][2] - start] == quote
        ]
        parent = (
            min(containing, key=lambda other: (-len(quotations[other]), other))
            if containing
            else eid
        )
        passage = quotations[parent]
        pid = next((pid for pid, value in passages.items() if value == passage), None)
        if pid is None:
            pid = 'p' + str(len(passages) + 1)
            passages[pid] = passage
        source['passage'] = pid
        source.pop('passage_span', None)
        if passage != quote:
            start = full[eid][1] - full[parent][1]
            source['passage_span'] = [start, start + len(quote)]
    result['passages'] = passages


def _resize(result, size):
    """Update self-describing counters from a wire size containing their old values."""
    usage = result['usage']
    original = size
    width = len(str(usage['characters'])) + len(str(usage['utf8_bytes']))
    size = original
    for _ in range(20):
        # Only the two ASCII integer fields change; the rest of the JSON is fixed.
        delta = sum(len(str(value)) for value in size) - width
        updated = original[0] + delta, original[1] + delta
        if updated == size:
            usage['characters'], usage['utf8_bytes'] = size
            return size[0]
        size = updated
    raise ValueError('Could not measure response envelope')


def _measure(result):
    text = serialise(result)
    return _resize(result, (len(text), len(text.encode('utf-8'))))


def _envelope(seed, policy, outgoing, incoming):
    return {
        'seed': seed,
        'policy': {
            **{k: v for k, v in asdict(policy).items() if k not in ('outgoing', 'incoming')},
            'outgoing': list(dict.fromkeys(outgoing)),
            'incoming': incoming,
        },
        'entities': {},
        'assertions': {},
        'paths': [],
        'identities': {},
        'sources': {},
        'passages': {},
        'omissions': {
            'limits': {},
            'hubs': 0,
            'invalid_citations': 0,
            'citation_errors': {},
            'alternate_routes': 0,
            'further_unknown': False,
        },
        'usage': {
            'expanded': 0,
            'frontier_peak': 1,
            'assertions': 0,
            'passages': 0,
            'characters': 0,
            'utf8_bytes': 0,
        },
    }


def _prune(result):
    if 'matches' in result:
        context = {
            m['source']: result['source_context'][m['source']]
            for m in result['matches']
            if m['channel'] == 'text'
        }
        for match in result['matches']:
            context.update(match.get('context_sources', {}))
        result['source_context'] = context
        if 'selection' in result:
            result['selection']['selected_packages'] = len(result['matches'])
    used = {s['assertion'] for path in result['paths'] for s in path}
    result['assertions'] = {a: r for a, r in result['assertions'].items() if a in used}
    sources = {e for r in result['assertions'].values() for e in r['sources']} | set(
        result.get('source_context', {})
    )
    identities = {i for r in result['assertions'].values() for i in r['identities']}
    entities = {
        r[e]
        for r in result['assertions'].values()
        for e in ('subject', 'object')
        if e == 'subject' or not r['object_literal']
    }
    result['sources'] = {e: s for e, s in result['sources'].items() if e in sources}
    if any('passage_span' in source for source in result['sources'].values()):
        _coalesce(result)
    passages = {s['passage'] for s in result['sources'].values()}
    result['passages'] = {p: q for p, q in result['passages'].items() if p in passages}
    result['identities'] = {i: r for i, r in result['identities'].items() if i in identities}
    result['entities'] = {i: r for i, r in result['entities'].items() if i in entities}
    result['usage']['assertions'] = len(result['assertions'])
    result['usage']['passages'] = len(result['passages'])
