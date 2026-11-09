"""Initialise or select local datasets, optionally cloned using the user's Git setup."""

import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from urllib.parse import urlsplit

from knot.shared.datasets import config_path, read_config
from knot.shared.storage import atomic_json, managed_path, validate_dataset_paths

TRANSIENTS = ('drafts/', 'views/', '.local-runtime/', 'notes/.lock', 'reviews/.lock')


def is_dataset(root):
    root = Path(root).resolve()
    marker = managed_path(root, 'knot.json')
    if marker.exists():
        if json.loads(marker.read_text()) != {'schema_version': 1}:
            raise ValueError('Unsupported dataset marker')
        return True
    return managed_path(root, 'notes/registry.json').is_file() or any(
        managed_path(root, 'graph').glob('*.trig')
    )


def select(root):
    root = validate_dataset_paths(Path(root).expanduser())
    if not root.is_dir() or not is_dataset(root):
        raise ValueError(
            'Not a KNOT dataset; initialise an empty folder with knot dataset init PATH'
        )
    config = {**read_config(), 'schema_version': 1, 'data_root': str(root)}
    atomic_json(config_path(), config)
    return root


def initialise(root):
    root = validate_dataset_paths(Path(root).expanduser())
    if root.exists():
        if not root.is_dir():
            raise ValueError('Dataset path must be a directory')
        if is_dataset(root):
            return root
        permitted = {'.git', '.gitignore', '.gitattributes', 'README.md', 'LICENSE'}
        if any(p.name not in permitted for p in root.iterdir()):
            raise ValueError('Refusing to initialise a nonempty folder that is not a KNOT dataset')
        if any(p.is_symlink() for p in root.iterdir()):
            raise ValueError('Refusing to initialise through existing symlinks')
    root.mkdir(parents=True, exist_ok=True)
    for name, additions in (
        ('.gitignore', ''.join('/' + name + '\n' for name in TRANSIENTS)),
        ('.gitattributes', '* -text\n'),
    ):
        path = root / name
        previous = path.read_text() if path.exists() else ''
        path.write_text(
            previous + ('\n' if previous and not previous.endswith('\n') else '') + additions
        )
    atomic_json(
        root / 'organisation/catalogue.json', {'themes': [], 'entity_types': {}, 'overrides': {}}
    )
    from knot.graph.knowledge import rebuild

    rebuild(root)
    atomic_json(root / 'knot.json', {'schema_version': 1})
    return root


def clone(url, destination=None):
    if not url or url.startswith('-') or '\n' in url or '\r' in url:
        raise ValueError('Supply a Git URL or local repository path')
    parsed = urlsplit(url)
    scp = re.fullmatch(r'(?:[\w.-]+@)?[\w.-]+:[^\s]+', url)
    local = Path(url).expanduser().exists()
    if not local and not (
        parsed.scheme in {'https', 'http', 'ssh', 'git', 'file'} or (scp and '::' not in url)
    ):
        raise ValueError('Unsupported Git transport; use HTTPS, SSH or a local repository')
    if parsed.scheme in {'https', 'http'} and (
        parsed.username or parsed.password or parsed.query or parsed.fragment
    ):
        raise ValueError('Use Git credentials or SSH; do not embed credentials in a URL')
    if local:
        url = str(Path(url).expanduser().resolve())
    if destination is None:
        name = re.sub(r'[^\w.-]', '-', url.rstrip('/').rsplit('/', 1)[-1].rsplit(':', 1)[-1])
        name = name.removesuffix('.git').strip('.') or 'dataset'
        home = Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share'))
        destination = home / 'knot/datasets' / name
    destination = Path(destination).expanduser().absolute()
    if destination.exists() or destination.is_symlink():
        raise ValueError(
            'Clone destination already exists; use knot dataset use PATH for an existing dataset'
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Reserve this directory: cleanup must never remove a pre-existing destination.
    destination.mkdir()
    try:
        result = subprocess.run(
            [
                'git',
                '-c',
                'protocol.ext.allow=never',
                'clone',
                '--no-recurse-submodules',
                '--',
                url,
                str(destination),
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode:
            raise ValueError(
                'Git clone failed; check the repository URL, access and Git authentication'
            )
        return initialise(destination)
    except BaseException:
        shutil.rmtree(destination)
        raise
