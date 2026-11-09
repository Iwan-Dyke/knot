import json
import unittest

import test_migrate
import test_review_provenance

from knot.migrate import migrate
from knot.rdf import VOCAB
from knot.review import read_events


class CurationBoundaryTests(unittest.TestCase):
    def migration_fixture(self):
        fixture = test_migrate.MigrationTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        return fixture

    def review_fixture(self):
        fixture = test_review_provenance.ReviewProvenanceTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.fixture()
        return fixture

    def files(self, root):
        return {p.relative_to(root): p.read_bytes() for p in root.rglob('*') if p.is_file()}

    def test_invalid_correction_predicate_never_writes_a_review_event(self):
        fixture = self.review_fixture()
        before = self.files(fixture.root)
        for predicate in (VOCAB + 'notDefined', VOCAB + 'currentRevision'):
            with self.subTest(predicate=predicate), self.assertRaises(ValueError):
                fixture.decide('correct', replacement=fixture.replacement(predicate=predicate))
            self.assertEqual(self.files(fixture.root), before)
        self.assertEqual(read_events(fixture.root), [])

    def test_correction_literal_flag_must_be_boolean(self):
        fixture = self.review_fixture()
        before = self.files(fixture.root)
        for invalid in ('false', 1, None):
            with self.subTest(flag=invalid), self.assertRaises(ValueError):
                fixture.decide(
                    'correct', replacement=fixture.replacement(object_is_literal=invalid)
                )
            self.assertEqual(self.files(fixture.root), before)

    def test_source_backed_framework_definition_correction_remains_available(self):
        fixture = self.review_fixture()
        event = fixture.decide(
            'correct',
            replacement=fixture.replacement(
                predicate='http://www.w3.org/2004/02/skos/core#definition',
                object='The source describes planned work.',
                object_label='The source describes planned work.',
                object_is_literal=True,
            ),
        )
        self.assertEqual(len(read_events(fixture.root)), 1)
        self.assertIn('replacement_id', event)

    def test_invalid_imported_candidate_does_not_write_extracted_text(self):
        fixture = self.migration_fixture()
        fixture.claim['quote'] = 'An invented quotation.'
        fixture.claim_path.write_text(json.dumps([fixture.claim]))
        before = self.files(fixture.root)
        with self.assertRaisesRegex(ValueError, 'quote'):
            migrate(fixture.root)
        self.assertEqual(self.files(fixture.root), before)

    def test_invalid_framework_does_not_publish_any_migration_output(self):
        fixture = self.migration_fixture()
        (fixture.root / 'migration/frameworks.json').write_text(
            json.dumps({'frameworks': [], 'active_framework': 'unknown'})
        )
        before = self.files(fixture.root)
        with self.assertRaisesRegex(ValueError, 'framework'):
            migrate(fixture.root)
        self.assertEqual(self.files(fixture.root), before)

    def test_imported_and_corrected_assertions_share_the_domain_vocabulary(self):
        fixture = self.migration_fixture()
        fixture.claim['predicate'] = 'used'
        fixture.claim_path.write_text(json.dumps([fixture.claim]))
        self.assertEqual(migrate(fixture.root)['summary']['candidate_assertions'], 1)

    def test_navigation_property_is_not_an_imported_domain_relation(self):
        fixture = self.migration_fixture()
        fixture.claim['predicate'] = 'currentRevision'
        fixture.claim_path.write_text(json.dumps([fixture.claim]))
        before = self.files(fixture.root)
        with self.assertRaises(ValueError):
            migrate(fixture.root)
        self.assertEqual(self.files(fixture.root), before)


if __name__ == '__main__':
    unittest.main()
