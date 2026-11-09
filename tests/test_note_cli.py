import json
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from knot.notes import note_history, read_note


class NoteCliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name)
        self.root = self.directory / 'data'

    def test_delegated_commands_preserve_arguments_and_dataset_prefix(self):
        from knot.interfaces.note_cli import main

        for command, module, rooted in (
            ('view', 'knot.interfaces.view_cli', True),
            ('browse', 'knot.presentation.library', True),
            ('themes', 'knot.interfaces.theme_cli', True),
            ('theme', 'knot.interfaces.visual_theme_cli', False),
            ('dataset', 'knot.interfaces.dataset_cli', False),
            ('mcp', 'knot.interfaces.mcp_server', False),
        ):
            prefixes = [[], ['--data-root', str(self.root)], [f'--data-root={self.root}']]
            for prefix in prefixes if rooted else [[]]:
                arguments = ['--help']
                with self.subTest(command=command, prefix=prefix), patch(module + '.main') as run:
                    main([*prefix, command, *arguments])
                    run.assert_called_once_with([*prefix, *arguments])

    def cli(self, *arguments, body=None, success=True, just=False):
        if (
            arguments
            and arguments[0] == 'add'
            and (len(arguments) == 1 or arguments[1].startswith('--'))
        ):
            arguments = (*arguments, '--writing-only')
        command = ['just', 'notes'] if just else [sys.executable, '-m', 'knot.note_cli']
        result = subprocess.run(
            [*command, '--data-root', str(self.root), *arguments],
            input=body,
            capture_output=True,
            cwd=Path(__file__).resolve().parents[1],
        )
        if success:
            self.assertEqual(result.returncode, 0, result.stderr.decode())
        else:
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn(b'Traceback', result.stderr)
            self.assertNotIn(b'No module named', result.stderr)
        return result

    def add(self, body=b'A thought.\n', *arguments):
        return json.loads(self.cli('add', '-', *arguments, body=body).stdout)

    def test_saved_note_hint_refreshes_existing_graph_for_the_same_dataset(self):
        self.root = self.directory / "writer's notes"
        self.add(b'Earlier practice.', '--title', 'Earlier note')
        self.cli('view', '--legacy', '--no-open', '--visual-theme', 'matrix')
        graph = self.root / 'views/graph.html'
        before = graph.read_bytes()
        result = self.cli('add', '-', '--title', 'Learning scales', body=b'Practice helps.')
        saved = json.loads(result.stdout)
        self.assertEqual(read_note(self.root, saved['note'])['body'], 'Practice helps.')
        self.assertEqual(graph.read_bytes(), before)
        self.assertNotIn(saved['note'].encode(), before)
        self.assertIn(b'The graph is a snapshot', result.stderr)
        command = shlex.split(result.stderr.decode().splitlines()[-1])
        self.assertEqual(command, ['knot', 'view', '--data-root', str(self.root), '--open'])
        command.remove('--open')
        refreshed = subprocess.run(
            [
                sys.executable,
                '-m',
                'knot.note_cli',
                *command[1:],
                '--legacy',
                '--no-open',
                '--visual-theme',
                'matrix',
            ],
            capture_output=True,
        )
        self.assertEqual(refreshed.returncode, 0, refreshed.stderr.decode())
        self.assertIn(b'2 nodes, 0 claims', refreshed.stdout)
        self.assertIn(saved['note'], graph.read_text())
        self.assertEqual(self.cli('list').stderr, b'')

    def test_add_file_preserves_bytes_and_optional_metadata(self):
        body = b'\xef\xbb\xbf# A thought\r\nMaybe \xce\xbb?\r\n\n'
        path = self.directory / 'my note.org'
        path.write_bytes(body)
        saved = json.loads(
            self.cli(
                'add',
                str(path),
                '--title',
                'Reflection',
                '--author',
                'Writer',
                '--agent',
                'Codex',
                '--reason',
                'Requested capture',
                '--kind',
                'Thought',
            ).stdout
        )
        current = read_note(self.root, saved['note'])
        self.assertEqual(current['body'].encode(), body)
        self.assertEqual(current['format'], 'org')
        for key, expected in (
            ('title', 'Reflection'),
            ('author', 'Writer'),
            ('agent', 'Codex'),
            ('reason', 'Requested capture'),
            ('kind', 'Thought'),
        ):
            self.assertEqual(current[key], expected)
        self.assertEqual(current['revision'], saved['revision'])
        self.assertNotIn('body', saved)

    def test_curated_capture_validates_provenance_and_retains_original(self):
        original = self.add(b'Delivery remains planned.', '--author', 'Owner')
        metadata = {
            'method': 'faithful_restatement',
            'qualification': 'No completion established.',
            'sources': [
                {
                    'revision': original['revision'],
                    'sha256': original['body_sha256'],
                    'text_sha256': original['body_sha256'],
                    'quote': 'Delivery remains planned.',
                    'character_offset': 0,
                    'start_line': 1,
                }
            ],
        }
        path = self.directory / 'provenance.json'
        path.write_text(json.dumps(metadata))
        saved = self.add(
            b'The source reports planned delivery.',
            '--title',
            'Planned delivery',
            '--author',
            'Codex',
            '--agent',
            'Codex',
            '--derivation',
            str(path),
        )
        self.assertEqual(saved['derivation'], metadata)
        self.assertEqual(read_note(self.root, original['note'])['revision'], original['revision'])
        metadata['sources'][0]['quote'] = 'Delivery completed.'
        path.write_text(json.dumps(metadata))
        self.cli(
            'add',
            '-',
            '--title',
            'Unsupported',
            '--author',
            'Codex',
            '--agent',
            'Codex',
            '--derivation',
            str(path),
            body=b'Unsupported.',
            success=False,
        )
        self.assertEqual(len(json.loads(self.cli('list').stdout)), 2)

    def test_stdin_show_and_empty_note_preserve_exact_bytes(self):
        for body in (b'', 'Unicode \u03bb\U0001f642\r\nNo final newline'.encode()):
            with self.subTest(body=body):
                saved = self.add(body)
                shown = json.loads(self.cli('show', saved['note']).stdout)
                self.assertEqual(shown['body'].encode(), body)
                raw = self.cli('show', saved['note'], '--body-only').stdout
                self.assertEqual(raw, body)
                self.assertIsNone(shown['author'])
                self.assertIsNone(shown['agent'])
                self.assertEqual(shown['entities'], [])
        self.assertFalse((self.root / 'graph').exists())

    def test_save_requires_expected_revision_and_retains_metadata(self):
        first = self.add(b'Original\r\n', '--title', 'Keep me', '--format', 'org')
        before = (self.root / 'notes/registry.json').read_bytes()
        missing = self.cli('save', first['note'], '-', body=b'Next', success=False)
        self.assertIn(b'--expected', missing.stderr)
        self.assertEqual((self.root / 'notes/registry.json').read_bytes(), before)
        result = self.cli('save', first['note'], '-', '--expected', first['revision'], body=b'Next')
        second = json.loads(result.stdout)
        self.assertIn(b'knot view', result.stderr)
        self.assertEqual(second['title'], 'Keep me')
        self.assertEqual(second['format'], 'org')
        before = (self.root / 'notes/registry.json').read_bytes()
        stale = self.cli(
            'save',
            first['note'],
            '-',
            '--expected',
            first['revision'],
            body=b'Stale draft',
            success=False,
        )
        self.assertIn(b'head changed', stale.stderr)
        self.assertNotIn(b'knot view', stale.stderr)
        self.assertEqual((self.root / 'notes/registry.json').read_bytes(), before)
        raw = self.cli(
            'show',
            first['note'],
            '--revision',
            first['revision'],
            '--body-only',
        ).stdout
        self.assertEqual(raw, b'Original\r\n')
        again = json.loads(
            self.cli(
                'save', first['note'], '-', '--expected', second['revision'], body=b'Next'
            ).stdout
        )
        self.assertEqual(again['revision'], second['revision'])
        self.assertEqual(len(note_history(self.root, first['note'])), 2)

    def test_entities_and_explicit_metadata_clearing(self):
        graph = self.root / 'graph/entities.trig'
        graph.parent.mkdir(parents=True)
        graph.write_text(
            '<urn:knot:metadata> { <urn:project:test> '
            '<http://www.w3.org/2000/01/rdf-schema#label> "Test project" . }'
        )
        first = self.add(
            b'Linked',
            '--entity',
            'urn:project:test',
            '--title',
            'Title',
            '--author',
            'Writer',
            '--kind',
            'Hypothesis',
        )
        self.assertEqual(first['entities'], ['urn:project:test'])
        second = json.loads(
            self.cli(
                'save',
                first['note'],
                '-',
                '--expected',
                first['revision'],
                '--clear-entities',
                '--clear-title',
                '--clear-author',
                '--clear-kind',
                body=b'Linked',
            ).stdout
        )
        self.assertEqual(second['entities'], [])
        for key in ('title', 'author', 'kind'):
            self.assertIsNone(second[key])
        self.assertEqual(first['body_path'], second['body_path'])

    def test_list_and_history_include_verified_metadata_without_bodies(self):
        self.assertEqual(json.loads(self.cli('list').stdout), [])
        self.assertFalse(self.root.exists())
        first = self.add(b'First')
        second = json.loads(
            self.cli(
                'save',
                first['note'],
                '-',
                '--expected',
                first['revision'],
                body=b'Second',
            ).stdout
        )
        listing = json.loads(self.cli('list').stdout)
        self.assertEqual([note['revision'] for note in listing], [second['revision']])
        history = json.loads(self.cli('history', first['note']).stdout)
        self.assertEqual(
            [note['revision'] for note in history], [first['revision'], second['revision']]
        )
        self.assertTrue(all('body' not in note for note in listing + history))
        (self.root / first['body_path']).write_bytes(b'Corrupt old source')
        failure = self.cli('list', success=False)
        self.assertIn(b'hash mismatch', failure.stderr)

    def test_invalid_input_creates_no_note_and_reports_errors_without_tracebacks(self):
        for arguments, body in (
            (('add', str(self.directory / 'missing.md')), None),
            (('add', '-'), b'\xff'),
            (('add', '-', '--kind', 'Unsupported'), b'Text'),
            (('add', '-', '--entity', 'urn:unknown:entity'), b'Text'),
            (('show', 'invalid-note-id'), None),
        ):
            with self.subTest(arguments=arguments):
                self.cli(*arguments, body=body, success=False)
                self.assertFalse((self.root / 'notes/registry.json').exists())

    def test_just_forwards_spaces_and_shell_characters_literally(self):
        title = 'A title $(printf expanded) `printf expanded` "with quotes"'
        saved = json.loads(self.cli('add', '-', '--title', title, body=b'Body', just=True).stdout)
        self.assertEqual(read_note(self.root, saved['note'])['title'], title)

    def test_wizard_saves_personal_thinking_with_preview(self):
        answers = (
            'Working locally\nWriter\n\n'
            'An offline afternoon.\n\nI value control.\nMaybe λ matters too.\n/done\nyes\n'
        )
        result = self.cli('add', body=answers.encode())
        saved = json.loads(result.stdout)
        current = read_note(self.root, saved['note'])
        self.assertEqual(current['title'], 'Working locally')
        self.assertEqual(current['author'], 'Writer')
        self.assertIsNone(current['kind'])
        self.assertIsNone(current['agent'])
        self.assertEqual(current['entities'], [])
        self.assertEqual(
            current['body'],
            'An offline afternoon.\n\nI value control.\nMaybe λ matters too.\n',
        )
        self.assertIn(current['body'].encode(), result.stderr)
        self.assertIn(b'knot view', result.stderr)
        self.assertEqual(len(note_history(self.root, saved['note'])), 1)

    def test_wizard_cancel_eof_and_empty_capture_do_not_write(self):
        for answers, message in (
            (b'Title\n', b'input ended'),
            (b'\n\n\nDraft text\n/cancel\n', b'nothing saved'),
            (b'\n\n\nThought\n/done\nno\n', b'nothing saved'),
            (b'\n\n\n/done\nyes\n', b'no note text'),
        ):
            with self.subTest(answers=answers):
                result = self.cli('add', body=answers, success=False)
                self.assertFalse((self.root / 'notes/registry.json').exists())
                self.assertEqual(result.stdout, b'')
                self.assertIn(message, result.stderr)
                self.assertNotIn(b'knot view', result.stderr)

    def test_wizard_metadata_flags_skip_prompts_and_validate_kind(self):
        result = self.cli(
            'add',
            '--title',
            'Question',
            '--author',
            'Writer',
            body=b'Invalid\nQuestion\nWhat happened?\n/done\ny\n',
        )
        saved = json.loads(result.stdout)
        self.assertEqual(saved['kind'], 'Question')
        self.assertEqual(saved['author'], 'Writer')
        self.assertEqual(saved['title'], 'Question')
        self.assertIn(b'Choose a listed kind', result.stderr)
        self.assertNotIn(b'Your name / author', result.stderr)

    def test_wizard_rejects_org_before_prompting(self):
        result = self.cli('add', '--format', 'org', body=b'', success=False)
        self.assertIn(b'use a file', result.stderr)
        self.assertFalse(self.root.exists())

    def test_repository_launcher_uses_existing_cli(self):
        launcher = Path(__file__).resolve().parents[1] / 'knot'
        result = subprocess.run(
            [str(launcher), '--data-root', str(self.root), 'list'],
            cwd=self.directory,
            capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        self.assertEqual(json.loads(result.stdout), [])


if __name__ == '__main__':
    unittest.main()
