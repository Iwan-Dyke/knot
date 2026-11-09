import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from unittest.mock import patch

from knot.inventory import digest
from knot.notes import create_note, note_history, read_note, save_note


class NoteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def files(self):
        return {
            p.relative_to(self.root): p.read_bytes() for p in self.root.rglob('*') if p.is_file()
        }

    def test_independent_note_preserves_exact_utf8_without_required_metadata(self):
        body = '# Unfinished thought\r\nλ🙂\r\n\r\nMaybe this is wrong.\n'
        note = create_note(self.root, body)
        self.assertEqual(note['body'], body)
        self.assertIsNone(note['title'])
        self.assertIsNone(note['author'])
        self.assertEqual(note['format'], 'markdown')
        self.assertEqual((self.root / note['body_path']).read_bytes(), body.encode())
        self.assertEqual(note['body_sha256'], digest(body.encode()))
        self.assertEqual(note, read_note(self.root, note['note']))
        self.assertEqual(len(note_history(self.root, note['note'])), 1)
        self.assertFalse((self.root / 'graph').exists())
        self.assertFalse((self.root / 'reviews').exists())

    def test_empty_org_note_and_invalid_inputs(self):
        note = create_note(self.root, b'', format='org')
        self.assertEqual(note['body'], '')
        self.assertEqual(note['format'], 'org')
        before = self.files()
        for arguments in ({'body': b'\xff'}, {'body': 42}, {'format': 'html'}, {'title': []}):
            with self.subTest(arguments=arguments), self.assertRaises(ValueError):
                create_note(self.root, **arguments)
            self.assertEqual(self.files(), before)

    def test_distinct_notes_share_body_storage_without_sharing_identity(self):
        first = create_note(self.root, 'Same writing.', author='Author A')
        second = create_note(self.root, 'Same writing.', author='Author B')
        self.assertNotEqual(first['note'], second['note'])
        self.assertNotEqual(first['revision'], second['revision'])
        self.assertEqual(first['body_path'], second['body_path'])
        self.assertEqual(read_note(self.root, first['note'])['author'], 'Author A')

    def test_body_metadata_and_revert_revisions_preserve_history(self):
        with patch('knot.notes._now', return_value='2026-11-04T12:00:00.000000Z'):
            first = create_note(self.root, 'A hypothesis.', title='First', author='Alex')
            second = save_note(
                self.root, first['note'], 'A conclusion.', expected=first['revision']
            )
            third = save_note(
                self.root,
                first['note'],
                'A conclusion.',
                expected=second['revision'],
                title='Renamed',
            )
            fourth = save_note(
                self.root, first['note'], 'A hypothesis.', expected=third['revision'], title=None
            )
        history = note_history(self.root, first['note'])
        self.assertEqual(
            [r['revision'] for r in history],
            [r['revision'] for r in (first, second, third, fourth)],
        )
        self.assertEqual(len({r['revision'] for r in history}), 4)
        self.assertTrue(all(r['created_at'] == first['created_at'] for r in history))
        self.assertEqual(second['title'], 'First')
        self.assertEqual(third['body_path'], second['body_path'])
        self.assertEqual(fourth['body_path'], first['body_path'])
        self.assertIsNone(fourth['title'])
        self.assertEqual(history[1]['parent'], first['revision'])
        self.assertEqual(read_note(self.root, first['note'], revision=first['revision']), first)

    def test_unchanged_save_is_idempotent_without_changing_time_or_files(self):
        note = create_note(self.root, 'Notes.', title='Title', agent='Editor')
        before = self.files()
        with patch(
            'knot.notes._now', side_effect=AssertionError('Unchanged save needs no timestamp')
        ):
            again = save_note(
                self.root, note['note'], 'Notes.', expected=note['revision'], agent='Editor'
            )
        self.assertEqual(note, again)
        self.assertEqual(self.files(), before)

    def test_revision_time_and_agent_are_separate_from_note_creation_and_author(self):
        with patch('knot.notes._now', return_value='2026-11-04T12:00:00.000000Z'):
            first = create_note(self.root, 'A hypothesis.', author='Alex', agent='Editor A')
        with patch('knot.notes._now', return_value='2026-11-05T09:00:00.000000Z'):
            second = save_note(
                self.root,
                first['note'],
                'A revised hypothesis.',
                expected=first['revision'],
                agent='Editor B',
                reason='New evidence changes my interpretation.',
            )
        self.assertEqual(second['created_at'], first['created_at'])
        self.assertEqual(second['modified_at'], '2026-11-05T09:00:00.000000Z')
        self.assertEqual(second['author'], 'Alex')
        self.assertEqual(second['agent'], 'Editor B')
        self.assertEqual(first['agent'], 'Editor A')
        self.assertIsNone(first['reason'])

    def test_missing_registry_and_existing_corrupt_blob_are_not_reinitialized(self):
        note = create_note(self.root, 'A source.')
        blob = self.root / note['body_path']
        blob.write_bytes(b'Corrupt')
        before = self.files()
        with self.assertRaisesRegex(ValueError, 'hash'):
            create_note(self.root, 'A source.')
        self.assertEqual(self.files(), before)
        (self.root / 'notes/registry.json').unlink()
        before = self.files()
        with self.assertRaisesRegex(ValueError, 'registry missing'):
            create_note(self.root, 'Another source.')
        self.assertEqual(self.files(), before)

    def test_stale_save_fails_before_writing_any_evidence(self):
        first = create_note(self.root, 'First.')
        save_note(self.root, first['note'], 'Second.', expected=first['revision'])
        before = self.files()
        with self.assertRaisesRegex(ValueError, 'head changed'):
            save_note(self.root, first['note'], 'Stale draft.', expected=first['revision'])
        self.assertEqual(self.files(), before)

    def test_concurrent_saves_require_the_current_head(self):
        note = create_note(self.root, 'First.')
        barrier = Barrier(2)

        def update(body):
            barrier.wait(timeout=5)
            try:
                return save_note(self.root, note['note'], body, expected=note['revision'])
            except ValueError as error:
                return str(error)

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(update, ['Draft A.', 'Draft B.']))
        self.assertEqual(sum(isinstance(r, dict) for r in results), 1)
        self.assertTrue(any(isinstance(r, str) and 'head changed' in r for r in results))
        self.assertEqual(len(note_history(self.root, note['note'])), 2)

    def test_failed_head_publication_keeps_previous_history_and_retry_is_safe(self):
        note = create_note(self.root, 'Committed.')
        registry = self.root / 'notes/registry.json'
        before = registry.read_bytes()
        with patch('knot.notes.atomic_json', side_effect=OSError('Interrupted publication')):
            with self.assertRaises(OSError):
                save_note(self.root, note['note'], 'New body.', expected=note['revision'])
        self.assertEqual(registry.read_bytes(), before)
        self.assertEqual(read_note(self.root, note['note']), note)
        self.assertEqual(len(note_history(self.root, note['note'])), 1)
        uncommitted = next(
            p
            for p in (self.root / 'notes/revisions').glob('*.json')
            if p.stem != note['revision'].rsplit(':', 1)[1]
        )
        with self.assertRaisesRegex(ValueError, 'committed history'):
            read_note(
                self.root, note['note'], revision='urn:knot:note-revision:' + uncommitted.stem
            )
        updated = save_note(self.root, note['note'], 'New body.', expected=note['revision'])
        self.assertEqual(updated['parent'], note['revision'])
        self.assertEqual(len(note_history(self.root, note['note'])), 2)

    def test_corrupt_body_and_manifest_fail_without_advancing_the_head(self):
        for target in ('body', 'manifest'):
            with self.subTest(target=target), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                note = create_note(root, 'Verified.')
                registry = (root / 'notes/registry.json').read_bytes()
                path = (
                    root / note['body_path']
                    if target == 'body'
                    else root / 'notes/revisions' / (note['revision'].rsplit(':', 1)[1] + '.json')
                )
                path.write_bytes(b'changed')
                with self.assertRaisesRegex(ValueError, 'hash'):
                    read_note(root, note['note'])
                with self.assertRaises(ValueError):
                    save_note(root, note['note'], 'Next.', expected=note['revision'])
                self.assertEqual((root / 'notes/registry.json').read_bytes(), registry)

    def test_missing_ancestor_and_damaged_registry_fail_explicitly(self):
        note = create_note(self.root, 'First.')
        save_note(self.root, note['note'], 'Second.', expected=note['revision'])
        (self.root / 'notes/revisions' / (note['revision'].rsplit(':', 1)[1] + '.json')).unlink()
        with self.assertRaisesRegex(ValueError, 'missing'):
            note_history(self.root, note['note'])
        registry = self.root / 'notes/registry.json'
        registry.write_text('{')
        before = self.files()
        with self.assertRaises(ValueError):
            create_note(self.root, 'Cannot erase a broken registry.')
        self.assertEqual(self.files(), before)

    def test_unsafe_ids_symlinks_and_other_notes_revisions_are_rejected(self):
        first = create_note(self.root, 'First.')
        other = create_note(self.root, 'Other.')
        with self.assertRaisesRegex(ValueError, 'committed history'):
            read_note(self.root, first['note'], revision=other['revision'])
        for note_id in ('../../outside', 'urn:knot:note:../outside'):
            with self.assertRaises(ValueError):
                read_note(self.root, note_id)
        snapshot = self.root / first['body_path']
        with tempfile.TemporaryDirectory() as directory:
            external = Path(directory) / 'body.txt'
            external.write_bytes(snapshot.read_bytes())
            snapshot.unlink()
            snapshot.symlink_to(external)
            with self.assertRaisesRegex(ValueError, 'Unsafe'):
                read_note(self.root, first['note'])

    def test_existing_graph_reviews_and_source_files_are_untouched(self):
        for path in ('graph/existing.trig', 'reviews/events/existing.trig', 'sources/original.txt'):
            file = self.root / path
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_bytes(b'Existing knowledge')
        before = self.files()
        note = create_note(self.root, 'Native note.')
        save_note(self.root, note['note'], 'Edited native note.', expected=note['revision'])
        self.assertTrue(
            all((self.root / p).read_bytes() == content for p, content in before.items())
        )
        self.assertEqual(sorted(p.name for p in (self.root / 'graph').iterdir()), ['existing.trig'])

    def test_unsupported_registry_version_is_not_silently_replaced(self):
        registry = self.root / 'notes/registry.json'
        registry.parent.mkdir()
        registry.write_text(json.dumps({'schema_version': 2, 'notes': {}}))
        before = registry.read_bytes()
        with self.assertRaisesRegex(ValueError, 'registry'):
            create_note(self.root, 'New.')
        self.assertEqual(registry.read_bytes(), before)
