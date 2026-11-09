"""Copy the tool into a fresh directory without datasets or Git history."""

import argparse
import shutil
from pathlib import Path

FILES = (
    '.gitattributes',
    '.gitignore',
    'AGENTS.md',
    'CONTRIBUTING.md',
    'LICENSE',
    'LICENSE_SCOPE.txt',
    'README.md',
    'THIRD_PARTY_NOTICES.txt',
    'install.sh',
    'justfile',
    'knot',
    'pyproject.toml',
)
DIRECTORIES = (
    'src/knot',
    'tests',
    'scripts',
    'queries',
    'docs',
    'design_decisions',
    'data-examples',
)


def export_code(root, destination):
    root, destination = Path(root).resolve(), Path(destination).absolute()
    if destination.resolve().is_relative_to(root):
        raise ValueError('Export destination must be outside the source checkout')
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(f'Export destination already exists: {destination}')
    paths = [root / name for name in FILES]
    for name in DIRECTORIES:
        directory = root / name
        for ancestor in (directory, *directory.parents):
            if ancestor == root:
                break
            if ancestor.is_symlink():
                raise ValueError(f'Cannot export symlink: {ancestor.relative_to(root)}')
        paths.append(directory)
        paths.extend(sorted(directory.rglob('*')))
    selected = []
    for path in paths:
        relative = path.relative_to(root)
        if '__pycache__' in relative.parts or path.suffix in ('.pyc', '.pyo'):
            continue
        if any(part.startswith('.') for part in relative.parts) and str(relative) not in FILES:
            continue
        # A link inside an allowed directory must not pull in private storage.
        if path.is_symlink():
            raise ValueError(f'Cannot export symlink: {relative}')
        if path.is_file():
            selected.append((path, relative))
    destination.mkdir(parents=True)
    for path, relative in selected:
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
    return len(selected)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    try:
        count = export_code(Path(__file__).resolve().parents[1], args.destination)
    except (ValueError, OSError) as error:
        parser.exit(1, f'{error}\n')
    print(f'Exported {count} tool files to {args.destination.resolve()}')


if __name__ == '__main__':
    main()
