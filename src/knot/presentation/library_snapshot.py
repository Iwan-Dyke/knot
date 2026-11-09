"""Export a verified, read-only Knowledge Library and focused Graph snapshot."""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from pyoxigraph import NamedNode

from knot.curating.entity_labels import apply_entity_labels
from knot.curating.evidence_accounts import annotate_accounts
from knot.graph.knowledge import entries
from knot.graph.query import identity_bindings, load_store
from knot.graph.rdf import DERIVED, LABEL, META, RDF_TYPE, VOCAB, one, values
from knot.presentation.markup import render_markup
from knot.presentation.note_records import curated_notes
from knot.retrieval_engine.context import _labels
from knot.retrieval_engine.evidence import _Evidence
from knot.reviewing.state import read_events
from knot.shared.storage import DATASET_DIRECTORIES, digest, managed_path
from knot.shared.vocabulary import TYPES, local_name
from knot.writing.notes import _history, _registry
from knot.writing.sources import add_note_sources
from knot.writing.themes import read_catalogue


def input_signature(root):
    """Cover authoritative inputs, including file-set changes; never hash generated views."""
    root = Path(root).resolve()
    paths = []
    for directory in DATASET_DIRECTORIES:
        paths.extend(
            managed_path(root, p.relative_to(root))
            for p in managed_path(root, directory).rglob('*')
            if p.is_symlink() or (p.is_file() and not p.name.endswith('.lock'))
        )
    fingerprints = []
    for path in sorted(paths):
        with path.open('rb') as stream:
            fingerprints.append(
                (str(path.relative_to(root)), hashlib.file_digest(stream, 'sha256').hexdigest())
            )
    return digest(json.dumps(fingerprints).encode())


