import json
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

from pyoxigraph import NamedNode

from knot.access import AccessScope
from knot.inventory import build_inventory, digest
from knot.knowledge import rebuild
from knot.migrate import migrate
from knot.notes import create_note, read_note
from knot.query import identity_bindings, load_store
from knot.rdf import META, RDF_TYPE, VOCAB, identifier, one, values
from knot.retrieval import Policy, _prepare, lookup, retrieve
from knot.review import decide, fingerprint, inspect_assertion


class SemanticIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'sources').mkdir()
        self.text = '* Workflow model\nThe workshop agreed to separate the two workflows.\n'
        with ZipFile(self.root / 'sources/accounts.zip', 'w') as archive:
            archive.writestr('workshop.org', self.text)
        build_inventory(self.root)
        self.sha = digest(self.text.encode())
        self.source_entity = identifier('entity', self.sha + '\0Workflow model')
        self.canonical = 'urn:example:workflow-model'
        self.claim = {
            'source_sha256': self.sha,
            'quote': 'The workshop agreed to separate the two workflows.',
            'subject': 'Workflow model',
            'predicate': 'madeDecision',
            'object': 'Separate workflows',
            'origin': 'explicit',
            'rationale': 'Recorded workshop choice; deciding individuals unspecified.',
        }
        (self.root / 'migration/curated-test.json').write_text(json.dumps([self.claim]))
        migrate(self.root)
        store = load_store(self.root / 'graph', history=True, include_notes=False)
        self.aid = next(
            store.quads_for_pattern(None, NamedNode(RDF_TYPE), NamedNode(VOCAB + 'Assertion'), META)
        ).subject.value

    def bind(self, *, status='accepted', reviewer='Test curator', time='2026-11-05T12:00:00Z'):
        binding = {
            'source_sha256': self.sha,
            'label': 'Workflow model',
            'entity_id': self.canonical,
            'status': status,
            'rationale': 'The source records this identified workflow model.',
            'reviewer': reviewer,
            'time': time,
        }
        (self.root / 'migration/entities.json').write_text(json.dumps({'bindings': [binding]}))
        migrate(self.root)

    def test_identity_review_attribution_reaches_the_retrieval_receipt(self):
        self.bind()
        result = retrieve(self.root, self.canonical, Policy(max_chars=16000))
        receipt = next(iter(result['identities'].values()))
        self.assertEqual(receipt['reviewer'], 'Test curator')
        self.assertEqual(receipt['time'], '2026-11-05T12:00:00Z')

    def test_invalid_identity_review_attribution_does_not_publish_generated_output(self):
        graph = self.root / 'graph/knowledge.trig'
        original = graph.read_bytes()
        for reviewer, time in (('', '2026-11-05'), ('Reviewer', None)):
            with self.subTest(reviewer=reviewer, time=time):
                with self.assertRaisesRegex(ValueError, 'Invalid identity review'):
                    self.bind(reviewer=reviewer, time=time)
                self.assertEqual(graph.read_bytes(), original)

    def test_identity_projection_preserves_assertions_reviews_and_native_manifest(self):
        decide(
            self.root, self.aid, 'accept', reviewer='Reviewer', reason='Checked source fidelity.'
        )
        before = load_store(self.root / 'graph', history=True, include_notes=False)
        original_fingerprint = fingerprint(before, self.aid)
        note = create_note(self.root, 'Workflow reflection.\n', entities=[self.source_entity])
        immutable = {
            path: path.read_bytes()
            for prefix in ('notes', 'sources', 'reviews')
            for path in (self.root / prefix).rglob('*')
            if path.is_file() and path.name != '.lock'
        }
        self.bind()
        history = load_store(self.root / 'graph', history=True, include_notes=False)
        self.assertEqual(fingerprint(history, self.aid), original_fingerprint)
        self.assertEqual(inspect_assertion(history, self.aid)['status'], 'Accepted')
        original = next(history.quads_for_pattern(None, None, None, NamedNode(self.aid)))
        self.assertEqual(original.subject.value, self.source_entity)
        projected = load_store(self.root / 'graph', include_notes=False)
        self.assertEqual(
            next(projected.quads_for_pattern(None, None, None, NamedNode(self.aid))).subject.value,
            self.canonical,
        )
        prepared, _, _, _ = _prepare(self.root)
        header = json.loads(one(prepared, note['revision'], VOCAB + 'noteMetadata').value)
        self.assertEqual(header['navigation_entities'], [self.canonical])
        self.assertEqual(read_note(self.root, note['note'])['entities'], [self.source_entity])
        self.assertTrue(all(path.read_bytes() == body for path, body in immutable.items()))

    def test_unreviewed_identity_does_not_project_or_expose_denied_sources(self):
        self.bind(status='unreviewed')
        store = load_store(self.root / 'graph', include_notes=False)
        self.assertFalse(identity_bindings(store))
        self.assertEqual(
            lookup(self.root, 'Workflow model')['candidates'][0]['id'], self.source_entity
        )
        self.assertFalse(lookup(self.root, 'Workflow model', scope=AccessScope())['candidates'])

    def test_actor_free_correction_keeps_history_without_inventing_actor_or_acceptance(self):
        decide(self.root, self.aid, 'accept', reviewer='Reviewer', reason='Previous source review.')
        history = load_store(self.root / 'graph', history=True, include_notes=False)
        old_fingerprint = fingerprint(history, self.aid)
        original = next(history.quads_for_pattern(None, None, None, NamedNode(self.aid)))
        event = decide(
            self.root,
            self.aid,
            'correct',
            reviewer='Semantic curator',
            reason='The model is the decision subject, not an identified decision-maker.',
            replacement={
                'subject': original.object.value,
                'predicate': VOCAB + 'decisionAbout',
                'object': original.subject.value,
                'subject_label': 'Separate workflows',
                'object_label': 'Workflow model',
                'rationale': 'The decision concerns the workflow model; deciding individuals unspecified.',
            },
        )
        (self.root / 'organisation').mkdir()
        (self.root / 'organisation/catalogue.json').write_text(json.dumps({'themes': []}))
        rebuild(self.root)
        current = retrieve(self.root, self.source_entity, Policy(max_chars=16000))
        self.assertNotIn(self.aid, current['assertions'])
        claim = current['assertions'][event['replacement_id']]
        self.assertEqual(claim['predicate'], VOCAB + 'decisionAbout')
        self.assertEqual(claim['status'], 'Unreviewed')
        self.assertEqual(claim['origin'], 'Inferred')
        self.assertFalse(any('person' in eid for eid in current['entities']))
        self.assertFalse(
            retrieve(self.root, self.source_entity, Policy(max_chars=16000, accepted_only=True))[
                'assertions'
            ]
        )
        history = load_store(self.root / 'graph', history=True, include_notes=False)
        self.assertEqual(fingerprint(history, self.aid), old_fingerprint)
        self.assertEqual(inspect_assertion(history, self.aid)['lifecycle'], 'Superseded')
        self.assertEqual(inspect_assertion(history, self.aid)['status'], 'Accepted')
        self.assertEqual(
            values(history, self.aid, 'http://www.w3.org/ns/prov#wasDerivedFrom'),
            values(history, event['replacement_id'], 'http://www.w3.org/ns/prov#wasDerivedFrom'),
        )
