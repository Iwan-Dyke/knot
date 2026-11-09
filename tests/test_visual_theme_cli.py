import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pyvis.network import Network

from knot.presentation.visualise import add_claim, write_view
from knot.writing.notes import create_note

PROJECT = Path(__file__).resolve().parents[1]


class VisualThemeCommandTests(unittest.TestCase):
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

    def cli(self, *args, ok=True, cwd=None):
        result = subprocess.run(
            [sys.executable, '-m', 'knot.interfaces.note_cli', *map(str, args)],
            cwd=cwd or self.base,
            env=self.env,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode == 0, ok, result.stderr)
        self.assertNotIn('Traceback', result.stderr)
        return result

    def test_selection_before_dataset_setup_survives_dataset_switches_and_overrides(self):
        listed = json.loads(self.cli('theme', 'list').stdout)
        self.assertEqual(listed['selected'], 'matrix')
        self.assertEqual(listed['themes'], ['matrix', 'midnight', 'paper'])
        self.assertFalse(self.config.exists())
        self.cli('theme', 'use', 'paper')
        self.cli('list', ok=False)
        for name in ('one', 'two'):
            self.cli('dataset', 'init', self.base / name)
            config = json.loads(self.config.read_text())
            self.assertEqual(config['visual_theme'], 'paper')
            self.assertEqual(config['data_root'], str(self.base / name))
        create_note(self.base / 'two', 'A synthetic thought.')
        output = self.base / 'view.html'
        self.cli('view', '--output', output)
        self.assertIn('--background: #faf8f3;', output.read_text())
        self.cli('view', '--visual-theme', 'midnight', '--output', output)
        self.assertIn('--background: #111827;', output.read_text())
        self.assertEqual(json.loads(self.config.read_text())['visual_theme'], 'paper')
        self.cli('theme', 'use', 'matrix')
        self.assertEqual(json.loads(self.cli('theme', 'show').stdout)['selected'], 'matrix')

    def test_dropped_css_is_discovered_and_used_for_page_and_canvas(self):
        folder = self.config.parent / 'themes'
        folder.mkdir(parents=True)
        path = folder / 'ocean.css'
        path.write_text("""/* Custom palette */
            :root { color-scheme: dark;
                --background: #123456; --entity: #345678;
                --accepted: #abcdef; --font-graph: serif; }
        """)
        listed = json.loads(self.cli('theme', 'list').stdout)
        self.assertEqual(Path(listed['directory']), folder)
        self.assertIn('ocean', listed['themes'])
        self.cli('theme', 'use', 'ocean')
        self.assertEqual(json.loads(self.config.read_text())['visual_theme'], 'ocean')
        network = Network(directed=True, cdn_resources='in_line')
        add_claim(
            network,
            {
                'id': 'claim',
                'source': 'a',
                'target': 'b',
                'subject': 'A',
                'object': 'B',
                'relation': 'relatedTo',
                'status': 'Accepted',
                'origin': 'Explicit',
            },
        )
        with patch.dict(os.environ, self.env):
            from knot.presentation.styles import selected_theme

            write_view(network, self.base / 'view.html', visual_theme=selected_theme())
        self.assertEqual(network.bgcolor, '#123456')
        self.assertEqual(network.get_node('a')['color']['background'], '#345678')
        self.assertEqual(network.get_node('a')['font']['face'], 'serif')
        self.assertEqual(network.edges[0]['color'], '#abcdef')

    def test_external_theme_path_is_saved_absolute_and_invalid_choice_preserves_config(self):
        path = self.base / 'external.json'
        path.write_text(
            json.dumps(
                {'schema_version': 1, 'name': 'External', 'colors': {'background': '#123456'}}
            )
        )
        self.cli('theme', 'use', 'external.json')
        self.assertEqual(json.loads(self.config.read_text())['visual_theme'], str(path))
        outside = self.base / 'elsewhere'
        outside.mkdir()
        self.assertEqual(
            json.loads(self.cli('theme', 'show', cwd=outside).stdout)['selected'], str(path)
        )
        before = self.config.read_bytes()
        self.cli('theme', 'use', 'does-not-exist', ok=False)
        self.assertEqual(self.config.read_bytes(), before)
        path.unlink()
        self.cli('theme', 'show', ok=False)
        self.cli('theme', 'use', 'matrix')

    def test_create_writes_editable_css_without_overwriting_or_changing_selection(self):
        self.cli('theme', 'use', 'paper')
        before = self.config.read_bytes()
        self.cli('theme', 'create', 'personal', '--from', 'midnight')
        path = self.config.parent / 'themes/personal.css'
        self.assertIn('--background: #111827;', path.read_text())
        self.assertEqual(self.config.read_bytes(), before)
        original = path.read_bytes()
        self.cli('theme', 'create', 'personal', ok=False)
        self.cli('theme', 'create', '../escape', ok=False)
        self.cli('theme', 'create', 'matrix', ok=False)
        self.assertEqual(path.read_bytes(), original)
        self.cli('theme', 'use', 'personal')
        self.assertEqual(json.loads(self.config.read_text())['visual_theme'], 'personal')

    def test_builtin_names_are_reserved_and_css_wins_over_json_in_user_folder(self):
        folder = self.config.parent / 'themes'
        folder.mkdir(parents=True)
        for name in ('matrix', 'custom'):
            (folder / f'{name}.json').write_text(
                json.dumps(
                    {
                        'schema_version': 1,
                        'name': 'Custom',
                        'colors': {'background': '#abcdef'},
                    }
                )
            )
            (folder / f'{name}.css').write_text(':root { --background: #123456; }')
        with patch.dict(os.environ, self.env):
            from knot.presentation.styles import load_theme

            self.assertEqual(load_theme('matrix')['colors']['background'], '#020a02')
            self.assertEqual(load_theme('custom')['colors']['background'], '#123456')
        self.cli('theme', 'use', folder / 'matrix.css')
        self.assertEqual(
            json.loads(self.config.read_text())['visual_theme'], str(folder / 'matrix.css')
        )

    def test_invalid_css_and_corrupt_config_do_not_replace_settings(self):
        self.cli('theme', 'use', 'paper')
        before = self.config.read_bytes()
        path = self.base / 'invalid.css'
        for css in (
            ':root { --unknown: #123456; }',
            'body { background: red; }',
            '@import "https://example.invalid/style.css"; :root { --accent: #123456; }',
            ':root { --accent: url(https://example.invalid/image); }',
            ':root { --font-ui: "unterminated; }',
            ':root { --accent: #123456;',
            ':root { --accent: #123456; --accent: #abcdef; }',
            ':root { --accent: #123456; } </style><script>alert(1)</script>',
        ):
            with self.subTest(css=css):
                path.write_text(css)
                self.cli('theme', 'use', path, ok=False)
                self.assertEqual(self.config.read_bytes(), before)
        self.config.write_text('{broken')
        self.cli('theme', 'use', 'matrix', ok=False)
        self.assertEqual(self.config.read_text(), '{broken')
