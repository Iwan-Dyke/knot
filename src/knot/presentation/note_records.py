"""Verified current-note records shared by offline presentation surfaces."""

import json
from collections import defaultdict
from pathlib import Path

from pyoxigraph import NamedNode

from knot.graph.rdf import META, VOCAB, values
from knot.retrieval_engine.evidence import _Evidence


def curated_notes(root, store, entity_ids, *, include_all=False):
    """Export verified current notes once, indexed by declared canonical associations."""
    entity_ids = set(entity_ids)
    notes, associations = {}, defaultdict(list)
    reader = _Evidence(root, store)
    candidates = []
    for quad in store.quads_for_pattern(None, NamedNode(VOCAB + 'noteMetadata'), None, META):
        revision = quad.subject.value
        header = json.loads(quad.object.value)
        if (not include_all and not header.get('derivation')) or not any(
            value.value == 'true' for value in values(store, revision, VOCAB + 'nativeTextEligible')
        ):
            continue
        linked = set(header['navigation_entities'])
        if not include_all:
            linked &= entity_ids
        if linked or include_all:
            candidates.append(
                ((header['title'] or '').casefold(), header['id'], revision, header, linked)
            )
    for _, note_id, revision, header, linked in sorted(candidates):
        body, _ = reader.revision(revision)
        derivation = header.get('derivation') or {}
        sources = []
        for pin in derivation.get('sources', []):
            _, original = reader.revision(pin['revision'])
            source_note = original.get('native_note', {})
            sources.append(
                {
                    **pin,
                    'snapshot': original['snapshot'],
                    'text_path': original['text_path'],
                    'title': source_note.get('title') or Path(original['snapshot']).name,
                    'author': source_note.get('author'),
                }
            )
        notes[note_id] = {
            'id': note_id,
            'revision': revision,
            'title': header['title'] or 'Untitled note',
            'body': body,
            'author': header['author'],
            'kind': header['kind'],
            'method': derivation.get('method'),
            'qualification': derivation.get('qualification'),
            'sources': sources,
            'entities': sorted(linked),
            'navigation': header.get('navigation')
            or {'links': [], 'themes': [], 'declarations': []},
        }
        for entity in sorted(linked):
            associations[entity].append(note_id)
    return {'notes': notes, 'entities': dict(associations)}
