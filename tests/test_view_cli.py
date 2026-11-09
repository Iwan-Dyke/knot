import contextlib
import io
import json
import os
import subprocess
import tempfile
import unittest
from html import escape
from pathlib import Path
from unittest.mock import patch

from knot.interfaces.note_cli import main
from knot.writing.notes import create_note


class ViewCliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.root = self.directory / 'selected'
        create_note(self.root, 'A saved thought.', title='Saved thought')
        renderer = patch(
            'knot.presentation.library_snapshot.render_markup',
            side_effect=lambda body, format: '<pre>' + escape(body) + '</pre>',
        )
        renderer.start()
        self.addCleanup(renderer.stop)
        theme = patch('knot.presentation.library.selected_theme', return_value='matrix')
        theme.start()
        self.addCleanup(theme.stop)

    def call(self, *arguments):
        with contextlib.redirect_stdout(io.StringIO()):
            main(list(arguments))

    def test_view_opens_one_file_containing_both_graph_and_library(self):
        with patch('knot.presentation.library.open_view') as opened:
            self.call('--data-root', str(self.root), 'view')
        output = self.root / 'views/library.html'
        opened.assert_called_once_with(output)
        html = output.read_text()
        for marker in ('id="view-graph"', 'id="view-library"', 'Saved thought'):
            self.assertIn(marker, html)

    def test_export_only_and_explicit_open_are_supported(self):
        output = self.directory / 'export.html'
        with patch('knot.presentation.library.open_view') as opened:
            self.call('view', '--data-root', str(self.root), '--output', str(output), '--no-open')
            opened.assert_not_called()
            self.assertTrue(output.exists())
            self.call('view', '--data-root', str(self.root), '--open')
            opened.assert_called_once()

    def test_example_ignores_selected_dataset_and_preserves_its_files_and_config(self):
        config = self.directory / 'config.json'
        config.write_text(json.dumps({'schema_version': 1, 'data_root': str(self.root)}))
        before = {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        config_before = config.read_bytes()
        demo = self.directory / 'demo'
        demo.mkdir()
        output = self.directory / 'example.html'
        with (
            patch.dict(os.environ, {'KNOT_DATA_ROOT': str(self.root), 'KNOT_CONFIG': str(config)}),
            patch('knot.presentation.library.tempfile.mkdtemp', return_value=str(demo)),
            patch('knot.presentation.library.open_view') as opened,
        ):
            self.call('view', 'example', '--output', str(output))
        opened.assert_called_once_with(output)
        html = output.read_text()
        self.assertIn('Community garden plan', html)
        payload = html.split('<script id="library-data" type="application/json">')[1].split(
            '</script>'
        )[0]
        model = json.loads(payload)
        self.assertEqual(
            model['entities'][model['initial_record']]['title'], 'Community garden project'
        )
        self.assertGreaterEqual(
            sum(model['initial_record'] in (r['from'], r['to']) for r in model['relations']), 5
        )
        self.assertNotIn('Saved thought', html)
        self.assertEqual(before, {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()})
        self.assertEqual(config.read_bytes(), config_before)

    def test_example_rejects_an_explicit_dataset_before_creating_files(self):
        with (
            patch('knot.presentation.library.tempfile.mkdtemp') as temporary,
            contextlib.redirect_stderr(io.StringIO()),
            self.assertRaises(SystemExit) as error,
        ):
            self.call('view', 'example', '--data-root', str(self.root))
        self.assertEqual(error.exception.code, 2)
        temporary.assert_not_called()

    def test_example_search_override_starts_with_search_instead_of_a_selected_record(self):
        demo = self.directory / 'demo'
        demo.mkdir()
        output = self.directory / 'search.html'
        with patch('knot.presentation.library.tempfile.mkdtemp', return_value=str(demo)):
            self.call(
                'view', 'example', '--focus', 'readiness', '--output', str(output), '--no-open'
            )
        model = json.loads(
            output.read_text()
            .split('<script id="library-data" type="application/json">')[1]
            .split('</script>')[0]
        )
        self.assertEqual(model['initial_search'], 'readiness')
        self.assertNotIn('initial_record', model)

    def test_legacy_view_remains_an_explicit_option(self):
        with patch('knot.presentation.visualise.open_view') as opened:
            self.call('view', '--legacy', '--data-root', str(self.root), '--visual-theme', 'matrix')
        opened.assert_called_once_with(self.root / 'views/graph.html')

    def test_initial_focus_is_search_metadata_without_removing_knowledge(self):
        with patch('knot.presentation.library.open_view'):
            self.call('view', 'different search', '--data-root', str(self.root))
        html = (self.root / 'views/library.html').read_text()
        payload = html.split('<script id="library-data" type="application/json">')[1].split(
            '</script>'
        )[0]
        model = json.loads(payload)
        self.assertEqual(model['initial_search'], 'different search')
        self.assertEqual(len(model['notes']), 1)

    def test_just_visualise_routes_to_the_same_command(self):
        result = subprocess.run(
            ['just', '--dry-run', 'visualise', 'example', '--no-open'],
            cwd=Path(__file__).resolve().parents[1],
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertIn('knot.interfaces.view_cli', result.stderr)


if __name__ == '__main__':
    unittest.main()
