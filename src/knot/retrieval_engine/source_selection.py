"""Bounded source routing using eligible metadata and unverified text samples."""

import json
import re
from collections import defaultdict
from pathlib import Path

from knot.graph.rdf import DERIVED, VOCAB, one, values


def source_unit(seed):
    if not isinstance(seed, str) or '#knot-unit=' not in seed:
        return None
    revision, selector = seed.rsplit('#knot-unit=', 1)
    match = re.fullmatch(r'(\d+):(\d+):([0-9a-f]{64})', selector)
    if not match or revision.startswith('urn:knot:note-revision:'):
        raise ValueError('Use an exact source unit or the explicit native history interface')
    return revision, int(match[1]), int(match[2]), match[3]


def select_revisions(revisions, store, records, scorer, evidence, limits, result, aliases):
    if len(revisions) <= limits.max_source_revisions:
        return revisions
    # Hints never leave this routing stage as quotations. Full source and locator
    # verification is still required before any result can cite a selected source.
    from knot.retrieval_engine.ranking import tokens

    metadata = defaultdict(list)
    for record in records:
        for eid in values(store, record['id'], DERIVED):
            revision = one(store, eid.value, VOCAB + 'revision').value
            metadata[revision].append(
                record['subject']['label']
                + ' '
                + record['object']['label']
                + ' '
                + one(store, eid.value, VOCAB + 'quote').value[:2048]
            )
    alias_terms = [tokens(a) for a in aliases if tokens(a)]

    def rank(text):
        local = any(terms <= tokens(text) for terms in alias_terms)
        return local, scorer.score(text)['score']

    ranked = []
    for revision in revisions:
        native = values(store, revision, VOCAB + 'noteMetadata')
        title = json.loads(native[0].value).get('title') or '' if native else ''
        name = Path(one(store, revision, VOCAB + 'snapshotPath').value).name
        hint = ' '.join([title, name, *metadata[revision]])
        ranked.append((rank(hint), revision))
    ranked.sort(key=lambda item: (-item[0][0], -item[0][1], item[1]))
    sampling = {
        'method': 'eligible-metadata-and-bounded-samples-v1',
        'unverified_routing_hints': True,
        'max_revision_previews': limits.max_revision_previews,
        'max_preview_bytes': limits.max_preview_bytes,
        'sampled_revisions': 0,
        'bytes_read': 0,
        'preview_errors': 0,
        'unsampled_revisions': max(0, len(ranked) - limits.max_revision_previews),
    }
    sampled = []
    for priority, revision in ranked[: limits.max_revision_previews]:
        try:
            preview, size = evidence.preview(revision, limits.max_preview_bytes)
            sampling['bytes_read'] += size
            priority = max(priority, rank(preview))
        except (ValueError, UnicodeError):
            sampling['preview_errors'] += 1
        sampling['sampled_revisions'] += 1
        sampled.append((priority, revision))
    sampled.extend(ranked[limits.max_revision_previews :])
    sampled.sort(key=lambda item: (-item[0][0], -item[0][1], item[1]))
    result['ranking']['source_selection'] = sampling
    return [revision for _, revision in sampled[: limits.max_source_revisions]]
