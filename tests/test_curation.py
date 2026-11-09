import copy
import json
import tempfile
import unittest
from pathlib import Path

from pyoxigraph import Literal, NamedNode

from knot.curation import prepare_candidate, publish_candidate
from knot.curation_rules import relationship_warnings, validate_relationship
from knot.notes import create_note, read_note
from knot.provenance import source_pin
from knot.query import load_store
from knot.rdf import VOCAB, identifier, one
from knot.retrieval import Policy, retrieve, serialise
from knot.review import decide, inspect_assertion


class CurationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = create_note(
            self.root, 'λ🙂 We planned to migrate the pipeline.\r\n', author='Owner'
        )
        self.pin = source_pin(self.root, self.source['revision'], self.source['body'], 0)
        self.candidate = {
            'id': 'urn:knot:assertion:test-plan',
            'subject': {'id': 'urn:test:team', 'label': 'Data engineering team'},
            'predicate': VOCAB + 'proposed',
            'object': {'id': 'urn:test:migration', 'label': 'Pipeline migration proposal'},
            'origin': 'Explicit',
            'rationale': 'The team describes a plan; delivery is not established.',
            'agent': 'urn:test:agent:curator',
            'generated_at': '2026-11-05T12:00:00Z',
            'sources': [self.pin],
        }

    def files(self):
        return {
            p.relative_to(self.root): p.read_bytes() for p in self.root.rglob('*') if p.is_file()
        }

    def test_preview_then_publish_then_explicit_review_and_retrieval(self):
        before = self.files()
        preview = prepare_candidate(self.root, self.candidate)
        self.assertEqual(self.files(), before)
        self.assertEqual(preview['source_accounts'], [self.source['body_sha256']])
        published = publish_candidate(self.root, self.candidate)
        self.assertTrue(published['created'])
        store = load_store(self.root / 'graph', history=True)
        detail = inspect_assertion(store, self.candidate['id'])
        self.assertEqual(detail['status'], 'Unreviewed')
        self.assertEqual(detail['origin'], 'Explicit')
        response = retrieve(self.root, 'urn:test:team', Policy(max_chars=24000))
        self.assertIn(self.candidate['id'], serialise(response))
        self.assertIn('Unreviewed', serialise(response))
        decide(self.root, self.candidate['id'], 'accept', reviewer='Owner', reason='Checked plan.')
        after_review = self.files()
        retried = publish_candidate(self.root, self.candidate)
        self.assertFalse(retried['created'])
        self.assertEqual(self.files(), after_review)
        self.assertEqual(read_note(self.root, self.source['note']), self.source)

    def test_invalid_candidates_leave_all_files_unchanged(self):
        before = self.files()
        changes = [
            ('predicate', VOCAB + 'inventedRelationship'),
            ('predicate', VOCAB + 'reviewStatus'),
            ('id', 'not an IRI'),
            ('origin', 'Accepted'),
            ('generated_at', 'yesterday'),
            ('sources', [{**self.pin, 'quote': 'Delivery succeeded.'}]),
            ('sources', [{**self.pin, 'character_offset': 1}]),
            ('sources', [{**self.pin, 'sha256': '0' * 64}]),
            ('subject', {'id': 'urn:a', 'label': ''}),
            ('status', 'Accepted'),
        ]
        for key, value in changes:
            candidate = {**self.candidate, key: value}
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                publish_candidate(self.root, candidate)
            self.assertEqual(self.files(), before)

    def test_reuse_identifier_cannot_change_an_existing_claim(self):
        publish_candidate(self.root, self.candidate)
        before = self.files()
        with self.assertRaisesRegex(ValueError, 'collision'):
            publish_candidate(self.root, {**self.candidate, 'predicate': VOCAB + 'implemented'})
        self.assertEqual(self.files(), before)

    def test_append_preserves_existing_bytes_and_typed_literal(self):
        publish_candidate(self.root, self.candidate)
        path = self.root / 'graph/additions.trig'
        before = path.read_bytes()
        candidate = copy.deepcopy(self.candidate)
        candidate.update(id='urn:knot:assertion:test-count', predicate=VOCAB + 'eventCount')
        candidate['object'] = {
            'value': '18',
            'datatype': 'http://www.w3.org/2001/XMLSchema#integer',
            'label': '18 events',
        }
        # Exact pins prove provenance, not semantic support; this remains Unreviewed.
        publish_candidate(self.root, candidate)
        self.assertTrue(path.read_bytes().startswith(before))
        store = load_store(self.root / 'graph', history=True)
        triple = next(store.quads_for_pattern(None, None, None, NamedNode(candidate['id'])))
        self.assertEqual(
            triple.object, Literal('18', datatype=NamedNode(candidate['object']['datatype']))
        )
        self.assertEqual(
            one(store, candidate['id'], VOCAB + 'reviewStatus').value, VOCAB + 'Unreviewed'
        )

    def test_missing_types_do_not_invent_an_actor_or_reject_a_plan(self):
        warnings = relationship_warnings(VOCAB + 'madeDecision', set())
        self.assertEqual(warnings, [])
        warnings = relationship_warnings(VOCAB + 'madeDecision', {VOCAB + 'Project'})
        self.assertIn('decision_subject_needs_review', {w['code'] for w in warnings})
        warnings = relationship_warnings(
            VOCAB + 'implemented', set(), quotes=['We planned to migrate the pipeline.']
        )
        self.assertIn('claim_qualification_needs_review', {w['code'] for w in warnings})
        validate_relationship(NamedNode('urn:a'), NamedNode(VOCAB + 'relatedTo'), Literal('1984'))

    def test_native_and_generated_evidence_identities_cannot_be_assertion_entities(self):
        other = create_note(self.root, 'Independent reflection.')
        before = self.files()
        for identity in (other['note'], other['revision']):
            with self.assertRaises(ValueError):
                publish_candidate(self.root, {**self.candidate, 'id': identity})
        eid = identifier(
            'evidence', self.candidate['id'] + '\0' + json.dumps(self.pin, sort_keys=True)
        )
        for field in ('subject', 'object'):
            candidate = copy.deepcopy(self.candidate)
            candidate[field]['id'] = eid
            with self.assertRaisesRegex(ValueError, 'collision'):
                publish_candidate(self.root, candidate)
        self.assertEqual(self.files(), before)

    def test_bad_known_literal_lexical_forms_fail_without_changing_data(self):
        before = self.files()
        for datatype, value in (('integer', 'eighteen'), ('decimal', 'NaN'), ('boolean', 'maybe')):
            candidate = copy.deepcopy(self.candidate)
            candidate['object'] = {
                'value': value,
                'label': value,
                'datatype': 'http://www.w3.org/2001/XMLSchema#' + datatype,
            }
            with self.assertRaisesRegex(ValueError, 'lexical'):
                publish_candidate(self.root, candidate)
        self.assertEqual(self.files(), before)


if __name__ == '__main__':
    unittest.main()
