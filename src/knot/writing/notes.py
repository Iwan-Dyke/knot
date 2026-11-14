"""Native note revisions and navigation, without assertion extraction."""

import fcntl
import json
import re
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from pyoxigraph import NamedNode

from knot.graph.rdf import DERIVED, LABEL, META, RDF_TYPE, VOCAB, Dataset, write_bytes
from knot.shared.storage import atomic_json, digest, managed_path

NOTE = 'urn:knot:note:'
REVISION = 'urn:knot:note-revision:'
HASH = re.compile(r'[0-9a-f]{64}')
KEEP = object()
FIELDS = {
    'schema_version',
    'note',
    'parent',
    'body_sha256',
    'body_path',
    'format',
    'created_at',
    'modified_at',
    'title',
    'author',
    'agent',
    'reason',
}
CURRENT = 'urn:knot:notes'
HISTORY = 'urn:knot:note-history'


def _kind(value):
    from knot.shared.vocabulary import KINDS

    if value is not None and (not isinstance(value, str) or value not in KINDS):
        raise ValueError('Unknown note knowledge kind')


def _entity_ids(entities):
    if not isinstance(entities, (list, tuple, set, frozenset)):
        raise ValueError('Note entities must be a collection of explicit IRIs')
    for entity in entities:
        if not isinstance(entity, str):
            raise ValueError('Note entities must be explicit IRIs')
        NamedNode(entity)
    return sorted(set(entities))


def _entity_view(root):
    from knot.graph.query import identity_bindings, load_store
    from knot.shared.vocabulary import TYPES

    store = load_store(Path(root) / 'graph', include_notes=False, allow_empty=True)
    bindings = identity_bindings(store)
    sources = {
        q.object
        for q in store.quads_for_pattern(None, NamedNode(VOCAB + 'sourceEntity'), None, META)
    }
    known = {
        q.subject for q in store.quads_for_pattern(None, NamedNode(LABEL), None, META)
    } - sources
    known.update(bindings.values())
    entity_types = {NamedNode(VOCAB + kind) for kind in TYPES}
    for graph in (META, NamedNode('urn:knot:organisation')):
        known.update(
            q.subject
            for q in store.quads_for_pattern(None, NamedNode(RDF_TYPE), None, graph)
            if q.object in entity_types
        )
    for assertion in store.quads_for_pattern(
        None, NamedNode(RDF_TYPE), NamedNode(VOCAB + 'Assertion'), META
    ):
        for quad in store.quads_for_pattern(None, None, None, assertion.subject):
            known.add(quad.subject)
            if isinstance(quad.object, NamedNode):
                known.add(quad.object)
    known.update(
        NamedNode(e['id'])
        for n in list_notes(root)
        for e in n.get('navigation', {}).get('declarations', [])
    )
    return bindings, known


def _canonical_entities(root, entities, *, view=None):
    entities = _entity_ids(entities)
    if not entities:
        return []
    bindings, known = _entity_view(root) if view is None else view
    resolved = {bindings.get(NamedNode(entity), NamedNode(entity)) for entity in entities}
    if not resolved <= known:
        raise ValueError('Note associations require existing entity IRIs in the identity view')
    return sorted(entity.value for entity in resolved)


def _now():
    return datetime.now(timezone.utc).isoformat(timespec='microseconds').replace('+00:00', 'Z')


def _encode(value):
    return (
        json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')) + '\n'
    ).encode('utf-8')


def _path(root, relative):
    # Managed paths are fixed by the format, never redirects to other user files.
    return managed_path(root, relative)


def _note_id(value):
    if not isinstance(value, str) or not value.startswith(NOTE):
        raise ValueError('Invalid note identifier')
    try:
        key = str(UUID(value.removeprefix(NOTE)))
    except ValueError as error:
        raise ValueError('Invalid note identifier') from error
    if value != NOTE + key:
        raise ValueError('Invalid note identifier')


