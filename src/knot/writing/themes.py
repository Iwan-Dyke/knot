"""Add topic definitions without replacing existing meanings or review decisions."""

import json

from knot.shared.storage import atomic_json, managed_path
from knot.shared.theme_definitions import validate_themes


def read_catalogue(root):
    path = managed_path(root, 'organisation/catalogue.json')
    catalogue = (
        json.loads(path.read_bytes())
        if path.exists()
        else {
            'themes': [],
            'entity_types': {},
            'overrides': {},
        }
    )
    if not isinstance(catalogue, dict):
        raise ValueError('Organisation catalogue must be an object')
    validate_themes(catalogue.get('themes'))
    return catalogue


def add_themes(root, definitions):
    validate_themes(definitions)
    catalogue = read_catalogue(root)
    existing = {theme['id']: theme for theme in catalogue['themes']}
    additions = []
    for theme in definitions:
        if theme['id'] in existing:
            if existing[theme['id']] != theme:
                raise ValueError(f'Theme already exists with a different definition: {theme["id"]}')
        else:
            additions.append(theme)
    if additions:
        catalogue['themes'].extend(additions)
        atomic_json(managed_path(root, 'organisation/catalogue.json'), catalogue)
    return catalogue['themes']
