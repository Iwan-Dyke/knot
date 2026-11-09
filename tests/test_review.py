import json
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

from pyoxigraph import NamedNode, Quad, RdfFormat

from knot.inventory import build_inventory, digest
from knot.migrate import VOCAB, migrate
from knot.query import load_store
from knot.review import META, decide, inspect_assertion, values


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'sources').mkdir()
        text = '* Decision\nI selected Atlas.\n'
        with ZipFile(self.root / 'sources/test.zip', 'w') as archive:
            archive.writestr('note.org', text)
        build_inventory(self.root)
        claim = {
            'source_sha256': digest(text.encode()),
            'quote': 'I selected Atlas.',
            'subject': 'Person',
            'predicate': 'selected',
            'object': 'Atlas',
            'origin': 'explicit',
            'rationale': 'Recorded choice.',
        }
        (self.root / 'migration/curated-test.json').write_text(json.dumps([claim]))
        migrate(self.root)
        store = load_store(self.root / 'graph')
        self.target = list(
            store.query(
                'SELECT ?a WHERE { GRAPH <urn:knot:metadata> { ?a a <urn:knot:vocab:Assertion> }}'
            )
        )[0]['a'].value

    def decide(self, action, **kwargs):
        return decide(
            self.root,
            self.target,
            action,
            reviewer='Test reviewer',
            reason='Checked source',
            **kwargs,
        )

    def test_accept_survives_rebuild_with_single_effective_status(self):
        original = (self.root / 'graph/knowledge.trig').read_bytes()
        self.decide('accept')
        migrate(self.root)
        self.assertEqual(original, (self.root / 'graph/knowledge.trig').read_bytes())
        result = inspect_assertion(load_store(self.root / 'graph'), self.target)
        self.assertEqual(result['status'], 'Accepted')
        self.assertEqual(result['evidence'][0]['quote'], 'I selected Atlas.')
        self.assertEqual(len(result['history']), 1)

    def test_rejection_excludes_domain_triple_but_retains_history(self):
        self.decide('reject')
        store = load_store(self.root / 'graph')
        self.assertEqual(
            len(list(store.quads_for_pattern(None, None, None, NamedNode(self.target)))), 0
        )
        historical = load_store(self.root / 'graph', history=True)
        self.assertEqual(inspect_assertion(historical, self.target)['status'], 'Rejected')
        self.assertEqual(len(inspect_assertion(historical, self.target)['triples']), 1)

    def test_correction_keeps_original_and_does_not_inherit_acceptance(self):
        self.decide('accept')
        event = self.decide(
            'correct',
            replacement={
                'subject': 'urn:person:correct',
                'predicate': VOCAB + 'selected',
                'object': 'urn:project:atlas',
                'subject_label': 'Corrected person',
                'object_label': 'Atlas',
                'rationale': 'Corrected attribution based on source review.',
            },
        )
        store = load_store(self.root / 'graph', history=True)
        self.assertEqual(inspect_assertion(store, self.target)['lifecycle'], 'Superseded')
        replacement = inspect_assertion(store, event['replacement_id'])
        self.assertEqual(replacement['status'], 'Unreviewed')
        self.assertEqual(replacement['evidence'][0]['quote'], 'I selected Atlas.')
        migrate(self.root)
        decide(
            self.root,
            event['replacement_id'],
            'accept',
            reviewer='Test',
            reason='Reviewed replacement',
        )
        self.assertEqual(
            inspect_assertion(load_store(self.root / 'graph'), event['replacement_id'])['status'],
            'Accepted',
        )

    def test_invalid_decision_and_stale_state_write_nothing(self):
        with self.assertRaises(ValueError):
            self.decide('accept', expected='urn:nonexistent-event')
        with self.assertRaises(ValueError):
            self.decide('correct', replacement={'subject': 'not an IRI'})
        self.assertEqual(list((self.root / 'reviews/events').glob('*.trig')), [])

    def test_changed_assertion_invalidates_review(self):
        self.decide('accept')
        path = self.root / 'graph/knowledge.trig'
        path.write_text(path.read_text().replace('Recorded choice.', 'Changed explanation.'))
        with self.assertRaisesRegex(ValueError, 'changed'):
            load_store(self.root / 'graph')

    def test_changed_evidence_invalidates_review(self):
        self.decide('accept')
        path = self.root / 'graph/knowledge.trig'
        path.write_text(path.read_text().replace('I selected Atlas.', 'I did not select Atlas.'))
        with self.assertRaisesRegex(ValueError, 'changed'):
            load_store(self.root / 'graph')

    def test_forked_history_is_rejected(self):
        first = self.decide('accept')
        second = self.decide('reject')
        path = self.root / 'reviews/events' / (second['id'].rsplit(':', 1)[-1] + '.trig')
        path.write_text(path.read_text().replace(first['id'], 'urn:knot:review:start'))
        with self.assertRaisesRegex(ValueError, 'history'):
            load_store(self.root / 'graph')

    def test_unknown_target_cannot_be_reviewed(self):
        with self.assertRaisesRegex(ValueError, 'Unknown'):
            decide(self.root, 'urn:missing', 'accept', reviewer='Test', reason='No source')
        self.assertEqual(list((self.root / 'reviews/events').glob('*.trig')), [])

    def test_replacement_can_be_explicitly_accepted(self):
        event = self.decide(
            'correct',
            accept_replacement=True,
            replacement={
                'subject': 'urn:person:correct',
                'predicate': VOCAB + 'selected',
                'object': 'urn:project:atlas',
                'subject_label': 'Corrected person',
                'object_label': 'Atlas',
                'rationale': 'Human correction',
            },
        )
        result = inspect_assertion(load_store(self.root / 'graph'), event['replacement_id'])
        self.assertEqual(result['status'], 'Accepted')

    def test_framework_correction_retains_its_classification(self):
        store = load_store(self.root / 'graph', history=True)
        framework = NamedNode('urn:example:framework')
        for predicate, obj in (
            ('recordKind', NamedNode(VOCAB + 'FrameworkDefinition')),
            ('framework', framework),
        ):
            store.add(Quad(NamedNode(self.target), NamedNode(VOCAB + predicate), obj, META))
        store.dump(output=self.root / 'graph/knowledge.trig', format=RdfFormat.TRIG)
        event = self.decide(
            'correct',
            replacement={
                'subject': 'urn:example:skill',
                'predicate': VOCAB + 'relatedTo',
                'object': 'urn:example:criterion',
                'subject_label': 'Skill',
                'object_label': 'Criterion',
                'rationale': 'Corrected framework definition',
            },
        )
        store = load_store(self.root / 'graph', history=True)
        target = event['replacement_id']
        self.assertEqual(
            values(store, target, VOCAB + 'recordKind'), [NamedNode(VOCAB + 'FrameworkDefinition')]
        )
        self.assertEqual(values(store, target, VOCAB + 'framework'), [framework])
        self.assertEqual(
            len(
                list(load_store(self.root / 'graph').query(Path('queries/evidence.rq').read_text()))
            ),
            0,
        )