def _revision_hash(value):
    if not isinstance(value, str) or not value.startswith(REVISION):
        raise ValueError('Invalid note revision identifier')
    key = value.removeprefix(REVISION)
    if not HASH.fullmatch(key):
        raise ValueError('Invalid note revision identifier')
    return key


def _metadata(format, title, author, agent, reason):
    if format not in ('markdown', 'org') or any(
        value is not None and not isinstance(value, str) for value in (title, author, agent, reason)
    ):
        raise ValueError('Notes require Markdown/Org and optional text metadata')


def _body(value):
    if isinstance(value, str):
        value = value.encode('utf-8')
    if not isinstance(value, bytes):
        raise ValueError('A note body must be UTF-8 text or bytes')
    value.decode('utf-8')
    return value


def _registry(root):
    path = _path(root, 'notes/registry.json')
    if not path.exists():
        if any(_path(root, 'notes/revisions').glob('*.json')):
            raise ValueError('Note registry missing; restore it before writing')
        return {'schema_version': 2, 'notes': {}, 'history': {}}
    value = json.loads(path.read_bytes())
    if (
        not isinstance(value, dict)
        or set(value)
        != (
            {'schema_version', 'notes', 'history'}
            if value.get('schema_version') == 2
            else {'schema_version', 'notes'}
        )
        or type(value['schema_version']) is not int
        or value['schema_version'] not in (1, 2)
        or not isinstance(value['notes'], dict)
    ):
        raise ValueError('Invalid note registry')
    for note, head in value['notes'].items():
        _note_id(note)
        _revision_hash(head)
    if value['schema_version'] == 2:
        history = value['history']
        if not isinstance(history, dict) or set(history) != set(value['notes']):
            raise ValueError('Invalid note registry history')
        seen = set()
        for note, revisions in history.items():
            if (
                not isinstance(revisions, list)
                or not revisions
                or revisions[-1] != value['notes'][note]
            ):
                raise ValueError('Invalid note registry history')
            for revision in revisions:
                _revision_hash(revision)
                if revision in seen:
                    raise ValueError('Duplicate committed note revision')
                seen.add(revision)
    return value


def _verified(root, relative, sha256):
    try:
        content = _path(root, relative).read_bytes()
    except FileNotFoundError as error:
        raise ValueError(f'Note evidence missing: {relative}') from error
    if digest(content) != sha256:
        raise ValueError(f'Note evidence hash mismatch: {relative}')
    return content


def _read_revision(root, note, revision, *, verify_body=True):
    key = _revision_hash(revision)
    raw = _verified(root, f'notes/revisions/{key}.json', key)
    value = json.loads(raw)
    version = value.get('schema_version') if isinstance(value, dict) else None
    fields = FIELDS | {'entities', 'kind'} if version in (2, 3, 4) else FIELDS
    if version in (3, 4):
        fields |= {'derivation'}
    if version == 4:
        fields |= {'navigation'}
    if (
        not isinstance(value, dict)
        or set(value) != fields
        or type(version) is not int
        or version not in (1, 2, 3, 4)
        or value['note'] != note
        or not isinstance(value['body_sha256'], str)
        or not HASH.fullmatch(value['body_sha256'])
        or _encode(value) != raw
    ):
        raise ValueError('Invalid note revision manifest')
    entities, kind = value.get('entities', []), value.get('kind')
    if not isinstance(entities, list) or entities != _entity_ids(entities):
        raise ValueError('Invalid note association metadata')
    _kind(kind)
    _metadata(value['format'], value['title'], value['author'], value['agent'], value['reason'])
    if version in (3, 4):
        _curated_metadata(value.get('derivation'), value['title'], value['author'], value['agent'])
        if version == 3 and value['derivation'] is None:
            raise ValueError('Curated revision requires derivation metadata')
    if value['parent'] is not None:
        _revision_hash(value['parent'])
    for field in ('created_at', 'modified_at'):
        timestamp = value[field]
        if not isinstance(timestamp, str):
            raise ValueError('Invalid note timestamp')
        parsed = datetime.fromisoformat(timestamp)
        if (
            parsed.tzinfo != timezone.utc
            or parsed.isoformat(timespec='microseconds').replace('+00:00', 'Z') != timestamp
        ):
            raise ValueError('Invalid note timestamp')
    if value['body_path'] != f'sources/revisions/{value["body_sha256"]}/note.txt':
        raise ValueError('Invalid note body path')
    body = (
        _verified(root, value['body_path'], value['body_sha256']).decode('utf-8')
        if verify_body
        else None
    )
    if version == 4:
        from knot.writing.navigation import validate_navigation

        validate_navigation(value['navigation'], body)
    return {**value, 'entities': entities, 'kind': kind, 'revision': revision, 'body': body}


