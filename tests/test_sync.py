import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from knot.sync import push, refresh


class SyncTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / 'checkout'
        self.remote = Path(self.tmp.name) / 'remote.git'
        self.root.mkdir()
        self.git('init', '-b', 'main')
        self.git('config', 'user.name', 'Test')
        self.git('config', 'user.email', 'test@example.invalid')
        (self.root / 'data').mkdir()
        (self.root / 'data/note.txt').write_text('Original')
        self.git('add', '.')
        self.git('commit', '-m', 'Initial')
        self.git('init', '--bare', str(self.remote))
        self.git('remote', 'add', 'origin', str(self.remote))
        self.git('push', '-u', 'origin', 'main')

    def git(self, *args):
        return subprocess.run(
            ['git', '-C', str(self.root), *args],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

    def test_commit_and_push_with_literal_message(self):
        (self.root / 'data/note.txt').write_text('Updated')
        message = 'Notes with $(touch unwanted) and `literal` text'
        with patch('knot.note_cli._ask', return_value=message):
            push(self.root / 'data')
        self.assertEqual(self.git('log', '-1', '--format=%s'), message)
        self.assertEqual(self.git('rev-parse', 'HEAD'), self.git('rev-parse', '@{upstream}'))
        self.assertEqual(self.git('status', '--porcelain'), '')
        self.assertFalse((self.root / 'unwanted').exists())

    def test_blank_message_cancels_before_staging(self):
        (self.root / 'data/note.txt').write_text('Updated')
        before = self.git('status', '--porcelain')
        with patch('knot.note_cli._ask', return_value=''):
            push(self.root / 'data')
        self.assertEqual(self.git('status', '--porcelain'), before)

    def test_only_knowledge_is_committed_including_already_staged_notes(self):
        (self.root / 'app.py').write_text('Unrelated work')
        (self.root / 'data/note.txt').write_text('Updated')
        (self.root / 'data/drafts').mkdir()
        (self.root / 'data/drafts/local.json').write_text('{}')
        (self.root / 'data/.extra').write_text('Knowledge metadata')
        self.git('add', 'data/note.txt')
        with patch('knot.note_cli._ask', return_value='Save knowledge'):
            push(self.root / 'data')
        committed = self.git('show', '--format=', '--name-only', 'HEAD').splitlines()
        self.assertEqual(committed, ['data/.extra', 'data/note.txt'])
        self.assertIn('?? app.py', self.git('status', '--porcelain'))

    def test_unrelated_staged_files_are_preserved(self):
        (self.root / 'app.py').write_text('Unrelated work')
        self.git('add', 'app.py')
        before = self.git('status', '--porcelain')
        with self.assertRaisesRegex(ValueError, 'staged'):
            push(self.root / 'data')
        self.assertEqual(self.git('status', '--porcelain'), before)

    def test_push_handles_deletions_and_unusual_filenames(self):
        (self.root / 'data/note.txt').unlink()
        unusual = 'data/:a note\nwith a newline.txt'
        (self.root / unusual).write_text('New content')
        with patch('knot.note_cli._ask', return_value='Update knowledge files'):
            push(self.root / 'data')
        self.assertEqual(self.git('status', '--porcelain'), '')
        self.assertEqual(self.git('show', f'HEAD:{unusual}'), 'New content')

    def test_missing_upstream_fails_before_staging(self):
        self.git('branch', '--unset-upstream')
        (self.root / 'data/note.txt').write_text('Updated')
        before = self.git('status', '--porcelain')
        with self.assertRaisesRegex(ValueError, 'upstream'):
            push(self.root / 'data')
        self.assertEqual(self.git('status', '--porcelain'), before)

    def test_failed_push_keeps_commit_and_retry_does_not_duplicate(self):
        (self.root / 'data/note.txt').write_text('Updated')
        self.git('remote', 'set-url', '--push', 'origin', str(self.remote / 'missing'))
        with patch('knot.note_cli._ask', return_value='Save note'):
            with self.assertRaisesRegex(ValueError, 'retry'):
                push(self.root / 'data')
        committed = self.git('rev-parse', 'HEAD')
        self.git('remote', 'set-url', '--push', 'origin', str(self.remote))
        with patch('knot.note_cli._ask', side_effect=AssertionError('No new commit needed')):
            push(self.root / 'data')
        self.assertEqual(self.git('rev-parse', 'HEAD'), committed)
        self.assertEqual(self.git('rev-parse', '@{upstream}'), committed)

    def advance_remote(self):
        other = self.root.parent / 'other'
        self.git('clone', '--branch', 'main', str(self.remote), str(other))
        self.git('-C', str(other), 'config', 'user.name', 'Test')
        self.git('-C', str(other), 'config', 'user.email', 'test@example.invalid')
        (other / 'data/remote-note.txt').write_text('A note from another machine')
        self.git('-C', str(other), 'add', '.')
        self.git('-C', str(other), 'commit', '-m', 'Remote note')
        self.git('-C', str(other), 'push')
        return self.git('-C', str(other), 'rev-parse', 'HEAD')

    def test_refresh_fast_forwards_and_is_safe_to_repeat(self):
        remote_head = self.advance_remote()
        refresh(self.root / 'data')
        refresh(self.root / 'data')
        self.assertEqual(self.git('rev-parse', 'HEAD'), remote_head)
        self.assertEqual(
            (self.root / 'data/remote-note.txt').read_text(), 'A note from another machine'
        )
        self.assertEqual(self.git('status', '--porcelain'), '')

    def test_refresh_preserves_uncommitted_and_untracked_work(self):
        for filename in ('data/note.txt', 'app.py'):
            with self.subTest(filename=filename):
                path = self.root / filename
                path.write_text('Unsaved work')
                before = self.git('rev-parse', 'HEAD')
                with self.assertRaisesRegex(ValueError, 'uncommitted'):
                    refresh(self.root / 'data')
                self.assertEqual(path.read_text(), 'Unsaved work')
                self.assertEqual(self.git('rev-parse', 'HEAD'), before)
                if filename == 'data/note.txt':
                    path.write_text('Original')

    def test_refresh_refuses_divergence_even_when_autostash_or_rebase_is_configured(self):
        self.advance_remote()
        (self.root / 'data/local-note.txt').write_text('Local note')
        self.git('add', '.')
        self.git('commit', '-m', 'Local note')
        self.git('config', 'pull.rebase', 'true')
        self.git('config', 'rebase.autoStash', 'true')
        before = self.git('rev-parse', 'HEAD')
        with self.assertRaisesRegex(ValueError, 'Refresh failed'):
            refresh(self.root / 'data')
        self.assertEqual(self.git('rev-parse', 'HEAD'), before)
        self.assertEqual(self.git('status', '--porcelain'), '')
        self.assertFalse((self.root / 'data/remote-note.txt').exists())

    def test_refresh_requires_an_upstream(self):
        self.git('branch', '--unset-upstream')
        with self.assertRaisesRegex(ValueError, 'upstream'):
            refresh(self.root / 'data')
