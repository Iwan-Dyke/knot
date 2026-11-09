import copy
import tempfile
import unittest
from pathlib import Path

from pyoxigraph import NamedNode

from knot.curation import prepare_candidate, publish_candidate
from knot.notes import create_note, note_history, read_note, save_note
from knot.provenance import source_pin
from knot.query import load_store
from knot.rdf import META, RDF_TYPE, VOCAB
from knot.retrieval import Policy, retrieve
from knot.review import decide, fingerprint, inspect_assertion, read_events


class CurationLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.policy = Policy(max_chars=40000, max_passages=8)

    def files(self):
        return {
            p.relative_to(self.root): p.read_bytes() for p in self.root.rglob('*') if p.is_file()
        }

    def pin(self, source):
        return source_pin(self.root, source['revision'], source['body'], 0)

    def curate(self, source, body, *, title, qualification, kind='Statement'):
        return create_note(
            self.root,
            body,
            title=title,
            author='Codex',
            agent='Codex',
            kind=kind,
            derivation={
                'method': 'faithful_restatement',
                'qualification': qualification,
                'sources': [self.pin(source)],
            },
        )

    def candidate(self, key, predicate, sources, *, subject, object):
        return {
            'id': 'urn:knot:assertion:scenario-' + key,
            'subject': {'id': 'urn:scenario:' + subject[0], 'label': subject[1]},
            'predicate': VOCAB + predicate,
            'object': {'id': 'urn:scenario:' + object[0], 'label': object[1]},
            'origin': 'Explicit',
            'rationale': 'Preserve the source attribution and qualifications.',
            'agent': 'urn:scenario:agent:codex',
            'generated_at': '2026-11-05T12:00:00Z',
            'sources': [self.pin(source) for source in sources],
        }

    def assertions(self):
        store = load_store(self.root / 'graph')
        return {
            q.subject.value
            for q in store.quads_for_pattern(
                None, NamedNode(RDF_TYPE), NamedNode(VOCAB + 'Assertion'), META
            )
        }

    def test_engineering_plan_capture_curation_publication_review_and_retrieval(self):
        original = (
            b'The field research team proposed an Orion weather sensor template.\r\n'
            b'Delivery is unconfirmed.\r\n'
        )
        source = create_note(self.root, original, author='Owner')
        curated = self.curate(
            source,
            'The Orion weather sensor template is a proposal; delivery is unconfirmed.',
            title='Orion weather sensor template proposal',
            qualification='A reported proposal, not evidence of implementation.',
            kind='Idea',
        )
        self.assertEqual(self.assertions(), set())
        candidate = self.candidate(
            'engineering-plan',
            'proposed',
            [source],
            subject=('field-team', 'Field research team'),
            object=('notebook-proposal', 'Orion weather sensor template proposal'),
        )
        publish_candidate(self.root, candidate)
        response = retrieve(self.root, candidate['subject']['id'], self.policy)
        self.assertEqual(response['assertions'][candidate['id']]['status'], 'Unreviewed')
        self.assertEqual(response['assertions'][candidate['id']]['predicate'], VOCAB + 'proposed')
        self.assertFalse(
            retrieve(self.root, candidate['subject']['id'], Policy(accepted_only=True))[
                'assertions'
            ]
        )
        self.assertEqual(read_events(self.root), [])
        before = fingerprint(load_store(self.root / 'graph', history=True), candidate['id'])
        decide(
            self.root,
            candidate['id'],
            'accept',
            reviewer='Owner',
            reason='The original source records this proposal, not completed delivery.',
        )
        accepted = retrieve(
            self.root, candidate['subject']['id'], Policy(accepted_only=True, max_chars=40000)
        )
        self.assertEqual(accepted['assertions'][candidate['id']]['status'], 'Accepted')
        self.assertEqual(accepted['assertions'][candidate['id']]['origin'], 'Explicit')
        self.assertEqual(
            fingerprint(load_store(self.root / 'graph', history=True), candidate['id']), before
        )
        note_result = retrieve(self.root, curated['note'], self.policy)
        citation = next(iter(note_result['sources'].values()))
        self.assertEqual(citation['native_note']['author'], 'Codex')
        self.assertEqual(citation['native_note']['derivation'], curated['derivation'])
        self.assertEqual(citation['representation'], 'CuratedKnowledge')
        self.assertEqual((self.root / source['body_path']).read_bytes(), original)
        self.assertEqual(read_note(self.root, source['note']), source)
        self.assertEqual(len(note_history(self.root, source['note'])), 1)

    def test_leadership_feedback_stays_an_attributed_report_after_review(self):
        source = create_note(
            self.root,
            'After the garden workshop, Alex reported that Jordan described '
            'the planting guide as clear and useful. This records her assessment.',
            author='Alex Morgan',
        )
        curated = self.curate(
            source,
            'Alex reported positive feedback from Jordan on the garden workshop: '
            'she described the planting guide as clear and useful.',
            title='Reported feedback on the garden workshop',
            qualification='Reported feedback, not an independent assessment of competence.',
            kind='Assessment',
        )
        candidate = self.candidate(
            'briefing-feedback',
            'reportedOutcome',
            [source, curated],
            subject=('garden-workshop', 'Garden workshop'),
            object=('reported-feedback', 'Jordan’s reported garden workshop feedback'),
        )
        publish_candidate(self.root, candidate)
        decide(
            self.root,
            candidate['id'],
            'accept',
            reviewer='Owner',
            reason='The representation faithfully preserves the attributed feedback.',
        )
        result = retrieve(self.root, candidate['subject']['id'], self.policy)
        self.assertEqual(set(result['assertions']), {candidate['id']})
        self.assertEqual(
            result['assertions'][candidate['id']]['predicate'], VOCAB + 'reportedOutcome'
        )
        self.assertTrue(
            any(source['independence'] == 'DerivedAccount' for source in result['sources'].values())
        )
        self.assertEqual(
            {source['native_note']['author'] for source in result['sources'].values()},
            {'Alex Morgan', 'Codex'},
        )
        self.assertIn(source['body'], result['passages'].values())
        self.assertIn(curated['body'], result['passages'].values())

    def test_reading_curation_does_not_invent_personal_application(self):
        source = create_note(
            self.root,
            'Reading note: An invented field guide recommends measuring soil before planting. '
            'I have not yet tried this approach.',
            author='Owner',
        )
        curated = self.curate(
            source,
            'The reading note describes measuring soil before planting as a gardening '
            'approach. Personal application has not been established.',
            title='Measuring soil before planting',
            qualification='The owner’s reading interpretation; no evidence of personal application.',
            kind='Thought',
        )
        result = retrieve(self.root, curated['note'], self.policy)
        self.assertEqual(self.assertions(), set())
        self.assertEqual(result['assertions'], {})
        self.assertEqual(curated['entities'], [])
        self.assertIn(curated['body'], result['passages'].values())
        self.assertTrue(
            all(context['claim_review'] is None for context in result['source_context'].values())
        )
        self.assertFalse((self.root / 'graph/additions.trig').exists())

    def test_unlinked_reflection_is_retrievable_without_manufactured_entities(self):
        source = create_note(
            self.root,
            'Maybe a quiet morning would help me think. I am unsure and want to revisit it.',
            author='Owner',
            kind='Thought',
        )
        self.assertIsNone(source['title'])
        self.assertEqual(source['entities'], [])
        self.assertEqual(self.assertions(), set())
        result = retrieve(self.root, source['note'], self.policy)
        self.assertEqual(result['assertions'], {})
        self.assertIn(source['body'], result['passages'].values())
        self.assertEqual(read_events(self.root), [])

    def test_source_revision_and_two_restatements_retain_one_leaf_account(self):
        source = create_note(
            self.root, 'The owner reports 7 Aurora sensor calibrations.', author='Owner'
        )
        first = self.curate(
            source,
            'The reported Aurora outcome is 7 sensor calibrations.',
            title='Reported Aurora calibration count',
            qualification='One owner account; not independent verification.',
        )
        second = self.curate(
            first,
            'One owner account reports 7 sensor calibrations for Aurora.',
            title='Aurora calibration count and its attribution',
            qualification='A restatement of the same original owner account.',
        )
        revised = save_note(
            self.root,
            source['note'],
            source['body'],
            expected=source['revision'],
            title='Original outcome report',
        )
        candidate = self.candidate(
            'reported-count',
            'reportedOutcome',
            [source, revised, first, second],
            subject=('aurora-calibration', 'Aurora sensor calibration activity'),
            object=('migration-outcome', 'Reported Aurora outcome of 7 sensor calibrations'),
        )
        prepared = prepare_candidate(self.root, candidate)
        self.assertEqual(prepared['source_accounts'], [source['body_sha256']])
        receipt = publish_candidate(self.root, candidate)
        self.assertEqual(receipt['source_accounts'], [source['body_sha256']])
        result = retrieve(self.root, candidate['subject']['id'], self.policy)
        self.assertEqual(len(result['sources']), 4)
        derived = [s for s in result['sources'].values() if s['independence'] == 'DerivedAccount']
        self.assertEqual(len(derived), 2)
        self.assertTrue(all(s['source_accounts'] == [source['body_sha256']] for s in derived))
        self.assertEqual(
            inspect_assertion(load_store(self.root / 'graph'), candidate['id'])['status'],
            'Unreviewed',
        )

    def test_invalid_provenance_prevents_curation_or_candidate_publication(self):
        source = create_note(self.root, 'Implementation remains a proposal.', author='Owner')
        candidate = self.candidate(
            'invalid-provenance',
            'proposed',
            [source],
            subject=('team', 'Engineering team'),
            object=('proposal', 'Implementation proposal'),
        )
        original = self.files()
        bad_pin = copy.deepcopy(candidate['sources'][0])
        bad_pin['quote'] = 'Implementation succeeded.'
        with self.assertRaises(ValueError):
            create_note(
                self.root,
                'Implementation succeeded.',
                title='Unsupported outcome',
                author='Codex',
                agent='Codex',
                derivation={
                    'method': 'faithful_restatement',
                    'qualification': 'A claimed restatement.',
                    'sources': [bad_pin],
                },
            )
        self.assertEqual(self.files(), original)
        with self.assertRaises(ValueError):
            publish_candidate(self.root, {**candidate, 'sources': [bad_pin]})
        self.assertEqual(self.files(), original)
        self.assertEqual(read_events(self.root), [])


if __name__ == '__main__':
    unittest.main()
