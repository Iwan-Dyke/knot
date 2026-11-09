import tempfile
import unittest
from html import unescape
from pathlib import Path
from unittest.mock import patch

from pyvis.network import Network

from knot.presentation.library import render_snapshot
from knot.presentation.viewer_assets import ASSETS
from knot.presentation.visualise import write_view


class ViewerLicenceTests(unittest.TestCase):
    def legacy_html(self, output):
        network = Network(directed=True, cdn_resources='in_line', filter_menu=True)
        network.add_node('synthetic', label='Synthetic note')
        write_view(network, output)
        return output.read_text()

    def test_both_exports_include_bundled_component_notices(self):
        with tempfile.TemporaryDirectory() as directory:
            for html in (render_snapshot({}), self.legacy_html(Path(directory) / 'graph.html')):
                text = unescape(html)
                for filename in (
                    'knot-license.txt',
                    'vis-network-license.txt',
                    'vis-network-dependencies-license.txt',
                ):
                    self.assertTrue(
                        (ASSETS / filename).read_text() in text,
                        f'Incomplete notice file: {filename}',
                    )
                for attribution in (
                    'KNOT authors',
                    'Almende B.V.',
                    'Sebastian McKenzie and other contributors',
                    'Denis Pushkarev',
                    'Facebook, Inc.',
                    'Microsoft Corporation.',
                    'Component contributors',
                    'NAVER Corp.',
                    'Robert Kieffer and other contributors',
                    'Marco Ziccardi',
                    'Andrei Mackenzie',
                    'Johannes Baag',
                ):
                    with self.subTest(attribution=attribution):
                        self.assertTrue(attribution in text, f'Missing notice: {attribution}')

    def test_legacy_has_complete_pyvis_notice_and_excludes_unused_menu_assets(self):
        from importlib.metadata import distribution

        pyvis_notice = distribution('pyvis').locate_file('pyvis-0.3.2.dist-info/LICENSE_BSD.txt')
        with tempfile.TemporaryDirectory() as directory:
            html = self.legacy_html(Path(directory) / 'graph.html')
        self.assertTrue(pyvis_notice.read_text() in unescape(html), 'Missing complete PyVis notice')
        self.assertFalse('Tom Select' in html, 'Unused Tom Select asset was embedded')
        self.assertFalse('new TomSelect' in html, 'Unused Tom Select widget was enabled')

    def test_changed_embedded_assets_require_notice_review_before_export(self):
        read_text = Path.read_text
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'graph.html'
            output.write_text('previous export')
            for filename in ('vis-network.min.js', 'vis-network.css', 'template.html', 'utils.js'):

                def changed(path, *args, **kwargs):
                    text = read_text(path, *args, **kwargs)
                    return text + '\n/* changed asset */' if path.name == filename else text

                with self.subTest(filename=filename), patch.object(Path, 'read_text', changed):
                    if filename.startswith('vis-network'):
                        with self.assertRaisesRegex(ValueError, 'licence.*review'):
                            render_snapshot({})
                    with self.assertRaisesRegex(ValueError, 'licence.*review'):
                        self.legacy_html(output)
                self.assertEqual(output.read_text(), 'previous export')

    def test_changed_pyvis_version_requires_review(self):
        with patch('knot.presentation.viewer_assets.metadata.version', return_value='99.0'):
            with self.assertRaisesRegex(ValueError, 'licence.*review'):
                render_snapshot({})
            with tempfile.TemporaryDirectory() as directory:
                with self.assertRaisesRegex(ValueError, 'licence.*review'):
                    self.legacy_html(Path(directory) / 'graph.html')


if __name__ == '__main__':
    unittest.main()
