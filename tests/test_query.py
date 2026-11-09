import tempfile
import unittest
from pathlib import Path

from pyoxigraph import RdfFormat, Store

from knot.query import load_store


class QueryTests(unittest.TestCase):
    def test_conflicting_accepted_identities_are_rejected(self):
        from knot.query import apply_identities

        store = Store()
        store.load(
            input="""PREFIX k: <urn:knot:vocab:>
            GRAPH <urn:knot:metadata> {
                <urn:proposal:one> k:sourceEntity <urn:source>;
                    k:entity <urn:person:one>; k:reviewStatus k:Accepted.
                <urn:proposal:two> k:sourceEntity <urn:source>;
                    k:entity <urn:person:two>; k:reviewStatus k:Accepted.
            }""",
            format=RdfFormat.TRIG,
        )
        with self.assertRaisesRegex(ValueError, 'Conflicting accepted identity'):
            apply_identities(store)

    def test_directory_loads_imported_and_review_graphs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'knowledge.trig').write_text('<urn:import> { <urn:a> <urn:p> <urn:b> }')
            (root / 'review.trig').write_text('<urn:review> { <urn:a> <urn:p> <urn:c> }')
            self.assertEqual(len(load_store(root)), 2)
            self.assertEqual(len(load_store(root / 'review.trig')), 1)

    def test_empty_directory_is_an_error(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                load_store(Path(directory))
