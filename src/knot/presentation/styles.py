"""Declarative palettes shared by the offline page and canvas graph."""

import json
import re
from pathlib import Path

from knot.shared.datasets import config_path, read_config
from knot.shared.storage import atomic_json

THEMES = Path(__file__).with_name('themes')
DEFAULT = json.loads((THEMES / 'matrix.json').read_text())
SLUG = r'[a-z][a-z0-9-]*'


def theme_directory():
    return config_path().parent.resolve() / 'themes'


def theme_paths():
    paths = {}
    # Bundled names stay stable; CSS takes precedence when a custom name has both formats.
    for directory in (theme_directory(), THEMES):
        for extension in ('json', 'css'):
            for path in sorted(directory.glob(f'*.{extension}')):
                if path.is_file() and re.fullmatch(SLUG, path.stem):
                    paths[path.stem] = path
    return paths


def selected_theme():
    return read_config().get('visual_theme', 'matrix')


def theme_path(selector):
    return theme_paths().get(selector, Path(selector).expanduser())


def select_theme(selector):
    config = read_config()
    load_theme(selector)
    selected = selector if selector in theme_paths() else str(theme_path(selector).resolve())
    atomic_json(config_path(), {**config, 'schema_version': 1, 'visual_theme': selected})
    return selected


def create_theme(name, source='matrix'):
    if not re.fullmatch(SLUG, name):
        raise ValueError('Theme name must be a lowercase slug')
    if name in theme_paths():
        raise ValueError(f'Theme already exists: {name}')
    theme = load_theme(source)
    path = theme_directory() / f'{name}.css'
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as file:
        file.write('/* Edit this palette, then select it with knot theme use. */\n')
        file.write(stylesheet(theme))
    return path


def _css_theme(text, path):
    text = re.sub(r'/\*.*?\*/', '', text, flags=re.S)
    block = re.fullmatch(r'\s*:root\s*\{([^{}]*)\}\s*', text, flags=re.S)
    if block is None:
        raise ValueError('CSS themes require one :root block of colour and font variables')
    supplied = {
        'schema_version': 1,
        'name': path.stem.replace('-', ' ').title(),
        'colors': {},
        'fonts': {},
    }
    seen = set()
    for declaration in block[1].split(';'):
        if not declaration.strip():
            continue
        key, separator, value = declaration.partition(':')
        key, value = key.strip(), value.strip()
        if not separator or key in seen:
            raise ValueError('Invalid or duplicate CSS theme declaration')
        seen.add(key)
        if key == 'color-scheme':
            supplied['color_scheme'] = value
        elif key.startswith('--font-'):
            supplied['fonts'][key.removeprefix('--font-')] = value
        elif key.startswith('--'):
            supplied['colors'][key.removeprefix('--')] = value
        else:
            raise ValueError(f'Unsupported CSS theme property: {key}')
    return supplied


def load_theme(selector='matrix'):
    path = theme_path(selector)
    try:
        text = path.read_text(encoding='utf-8')
        supplied = _css_theme(text, path) if path.suffix == '.css' else json.loads(text)
    except (OSError, ValueError) as error:
        raise ValueError(f'Cannot read visual theme {selector}: {error}') from error
    if (
        not isinstance(supplied, dict)
        or set(supplied) - set(DEFAULT)
        or type(supplied.get('schema_version')) is not int
        or supplied['schema_version'] != 1
        or not isinstance(supplied.get('name'), str)
        or not supplied['name'].strip()
        or supplied.get('color_scheme', 'dark') not in ('dark', 'light')
    ):
        raise ValueError('Visual theme requires schema_version 1, a name and supported fields')
    result = {**DEFAULT, **supplied}
    for section in ('colors', 'fonts'):
        overrides = supplied.get(section, {})
        if not isinstance(overrides, dict) or set(overrides) - set(DEFAULT[section]):
            raise ValueError(f'Unknown or invalid visual theme {section}')
        result[section] = {**DEFAULT[section], **overrides}
        for key, value in result[section].items():
            # Values are embedded into CSS; arbitrary CSS and remote assets are not palettes.
            family = r"""(?:[\w-]+(?: +[\w-]+)*|'[\w -]+'|"[\w -]+")"""
            pattern = (
                r'#(?:[0-9a-fA-F]{3,4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})'
                if section == 'colors'
                else family + r'(?:, *' + family + r')*'
            )
            if not isinstance(value, str) or not value.strip() or not re.fullmatch(pattern, value):
                raise ValueError(f'Invalid visual theme {section}.{key}')
    return result


def stylesheet(theme):
    declarations = [f'color-scheme: {theme["color_scheme"]};']
    declarations.extend(f'--{key}: {value};' for key, value in theme['colors'].items())
    declarations.extend(f'--font-{key}: {value};' for key, value in theme['fonts'].items())
    return ':root {\n  ' + '\n  '.join(declarations) + '\n}\n'


def node_style(role, *, note_role=None, theme=DEFAULT):
    colors, face = theme['colors'], theme['fonts']['graph']
    if role == 'note':
        return {
            'color': colors['entity-note' if note_role == 'entity' else 'note'],
            'font': {'color': colors['note-text'], 'face': face, 'size': 13},
            'shadow': {'enabled': False},
        }
    if role == 'theme':
        return {'color': colors['theme'], 'font': {'color': colors['theme-text'], 'face': face}}
    return {
        'color': {
            'background': colors['entity'],
            'border': colors['accent'],
            'highlight': {'background': colors['text'], 'border': colors['accent']},
        },
        'font': {'color': colors['text'], 'face': face, 'size': 13},
        'shadow': {'enabled': True, 'color': colors['glow'], 'size': 14, 'x': 0, 'y': 0},
    }


def edge_style(edge, theme=DEFAULT):
    colors, face = theme['colors'], theme['fonts']['graph']
    if edge.get('navigation'):
        return {
            'color': colors['navigation'],
            'font': {'color': colors['navigation-text'], 'face': face, 'size': 10},
        }
    if edge.get('organisation'):
        reviewed = set(edge['memberships'].values()) == {'Accepted'}
        return {
            'color': {'color': colors['theme-accepted' if reviewed else 'theme'], 'opacity': 0.4}
        }
    return {
        'color': colors['accepted' if edge.get('status') == 'Accepted' else 'unreviewed'],
        'font': {
            'color': colors['edge-text'],
            'face': face,
            'size': 10,
            'strokeWidth': 3,
            'strokeColor': colors['background'],
        },
    }


def apply_theme(network, theme):
    network.bgcolor = theme['colors']['background']
    for node in network.nodes:
        node.update(node_style(node.get('role'), note_role=node.get('noteRole'), theme=theme))
        for attribute in node.get('attributes', []):
            attribute.update(edge_style(attribute, theme))
    for edge in network.edges:
        edge.update(edge_style(edge, theme))
