import json
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile, ZipInfo

from knot.inventory import build_inventory


class InventoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'sources').mkdir()

    def archive(self, name, entries):
        path = self.root / 'sources' / name
        with ZipFile(path, 'w') as archive:
            for member, content in entries:
                archive.writestr(member, content)
        return path

    def test_duplicates_revisions_and_idempotency(self):
        self.archive('weeknotes.zip', [('weeknotes/a.org', 'same'), ('weeknotes/b.org', 'old')])
        self.archive('g7.zip', [('g7/weeknotes/a.org', 'same'), ('g7/weeknotes/b.org', 'new')])
        first = build_inventory(self.root)
        self.assertEqual(first['summary']['files'], 4)
        self.assertEqual(first['summary']['unique_contents'], 3)
        self.assertEqual(first['summary']['duplicate_occurrences'], 1)
        self.assertEqual(first['summary']['documents_with_multiple_revisions'], 1)
        self.assertEqual(first, build_inventory(self.root))
        for entry in first['entries']:
            self.assertEqual(entry['migration_status'], 'pending')
            self.assertTrue((self.root / entry['snapshot']).is_file())

    def test_unsafe_members_are_recorded_without_extraction(self):
        link = ZipInfo('links.org')
        link.create_system = 3
        link.external_attr = 0o120777 << 16
        self.archive(
            'bad.zip', [('../escape.org', 'bad'), (link, '/etc/passwd'), ('safe.org', 'safe')]
        )
        result = build_inventory(self.root)
        self.assertEqual(result['summary']['errors'], 2)
        self.assertFalse((self.root / 'escape.org').exists())
        self.assertEqual(len(result['entries']), 3)
        self.assertEqual(json.loads((self.root / 'migration/inventory.json').read_text()), result)

    def test_size_limit_and_corrupted_existing_snapshot(self):
        self.archive('one.zip', [('one.org', 'hello')])
        rejected = build_inventory(self.root, max_member_bytes=4)
        self.assertEqual(rejected['summary']['errors'], 1)
        good = build_inventory(self.root)
        (self.root / good['entries'][0]['snapshot']).write_text('tampered')
        result = build_inventory(self.root)
        self.assertEqual(result['summary']['errors'], 1)
        self.assertIn('hash', result['entries'][0]['error'])

    def test_directory_and_unsupported_extension_are_accounted_for(self):
        self.archive('other.zip', [('folder/', ''), ('folder/file.pdf', b'%PDF-data')])
        result = build_inventory(self.root)
        self.assertEqual(result['summary']['members'], 2)
        self.assertEqual(result['summary']['files'], 1)
        self.assertEqual(result['entries'][0]['status'], 'directory')
        self.assertEqual(result['entries'][1]['extension'], '.pdf')

    def test_retired_archive_preserves_occurrences_and_accepts_new_sources(self):
        archive = self.archive('old.zip', [('folder/', ''), ('folder/note.org', 'same')])
        retired = build_inventory(self.root)
        retired['archives'][0]['retired'] = True
        ledger = self.root / 'migration/inventory.json'
        ledger.write_text(json.dumps(retired))
        archive.unlink()
        self.assertEqual(build_inventory(self.root), retired)
        self.archive('new.zip', [('new.org', 'same')])
        result = build_inventory(self.root)
        self.assertEqual(result['summary']['archives'], 2)
        self.assertEqual(result['summary']['verified_files'], 2)
        self.assertEqual(result['summary']['duplicate_occurrences'], 1)
        self.assertEqual(result, build_inventory(self.root))

    def test_missing_archive_does_not_erase_inventory(self):
        archive = self.archive('one.zip', [('one.org', 'hello')])
        build_inventory(self.root)
        ledger = self.root / 'migration/inventory.json'
        original = ledger.read_bytes()
        archive.unlink()
        with self.assertRaisesRegex(ValueError, 'Archive missing'):
            build_inventory(self.root)
        self.assertEqual(ledger.read_bytes(), original)

    def test_retired_archive_requires_intact_snapshots(self):
        archive = self.archive('one.zip', [('one.org', 'hello')])
        retired = build_inventory(self.root)
        retired['archives'][0]['retired'] = True
        ledger = self.root / 'migration/inventory.json'
        ledger.write_text(json.dumps(retired))
        original = ledger.read_bytes()
        archive.unlink()
        snapshot = self.root / retired['entries'][0]['snapshot']
        for content in ('tampered', None):
            with self.subTest(content=content):
                if content is None:
                    snapshot.unlink()
                else:
                    snapshot.write_text(content)
                with self.assertRaisesRegex(ValueError, 'Snapshot'):
                    build_inventory(self.root)
                self.assertEqual(ledger.read_bytes(), original)

    def test_retirement_does_not_skip_verification_of_a_present_archive(self):
        archive = self.archive('one.zip', [('one.org', 'hello')])
        retired = build_inventory(self.root)
        retired['archives'][0]['retired'] = True
        ledger = self.root / 'migration/inventory.json'
        ledger.write_text(json.dumps(retired))
        self.assertEqual(build_inventory(self.root), retired)
        original = ledger.read_bytes()
        archive.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'Retired archive changed'):
            build_inventory(self.root)
        self.assertEqual(ledger.read_bytes(), original)


if __name__ == '__main__':
    unittest.main()
