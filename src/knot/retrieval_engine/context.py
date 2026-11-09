"""Prepare eligible graph and source views for retrieval and discovery."""

from collections import defaultdict
from pathlib import Path

from knot.curating.entity_labels import apply_entity_labels
from knot.graph.knowledge import entries
from knot.graph.query import load_store
from knot.graph.rdf import LABEL, values


def _labels(store, records):
    labels = defaultdict(set)
    for record in records:
        for end in ('subject', 'object'):
            entity = record[end]
            if entity.get('literal'):
                continue
            labels[entity['id']].add(entity['label'])
            labels[entity['id']].update(v.value for v in values(store, entity['id'], LABEL))
    return labels


def lookup(root, text, *, limit=10, scope=None):
    """Return candidates, never automatically select an ambiguous label."""
    if not text.strip() or type(limit) is not int or limit < 1:
        raise ValueError('Supply nonempty seed text and a positive candidate limit')
    if scope is None:
        store = load_store(Path(root) / 'graph', include_notes=False, allow_empty=True)
        labels = _labels(store, entries(store))
        from knot.writing.sources import add_note_sources

        add_note_sources(root, store, store, labels)
        _, labels = apply_entity_labels(root, store, [], labels)
    else:
        _, _, _, labels = _prepare(root, scope=scope)
    folded = text.casefold().strip()
    candidates = []
    for eid, names in sorted(labels.items()):
        match = (
            'iri' if text == eid else 'exact' if folded in {n.casefold() for n in names} else None
        )
        if match:
            candidates.append({'id': eid, 'labels': sorted(names), 'match': match})
    if not candidates:
        for eid, names in sorted(labels.items()):
            if any(folded in name.casefold() for name in names):
                candidates.append({'id': eid, 'labels': sorted(names), 'match': 'lexical'})
    return {'candidates': candidates[:limit], 'truncated': len(candidates) > limit}


def _prepare(root, *, scope=None, note_revision=None):
    """Read one graph snapshot; evaluation can separate loading from traversal."""
    root = Path(root)
    from knot.writing.sources import add_note_sources, curated_scope

    scope = curated_scope(root, scope)
    # Owner graph projection reads all history. Retrieval first scopes ordinary
    # evidence, then adapts only permitted native revisions without denied reads.
    store = load_store(root / 'graph', include_notes=False, allow_empty=True)
    records = entries(store)
    labels = _labels(store, records)
    original = load_store(root / 'graph', history=True, include_notes=False, allow_empty=True)
    prepared = (
        (store, original, records, labels)
        if scope is None
        else scope.apply(store, original, records, labels)
    )
    add_note_sources(
        root, prepared[0], prepared[1], prepared[3], scope=scope, note_revision=note_revision
    )
    records, labels = apply_entity_labels(root, prepared[0], prepared[2], prepared[3], scope=scope)
    from knot.curating.evidence_accounts import annotate_accounts

    records = annotate_accounts(root, prepared[0], records, scope=scope)
    return prepared[0], prepared[1], records, labels