def _history(root, note, registry):
    _note_id(note)
    head = registry['notes'].get(note)
    if head is None:
        raise ValueError(f'Unknown note: {note}')
    revisions, seen = [], set()
    while head is not None:
        if head in seen:
            raise ValueError('Cyclic note revision history')
        seen.add(head)
        revision = _read_revision(root, note, head)
        if revisions and revision['created_at'] != revisions[0]['created_at']:
            raise ValueError('Note creation time changed across revisions')
        revisions.append(revision)
        head = revision['parent']
    result = list(reversed(revisions))
    if (
        registry['schema_version'] == 2
        and [r['revision'] for r in result] != registry['history'][note]
    ):
        raise ValueError('Committed note history does not match its ancestry')
    return result


@contextmanager
def _writer(root):
    _path(root, 'notes').mkdir(parents=True, exist_ok=True)
    with _path(root, 'notes/.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def _preserve(root, relative, content):
    path = _path(root, relative)
    if path.exists():
        if path.read_bytes() != content:
            raise ValueError(f'Existing note evidence hash mismatch: {relative}')
    else:
        write_bytes(path, content)
    _verified(root, relative, digest(content))


def _commit(root, registry, note, content, metadata, previous, *, agent, reason):
    registry = _indexed_registry(root, registry)
    now = _now()
    sha256 = digest(content)
    manifest = {
        'schema_version': 4 if 'navigation' in metadata else 3 if metadata.get('derivation') else 2,
        'note': note,
        'parent': previous['revision'] if previous else None,
        'created_at': previous['created_at'] if previous else now,
        'modified_at': now,
        'body_sha256': sha256,
        'body_path': f'sources/revisions/{sha256}/note.txt',
        **metadata,
        'agent': agent,
        'reason': reason,
    }
    raw = _encode(manifest)
    revision = REVISION + digest(raw)
    _preserve(root, manifest['body_path'], content)
    _preserve(root, f'notes/revisions/{digest(raw)}.json', raw)
    saved = _read_revision(root, note, revision)
    registry['notes'][note] = revision
    registry['history'].setdefault(note, []).append(revision)
    # The single atomic head update is the publication point. Unreferenced blobs
    # from interrupted saves are not committed history and may be reused on retry.
    atomic_json(_path(root, 'notes/registry.json'), registry)
    return saved


def _indexed_registry(root, registry):
    if registry['schema_version'] == 2:
        return registry
    return {
        'schema_version': 2,
        'notes': dict(registry['notes']),
        'history': {
            note: [r['revision'] for r in _history(root, note, registry)]
            for note in registry['notes']
        },
    }


def index_note_revisions(root):
    """Owner-only upgrade of the publication index; never changes source evidence.

    Scoped readers need committed membership without visiting denied descendants.
    Legacy registries are verified and upgraded explicitly, or on the next commit.
    """
    root = Path(root).resolve()
    with _writer(root):
        registry = _registry(root)
        indexed = _indexed_registry(root, registry)
        if registry['schema_version'] != 2:
            atomic_json(_path(root, 'notes/registry.json'), indexed)
        return {
            'notes': len(indexed['notes']),
            'revisions': sum(map(len, indexed['history'].values())),
        }


def create_note(
    root,
    body='',
    *,
    format='markdown',
    title=None,
    author=None,
    agent=None,
    reason=None,
    entities=(),
    kind=None,
    derivation=None,
    navigation=None,
    note_id=None,
):
    """Create an independent note and its first immutable revision."""
    content = _body(body)
    if navigation is not None:
        from knot.writing.navigation import validate_selection

        validate_selection(root, navigation, content.decode('utf-8'))
    if note_id is not None:
        _note_id(note_id)
    _metadata(format, title, author, agent, reason)
    _kind(kind)
    entities = _canonical_entities(root, entities)
    _curated_metadata(derivation, title, author, agent)
    if derivation is not None:
        from knot.curating.provenance import validate_sources

        validate_sources(root, derivation['sources'])
    root = Path(root).resolve()
    with _writer(root):
        registry = _registry(root)
        note = note_id or NOTE + str(uuid4())
        if note in registry['notes']:
            raise ValueError('Note identifier already exists')
        if not _path(root, 'notes/registry.json').exists():
            atomic_json(_path(root, 'notes/registry.json'), registry)
        return _commit(
            root,
            registry,
            note,
            content,
            {
                'format': format,
                'title': title,
                'author': author,
                'entities': entities,
                'kind': kind,
                **({'derivation': derivation} if derivation is not None else {}),
                **(
                    {'navigation': navigation, 'derivation': derivation}
                    if navigation is not None
                    else {}
                ),
            },
            None,
            agent=agent,
            reason=reason,
        )


def list_notes(root):
    """Read current notes in ID order, verifying their complete committed histories."""
    root = Path(root).resolve()
    registry = _registry(root)
    return [_history(root, note, registry)[-1] for note in sorted(registry['notes'])]


def note_history(root, note):
    """Read committed versions oldest first, verifying manifests and source bytes."""
    root = Path(root).resolve()
    return _history(root, note, _registry(root))


def read_note(root, note, *, revision=None):
    """Read the current version or an explicit version in its committed ancestry."""
    history = note_history(root, note)
    if revision is None:
        return history[-1]
    _revision_hash(revision)
    for saved in history:
        if saved['revision'] == revision:
            return saved
    raise ValueError("Revision is not in this note's committed history")


def save_note(
    root,
    note,
    body,
    *,
    expected,
    format=KEEP,
    title=KEEP,
    author=KEEP,
    agent=None,
    reason=None,
    entities=KEEP,
    kind=KEEP,
    derivation=KEEP,
    navigation=KEEP,
):
    """Save against an expected head; omitted state is preserved, None clears it.

    Agent/reason describe an actual commit. They do not create an audit-only
    revision when the body, format, title and author are unchanged.
    """
    content = _body(body)
    _note_id(note)
    _revision_hash(expected)
    root = Path(root).resolve()
    with _writer(root):
        registry = _registry(root)
        previous = _history(root, note, registry)[-1]
        if previous['revision'] != expected:
            raise ValueError('Note head changed; reload before saving')
        metadata = {
            key: previous[key] if value is KEEP else value
            for key, value in (('format', format), ('title', title), ('author', author))
        }
        _metadata(**metadata, agent=agent, reason=reason)
        selected_kind = previous['kind'] if kind is KEEP else kind
        _kind(selected_kind)
        metadata.update(
            entities=previous['entities']
            if entities is KEEP
            else _canonical_entities(root, entities),
            kind=selected_kind,
        )
        selected_navigation = previous.get('navigation') if navigation is KEEP else navigation
        if selected_navigation is not None:
            from knot.writing.navigation import validate_selection

            validate_selection(
                root,
                selected_navigation,
                content.decode('utf-8'),
                previous=previous.get('navigation'),
            )
            metadata['navigation'] = selected_navigation
            metadata['derivation'] = previous.get('derivation')
        selected_derivation = previous.get('derivation') if derivation is KEEP else derivation
        if selected_derivation is not None and previous.get('derivation') is None:
            raise ValueError('Create a separate curated note; preserve the original source')
        if selected_derivation is None and previous.get('derivation') is not None:
            raise ValueError('A curated note must retain its derivation')
        if selected_derivation is not None:
            from knot.curating.provenance import validate_sources

            # An omitted saving agent retains the prior attribution for a no-op;
            # a real curated edit must name the agent responsible for that edit.
            _curated_metadata(
                selected_derivation,
                metadata['title'],
                metadata['author'],
                agent or previous['agent'],
            )
            validate_sources(root, selected_derivation['sources'])
            metadata['derivation'] = selected_derivation
        if previous['body_sha256'] == digest(content) and all(
            previous.get(k) == v for k, v in metadata.items()
        ):
            return previous
        if selected_derivation is not None and not agent:
            raise ValueError('A curated edit requires the actual saving agent')
        return _commit(
            root, registry, note, content, metadata, previous, agent=agent, reason=reason
        )


def _curated_metadata(derivation, title, author, agent):
    if derivation is None:
        return
    from knot.curating.provenance import validate_derivation

    validate_derivation(derivation)
    if not all(isinstance(value, str) and value.strip() for value in (title, author, agent)):
        raise ValueError('Curated notes require a title, actual author and saving agent')


def build_note_projection(root, store):
    """Rebuild verified current navigation and declared history in one dataset.

    The registry is read once. Immutable ancestors stay consistent even if a save
    publishes a new head while this snapshot is being projected. No index is kept.
    """
    from knot.graph.query import identity_bindings

    root = Path(root).resolve()
    registry = _registry(root)
    bindings = identity_bindings(store)
    dataset = Dataset()
    for note in sorted(registry['notes']):
        history = _history(root, note, registry)
        latest = history[-1]
        from knot.writing.navigation import project_navigation

        project_navigation(dataset, latest, note, CURRENT, bindings=bindings)
        dataset.add(note, RDF_TYPE, VOCAB + 'Note', graph=CURRENT)
        dataset.add(note, VOCAB + 'currentRevision', latest['revision'], graph=CURRENT)
        for entity in latest['entities']:
            target = bindings.get(NamedNode(entity), NamedNode(entity)).value
            dataset.add(note, VOCAB + 'associatedEntity', target, graph=CURRENT)
        for saved in history:
            revision = saved['revision']
            project_navigation(dataset, saved, revision, HISTORY)
            dataset.add(note, VOCAB + 'revision', revision, graph=HISTORY)
            dataset.add(revision, RDF_TYPE, VOCAB + 'NoteRevision', graph=HISTORY)
            dataset.add(revision, VOCAB + 'note', note, graph=HISTORY)
            if saved.get('derivation'):
                for pin in saved['derivation']['sources']:
                    dataset.add(revision, DERIVED, pin['revision'], graph=HISTORY)
            if saved['parent'] is not None:
                dataset.add(revision, VOCAB + 'previousRevision', saved['parent'], graph=HISTORY)
            for entity in saved['entities']:
                dataset.add(revision, VOCAB + 'associatedEntity', entity, graph=HISTORY)
            for key, value in (
                ('snapshotPath', saved['body_path']),
                ('sha256', saved['body_sha256']),
                ('manifestSha256', _revision_hash(revision)),
                ('manifestPath', f'notes/revisions/{_revision_hash(revision)}.json'),
                ('format', saved['format']),
                ('savingAgent', saved['agent']),
                ('revisionReason', saved['reason']),
            ):
                if value is not None:
                    dataset.add(revision, VOCAB + key, value, literal=True, graph=HISTORY)
            for subject, graph in [(revision, HISTORY)] + (
                [(note, CURRENT)] if saved is latest else []
            ):
                for predicate, value in (
                    (LABEL, saved['title']),
                    (VOCAB + 'author', saved['author']),
                    (VOCAB + 'createdAt', saved['created_at']),
                    (VOCAB + 'modifiedAt', saved['modified_at']),
                ):
                    if value is not None:
                        dataset.add(subject, predicate, value, literal=True, graph=graph)
                if saved['kind'] is not None:
                    dataset.add(subject, VOCAB + 'noteKind', VOCAB + saved['kind'], graph=graph)
    return dataset.text().encode('utf-8')
