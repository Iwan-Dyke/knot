import importlib.util
import subprocess
import tempfile
import unittest
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    'export_code', Path(__file__).resolve().parents[1] / 'scripts/export_code.py'
)
EXPORT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(EXPORT)


class ExportCodeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'source'
        self.root.mkdir()
        self.destination = self.root.parent / 'clean code'

    def write(self, name, body='example'):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body)
        return path

    def test_new_repository_does_not_stage_private_data_or_runtime_link(self):
        project = Path(__file__).resolve().parents[1]
        self.write('.gitignore', (project / '.gitignore').read_text())
        self.write('src/knot/__init__.py')
        self.write('data/notes/registry.json')
        self.write('data/.local-runtime/venv/pyvenv.cfg')
        (self.root / '.venv').symlink_to('data/.local-runtime/venv', target_is_directory=True)
        for args in (('init', '-q'), ('add', '.')):
            subprocess.run(['git', '-C', str(self.root), *args], check=True, capture_output=True)
        staged = subprocess.run(
            ['git', '-C', str(self.root), 'ls-files'],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.splitlines()
        self.assertEqual(staged, ['.gitignore', 'src/knot/__init__.py'])

    def test_exports_tool_files_without_private_data_history_or_generated_files(self):
        self.write('README.md')
        launcher = self.write('knot')
        launcher.chmod(0o755)
        self.write('src/knot/__init__.py')
        self.write('src/knot/presentation/viewer.js')
        self.write('tests/support/evaluation.py')
        self.write('tests/retrieval_wire_hashes.json')
        self.write('data-examples/question.md', 'An invented public example.')
        for name in (
            'data/notes/registry.json',
            'experiments/run.py',
            '.git/config',
            '.venv/bin/python',
            'src/knot/__pycache__/module.pyc',
            'src/knot_knowledge.egg-info/PKG-INFO',
            'dist/package.whl',
            'private.md',
        ):
            self.write(name)
        EXPORT.export_code(self.root, self.destination)
        self.assertEqual(
            sorted(
                p.relative_to(self.destination).as_posix()
                for p in self.destination.rglob('*')
                if p.is_file()
            ),
            [
                'README.md',
                'data-examples/question.md',
                'knot',
                'src/knot/__init__.py',
                'src/knot/presentation/viewer.js',
                'tests/retrieval_wire_hashes.json',
                'tests/support/evaluation.py',
            ],
        )
        self.assertEqual((self.destination / 'knot').stat().st_mode & 0o777, 0o755)

    def test_existing_destination_and_nested_destination_are_rejected(self):
        self.destination.mkdir()
        marker = self.destination / 'keep.txt'
        marker.write_text('keep')
        with self.assertRaises(FileExistsError):
            EXPORT.export_code(self.root, self.destination)
        self.assertEqual(marker.read_text(), 'keep')
        with self.assertRaises(ValueError):
            EXPORT.export_code(self.root, self.root / 'export')
        self.assertFalse((self.root / 'export').exists())

    def test_symlinks_cannot_copy_private_files_or_directories(self):
        private = self.write('data/private.md', 'private')
        for target in (private, private.parent):
            with self.subTest(target=target):
                link = self.root / 'docs'
                link.symlink_to(target)
                with self.assertRaisesRegex(ValueError, 'symlink'):
                    EXPORT.export_code(self.root, self.destination)
                self.assertFalse(self.destination.exists())
                link.unlink()
        self.write('src/knot/__init__.py')
        (self.root / 'src/knot/leak.py').symlink_to(private)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            EXPORT.export_code(self.root, self.destination)
        self.assertFalse(self.destination.exists())

    def test_symlink_in_an_allowed_directory_parent_is_rejected(self):
        self.write('data/knot/__init__.py', 'private')
        (self.root / 'src').symlink_to(self.root / 'data', target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            EXPORT.export_code(self.root, self.destination)
        self.assertFalse(self.destination.exists())
