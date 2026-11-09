"""Versioned, author-declared note navigation and source-backed referents."""

import re
from pathlib import Path
from uuid import UUID

from knot.graph.rdf import DERIVED, LABEL, RDF_TYPE, VOCAB


def theme_choices(root):
    from knot.writing.themes import read_catalogue

    return read_catalogue(root)['themes']


def validate_navigation(value, body=None):
    from knot.shared.vocabulary import TYPES
    from knot.writing.notes import _note_id

    if not isinstance(value, dict) or set(value) != {'themes', 'links', 'declarations'}:
        raise ValueError('Navigation requires themes, links and declarations')
    if any(not isinstance(items, list) for items in value.values()):
        raise ValueError('Navigation fields must be lists')
    for theme in value['themes']:
        if (
            not isinstance(theme, dict)
            or set(theme) != {'id', 'label'}
            or not isinstance(theme['id'], str)
            or not re.fullmatch('[a-z][a-z0-9-]*', theme['id'])
            or not isinstance(theme['label'], str)
            or not theme['label'].strip()
        ):
            raise ValueError('Invalid theme selection')
    for link in value['links']:
        if (
            not isinstance(link, dict)
            or set(link) != {'note', 'reason'}
            or not isinstance(link['reason'], str)
            or not link['reason'].strip()
        ):
            raise ValueError('Note links need a target and explanation')
        _note_id(link['note'])
    for entity in value['declarations']:
        if not isinstance(entity, dict) or set(entity) != {
            'id',
            'label',
            'type',
            'quote',
            'offset',
        }:
            raise ValueError('Invalid entity declaration')
        if not isinstance(entity['id'], str) or not entity['id'].startswith('urn:knot:entity:'):
            raise ValueError('Invalid declared entity identifier')
        if str(UUID(entity['id'].removeprefix('urn:knot:entity:'))) != entity['id'][16:]:
            raise ValueError('Invalid declared entity UUID')
        if (
            entity['type'] not in TYPES
            or not isinstance(entity['label'], str)
            or not entity['label'].strip()
        ):
            raise ValueError('Entity needs a name and supported type')
        if (
            not isinstance(entity['quote'], str)
            or not entity['quote']
            or type(entity['offset']) is not int
            or entity['offset'] < 0
        ):
            raise ValueError('Entity declaration needs exact source text and offset')
        if (
            body is not None
            and body[entity['offset'] : entity['offset'] + len(entity['quote'])] != entity['quote']
        ):
            raise ValueError('Entity quotation does not match note text')
    for field, key in (('themes', 'id'), ('links', 'note'), ('declarations', 'id')):
        ids = [item[key] for item in value[field]]
        if len(ids) != len(set(ids)):
            raise ValueError('Duplicate navigation selection')


def validate_selection(root, value, body, *, previous=None):
    from pyoxigraph import NamedNode

    from knot.graph.query import load_store
    from knot.writing.notes import list_notes, read_note

    validate_navigation(value, body)
    catalogue = {t['id']: t['label'] for t in theme_choices(root)}
    for theme in value['themes']:
        if (
            theme not in (previous or {}).get('themes', [])
            and catalogue.get(theme['id']) != theme['label']
        ):
            raise ValueError('Select an existing theme from the catalogue')
    for link in value['links']:
        read_note(root, link['note'])
    existing = {
        e['id'] for n in list_notes(root) for e in n.get('navigation', {}).get('declarations', [])
    }
    retained = {e['id']: e for e in (previous or {}).get('declarations', [])}
    store = load_store(Path(root) / 'graph', include_notes=False, allow_empty=True)
    for entity in value['declarations']:
        if entity['id'] in existing and retained.get(entity['id']) != entity:
            raise ValueError('Entity identifier already declared; reuse its association')
        if entity['id'] not in retained and any(
            store.quads_for_pattern(NamedNode(entity['id']), None, None, None)
        ):
            raise ValueError('Entity identifier already exists in the graph; select it instead')


def project_navigation(dataset, saved, subject, graph, *, bindings=None):
    from pyoxigraph import NamedNode

    navigation = saved.get('navigation', {})
    for theme in navigation.get('themes', []):
        tid = 'urn:knot:theme:' + theme['id']
        dataset.add(subject, VOCAB + 'theme', tid, graph=graph)
        dataset.add(tid, LABEL, theme['label'], literal=True, graph=graph)
        dataset.add(tid, RDF_TYPE, VOCAB + 'Theme', graph=graph)
    for index, link in enumerate(navigation.get('links', [])):
        lid = saved['revision'] + ':link:' + str(index)
        dataset.add(subject, VOCAB + 'linkedNote', link['note'], graph=graph)
        dataset.add(subject, VOCAB + 'noteLink', lid, graph=graph)
        dataset.add(lid, VOCAB + 'linkedNote', link['note'], graph=graph)
        dataset.add(lid, VOCAB + 'rationale', link['reason'], literal=True, graph=graph)
    for entity in navigation.get('declarations', []):
        original = NamedNode(entity['id'])
        eid = (bindings or {}).get(original, original).value
        dataset.add(eid, LABEL, entity['label'], literal=True, graph=graph)
        dataset.add(eid, RDF_TYPE, VOCAB + entity['type'], graph=graph)
        dataset.add(eid, DERIVED, saved['revision'], graph=graph)
        dataset.add(eid, VOCAB + 'reviewStatus', VOCAB + 'Unreviewed', graph=graph)
        dataset.add(eid, VOCAB + 'quote', entity['quote'], literal=True, graph=graph)
        dataset.add(eid, VOCAB + 'characterOffset', entity['offset'], literal=True, graph=graph)
        dataset.add(subject, VOCAB + 'associatedEntity', eid, graph=graph)
