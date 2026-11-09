"""Shared dataset path checks, byte hashing and atomic JSON publication."""

import hashlib
import json
import tempfile
from pathlib import Path


def managed_path(root, relative):
    """Resolve the chosen root, but never follow redirects inside a dataset."""
    root, relative = Path(root).resolve(), Path(relative)
    path = root / relative
    try:
        if relative.is_absolute() or '..' in relative.parts or path.resolve() != path:
            raise ValueError('Unsafe dataset path: managed files cannot use symlinks or traversal')
    except (OSError, RuntimeError) as error:
        raise ValueError('Unsafe dataset path') from error
    return path


DATASET_DIRECTORIES = (
    'graph',
    'notes',
    'sources',
    'reviews',
    'organisation',
    'curation',
    'migration',
)


def validate_dataset_paths(root):
    """Check admission/refresh metadata without reading file contents or Git internals."""
    root = Path(root).resolve()
    for name in ('drafts', 'views'):
        managed_path(root, name)
    for name in ('knot.json', '.gitignore', '.gitattributes', *DATASET_DIRECTORIES):
        path = managed_path(root, name)
        if path.is_dir():
            for child in path.rglob('*'):
                managed_path(root, child.relative_to(root))
    return root


def digest(data):
    return hashlib.sha256(data).hexdigest()


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, delete=False) as file:
        temporary = Path(file.name)
        json.dump(value, file, indent=2, ensure_ascii=False)
        file.write('\n')
    try:
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
