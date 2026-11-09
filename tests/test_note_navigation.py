import json
import tempfile
import unittest
from pathlib import Path

from knot.notes import create_note, read_note, save_note
from knot.query import load_store
from knot.retrieval import lookup


class NavigationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'organisation').mkdir()
        (self.root / 'organisation/catalogue.json').write_text(
            json.dumps({'themes': [{'id': 'learning', 'label': 'Learning', 'keywords': []}]})
        )

    def test_add_first_link_to_note_without_navigation(self):
        first = create_note(self.root, 'Original writing', title='Original')
        target = create_note(self.root, 'Related writing')
        self.assertNotIn('navigation', first)
        nav = {
            'themes': [],
            'links': [{'note': target['note'], 'reason': 'Related idea'}],
            'declarations': [],
        }
        saved = save_note(
            self.root,
            first['note'],
            first['body'],
            expected=first['revision'],
            navigation=nav,
            agent='Test',
        )
        self.assertEqual(saved['navigation'], nav)
        self.assertEqual(saved['body_sha256'], first['body_sha256'])
        self.assertEqual(saved['parent'], first['revision'])
        self.assertEqual(read_note(self.root, first['note'], revision=first['revision']), first)
        again = save_note(
            self.root,
            first['note'],
            saved['body'],
            expected=saved['revision'],
            navigation=nav,
            agent='Test',
        )
        self.assertEqual(again['revision'], saved['revision'])

    def test_navigation_survives_edits_and_projects_real_links(self):
        target = create_note(self.root, 'Earlier thought', title='Earlier')
        navigation = {
            'themes': [{'id': 'learning', 'label': 'Learning'}],
            'links': [{'note': target['note'], 'reason': 'Extends my earlier thought'}],
            'declarations': [],
        }
        first = create_note(self.root, 'New thinking', navigation=navigation)
        second = save_note(
            self.root, first['note'], 'New thinking revised', expected=first['revision']
        )
        self.assertEqual(second['navigation'], navigation)
        self.assertEqual(
            read_note(self.root, first['note'], revision=first['revision'])['body'], 'New thinking'
        )
        store = load_store(self.root / 'graph')
        self.assertTrue(
            bool(
                store.query(
                    f'ASK {{ GRAPH <urn:knot:notes> {{ <{first["note"]}> '
                    f'<urn:knot:vocab:linkedNote> <{target["note"]}> }} }}'
                )
            )
        )
        cleared = save_note(
            self.root,
            first['note'],
            second['body'],
            expected=second['revision'],
            navigation={'themes': [], 'links': [], 'declarations': []},
        )
        self.assertEqual(cleared['navigation']['themes'], [])

    def test_first_link_preserves_curated_derivation(self):
        from knot.provenance import source_pin

        source = create_note(self.root, 'Original account', author='Owner')
        derivation = {
            'method': 'faithful_restatement',
            'qualification': 'An attributed account, not independently verified.',
            'sources': [source_pin(self.root, source['revision'], 'Original account', 0)],
        }
        first = create_note(
            self.root,
            'The source records an account.',
            title='Account',
            author='Test',
            agent='Test',
            derivation=derivation,
        )
        nav = {
            'themes': [],
            'links': [{'note': source['note'], 'reason': 'Original evidence'}],
            'declarations': [],
        }
        saved = save_note(
            self.root,
            first['note'],
            first['body'],
            expected=first['revision'],
            navigation=nav,
            agent='Test',
        )
        self.assertEqual(saved['derivation'], first['derivation'])
        self.assertEqual(saved['body_sha256'], first['body_sha256'])
        self.assertEqual(saved['schema_version'], 4)
        self.assertEqual(read_note(self.root, source['note'])['revision'], source['revision'])

    def test_declared_entities_are_searchable_and_reusable(self):
        eid = 'urn:knot:entity:00000000-0000-4000-8000-000000000001'
        declared = {
            'id': eid,
            'label': 'Test concept',
            'type': 'Concept',
            'quote': 'Test concept',
            'offset': 0,
        }
        first = create_note(
            self.root,
            'Test concept is useful.',
            navigation={'themes': [], 'links': [], 'declarations': [declared]},
        )
        self.assertIn(eid, [c['id'] for c in lookup(self.root, 'Test concept')['candidates']])
        second = create_note(self.root, 'Another thought', entities=[eid])
        self.assertEqual(second['entities'], [eid])
        self.assertEqual(first['schema_version'], 4)

    def test_invalid_navigation_writes_nothing(self):
        with self.assertRaises(ValueError):
            create_note(
                self.root,
                'Text',
                navigation={
                    'themes': [{'id': 'missing', 'label': 'Missing'}],
                    'links': [],
                    'declarations': [],
                },
            )
        self.assertFalse((self.root / 'notes').exists())
