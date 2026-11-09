import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from knot.writing.notes import create_note, read_note
from knot.writing.sync import push, refresh

PROJECT = Path(__file__).resolve().parents[1]


class DatasetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.config = self.base / 'settings/config.json'
        self.env = {
            **os.environ,
            'KNOT_CONFIG': str(self.config),
            'PYTHONPATH': str(PROJECT / 'src'),
            'PYTHONDONTWRITEBYTECODE': '1',
        }
        self.env.pop('KNOT_DATA_ROOT', None)
        self.addCleanup(patch.stopall)
        patch.dict(os.environ, self.env).start()
        os.environ.pop('KNOT_DATA_ROOT', None)

    def cli(self, *args, ok=True, module='knot.interfaces.note_cli', body=None):
        result = subprocess.run(
            [sys.executable, '-m', module, *map(str, args)],
            cwd=self.base,
            env=self.env,
            input=body,
            capture_output=True,
            text=True,
        )
        if ok:
            self.assertEqual(result.returncode, 0, result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn('Traceback', result.stderr)
        return result

    def git(self, root, *args):
        return subprocess.run(
            ['git', '-C', str(root), *map(str, args)], check=True, capture_output=True, text=True
        ).stdout.strip()

    def identity(self, root):
        self.git(root, 'config', 'user.name', 'Test')
        self.git(root, 'config', 'user.email', 'test@example.invalid')

    def test_init_is_repeatable_and_capture_uses_selected_folder(self):
        root = self.base / 'local notes'
        self.cli('dataset', 'init', root)
        self.assertEqual(json.loads(self.config.read_text())['data_root'], str(root))
        self.assertFalse((root / '.git').exists())
        receipt = json.loads(self.cli('add', '-', body='Exact λ text.\n').stdout)
        before = {p.relative_to(root): p.read_bytes() for p in root.rglob('*') if p.is_file()}
        self.cli('dataset', 'init', root)
        self.assertEqual(
            before, {p.relative_to(root): p.read_bytes() for p in root.rglob('*') if p.is_file()}
        )
        self.assertEqual(read_note(root, receipt['note'])['body'], 'Exact λ text.\n')
        self.assertEqual(len(json.loads(self.cli('list').stdout)), 1)
        response = json.loads(
            self.cli(
                'get',
                '--question',
                'Exact',
                '--mode',
                'text',
                module='knot.retrieval_engine.service',
            ).stdout
        )
        self.assertTrue(response['passages'])
        self.cli('sources', module='knot.interfaces.mcp_server')
        self.cli('build', module='knot.graph.knowledge')
        self.assertFalse((self.base / 'data').exists())

    def test_use_existing_native_dataset_does_not_change_its_bytes(self):
        root = self.base / 'existing'
        saved = create_note(root, 'Existing note.')
        before = {p.relative_to(root): p.read_bytes() for p in root.rglob('*') if p.is_file()}
        self.cli('dataset', 'use', root)
        self.assertEqual(
            before, {p.relative_to(root): p.read_bytes() for p in root.rglob('*') if p.is_file()}
        )
        self.assertEqual(json.loads(self.cli('list').stdout)[0]['note'], saved['note'])

    def test_missing_invalid_or_unconfigured_dataset_never_falls_back(self):
        create_note(self.base / 'data', 'Do not select me implicitly.')
        self.cli('list', ok=False)
        folder = self.base / 'unrelated'
        folder.mkdir()
        (folder / 'keep.txt').write_text('Keep')
        self.cli('dataset', 'init', folder, ok=False)
        self.cli('dataset', 'use', folder, ok=False)
        self.assertFalse(self.config.exists())
        self.assertEqual((folder / 'keep.txt').read_text(), 'Keep')
        self.config.parent.mkdir()
        self.config.write_text('{broken')
        self.cli('list', ok=False)
        self.assertEqual(self.config.read_text(), '{broken')

    def test_precedence_explicit_then_environment_then_config(self):
        from knot.shared.datasets import resolve_data_root

        roots = [self.base / name for name in ('configured', 'environment', 'explicit')]
        for root in roots:
            create_note(root, root.name)
        self.cli('dataset', 'use', roots[0])
        self.assertEqual(resolve_data_root(), roots[0])
        with patch.dict(os.environ, {'KNOT_DATA_ROOT': str(roots[1])}):
            self.assertEqual(resolve_data_root(), roots[1])
            self.assertEqual(resolve_data_root(roots[2]), roots[2])
        roots[0].rename(self.base / 'moved')
        self.cli('list', ok=False)
        self.assertEqual(resolve_data_root(roots[2]), roots[2])

    def test_clone_empty_remote_first_push_refresh_and_transient_exclusions(self):
        remote = self.base / 'remote.git'
        subprocess.run(
            ['git', 'init', '--bare', '--initial-branch=main', str(remote)],
            check=True,
            capture_output=True,
        )
        root = self.base / 'clone with spaces'
        self.cli('dataset', 'clone', remote.as_uri(), root)
        self.assertTrue((root / 'knot.json').is_file())
        self.identity(root)
        saved = create_note(root, 'First remote note.')
        for name in ('drafts/private.json', 'views/private.html', '.local-runtime/private.txt'):
            p = root / name
            p.parent.mkdir(exist_ok=True)
            p.write_text('Do not publish')
        with patch('knot.interfaces.note_cli._ask', return_value='Initial dataset'):
            push(root)
        self.assertEqual(
            self.git(root, 'rev-parse', 'HEAD'), self.git(root, 'rev-parse', '@{upstream}')
        )
        self.assertNotIn('private', self.git(root, 'ls-files'))
        other = self.base / 'other'
        self.cli('dataset', 'clone', remote.as_uri(), other)
        self.assertEqual(read_note(other, saved['note'])['body'], 'First remote note.')
        self.identity(other)
        create_note(other, 'Second remote note.')
        with patch('knot.interfaces.note_cli._ask', return_value='Second note'):
            push(other)
        refresh(root)
        self.assertEqual(self.git(root, 'rev-parse', 'HEAD'), self.git(other, 'rev-parse', 'HEAD'))
        self.cli('dataset', 'clone', remote.as_uri(), root, ok=False)
        self.assertEqual(read_note(root, saved['note'])['body'], 'First remote note.')

    def test_clone_failure_preserves_configuration_and_rejects_command_urls(self):
        root = self.base / 'selected'
        self.cli('dataset', 'init', root)
        before = self.config.read_bytes()
        for url in (
            'ext::sh -c touch unwanted',
            '--upload-pack=touch',
            'https://user:secret@example.invalid/repo.git',
            (self.base / 'missing.git').as_uri(),
        ):
            destination = self.base / 'failed'
            self.cli('dataset', 'clone', url, destination, ok=False)
            self.assertFalse(destination.exists())
            self.assertEqual(self.config.read_bytes(), before)
        self.assertFalse((self.base / 'unwanted').exists())

    def test_launcher_keeps_callers_relative_file_and_dataset_paths(self):
        env = self.env
        root = self.base / 'relative-data'
        result = subprocess.run(
            [str(PROJECT / 'knot'), 'dataset', 'init', 'relative-data'],
            cwd=self.base,
            env=env,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        (self.base / 'input.md').write_text('Relative path note.')
        result = subprocess.run(
            [str(PROJECT / 'knot'), 'add', 'input.md'],
            cwd=self.base,
            env=env,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            read_note(root, json.loads(result.stdout)['note'])['body'], 'Relative path note.'
        )

    def test_default_clone_destination_and_standard_remote_transports(self):
        from knot.writing.datasets import clone

        with patch.dict(os.environ, {'XDG_DATA_HOME': str(self.base / 'managed')}):
            for index, url in enumerate(
                (
                    'https://example.invalid/team/notes.git',
                    'ssh://git@example.invalid/team/notes.git',
                    'git@example.invalid:team/notes.git',
                )
            ):
                destination = None if index == 0 else self.base / str(index)
                with patch('knot.writing.datasets.subprocess.run') as run:
                    run.return_value = subprocess.CompletedProcess([], 0, '', '')
                    root = clone(url, destination)
                self.assertIn('--no-recurse-submodules', run.call_args.args[0])
                self.assertEqual(run.call_args.args[0][-2], url)
                self.assertTrue((root / 'knot.json').is_file())
                if index == 0:
                    self.assertEqual(root, self.base / 'managed/knot/datasets/notes')

    def test_clone_of_unrelated_repository_does_not_replace_selection(self):
        selected = self.base / 'selected'
        self.cli('dataset', 'init', selected)
        before = self.config.read_bytes()
        unrelated = self.base / 'software'
        unrelated.mkdir()
        self.git(unrelated, 'init', '--initial-branch=main')
        self.identity(unrelated)
        (unrelated / 'app.py').write_text('print("not a dataset")')
        self.git(unrelated, 'add', '.')
        self.git(unrelated, 'commit', '-m', 'Synthetic unrelated software')
        destination = self.base / 'rejected'
        self.cli('dataset', 'clone', unrelated, destination, ok=False)
        self.assertFalse(destination.exists())
        self.assertEqual(self.config.read_bytes(), before)

    def test_staged_private_runtime_is_rejected_in_standalone_repository(self):
        root = self.base / 'standalone'
        self.cli('dataset', 'init', root)
        self.git(root, 'init', '--initial-branch=main')
        self.identity(root)
        remote = self.base / 'remote.git'
        subprocess.run(['git', 'init', '--bare', str(remote)], check=True, capture_output=True)
        self.git(root, 'remote', 'add', 'origin', str(remote))
        private = root / 'drafts/private.txt'
        private.parent.mkdir()
        private.write_text('Do not publish')
        self.git(root, 'add', '-f', str(private))
        before = self.git(root, 'diff', '--cached')
        with self.assertRaisesRegex(ValueError, 'outside knowledge'):
            push(root)
        self.assertEqual(self.git(root, 'diff', '--cached'), before)

    def test_all_entry_points_share_the_selected_dataset(self):
        root = self.base / 'shared'
        self.cli('dataset', 'init', root)
        create_note(root, 'A synthetic shared dataset note.')
        self.cli('summary', module='knot.graph.knowledge')
        self.cli('summary', module='knot.reviewing.writer')
        self.cli(module='knot.diagnostics.quality')
        self.cli('--output', self.base / 'view.html', module='knot.presentation.visualise')
        self.assertTrue((self.base / 'view.html').is_file())
        query = self.base / 'query.rq'
        query.write_text('SELECT ?s WHERE { ?s ?p ?o } LIMIT 1')
        self.cli(query, module='knot.graph.query')
        self.cli('sources', module='knot.interfaces.mcp_server')
        # Selection never supplies an MCP read grant or enables authoring.
        self.cli('serve', module='knot.interfaces.mcp_server', ok=False)