def build_snapshot(root):
    root = Path(root).resolve()
    store = load_store(root / 'graph', allow_empty=True)
    bindings = {source.value: target.value for source, target in identity_bindings(store).items()}
    records = entries(store)
    labels = _labels(store, records)
    add_note_sources(root, store, store, labels)
    # Label overlays also apply to associated entities without active claims. Use
    # the existing verifier rather than reading presentation profiles independently.
    name_records = [
        {
            'subject': {'id': id, 'label': sorted(names)[0]},
            'object': {'id': id, 'label': sorted(names)[0]},
        }
        for id, names in labels.items()
        if names
    ]
    displayed, labels = apply_entity_labels(root, store, records + name_records, labels)
    preferred = {
        r['subject']['id']: r['subject']['label']
        for r in displayed[len(records) :]
        if 'original_label' in r['subject']
    }
    records = displayed[: len(records)]
    records = annotate_accounts(root, store, records)
    payload = curated_notes(root, store, [], include_all=True)
    reader = _Evidence(root, store)
    notes, entities, bodies, sources, relations, claims = {}, {}, {}, {}, [], {}
    registry = _registry(root)

    def body_record(text, sha, format=None):
        record = bodies.setdefault(sha, {'text': text, 'html': {}})
        if format and format not in record['html']:
            record['html'][format] = render_markup(text, format)
        return sha

    def source_record(revision, evidence_reader=reader):
        if revision in sources:
            return sources[revision]
        text, verified = evidence_reader.revision(revision)
        native = verified.get('native_note') or {}
        record = {key: value for key, value in verified.items() if key != 'native_note'}
        record.update(
            title=native.get('title') or Path(verified['snapshot']).name,
            author=native.get('author'),
            note=native.get('id'),
            format=native.get('format'),
            body=body_record(text, verified['text_sha256'], native.get('format')),
            derivation=native.get('derivation'),
        )
        sources[revision] = record
        for pin in (native.get('derivation') or {}).get('sources', []):
            source_record(pin['revision'], evidence_reader)
        return record

    def entity(id, label=None, types=(), qualification=None):
        id = bindings.get(id, id)
        record = entities.setdefault(
            id,
            {
                'id': id,
                'title': preferred.get(id) or label or sorted(labels.get(id) or [id])[0],
                'types': [],
                'aliases': sorted(labels.get(id) or []),
                'typing': [],
                'themes': [],
            },
        )
        record['types'] = sorted(set(record['types']) | set(types))
        if qualification and qualification not in record['typing']:
            record['typing'].append(qualification)
        return record

    for id, current in payload['notes'].items():
        header = json.loads(one(store, current['revision'], VOCAB + 'noteMetadata').value)
        history = _history(root, id, registry)
        source = source_record(current['revision'])
        notes[id] = {k: v for k, v in current.items() if k != 'body'}
        notes[id].update(
            body=source['body'],
            format=header['format'],
            created_at=header['created_at'],
            modified_at=header['modified_at'],
            agent=header['agent'],
            reason=header['reason'],
            history=[
                {
                    k: r[k]
                    for k in (
                        'revision',
                        'parent',
                        'body_sha256',
                        'modified_at',
                        'author',
                        'agent',
                        'reason',
                        'title',
                        'format',
                    )
                }
                for r in history
            ],
        )
        for link in current['navigation']['links']:
            relations.append(
                {
                    'id': 'link:' + id + ':' + link['note'],
                    'from': id,
                    'to': link['note'],
                    'kind': 'link',
                    'label': 'links to',
                    'reason': link['reason'],
                    'revision': current['revision'],
                }
            )
        for target in current['entities']:
            if target not in notes and target not in payload['notes']:
                entity(target)
            if target != id:
                relations.append(
                    {
                        'id': 'association:' + id + ':' + target,
                        'from': id,
                        'to': target,
                        'kind': 'association',
                        'label': 'about',
                        'revision': current['revision'],
                        'reason': 'Author-declared note association; not claim acceptance.',
                    }
                )
        for declaration in current['navigation']['declarations']:
            item = entity(
                declaration['id'],
                declaration['label'],
                [declaration['type']],
                {'origin': 'AuthorDeclared', 'status': 'Unreviewed', 'note': id},
            )
            item['declaration'] = {**declaration, 'note': id, 'revision': current['revision']}

    def evidence(aid, evidence_reader):
        pins = []
        for item in values(evidence_reader.store, aid, DERIVED):
            quote, source = evidence_reader.citation(item.value)
            source_record(source['revision'], evidence_reader)
            pins.append(
                {
                    'id': item.value,
                    'revision': source['revision'],
                    'quote': quote,
                    'sha256': source['sha256'],
                    'text_sha256': source['text_sha256'],
                    'locator': source['locator'],
                }
            )
        return pins

    for record in records:
        aid = record['id']
        record['evidence'] = evidence(aid, reader)
        record['lifecycle'] = 'Active'
        term = next(store.quads_for_pattern(None, None, None, NamedNode(aid))).object
        if record['object']['literal']:
            record['object'].update(
                datatype=term.datatype.value, language=term.language, value=term.value
            )
        for endpoint in ('subject', 'object'):
            item = record[endpoint]
            if not item.get('literal') and item['id'] not in notes:
                e = entity(item['id'], item['label'], item['types'], record['classification'])
                for theme in record['themes']:
                    membership = {**theme, 'claim': aid}
                    if membership not in e['themes']:
                        e['themes'].append(membership)
        claims[aid] = record
        if not record['object']['literal']:
            relations.append(
                {
                    'id': aid,
                    'from': record['subject']['id'],
                    'to': record['object']['id'],
                    'kind': 'claim',
                    'label': local_name(record['predicate']),
                    'status': record['status'],
                    'origin': record['origin'],
                    'themes': record['themes'],
                    'knowledge_kind': record['kind'],
                }
            )

    # Include declared RDF entities even without active edges; never turn literals or
    # provenance resources into identities merely to populate the navigation tree.
    for quad in store.quads_for_pattern(None, NamedNode(RDF_TYPE), None, META):
        type = local_name(quad.object.value)
        if type in TYPES and type != 'Document' and quad.subject.value not in notes:
            names = values(store, quad.subject.value, LABEL)
            if names:
                entity(
                    quad.subject.value,
                    names[0].value,
                    [type],
                    {'origin': 'RecordedType', 'status': 'Unreviewed'},
                )

    events = [{k: v for k, v in event.items() if k != 'store'} for event in read_events(root)]
    historical = {}
    if events:
        history_store = load_store(root / 'graph', history=True, allow_empty=True)
        add_note_sources(root, history_store, history_store, {})
        history_reader = _Evidence(root, history_store)
        for aid in {e['target'] for e in events} | {
            e['replacement_id'] for e in events if 'replacement_id' in e
        }:
            triple = next(history_store.quads_for_pattern(None, None, None, NamedNode(aid)))
            historical[aid] = {
                'id': aid,
                'subject': triple.subject.value,
                'predicate': triple.predicate.value,
                'object': triple.object.value,
                # Historical evidence retains original endpoints. These additional
                # display keys let current canonical entities navigate that history.
                'display_subject': bindings.get(triple.subject.value, triple.subject.value),
                'display_object': bindings.get(triple.object.value, triple.object.value)
                if isinstance(triple.object, NamedNode)
                else None,
                **{
                    key: one(history_store, aid, VOCAB + pred).value
                    for key, pred in [
                        ('subject_label', 'subjectLabel'),
                        ('object_label', 'objectLabel'),
                        ('status', 'reviewStatus'),
                        ('lifecycle', 'lifecycle'),
                        ('origin', 'origin'),
                        ('rationale', 'rationale'),
                    ]
                },
                'evidence': evidence(aid, history_reader),
            }

    for item in entities.values():
        item['types'] = [t for t in item['types'] if t != 'Entity'] or ['Entity']
    themes = {t['id']: t for t in read_catalogue(root)['themes']}
    for note in notes.values():
        for theme in note['navigation']['themes']:
            themes.setdefault(theme['id'], {'id': theme['id'], 'label': theme['label']})
    for claim in claims.values():
        for theme in claim['themes']:
            themes.setdefault(theme['id'], {'id': theme['id'], 'label': theme['label']})
    return {
        'manifest': {
            'schema_version': 1,
            'generated_at': datetime.now(timezone.utc).isoformat(),
            'boundary': 'owner-local; all included content is disclosed',
            'history': 'Current and cited bodies; other historical bodies are not included.',
            'counts': {'notes': len(notes), 'entities': len(entities), 'claims': len(claims)},
        },
        'notes': notes,
        'entities': entities,
        'bodies': bodies,
        'sources': sources,
        'claims': claims,
        'relations': relations,
        'themes': list(themes.values()),
        'reviews': events,
        'historical_claims': historical,
    }
