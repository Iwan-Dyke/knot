import json
import shutil
import subprocess
import tempfile
import unittest
from html import escape
from pathlib import Path
from unittest.mock import patch

from knot.curating.provenance import source_pin
from knot.writing.notes import create_note, save_note
from knot.writing.themes import add_themes


class LibraryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'data'
        # Storage/projection tests do not require the optional converter. Its real
        # sandbox and output are exercised separately below and in browser tests.
        renderer = patch(
            'knot.presentation.library_snapshot.render_markup',
            side_effect=lambda body, format: '<pre>' + escape(body) + '</pre>',
        )
        renderer.start()
        self.addCleanup(renderer.stop)

    def snapshot(self):
        from knot.presentation.library import build_snapshot

        return build_snapshot(self.root)

    def example_builder(self):
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            'example_data', Path(__file__).resolve().parents[1] / 'scripts/example_data.py'
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.build_examples

    def test_isolated_notes_overlapping_themes_and_backlinks_share_identity(self):
        add_themes(
            self.root,
            [
                {'id': name, 'label': name.title(), 'keywords': []}
                for name in ('learning', 'projects')
            ],
        )
        isolated = create_note(self.root, 'An isolated question.')
        linked = create_note(
            self.root,
            '# A thought\n\nRead both ways.',
            title='A thought',
            navigation={
                'themes': [{'id': n, 'label': n.title()} for n in ('learning', 'projects')],
                'links': [{'note': isolated['note'], 'reason': 'An open question.'}],
                'declarations': [],
            },
        )
        before = {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        snapshot = self.snapshot()
        self.assertEqual(set(snapshot['notes']), {isolated['note'], linked['note']})
        self.assertEqual(snapshot['notes'][isolated['note']]['title'], 'Untitled note')
        self.assertEqual(len(snapshot['notes'][linked['note']]['navigation']['themes']), 2)
        self.assertEqual(len(snapshot['relations']), 1)
        self.assertEqual(snapshot['relations'][0]['to'], isolated['note'])
        self.assertEqual(snapshot['relations'][0]['kind'], 'link')
        self.assertEqual(snapshot['bodies'][linked['body_sha256']]['text'], linked['body'])
        self.assertEqual(before, {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()})

    def test_history_embeds_current_and_cited_bodies_and_preserves_authors(self):
        old = create_note(self.root, 'Original evidence.', title='Account', author='Source author')
        middle = save_note(
            self.root, old['note'], 'Intermediate wording.', expected=old['revision']
        )
        current = save_note(self.root, old['note'], 'Current wording.', expected=middle['revision'])
        curated = create_note(
            self.root,
            'The account reports evidence.',
            title='Restatement',
            author='Curator',
            agent='Test',
            derivation={
                'method': 'faithful_restatement',
                'qualification': 'One account only.',
                'sources': [source_pin(self.root, old['revision'], old['body'], 0)],
            },
        )
        snapshot = self.snapshot()
        self.assertEqual(snapshot['notes'][old['note']]['revision'], current['revision'])
        self.assertEqual(snapshot['notes'][curated['note']]['author'], 'Curator')
        self.assertEqual(snapshot['sources'][old['revision']]['author'], 'Source author')
        self.assertIn(old['body_sha256'], snapshot['bodies'])
        self.assertNotIn(middle['body_sha256'], snapshot['bodies'])
        self.assertEqual(len(snapshot['notes'][old['note']]['history']), 3)

    def test_failed_or_concurrent_export_preserves_previous_artifact(self):
        from knot.presentation.library import export_library

        create_note(self.root, 'Saved text.')
        output = Path(self.temp.name) / 'library.html'
        output.write_text('Previous valid export')
        with patch('knot.presentation.library.input_signature', side_effect=['before', 'after']):
            with self.assertRaisesRegex(ValueError, 'changed'):
                export_library(self.root, output)
        self.assertEqual(output.read_text(), 'Previous valid export')

    def test_corrupt_evidence_blocks_export(self):
        note = create_note(self.root, 'Evidence.')
        (self.root / note['body_path']).write_text('Tampered')
        with self.assertRaises(ValueError):
            self.snapshot()

    def test_associated_entity_uses_verified_preferred_name_without_claims(self):
        entity = 'urn:knot:entity:00000000-0000-4000-8000-000000000121'
        note = create_note(
            self.root,
            'Specific project name.',
            navigation={
                'themes': [],
                'links': [],
                'declarations': [
                    {
                        'id': entity,
                        'label': 'Old heading',
                        'type': 'Project',
                        'quote': 'Specific project name',
                        'offset': 0,
                    }
                ],
            },
        )
        path = self.root / 'curation/entity-labels.json'
        path.parent.mkdir()
        path.write_text(
            json.dumps(
                {
                    'schema_version': 1,
                    'profiles': [
                        {
                            'entity': entity,
                            'preferred_label': 'Specific project name',
                            'aliases': ['Old heading'],
                            'agent': 'Test',
                            'reason': 'Source-supported display name.',
                            'sources': [
                                source_pin(self.root, note['revision'], 'Specific project name', 0)
                            ],
                        }
                    ],
                }
            )
        )
        snapshot = self.snapshot()
        self.assertEqual(snapshot['entities'][entity]['title'], 'Specific project name')
        self.assertIn('Old heading', snapshot['entities'][entity]['aliases'])

    def test_examples_supply_verified_claims_history_and_no_source_mutations(self):
        build_examples = self.example_builder()
        ids = build_examples(self.root)
        before = {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        snapshot = self.snapshot()
        self.assertGreaterEqual(len(snapshot['claims']), 8)
        self.assertGreaterEqual(len(snapshot['notes']), 8)
        self.assertGreaterEqual(len(snapshot['entities']), 6)
        predicates = {c['predicate'].rsplit(':', 1)[-1] for c in snapshot['claims'].values()}
        self.assertTrue({'dependsOn', 'decisionAbout', 'workedOn', 'madeDecision'} <= predicates)
        isolated = ids['isolated']
        self.assertFalse(any(isolated in (r['from'], r['to']) for r in snapshot['relations']))
        reached = {ids['project']}
        while True:
            expanded = reached | {
                endpoint
                for r in snapshot['relations']
                if r['from'] in reached or r['to'] in reached
                for endpoint in (r['from'], r['to'])
            }
            if expanded == reached:
                break
            reached = expanded
        self.assertEqual(reached, (set(snapshot['notes']) | set(snapshot['entities'])) - {isolated})
        self.assertEqual(
            {c['status'] for c in snapshot['claims'].values()}, {'Accepted', 'Unreviewed'}
        )
        self.assertIn('urn:knot:assertion:example-suggestion', snapshot['historical_claims'])
        self.assertNotIn('urn:knot:assertion:example-suggestion', snapshot['claims'])
        self.assertIn(ids['cited_revision'], snapshot['sources'])
        self.assertEqual(before, {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()})
        with self.assertRaisesRegex(ValueError, 'empty'):
            build_examples(self.root)

    def test_reviewed_identity_has_one_entity_and_retains_historical_endpoints(self):
        from knot.graph.rdf import VOCAB, Dataset

        ids = self.example_builder()(self.root)
        canonical = 'urn:knot:entity:00000000-0000-4000-8000-000000000103'
        mapping = Dataset()
        mapping.add('urn:identity:example', VOCAB + 'sourceEntity', ids['project'])
        mapping.add('urn:identity:example', VOCAB + 'entity', canonical)
        mapping.add('urn:identity:example', VOCAB + 'reviewStatus', VOCAB + 'Accepted')
        (self.root / 'graph/identity.trig').write_text(mapping.text())
        before = {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        snapshot = self.snapshot()
        self.assertIn(canonical, snapshot['entities'])
        self.assertIn(ids['concept'], snapshot['entities'])
        self.assertNotIn(ids['project'], snapshot['entities'])
        self.assertEqual(snapshot['notes'][ids['garden']]['entities'], [canonical])
        historical = snapshot['historical_claims']['urn:knot:assertion:example-suggestion']
        self.assertEqual(historical['subject'], ids['project'])
        self.assertEqual(historical['display_subject'], canonical)
        self.assertEqual(before, {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()})

    def test_export_is_self_contained_and_does_not_bootstrap_a_network(self):
        from knot.presentation.library import export_library

        note = create_note(
            self.root,
            '</script><script>window.injected=true</script> KNOT_NOTICES KNOT_DATA /* GRAPH_FILTERS */',
        )
        output = Path(self.temp.name) / 'library.html'
        snapshot = export_library(self.root, output)
        html = output.read_text()
        payload = html.split('<script id="library-data" type="application/json">')[1].split(
            '</script>'
        )[0]
        self.assertEqual(json.loads(payload)['notes'][note['note']]['revision'], note['revision'])
        self.assertNotIn('</script>', payload)
        self.assertEqual(json.loads(payload)['bodies'][note['body_sha256']]['text'], note['body'])
        self.assertIn('Content-Security-Policy', html)
        self.assertNotIn('<script src=', html)
        self.assertEqual(
            snapshot['manifest']['boundary'], 'owner-local; all included content is disclosed'
        )

    def test_initial_record_is_verified_export_metadata(self):
        from knot.presentation.library import export_library

        note = create_note(self.root, 'A synthetic starting record.')
        before = {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        output = Path(self.temp.name) / 'library.html'
        model = export_library(self.root, output, initial_record=note['note'])
        self.assertEqual(model['initial_record'], note['note'])
        html = output.read_bytes()
        with self.assertRaisesRegex(ValueError, 'Initial record'):
            export_library(self.root, output, initial_record='urn:example:missing')
        self.assertEqual(output.read_bytes(), html)
        self.assertEqual(before, {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()})


class LibraryRuntimeTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'), 'Library model checks require Node.js')
    def test_library_navigation_and_focused_graph_model(self):
        subprocess.run(
            ['node', str(Path(__file__).resolve().parents[1] / 'scripts/test_library.cjs')],
            check=True,
            capture_output=True,
            text=True,
        )

    def test_missing_converter_has_an_actionable_error(self):
        from knot.presentation.markup import render_markup

        with patch('knot.presentation.markup.shutil.which', return_value=None):
            with self.assertRaisesRegex(ValueError, 'Install Pandoc separately'):
                render_markup('Example note', 'markdown')


@unittest.skipUnless(shutil.which('pandoc'), 'Pandoc is needed for rich rendering integration')
class MarkupTests(unittest.TestCase):
    def test_markdown_and_org_render_readably(self):
        from knot.presentation.markup import render_markup

        for fmt, body in [
            ('markdown', '# Heading\n\n**Strong**\n\n- One\n- Two'),
            ('org', '* Heading\n\n*Strong*\n\n- One\n- Two'),
        ]:
            with self.subTest(format=fmt):
                html = render_markup(body, fmt)
                self.assertIn('<h1', html)
                self.assertIn('<strong>Strong</strong>', html)
                self.assertIn('<li>', html)

    def test_hostile_markup_cannot_embed_resources_or_executable_html(self):
        from knot.presentation.markup import render_markup

        body = '<script>alert(1)</script>\n\n![image](https://example.invalid/pixel)\n\n[bad](javascript:alert%281%29)\n\n[good](https://example.org)'
        html = render_markup(body, 'markdown')
        self.assertNotIn('<script', html)
        self.assertNotIn('<img', html)
        self.assertNotIn('href="javascript:', html)
        self.assertIn('href="https://example.org"', html)

    def test_org_includes_cannot_read_files(self):
        from knot.presentation.markup import render_markup

        with tempfile.TemporaryDirectory() as temp:
            secret = Path(temp) / 'secret.txt'
            secret.write_text('UNIQUE_FILE_CONTENT_NOT_AUTHORISED')
            html = render_markup(f'* Heading\n#+INCLUDE: "{secret}"\n', 'org')
            self.assertNotIn('UNIQUE_FILE_CONTENT_NOT_AUTHORISED', html)


if __name__ == '__main__':
    unittest.main()
