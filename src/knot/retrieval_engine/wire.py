"""Optional, lossless sharing of provenance after bounded evidence selection."""

import copy

from knot.retrieval_engine.response import _measure, serialise

FORMAT = 'shared-provenance-v1'
CITATION_FIELDS = {'locator', 'passage', 'passage_span'}


def evidence_view(result):
    """Omit selection diagnostics, retaining the complete evidence and applied policy."""
    value = copy.deepcopy(result)
    for key in ('ranking', 'selection'):
        value.pop(key, None)
    for match in value.get('matches', []):
        match.pop('ranking', None)
        match.pop('fusion_score', None)
    value['usage'] = {
        key: item
        for key, item in value['usage'].items()
        if key in ('characters', 'utf8_bytes', 'assertions', 'passages')
    }
    value['diagnostics_omitted'] = ['ranking', 'selection', 'match_scores', 'work_counters']
    _measure(value)
    return value


def compact(result):
    """Share metadata and exact derivation pins; retain full format when smaller.

    This only transforms already authorised evidence. It performs no reads and
    does not change selection, review state, qualifications or source independence.
    """
    if result.get('format') == FORMAT:
        return copy.deepcopy(result)
    encoded = copy.deepcopy(result)
    encoded.update(format=FORMAT, source_metadata={}, derivation_sources={})
    metadata_ids, pin_ids = {}, {}

    def intern(value, table, ids, prefix):
        key = serialise(value)
        if key not in ids:
            ids[key] = prefix + str(len(ids) + 1)
            table[ids[key]] = value
        return ids[key]

    for eid, source in encoded.get('sources', {}).items():
        metadata = {key: value for key, value in source.items() if key not in CITATION_FIELDS}
        derivation = metadata.get('native_note', {}).get('derivation')
        if derivation:
            derivation['sources'] = [
                intern(pin, encoded['derivation_sources'], pin_ids, 'd')
                for pin in derivation['sources']
            ]
        ref = intern(metadata, encoded['source_metadata'], metadata_ids, 'r')
        encoded['sources'][eid] = {
            'metadata': ref,
            **{key: value for key, value in source.items() if key in CITATION_FIELDS},
        }
    _measure(encoded)
    return encoded if len(serialise(encoded)) < len(serialise(result)) else copy.deepcopy(result)


def expand(result):
    """Restore the full response and its exact wire counters without filesystem access."""
    if 'format' not in result:
        return copy.deepcopy(result)
    if result['format'] != FORMAT:
        raise ValueError('Unknown evidence response format')
    decoded = copy.deepcopy(result)
    try:
        for eid, source in decoded['sources'].items():
            metadata = copy.deepcopy(decoded['source_metadata'][source['metadata']])
            derivation = metadata.get('native_note', {}).get('derivation')
            if derivation:
                derivation['sources'] = [
                    copy.deepcopy(decoded['derivation_sources'][ref])
                    for ref in derivation['sources']
                ]
            decoded['sources'][eid] = {
                **metadata,
                **{key: value for key, value in source.items() if key != 'metadata'},
            }
    except (KeyError, TypeError) as error:
        raise ValueError('Invalid shared provenance reference') from error
    for key in ('format', 'source_metadata', 'derivation_sources'):
        del decoded[key]
    _measure(decoded)
    return decoded
