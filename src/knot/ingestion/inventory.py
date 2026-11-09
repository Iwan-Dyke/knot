"""Inventory ZIP occurrences and preserve verified source bytes, without conversion."""

import argparse
import json
import stat
from collections import defaultdict
from pathlib import Path, PurePosixPath
from zipfile import BadZipFile, ZipFile

from knot.shared.datasets import cli_data_root
from knot.shared.storage import atomic_json as atomic_json
from knot.shared.storage import digest as digest
from knot.shared.storage import managed_path


def logical_path(archive, member):
    parts = PurePosixPath(member).parts
    # The supplied bundles wrap their content in their archive stem. Weeknotes is
    # also a document namespace shared by both archives, so retain that component.
    if len(parts) > 1 and parts[0] == archive.stem and archive.stem != 'weeknotes':
        parts = parts[1:]
    return '/'.join(parts)


def verify_sources(root, inventory):
    root = Path(root).resolve()
    for archive in inventory['archives']:
        path = managed_path(root, archive['path'])
        if 'error' in archive:
            raise ValueError(f'Unverified archive: {path}')
        if not path.exists():
            if archive.get('retired') is True:
                continue
            raise ValueError(f'Archive missing without retirement record: {path}')
        if digest(path.read_bytes()) != archive['sha256']:
            if archive.get('retired') is True:
                raise ValueError(f'Retired archive changed; use a new archive filename: {path}')
            raise ValueError('Archive changed since inventory; rerun just inventory')
    for entry in inventory['entries']:
        if entry['status'] == 'directory':
            continue
        if entry['status'] != 'verified':
            raise ValueError(f'Unverified source occurrence: {entry["member"]}')
        snapshot = managed_path(root, entry['snapshot'])
        if not snapshot.is_file():
            raise ValueError(f'Snapshot missing: {snapshot}')
        if digest(snapshot.read_bytes()) != entry['sha256']:
            raise ValueError(f'Snapshot hash mismatch: {snapshot}')


def build_inventory(data_root, *, max_member_bytes=100_000_000, max_total_bytes=1_000_000_000):
    root = Path(data_root).resolve()
    managed_path(root, 'sources/revisions')
    entries, archives = [], []
    previous_path = managed_path(root, 'migration/inventory.json')
    if previous_path.exists():
        previous = json.loads(previous_path.read_text())
        for archive in previous['archives']:
            if archive.get('retired') is True:
                archives.append(archive)
                entries.extend(e for e in previous['entries'] if e['archive'] == archive['path'])
            elif not managed_path(root, archive['path']).is_file():
                raise ValueError(f'Archive missing without retirement record: {archive["path"]}')
    # Retiring a ZIP must not remove its occurrences or change assertion provenance.
    verify_sources(root, {'archives': archives, 'entries': entries})
    retired_paths = {archive['path'] for archive in archives}
    total = 0
    for archive_path in sorted(managed_path(root, 'sources').glob('*.zip')):
        archive_path = managed_path(root, archive_path.relative_to(root))
        if archive_path.relative_to(root).as_posix() in retired_paths:
            continue
        archive_hash = digest(archive_path.read_bytes())
        archive_record = {
            'path': archive_path.relative_to(root).as_posix(),
            'sha256': archive_hash,
            'bytes': archive_path.stat().st_size,
        }
        archives.append(archive_record)
        try:
            with ZipFile(archive_path) as archive:
                for index, member in enumerate(archive.infolist()):
                    entry = {
                        'occurrence_id': digest(f'{archive_hash}:{index}'.encode()),
                        'archive': archive_record['path'],
                        'archive_sha256': archive_hash,
                        'member_index': index,
                        'member': member.filename,
                        'bytes': member.file_size,
                        'compressed_bytes': member.compress_size,
                        'status': 'error',
                        'migration_status': 'pending',
                    }
                    entries.append(entry)
                    try:
                        path = PurePosixPath(member.filename)
                        if (
                            not member.filename
                            or path.is_absolute()
                            or '..' in path.parts
                            or '\\' in member.filename
                            or ':' in member.filename
                            or '\x00' in member.filename
                        ):
                            raise ValueError('unsafe member path')
                        mode = member.external_attr >> 16
                        if stat.S_ISLNK(mode):
                            raise ValueError('symbolic link member')
                        if member.flag_bits & 1:
                            raise ValueError('encrypted member')
                        if member.is_dir():
                            entry['status'] = 'directory'
                            entry['migration_status'] = 'not_applicable'
                            continue
                        if member.file_size > max_member_bytes:
                            raise ValueError('member exceeds size limit')
                        total += member.file_size
                        if total > max_total_bytes:
                            raise ValueError('archive collection exceeds total size limit')
                        with archive.open(member) as stream:
                            content = stream.read(max_member_bytes + 1)
                        if len(content) > max_member_bytes or len(content) != member.file_size:
                            raise ValueError('actual member size violates declared size or limit')
                        content_hash = digest(content)
                        snapshot = managed_path(
                            root, Path('sources/revisions') / content_hash / path.name
                        )
                        snapshot.parent.mkdir(parents=True, exist_ok=True)
                        if snapshot.exists():
                            if digest(snapshot.read_bytes()) != content_hash:
                                raise ValueError('existing snapshot hash mismatch')
                        else:
                            with snapshot.open('xb') as file:
                                file.write(content)
                        if digest(snapshot.read_bytes()) != content_hash:
                            raise ValueError('snapshot hash verification failed')
                        entry.update(
                            {
                                'status': 'verified',
                                'logical_path': logical_path(archive_path, member.filename),
                                'sha256': content_hash,
                                'extension': path.suffix.lower(),
                                'snapshot': snapshot.relative_to(root).as_posix(),
                            }
                        )
                    except (ValueError, OSError, BadZipFile, RuntimeError) as error:
                        entry['error'] = str(error)
        except (OSError, BadZipFile) as error:
            archive_record['error'] = str(error)

    archives.sort(key=lambda item: item['path'])
    entries.sort(key=lambda item: (item['archive'], item['member_index']))
    by_content, by_document = defaultdict(list), defaultdict(set)
    for entry in entries:
        if entry['status'] == 'verified':
            by_content[entry['sha256']].append(entry['occurrence_id'])
            by_document[entry['logical_path']].add(entry['sha256'])
    for entry in entries:
        if entry['status'] == 'verified':
            canonical = by_content[entry['sha256']][0]
            entry['duplicate_of'] = canonical if canonical != entry['occurrence_id'] else None
            entry['document_revision_count'] = len(by_document[entry['logical_path']])
    result = {
        'schema_version': 1,
        'stage': 'source_inventory',
        'archives': archives,
        'entries': entries,
        'summary': {
            'archives': len(archives),
            'members': len(entries),
            'files': sum(item['status'] != 'directory' for item in entries),
            'verified_files': sum(item['status'] == 'verified' for item in entries),
            'unique_contents': len(by_content),
            'duplicate_occurrences': sum(len(items) - 1 for items in by_content.values()),
            'documents_with_multiple_revisions': sum(
                len(items) > 1 for items in by_document.values()
            ),
            'errors': sum('error' in item for item in entries + archives),
        },
    }
    atomic_json(managed_path(root, 'migration/inventory.json'), result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-root', type=Path)
    args = parser.parse_args()
    args.data_root = cli_data_root(parser, args.data_root)
    result = build_inventory(args.data_root)
    print(json.dumps(result['summary'], indent=2))
    if not result['archives'] or result['summary']['errors']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
