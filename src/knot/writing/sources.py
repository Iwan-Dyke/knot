"""Adapt permitted native revisions to the existing source-text retrieval view."""

import json
from pathlib import Path

from pyoxigraph import NamedNode, RdfFormat

from knot.graph.query import identity_bindings
from knot.graph.rdf import LABEL, META, RDF_TYPE, VOCAB, Dataset, values
from knot.writing.notes import REVISION, _history, _read_revision, _registry, _revision_hash


def curated_scope(root, scope):
    """Remove derived grants lacking their input closure before graph projection.

    Only explicitly granted manifests are inspected. Denied input IDs found in an
    allowed manifest are checked against pins before their manifests can be read.
    """
    if scope is None or scope.whole_dataset:
        return scope
    from knot.curating.provenance import MAX_DERIVATION_DEPTH
    from knot.interfaces.access import AccessScope

    pins = dict(scope.revisions)
    native = {revision for revision in pins if revision.startswith(REVISION)}
    if not native:
        return scope
    root = Path(root).resolve()
    registry = _registry(root)
    if registry['schema_version'] != 2:
        raise ValueError('Run index_note_revisions locally before granting native revisions')
    members = {
        revision: note
        for note, revisions in registry['history'].items()
        for revision in revisions
        if revision in native
    }
    if native - members.keys():
        raise ValueError('Unavailable note revision')
    saved = {r: _read_revision(root, note, r, verify_body=False) for r, note in members.items()}
    for revision, value in saved.items():
        if value['body_sha256'] != pins[revision]:
            raise ValueError('Source grant no longer matches the dataset')
    admitted, depths = {}, {}

    def eligible(revision, visiting):
        if revision in visiting:
            raise ValueError('Cyclic derivation provenance')
        if len(visiting) > MAX_DERIVATION_DEPTH:
            raise ValueError('Derivation depth exceeds 32 input edges')
        if revision in admitted:
            if admitted[revision] and len(visiting) + depths[revision] > MAX_DERIVATION_DEPTH:
                raise ValueError('Derivation depth exceeds 32 input edges')
            return admitted[revision]
        derivation = saved[revision].get('derivation')
        sources = derivation['sources'] if derivation else []
        result, depth = True, 0
        for pin in sources:
            parent = pin['revision']
            if pins.get(parent) != pin['sha256'] or (
                parent in native and not eligible(parent, visiting | {revision})
            ):
                result = False
                break
            depth = max(depth, 1 + (depths[parent] if parent in native else 0))
        if result and len(visiting) + depth > MAX_DERIVATION_DEPTH:
            raise ValueError('Derivation depth exceeds 32 input edges')
        admitted[revision] = result
        depths[revision] = depth
        return result

    denied = {revision for revision in native if not eligible(revision, set())}
    return AccessScope(revisions=tuple(pair for pair in scope.revisions if pair[0] not in denied))


