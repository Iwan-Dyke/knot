import json
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

from pyoxigraph import RdfFormat, Store

from knot.inventory import build_inventory, digest
from knot.migrate import migrate


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'sources').mkdir()
        self.text = (
            '#+title: Example\n\n* Decision\n:PROPERTIES:\n:ID: example\n:END:\nI selected Atlas.\n'
        )
        with ZipFile(self.root / 'sources/test.zip', 'w') as archive:
            archive.writestr('test/note.org', self.text)
        build_inventory(self.root)
        self.claim = {
            'source_sha256': digest(self.text.encode()),
            'quote': 'I selected Atlas.',
            'subject': 'Example author',
            'predicate': 'selected',
            'object': 'Atlas',
            'origin': 'explicit',
            'rationale': 'Explicit selection in source.',
        }
        self.claim_path = self.root / 'migration/curated-test.json'
        self.claim_path.write_text(json.dumps([self.claim]))

    def test_roundtrip_provenance_coverage_and_rerun(self):
        first = migrate(self.root)
        self.assertEqual(first['summary']['candidate_assertions'], 1)
        self.assertEqual(first['summary']['human_accepted_assertions'], 0)
        passages = first['revisions'][self.claim['source_sha256']]['passages']
        self.assertEqual(len(passages[1]['assertions']), 1)
        self.assertEqual(passages[0]['semantic_status'], 'pending')
        graph = self.root / 'graph/knowledge.trig'
        original = graph.read_bytes()
        self.assertEqual(first, migrate(self.root))
        self.assertEqual(original, graph.read_bytes())
        store = Store()
        store.load(path=graph, format=RdfFormat.TRIG)
        result = list(
            store.query(
                'SELECT ?a WHERE { GRAPH <urn:knot:metadata> { ?a <urn:knot:vocab:reviewStatus> <urn:knot:vocab:Unreviewed> }}'
            )
        )
        self.assertEqual(len(result), 1)
        # Aliases on a shared identity must not multiply evidence query rows.
        store.update(
            'INSERT { GRAPH <urn:knot:metadata> { ?s <http://www.w3.org/2000/01/rdf-schema#label> "Alias" }} WHERE { GRAPH <urn:knot:metadata> { ?s <http://www.w3.org/2000/01/rdf-schema#label> "Atlas" }}'
        )
        evidence_query = Path('queries/evidence.rq').read_text()
        self.assertEqual(len(list(store.query(evidence_query))), 1)
        loaded = Store()
        loaded.load(input=store.dump(format=RdfFormat.TRIG), format=RdfFormat.TRIG)
        self.assertEqual(set(store), set(loaded))

    def test_invalid_quote_rejected_before_graph_write(self):
        self.claim['quote'] = 'Invented quote'
        self.claim_path.write_text(json.dumps([self.claim]))
        with self.assertRaisesRegex(ValueError, 'quote'):
            migrate(self.root)
        self.assertFalse((self.root / 'graph/knowledge.trig').exists())

    def test_curation_directory_preserves_legacy_graph_and_ledger(self):
        first = migrate(self.root)
        graph = self.root / 'graph/knowledge.trig'
        original = graph.read_bytes()
        (self.root / 'curation').mkdir()
        self.claim_path.rename(self.root / 'curation' / self.claim_path.name)
        self.assertEqual(first, migrate(self.root))
        self.assertEqual(graph.read_bytes(), original)

    def test_new_dataset_records_current_curation_location(self):
        (self.root / 'curation').mkdir()
        self.claim_path.rename(self.root / 'curation' / self.claim_path.name)
        result = migrate(self.root)
        self.assertEqual(result['summary']['candidate_assertions'], 1)
        store = Store()
        store.load(path=self.root / 'graph/knowledge.trig', format=RdfFormat.TRIG)
        rows = list(
            store.query(
                'SELECT ?path WHERE { GRAPH <urn:knot:metadata> { '
                '?assertion <urn:knot:vocab:curationFile> ?path }}'
            )
        )
        self.assertEqual([r['path'].value for r in rows], ['curation/curated-test.json'])

    def test_split_curation_inputs_fail_before_writing_outputs(self):
        (self.root / 'curation').mkdir()
        (self.root / 'curation/entities.json').write_text('{"bindings": []}')
        with self.assertRaisesRegex(ValueError, 'split'):
            migrate(self.root)
        self.assertFalse((self.root / 'graph/knowledge.trig').exists())
        self.assertFalse((self.root / 'migration/text').exists())

    def test_framework_import_preserves_existing_reviews_and_reruns(self):
        from knot.query import load_store
        from knot.review import decide, inspect_assertion

        migrate(self.root)
        store = load_store(self.root / 'graph')
        target = list(
            store.query(
                'SELECT ?a WHERE { GRAPH <urn:knot:metadata> { ?a a <urn:knot:vocab:Assertion> }}'
            )
        )[0]['a'].value
        decide(self.root, target, 'accept', reviewer='Test', reason='Checked')
        inventory = json.loads((self.root / 'migration/inventory.json').read_text())
        entry = next(e for e in inventory['entries'] if e['status'] == 'verified')
        catalog = {
            'active_framework': 'product',
            'frameworks': [
                {
                    'key': 'product',
                    'title': 'Example framework',
                    'sha256': entry['sha256'],
                    'snapshot': entry['snapshot'],
                    'skills': [
                        {
                            'name': 'Decision-making',
                            'quote': 'I selected Atlas.',
                            'levels': {'Expert': 'I selected Atlas.'},
                            'requirements': {'G7': 'Expert'},
                            'requirements_quote': 'I selected Atlas.',
                        }
                    ],
                }
            ],
        }
        (self.root / 'curation').mkdir()
        self.claim_path.rename(self.root / 'curation' / self.claim_path.name)
        framework_path = self.root / 'curation/frameworks.json'
        framework_path.write_text(json.dumps(catalog))
        first = migrate(self.root)
        original = (self.root / 'graph/frameworks.trig').read_bytes()
        self.assertEqual(
            inspect_assertion(load_store(self.root / 'graph', history=True), target)['status'],
            'Accepted',
        )
        self.assertEqual(
            len(
                list(load_store(self.root / 'graph').query(Path('queries/evidence.rq').read_text()))
            ),
            1,
        )
        self.assertEqual(first, migrate(self.root))
        self.assertEqual(original, (self.root / 'graph/frameworks.trig').read_bytes())
        framework_path.unlink()
        with self.assertRaisesRegex(ValueError, 'catalogue missing'):
            migrate(self.root)
        catalog['frameworks'][0]['skills'][0]['quote'] = 'Invented'
        framework_path.write_text(json.dumps(catalog))
        with self.assertRaisesRegex(ValueError, 'quotation'):
            migrate(self.root)
        self.assertEqual(original, (self.root / 'graph/frameworks.trig').read_bytes())

    def test_reviewed_graph_changes_not_overwritten(self):
        migrate(self.root)
        graph = self.root / 'graph/knowledge.trig'
        graph.write_text(graph.read_text() + '\n# user edit\n')
        with self.assertRaisesRegex(ValueError, 'reconcile'):
            migrate(self.root)

    def test_changed_snapshot_rejected(self):
        ledger = json.loads((self.root / 'migration/inventory.json').read_text())
        (self.root / ledger['entries'][0]['snapshot']).write_text('tampered')
        with self.assertRaisesRegex(ValueError, 'Snapshot hash'):
            migrate(self.root)

    def test_changed_archive_requires_new_inventory(self):
        (self.root / 'sources/test.zip').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'Archive changed'):
            migrate(self.root)

    def test_retired_archive_rebuild_preserves_graph_and_reviews(self):
        from knot.query import load_store
        from knot.review import decide, inspect_assertion

        first = migrate(self.root)
        graph = self.root / 'graph/knowledge.trig'
        original = graph.read_bytes()
        target = next(
            assertion
            for passage in first['revisions'][self.claim['source_sha256']]['passages']
            for assertion in passage['assertions']
        )
        decide(self.root, target, 'accept', reviewer='Test', reason='Checked')
        ledger = self.root / 'migration/inventory.json'
        inventory = json.loads(ledger.read_text())
        inventory['archives'][0]['retired'] = True
        ledger.write_text(json.dumps(inventory))
        (self.root / 'sources/test.zip').unlink()
        build_inventory(self.root)
        self.assertEqual(first, migrate(self.root))
        self.assertEqual(graph.read_bytes(), original)
        self.assertEqual(
            inspect_assertion(load_store(self.root / 'graph'), target)['status'], 'Accepted'
        )
        (self.root / inventory['entries'][0]['snapshot']).unlink()
        with self.assertRaisesRegex(ValueError, 'Snapshot'):
            migrate(self.root)
        self.assertEqual(graph.read_bytes(), original)

    def test_missing_unretired_archive_blocks_rebuild(self):
        (self.root / 'sources/test.zip').unlink()
        with self.assertRaisesRegex(ValueError, 'Archive missing'):
            migrate(self.root)
        self.assertFalse((self.root / 'graph/knowledge.trig').exists())

    def test_same_name_does_not_merge_across_sources_without_binding(self):
        other = '* Elsewhere\nI selected Atlas.\n'
        with ZipFile(self.root / 'sources/other.zip', 'w') as archive:
            archive.writestr('other.org', other)
        build_inventory(self.root)
        second = {**self.claim, 'source_sha256': digest(other.encode())}
        self.claim_path.write_text(json.dumps([self.claim, second]))
        migrate(self.root)
        store = Store()
        store.load(path=self.root / 'graph/knowledge.trig', format=RdfFormat.TRIG)
        query = 'SELECT ?s WHERE { GRAPH <urn:knot:metadata> { ?s <http://www.w3.org/2000/01/rdf-schema#label> "Atlas" }}'
        self.assertEqual(len(list(store.query(query))), 2)

    def test_unreviewed_identity_proposal_cannot_create_shared_endpoint(self):
        other = '* Elsewhere\nI selected Atlas.\n'
        with ZipFile(self.root / 'sources/other.zip', 'w') as archive:
            archive.writestr('other.org', other)
        build_inventory(self.root)
        second = {**self.claim, 'source_sha256': digest(other.encode())}
        self.claim_path.write_text(json.dumps([self.claim, second]))
        bindings = [
            {
                'source_sha256': c['source_sha256'],
                'label': 'Atlas',
                'entity_id': 'urn:proposed:atlas',
                'rationale': 'Possible identity',
                'status': 'unreviewed',
            }
            for c in (self.claim, second)
        ]
        path = self.root / 'migration/entities.json'
        path.write_text(json.dumps({'bindings': bindings}))
        migrate(self.root)
        from knot.query import load_store
        from knot.review import decide

        store = load_store(self.root / 'graph')
        targets = [
            row['a'].value
            for row in store.query(
                'SELECT ?a WHERE { GRAPH <urn:knot:metadata> { ?a a <urn:knot:vocab:Assertion> }}'
            )
        ]
        for target in targets:
            decide(
                self.root,
                target,
                'accept',
                reviewer='Test',
                reason='Correct claim, identity unreviewed',
            )
        store = load_store(self.root / 'graph')
        endpoints = list(
            store.query(
                'SELECT DISTINCT ?o WHERE { GRAPH ?a { ?s <urn:knot:vocab:selected> ?o } GRAPH <urn:knot:metadata> { ?a <urn:knot:vocab:reviewStatus> <urn:knot:vocab:Accepted> }}'
            )
        )
        self.assertEqual(len(endpoints), 2)

        # Identity confirmation changes traversal, not the reviewed source assertions.
        original_events = {
            p.name: p.read_bytes() for p in (self.root / 'reviews/events').glob('*.trig')
        }
        for binding in bindings:
            binding['status'] = 'accepted'
        path.write_text(json.dumps({'bindings': bindings}))
        migrate(self.root)
        store = load_store(self.root / 'graph')
        endpoints = list(
            store.query('SELECT DISTINCT ?o WHERE { GRAPH ?a { ?s <urn:knot:vocab:selected> ?o }}')
        )
        self.assertEqual([row['o'].value for row in endpoints], ['urn:proposed:atlas'])
        historical = load_store(self.root / 'graph', history=True)
        self.assertEqual(
            len(
                list(
                    historical.query(
                        'SELECT DISTINCT ?o WHERE { GRAPH ?a { ?s <urn:knot:vocab:selected> ?o }}'
                    )
                )
            ),
            2,
        )
        self.assertEqual(
            original_events,
            {p.name: p.read_bytes() for p in (self.root / 'reviews/events').glob('*.trig')},
        )
        for binding in bindings:
            binding['status'] = 'unreviewed'
        path.write_text(json.dumps({'bindings': bindings}))
        migrate(self.root)
        self.assertEqual(
            len(
                list(
                    load_store(self.root / 'graph').query(
                        'SELECT DISTINCT ?o WHERE { GRAPH ?a { ?s <urn:knot:vocab:selected> ?o }}'
                    )
                )
            ),
            2,
        )
        decide(self.root, targets[0], 'reject', reviewer='Test', reason='Later review still works')
        self.assertEqual(
            len(
                list(
                    load_store(self.root / 'graph').query(
                        'SELECT ?s WHERE { GRAPH ?a { ?s <urn:knot:vocab:selected> ?o }}'
                    )
                )
            ),
            1,
        )
