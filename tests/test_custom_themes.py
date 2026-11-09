import copy
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pyvis.network import Network
from test_visualise import Resources

from knot.presentation.visualise import add_claim, add_note_navigation, add_themes, write_view
from knot.writing.notes import create_note, read_note

PROJECT = Path(__file__).resolve().parents[1]


class VisualThemeTests(unittest.TestCase):
    def test_custom_theme_styles_page_and_graph_without_changing_knowledge(self):
        network = Network(directed=True, cdn_resources='in_line')
        for status in ('Accepted', 'Unreviewed'):
            add_claim(
                network,
                {
                    'id': status,
                    'source': 'urn:a',
                    'target': 'urn:b',
                    'subject': 'Example',
                    'object': 'Another example',
                    'relation': 'relatedTo',
                    'status': status,
                    'origin': 'Inferred',
                    'quote': 'Exact evidence.',
                },
            )
        add_themes(
            network,
            [
                {
                    'id': 'Accepted',
                    'subject': {'id': 'urn:a'},
                    'object': {'id': 'urn:b'},
                    'themes': [{'id': 'concepts', 'label': 'Concepts', 'status': 'Accepted'}],
                }
            ],
        )
        add_note_navigation(
            network,
            {
                'notes': {
                    'urn:note': {
                        'title': 'A concept',
                        'body': 'Thinking.',
                        'kind': None,
                        'entities': ['urn:a'],
                        'revision': 'urn:revision',
                        'navigation': {'themes': [], 'links': []},
                    }
                }
            },
            {},
        )
        before = copy.deepcopy(network.edges)
        colors = {
            'background': '#fefefe',
            'accent': '#123456',
            'entity': '#234567',
            'accepted': '#345678',
            'unreviewed': '#456789',
            'navigation': '#56789a',
            'theme': '#6789ab',
            'theme-accepted': '#789abc',
            'note': '#89abcd',
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            theme = root / 'custom.json'
            theme.write_text(
                json.dumps(
                    {
                        'schema_version': 1,
                        'name': 'Custom',
                        'color_scheme': 'light',
                        'colors': colors,
                        'fonts': {'graph': 'serif', 'ui': 'system-ui'},
                    }
                )
            )
            output = root / 'view.html'
            write_view(network, output, visual_theme=theme)
            html = output.read_text()
        self.assertIn('--background: #fefefe;', html)
        self.assertIn('--font-ui: system-ui;', html)
        self.assertIn('color-scheme: light;', html)
        self.assertEqual(network.bgcolor, colors['background'])
        self.assertEqual(network.get_node('urn:a')['color']['background'], colors['entity'])
        self.assertEqual(network.get_node('urn:a')['font']['face'], 'serif')
        self.assertEqual(network.get_node('urn:note')['color'], colors['note'])
        self.assertEqual(network.get_node('urn:knot:theme:concepts')['color'], colors['theme'])
        for old, new in zip(before, network.edges, strict=True):
            for key in old.keys() - {'color', 'font'}:
                self.assertEqual(new[key], old[key], key)
            if new.get('navigation'):
                self.assertEqual(new['color'], colors['navigation'])
            elif new.get('organisation'):
                self.assertEqual(new['color']['color'], colors['theme-accepted'])
            else:
                self.assertEqual(new['color'], colors[new['status'].lower()])
        resources = Resources()
        resources.feed(html)
        self.assertEqual(resources.external, [])

    def test_invalid_theme_does_not_overwrite_an_existing_export(self):
        invalid = [
            {'schema_version': 2},
            {'colors': {'unknown': '#123456'}},
            {'colors': {'accent': '</style><script>alert(1)</script>'}},
            {'colors': {'accent': 'url(https://example.invalid/image)'}},
            {'fonts': {'ui': 'serif; background:red'}},
            {'fonts': {'ui': "'unterminated font"}},
            {'color_scheme': 'auto'},
            {'colors': []},
            {'fonts': None},
            {'unexpected': True},
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output, theme = root / 'view.html', root / 'theme.json'
            for changes in invalid:
                with self.subTest(changes=changes):
                    output.write_text('Existing export')
                    theme.write_text(json.dumps({'schema_version': 1, 'name': 'Custom', **changes}))
                    with self.assertRaises(ValueError):
                        write_view(Network(), output, visual_theme=theme)
                    self.assertEqual(output.read_text(), 'Existing export')

    def test_builtin_and_custom_themes_are_independent(self):
        from knot.presentation.styles import load_theme

        matrix, paper = load_theme('matrix'), load_theme('paper')
        self.assertEqual(matrix['colors']['background'], '#020a02')
        self.assertEqual(paper['color_scheme'], 'light')
        self.assertNotEqual(matrix['colors']['background'], paper['colors']['background'])
        paper['colors']['background'] = '#000000'
        self.assertEqual(load_theme('matrix'), matrix)
        with self.assertRaises(ValueError):
            load_theme('missing-style')

    def test_bundled_theme_discovery_needs_no_code_registration(self):
        from knot.presentation.styles import load_theme

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'example.json').write_text(
                json.dumps(
                    {
                        'schema_version': 1,
                        'name': 'Example',
                        'colors': {'accent': '#123456'},
                    }
                )
            )
            with patch('knot.presentation.styles.THEMES', root):
                self.assertEqual(load_theme('example')['colors']['accent'], '#123456')

    def test_view_command_uses_external_theme_and_preserves_dataset(self):
        from knot.interfaces.note_cli import main

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'data'
            create_note(root, 'A synthetic concept.', title='Concept')
            before = {p: p.read_bytes() for p in root.rglob('*') if p.is_file()}
            theme = Path(directory) / 'theme.json'
            theme.write_text(
                json.dumps(
                    {
                        'schema_version': 1,
                        'name': 'Example',
                        'colors': {'background': '#abcdef'},
                    }
                )
            )
            output = Path(directory) / 'view.html'
            with patch('sys.stdout', new=io.StringIO()):
                main(
                    [
                        'view',
                        '--data-root',
                        str(root),
                        '--visual-theme',
                        str(theme),
                        '--output',
                        str(output),
                    ]
                )
            self.assertIn('--background: #abcdef;', output.read_text())
            self.assertEqual(before, {p: p.read_bytes() for p in root.rglob('*') if p.is_file()})


class KnowledgeThemeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / 'data'
        self.saved = create_note(self.root, 'An existing note.')
        self.env = {
            **os.environ,
            'KNOT_CONFIG': str(self.base / 'config.json'),
            'PYTHONPATH': str(PROJECT / 'src'),
            'PYTHONDONTWRITEBYTECODE': '1',
        }
        self.env.pop('KNOT_DATA_ROOT', None)
        self.cli('dataset', 'use', str(self.root))

    def cli(self, *args, ok=True):
        result = subprocess.run(
            [sys.executable, '-m', 'knot.interfaces.note_cli', *args],
            cwd=self.base,
            env=self.env,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode == 0, ok, result.stderr)
        self.assertNotIn('Traceback', result.stderr)
        return result

    def test_add_is_repeatable_and_available_to_note_navigation(self):
        arguments = (
            'themes',
            'add',
            'concepts',
            '--label',
            'Concepts',
            '--description',
            'Ideas and mental models.',
            '--keyword',
            'concept',
        )
        self.cli(*arguments)
        catalogue = self.root / 'organisation/catalogue.json'
        before = catalogue.read_bytes()
        self.cli(*arguments)
        self.assertEqual(catalogue.read_bytes(), before)
        definitions = json.loads(self.cli('themes', 'list').stdout)
        self.assertEqual(definitions[0]['id'], 'concepts')
        navigation = self.base / 'navigation.json'
        navigation.write_text(
            json.dumps(
                {
                    'themes': [{'id': 'concepts', 'label': 'Concepts'}],
                    'links': [],
                    'declarations': [],
                }
            )
        )
        body = self.base / 'note.md'
        body.write_text('A useful concept.')
        saved = json.loads(self.cli('add', str(body), '--navigation', str(navigation)).stdout)
        self.assertEqual(
            read_note(self.root, saved['note'])['navigation']['themes'][0]['id'], 'concepts'
        )
        self.assertEqual(
            read_note(self.root, self.saved['note'])['revision'], self.saved['revision']
        )

    def test_import_is_atomic_and_preserves_existing_catalogue_fields(self):
        path = self.root / 'organisation/catalogue.json'
        path.parent.mkdir()
        existing = {
            'themes': [{'id': 'existing', 'label': 'Existing', 'keywords': []}],
            'entity_types': {'Person': ['Example']},
            'overrides': {},
            'entity_type_overrides': {'urn:example:one': ['Person']},
        }
        path.write_text(json.dumps(existing))
        reviews = path.with_name('theme-reviews.json')
        reviews.write_text('Preserve existing review bytes')
        pack = self.base / 'themes.json'
        pack.write_text(
            json.dumps(
                [
                    {'id': 'concepts', 'label': 'Concepts', 'keywords': []},
                    {'id': 'existing', 'label': 'Different meaning', 'keywords': []},
                ]
            )
        )
        before = path.read_bytes()
        self.cli('themes', 'import', str(pack), ok=False)
        self.assertEqual(path.read_bytes(), before)
        pack.write_text(json.dumps([{'id': 'concepts', 'label': 'Concepts', 'keywords': []}]))
        self.cli('themes', 'import', str(pack))
        actual = json.loads(path.read_bytes())
        self.assertEqual(
            {k: v for k, v in actual.items() if k != 'themes'},
            {k: v for k, v in existing.items() if k != 'themes'},
        )
        self.assertEqual([t['id'] for t in actual['themes']], ['existing', 'concepts'])
        self.assertEqual(reviews.read_text(), 'Preserve existing review bytes')

    def test_invalid_definitions_do_not_create_a_catalogue(self):
        for definition in (
            {'id': '../escape', 'label': 'Invalid'},
            {'id': 'valid', 'label': ' '},
            {'id': 'valid', 'label': 'Valid', 'keywords': 'not a list'},
            {'id': 'valid', 'label': 'Valid', 'include_frameworks': 'yes'},
            {'id': 'valid', 'label': 'Valid', 'description': []},
        ):
            with self.subTest(definition=definition):
                pack = self.base / 'themes.json'
                pack.write_text(json.dumps([definition]))
                self.cli('themes', 'import', str(pack), ok=False)
                self.assertFalse((self.root / 'organisation/catalogue.json').exists())

    def test_keyword_theme_rebuild_preserves_assertions_and_review_status(self):
        from test_visualise import write_account_fixture

        from knot.graph.knowledge import entries, rebuild
        from knot.graph.query import load_store
        from knot.reviewing.state import fingerprint

        root = self.base / 'other-dataset'
        write_account_fixture(root)
        store = load_store(root / 'graph')
        before = {r['id']: (r['status'], fingerprint(store, r['id'])) for r in entries(store)}
        sources = {p: p.read_bytes() for p in root.rglob('*') if p.is_file()}
        self.cli(
            '--data-root',
            str(root),
            'themes',
            'add',
            'concepts',
            '--label',
            'Concepts',
            '--keyword',
            'rollout',
        )
        rebuild(root)
        store = load_store(root / 'graph')
        themed = entries(store, themes=['concepts'])
        self.assertTrue(themed)
        self.assertEqual(
            before, {r['id']: (r['status'], fingerprint(store, r['id'])) for r in entries(store)}
        )
        self.assertTrue(all(r['themes'][0]['status'] == 'Unreviewed' for r in themed))
        self.assertTrue(all(p.read_bytes() == body for p, body in sources.items()))
        self.assertFalse((self.root / 'organisation/catalogue.json').exists())