def add_note_sources(root, store, original, labels, *, scope=None, note_revision=None):
    """Select before reading manifests; never inspect denied bodies or descendants."""
    restricted = scope is not None and not scope.whole_dataset
    pins = dict(scope.revisions) if restricted else None
    allowed = {r for r in pins if r.startswith(REVISION)} if restricted else None
    if restricted and not allowed:
        if note_revision is not None:
            raise ValueError('Unavailable note revision')
        return
    if note_revision is not None:
        _revision_hash(note_revision)
        if restricted and note_revision not in allowed:
            raise ValueError('Unavailable note revision')
    root = Path(root).resolve()
    registry = _registry(root)
    if restricted and registry['schema_version'] != 2:
        raise ValueError('Run index_note_revisions locally before granting native revisions')
    histories = registry.get('history')
    registered_sources = {
        q.subject.value
        for q in store.quads_for_pattern(None, NamedNode(VOCAB + 'snapshotPath'), None, META)
        if q.subject.value.startswith(REVISION)
    }
    if histories is None and (note_revision is not None or registered_sources):
        histories = {
            note: [r['revision'] for r in _history(root, note, registry)]
            for note in registry['notes']
        }
    verified = {}
    if restricted or registered_sources:
        required = allowed if restricted else registered_sources
        members = {
            revision: note
            for note, revisions in histories.items()
            for revision in revisions
            if revision in required
        }
        if required - members.keys():
            raise ValueError('Unavailable note revision')
        for revision, note in members.items():
            saved = _read_revision(root, note, revision, verify_body=False)
            if restricted and pins[revision] != saved['body_sha256']:
                raise ValueError('Source grant no longer matches the dataset')
            # Factual RDF may also register a native source. It must agree with
            # the immutable manifest even when it is not the selected text head.
            for key, expected in (
                ('sha256', saved['body_sha256']),
                ('snapshotPath', saved['body_path']),
            ):
                registered = values(store, revision, VOCAB + key)
                if registered and (len(registered) != 1 or registered[0].value != expected):
                    raise ValueError('Native source registration does not match its manifest')
            verified[revision] = saved
    selected = {}
    if note_revision is not None:
        selected = {
            note: note_revision
            for note, revisions in histories.items()
            if note_revision in revisions
        }
        if not selected:
            raise ValueError('Unavailable note revision')
    elif restricted:
        for note, revisions in histories.items():
            visible = [revision for revision in revisions if revision in allowed]
            if visible:
                selected[note] = visible[-1]
    else:
        selected = registry['notes']
    bindings = identity_bindings(store)
    dataset = Dataset()
    sources = {revision: verified[revision] for revision in registered_sources}
    if note_revision is not None:
        # Selecting an exact text head must not remove permitted provenance needed
        # by display overlays or evidence-account qualifications. Keep the normal
        # view's heads as evidence only; text eligibility still follows selected.
        if restricted:
            for revisions in histories.values():
                visible = [revision for revision in revisions if revision in allowed]
                if visible:
                    sources[visible[-1]] = verified[visible[-1]]
        else:
            for note, revision in registry['notes'].items():
                sources[revision] = _read_revision(root, note, revision, verify_body=False)
    for note, revision in selected.items():
        sources[revision] = (
            verified[revision]
            if revision in verified
            else _read_revision(root, note, revision, verify_body=False)
        )
    # Include historical native inputs as evidence-only sources. They are not
    # promoted to current text heads and cannot change the original note's head.
    members = {
        revision: note for note, revisions in (histories or {}).items() for revision in revisions
    }
    pending = list(sources)
    while pending:
        saved = sources[pending.pop()]
        derivation = saved.get('derivation')
        for pin in derivation['sources'] if derivation else []:
            revision = pin['revision']
            if restricted and pins.get(revision) != pin['sha256']:
                raise ValueError('Unavailable derivation source')
            if revision.startswith(REVISION) and revision not in sources:
                if revision not in members:
                    raise ValueError('Unavailable derivation source')
                sources[revision] = _read_revision(
                    root, members[revision], revision, verify_body=False
                )
                pending.append(revision)
    for revision, saved in sorted(sources.items()):
        note = saved['note']
        text_head = selected.get(note) == revision
        entities = sorted(
            {bindings.get(NamedNode(e), NamedNode(e)).value for e in saved['entities']}
        )
        currentness = (
            'EvidenceRevision'
            if not text_head
            else 'ExplicitHistoricalRevision'
            if note_revision is not None
            else 'LatestGrantedRevision'
            if restricted
            else 'CurrentCommittedRevision'
        )
        header = {
            key: saved[key]
            for key in (
                'title',
                'author',
                'kind',
                'format',
                'created_at',
                'modified_at',
                'agent',
                'reason',
                'entities',
            )
        }
        if 'navigation' in saved:
            from knot.writing.navigation import project_navigation

            header['navigation'] = saved['navigation']
            project_navigation(dataset, saved, note, META.value, bindings=bindings)
            for entity in saved['navigation']['declarations']:
                declared = NamedNode(entity['id'])
                canonical = bindings.get(declared, declared).value
                labels.setdefault(canonical, set()).add(entity['label'])
                entities.append(canonical)
        header.update(id=note, currentness=currentness, navigation_entities=sorted(set(entities)))
        if saved.get('derivation') is not None:
            header['derivation'] = saved['derivation']
        dataset.add(note, RDF_TYPE, VOCAB + 'Document')
        dataset.add(note, VOCAB + 'revision', revision)
        dataset.add(revision, VOCAB + 'nativeNote', note)
        dataset.add(revision, VOCAB + 'nativeTextEligible', text_head, literal=True)
        for predicate, value in (
            ('snapshotPath', saved['body_path']),
            ('sha256', saved['body_sha256']),
            ('manifestPath', f'notes/revisions/{_revision_hash(revision)}.json'),
            ('manifestSha256', _revision_hash(revision)),
            ('noteMetadata', json.dumps(header, sort_keys=True, ensure_ascii=False)),
        ):
            dataset.add(revision, VOCAB + predicate, value, literal=True)
        if text_head:
            labels.setdefault(note, set()).add(saved['title'] or note)
            dataset.add(note, LABEL, saved['title'] or note, literal=True)
            for entity in entities:
                if entity not in labels:
                    labels[entity] = {entity}
    raw = dataset.text().encode()
    if raw:
        # These fields describe this eligible view, not authoritative assertion
        # metadata. Replace any prior adapter values in memory only.
        for target in (store,) if original is store else (store, original):
            for revision in sources:
                for key in (
                    'nativeNote',
                    'noteMetadata',
                    'nativeTextEligible',
                    'manifestPath',
                    'manifestSha256',
                ):
                    for quad in list(
                        target.quads_for_pattern(
                            NamedNode(revision), NamedNode(VOCAB + key), None, META
                        )
                    ):
                        target.remove(quad)
        store.load(input=raw, format=RdfFormat.TRIG)
        if original is not store:
            original.load(input=raw, format=RdfFormat.TRIG)
