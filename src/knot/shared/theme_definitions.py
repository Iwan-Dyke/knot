"""Validate dataset-owned knowledge themes without assigning memberships."""

import re


def validate_themes(themes):
    if not isinstance(themes, list):
        raise ValueError('Knowledge themes must be a list of definitions')
    seen = set()
    for theme in themes:
        if not isinstance(theme, dict) or set(theme) - {
            'id',
            'label',
            'description',
            'keywords',
            'include_frameworks',
        }:
            raise ValueError('Invalid knowledge theme fields')
        slug = theme.get('id')
        if not isinstance(slug, str) or not re.fullmatch(r'[a-z][a-z0-9-]*', slug) or slug in seen:
            raise ValueError('Theme identifiers must be unique lowercase slugs')
        seen.add(slug)
        if not isinstance(theme.get('label'), str) or not theme['label'].strip():
            raise ValueError('Theme labels cannot be empty')
        words = theme.get('keywords', [])
        if not isinstance(words, list) or any(
            not isinstance(w, str) or not w.strip() for w in words
        ):
            raise ValueError('Theme keywords must be a list of nonempty strings')
        if not isinstance(theme.get('description', ''), str):
            raise ValueError('Theme description must be text')
        if type(theme.get('include_frameworks', False)) is not bool:
            raise ValueError('Theme include_frameworks must be a boolean')
