"""Resolve a dataset explicitly, without depending on the application's location."""

import json
import os
from pathlib import Path


def config_path():
    if os.environ.get('KNOT_CONFIG'):
        return Path(os.environ['KNOT_CONFIG']).expanduser()
    return Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / 'knot/config.json'


def read_config():
    path = config_path()
    if not path.exists():
        return {}
    try:
        config = json.loads(path.read_text(encoding='utf-8'))
        if (
            not isinstance(config, dict)
            or config.get('schema_version') != 1
            or (
                'data_root' in config
                and (
                    not isinstance(config['data_root'], str)
                    or not Path(config['data_root']).is_absolute()
                )
            )
            or (
                'visual_theme' in config
                and (
                    not isinstance(config['visual_theme'], str)
                    or not config['visual_theme'].strip()
                )
            )
        ):
            raise ValueError('Invalid configuration')
        return config
    except (ValueError, TypeError) as error:
        raise ValueError(
            'Invalid KNOT configuration; repair it before selecting a dataset'
        ) from error


def resolve_data_root(explicit=None):
    if explicit is not None:
        # Explicit paths retain API/CLI support for first-note creation.
        return Path(explicit).expanduser().resolve()
    selected = os.environ.get('KNOT_DATA_ROOT') or read_config().get('data_root')
    if not selected:
        raise ValueError('No dataset selected. Run knot dataset init PATH, use PATH or clone URL')
    root = Path(selected).expanduser().resolve()
    if not root.is_dir():
        raise ValueError(
            'Selected dataset is missing; use knot dataset use PATH to select it again'
        )
    return root


def cli_data_root(parser, explicit=None):
    try:
        return resolve_data_root(explicit)
    except (ValueError, OSError) as error:
        parser.error(str(error))
