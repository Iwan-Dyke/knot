import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from knot.notes import create_note, read_note


class InstallTests(unittest.TestCase):
    def test_test_recipe_isolates_dataset_settings_and_cleans_up(self):
        project = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            checkout = Path(directory)
            shutil.copy2(project / 'justfile', checkout / 'justfile')
            interpreter = checkout / '.venv/bin/python'
            interpreter.parent.mkdir(parents=True)
            interpreter.write_text(
                '#!/usr/bin/env python3\n'
                'import json, os\n'
                'from pathlib import Path\n'
                'settings = {key: os.environ[key] for key in ("KNOT_CONFIG", "KNOT_DATA_ROOT")}\n'
                'Path(settings["KNOT_CONFIG"]).write_text("Synthetic test write")\n'
                'Path(os.environ["KNOT_TEST_RECEIPT"]).write_text(json.dumps(settings))\n'
            )
            interpreter.chmod(0o755)
            config, receipt = checkout / 'owner-config.json', checkout / 'receipt.json'
            config.write_text('Owner settings')
            result = subprocess.run(
                ['just', 'test'],
                cwd=checkout,
                env={
                    **os.environ,
                    'KNOT_CONFIG': str(config),
                    'KNOT_DATA_ROOT': str(checkout / 'owner-data'),
                    'KNOT_TEST_RECEIPT': str(receipt),
                },
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(config.read_text(), 'Owner settings')
            settings = json.loads(receipt.read_text())
            self.assertNotEqual(settings['KNOT_DATA_ROOT'], str(checkout / 'owner-data'))
            self.assertFalse(Path(settings['KNOT_CONFIG']).parent.exists())

    def test_knowledge_recipe_preserves_literal_arguments_and_paths_with_spaces(self):
        project = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'dataset with spaces'
            create_note(root, 'Synthetic note for task-runner argument handling.')
            marker = Path(directory) / 'unexpected-command'
            result = subprocess.run(
                [
                    'just',
                    'knowledge',
                    'show',
                    '--data-root',
                    str(root),
                    '--theme',
                    f'$(touch {marker})',
                ],
                cwd=project,
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertFalse(marker.exists(), 'A literal argument executed as shell code')
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertIn(f"Unknown theme: ['urn:knot:theme:$(touch {marker})']", result.stderr)
            self.assertEqual(result.stdout, '')

    def test_installed_capture_resume_link_push_refresh_from_another_directory(self):
        project = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            outside = Path(directory)
            checkout = outside / 'checkout with spaces'
            checkout.mkdir()
            shutil.copytree(
                project / 'src', checkout / 'src', ignore=shutil.ignore_patterns('__pycache__')
            )
            for name in ('knot', 'install.sh', '.gitignore'):
                shutil.copy2(project / name, checkout / name)
            # This fixture exercises the legacy private repository with tracked data.
            ignore = checkout / '.gitignore'
            ignore.write_text(ignore.read_text().replace('/data/\n', ''))
            (checkout / '.venv').symlink_to(project / '.venv', target_is_directory=True)
            root = checkout / 'data'
            target = create_note(root, 'Earlier thinking.', title='Earlier note')

            def run(*args, body=None):
                result = subprocess.run(
                    args,
                    cwd=outside,
                    input=body,
                    text=True,
                    capture_output=True,
                    timeout=30,
                    env={**os.environ, 'KNOT_DATA_ROOT': str(root)},
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                return result.stdout

            def git(*args):
                return run('git', '-C', str(checkout), *args).strip()

            git('init', '-b', 'main')
            git('config', 'user.name', 'Test')
            git('config', 'user.email', 'test@example.invalid')
            git('add', '.')
            git('commit', '-m', 'Synthetic baseline')
            remote = outside / 'remote.git'
            git('init', '--bare', str(remote))
            git('remote', 'add', 'origin', str(remote))
            git('push', '-u', 'origin', 'main')
            run('bash', str(checkout / 'install.sh'), '--bin-dir', str(outside / 'bin'))
            command = str(outside / 'bin/knot')
            run(command, 'refresh')
            draft = json.loads(
                run(
                    command,
                    'add',
                    body='My reflection\nWriter\nThought\nA personal thought.\n\nAn open question.\n/done\n'
                    '3\n2\nEarlier\n1\nExtends my earlier thinking.\n10\n',
                )
            )
            self.assertFalse(draft['published'])
            saved = json.loads(run(command, 'resume', body='1\n9\ny\n'))
            note = read_note(root, saved['note'])
            self.assertEqual(note['body'], 'A personal thought.\n\nAn open question.\n')
            self.assertEqual(
                note['navigation']['links'],
                [{'note': target['note'], 'reason': 'Extends my earlier thinking.'}],
            )
            backlinks = json.loads(run(command, 'list', '--linked-to', target['note']))
            self.assertEqual([n['note'] for n in backlinks], [saved['note']])
            run(command, 'push', body='Capture a connected reflection\n')
            run(command, 'refresh')
            self.assertEqual(git('status', '--porcelain'), '')
            self.assertEqual(git('rev-parse', 'HEAD'), git('rev-parse', '@{upstream}'))
            self.assertNotIn('data/drafts/', git('ls-files', 'data'))
            self.assertEqual(
                run('git', '--git-dir', str(remote), 'show', f'main:data/{note["body_path"]}'),
                note['body'],
            )

    def test_install_rerun_and_launch_from_another_directory(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / 'bin with spaces'
            for _ in range(2):
                result = subprocess.run(
                    ['bash', str(root / 'install.sh'), '--bin-dir', str(destination)],
                    cwd=directory,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
            result = subprocess.run(
                [str(destination / 'knot'), '--help'], cwd=directory, capture_output=True, text=True
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('agent-task', result.stdout)

    def test_existing_unrelated_command_is_preserved(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'knot'
            target.write_text('Unrelated command\n')
            result = subprocess.run(
                ['bash', str(root / 'install.sh'), '--bin-dir', directory],
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(target.read_text(), 'Unrelated command\n')
