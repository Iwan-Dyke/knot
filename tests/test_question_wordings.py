"""Alternative questions require exact, current, scoped semantic review."""

import json
import unittest
from unittest.mock import patch

import test_answering as fixture

from knot.evaluation import explanations
from knot.evaluation.answering import answer, revalidate
from knot.evaluation.snapshot import canonical_hash
from knot.graph.rdf import LABEL, RDF_TYPE, VOCAB, Dataset
from knot.interfaces.access import AccessScope
from knot.writing.notes import create_note, save_note

WORDINGS = ['Why did we choose batching?', 'What made batching the preferred option?']


class TestQuestionWordings(unittest.TestCase):
    def setUp(self):
        self.f = fixture.TestAnswering()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.root = self.f.root
        self.request = self.f.f.request

    def approve(self, request=None, wordings=WORDINGS):
        preview = explanations.prepare(self.root, request or self.request, wordings=wordings)
        return explanations.approve(
            self.root,
            preview,
            reviewer='Synthetic reviewer',
            reason='Checked the complete question meaning and answer.',
        )

    def test_preview_does_not_activate_wordings_and_approval_reuses_exact_answer(self):
        preview = explanations.prepare(self.root, self.request, wordings=WORDINGS)
        self.assertEqual(preview['wordings'], WORDINGS)
        self.assertEqual(answer(self.root, WORDINGS[0])['status'], 'unsupported_question')
        event = self.approve()
        for question in WORDINGS:
            result = answer(self.root, question)
            self.assertEqual(result['status'], 'answered')
            self.assertEqual(result['request'], self.request)
            self.assertEqual(result['answer'], self.f.f.note['body'])
            self.assertEqual(
                result['wording_review'],
                {'wording': question, 'event_sha256': event['event_sha256']},
            )
            self.assertEqual(result, answer(self.root, question))

    def test_complete_matching_never_drops_conditions_or_changes_case(self):
        self.approve()
        for question in [
            WORDINGS[0] + ' Did it succeed?',
            WORDINGS[0].replace('?', ' before 2024?'),
            WORDINGS[0].replace('batching', 'streaming'),
            WORDINGS[0].upper(),
        ]:
            with self.subTest(question=question):
                result = answer(self.root, question)
                self.assertEqual(result['status'], 'unsupported_question')
                self.assertNotIn('answer', result)
        self.assertEqual(answer(self.root, '  ' + WORDINGS[0] + '  ')['status'], 'answered')

    def test_invalid_or_reserved_wordings_cannot_override_a_builtin_contract(self):
        for wordings in [
            'text',
            [''],
            ['same', ' same '],
            ['x' * 2001],
            ['x' + str(i) for i in range(21)],
            [self.request['question']],
            [self.f.question],
            ['Does project "Falcon" have reviewed support for criterion "Safety"?'],
        ]:
            with self.subTest(wordings=wordings), self.assertRaises(ValueError):
                explanations.prepare(self.root, self.request, wordings=wordings)

    def test_tampered_preview_cannot_approve_unreviewed_wordings(self):
        preview = explanations.prepare(self.root, self.request, wordings=WORDINGS)
        preview['wordings'] = ['Was delivery successful?']
        with self.assertRaises(ValueError):
            explanations.approve(self.root, preview, reviewer='Synthetic reviewer', reason='Test')
        self.assertEqual(explanations.history(self.root, self.request), [])

    def test_reapproval_retains_omitted_wordings_and_explicit_clear_retires_them(self):
        self.approve()
        self.assertEqual(explanations.prepare(self.root, self.request)['wordings'], WORDINGS)
        saved = answer(self.root, WORDINGS[0])
        self.approve(wordings=[])
        checked = revalidate(self.root, saved)
        self.assertEqual(checked['status'], 'changed')
        self.assertEqual(checked['current']['status'], 'unsupported_question')
        self.assertNotIn('answer', checked['current'])
        self.assertEqual(answer(self.root, self.request['question'])['status'], 'answered')

    def test_withdrawal_stops_wording_reuse_without_restoring_saved_text(self):
        event = self.approve()
        saved = answer(self.root, WORDINGS[0])
        explanations.withdraw(
            self.root,
            self.request,
            expected=event['event_sha256'],
            reviewer='Synthetic reviewer',
            reason='Stop reuse',
        )
        checked = revalidate(self.root, saved)
        self.assertEqual(checked['status'], 'changed')
        self.assertEqual(checked['current']['status'], 'unknown')
        self.assertNotIn('answer', checked['current'])
        self.assertEqual(explanations.history(self.root, self.request)[-1]['wordings'], WORDINGS)

    def test_multiple_mappings_require_selection(self):
        self.approve()
        other, request, _ = self.f.another()
        self.approve(request)
        result = answer(self.root, WORDINGS[0])
        self.assertEqual(result['status'], 'needs_selection')
        self.assertEqual(len(result['choices']), 2)
        self.assertNotIn('answer', result)
        selected = answer(self.root, WORDINGS[0], explanation_revision=other['revision'])
        self.assertEqual(selected['answer'], other['body'])

    def test_different_decision_meanings_are_ambiguous_before_answer_execution(self):
        self.approve()
        other_decision = 'urn:example:decision:caching'
        graph = Dataset()
        graph.add(other_decision, LABEL, 'Caching choice', literal=True)
        graph.add(other_decision, RDF_TYPE, VOCAB + 'Decision')
        (self.root / 'graph/other.trig').write_text(graph.text())
        other = create_note(
            self.root,
            'An alternative decision account.',
            title='Alternative choice',
            author='Synthetic curator',
            agent='Synthetic curator',
            entities=[other_decision],
            derivation={
                'method': 'faithful_restatement',
                'qualification': 'Synthetic account.',
                'sources': [self.f.f.pin],
            },
        )
        request = {
            'decision': other_decision,
            'revision': other['revision'],
            'question': f'Why was decision "{other_decision}" chosen?',
        }
        self.approve(request)
        with patch('knot.evaluation.answering.explanations.answer') as execute:
            result = answer(self.root, WORDINGS[0])
            self.assertEqual(result['status'], 'needs_selection')
            self.assertEqual(len(result['choices']), 2)
            execute.assert_not_called()

    def test_missing_input_grant_does_not_read_or_disclose_the_review(self):
        self.approve()
        with patch('knot.evaluation.answering.explanations.history') as read:
            result = answer(self.root, WORDINGS[0], scope=self.f.f.scope(self.f.f.note))
            self.assertEqual(result['status'], 'unsupported_question')
            self.assertNotIn('answer', result)
            read.assert_not_called()

    def test_hidden_wordings_and_reviews_do_not_affect_a_granted_answer(self):
        self.approve()
        scope = self.f.f.scope(self.f.f.note, self.f.f.source)
        saved = answer(self.root, WORDINGS[0], scope=scope)
        _, request, _ = self.f.another()
        self.approve(request)
        original = explanations.history

        def guarded(root, value):
            self.assertNotEqual(value, request)
            return original(root, value)

        with patch('knot.evaluation.answering.explanations.history', side_effect=guarded):
            self.assertEqual(saved, answer(self.root, WORDINGS[0], scope=scope))
        denied = revalidate(self.root, saved, scope=AccessScope())
        self.assertEqual(denied['current']['status'], 'unsupported_question')
        self.assertNotIn('answer', denied['current'])
        self.assertNotIn('Synthetic reviewer', json.dumps(denied))
        self.assertNotIn(self.f.f.source['revision'], json.dumps(denied))

    def test_new_source_revision_invalidates_the_registered_wording_answer(self):
        self.approve()
        source = self.f.f.source
        save_note(
            self.root, source['note'], 'A corrected source account.', expected=source['revision']
        )
        result = answer(self.root, WORDINGS[0])
        self.assertEqual(result['status'], 'unknown')
        self.assertNotIn('answer', result)

    def test_candidate_budget_cannot_pick_from_incomplete_wording_search(self):
        self.approve()
        self.f.another()
        with patch('knot.evaluation.answering.MAX_WORDING_CANDIDATES', 1):
            result = answer(self.root, WORDINGS[0])
            self.assertEqual(result['status'], 'unknown')
            self.assertEqual(result['reasons'], ['candidate_budget'])
            self.assertNotIn('answer', result)
            self.assertEqual(
                answer(self.root, WORDINGS[0], explanation_revision=self.request['revision'])[
                    'status'
                ],
                'answered',
            )

    def test_new_wording_on_another_candidate_during_execution_fails(self):
        self.approve()
        _, request, _ = self.f.another()
        original = explanations.answer

        def changing(*args, **kwargs):
            result = original(*args, **kwargs)
            self.approve(request)
            return result

        with patch('knot.evaluation.answering.explanations.answer', side_effect=changing):
            with self.assertRaisesRegex(ValueError, 'reviews changed'):
                answer(self.root, WORDINGS[0])

    def test_legacy_event_without_wordings_keeps_its_existing_approval(self):
        event = self.f.f.approve()
        directory = explanations._directory(self.root, self.request)
        path = directory / (event['event_sha256'] + '.json')
        event.pop('wordings', None)
        event['event_sha256'] = canonical_hash(
            {k: v for k, v in event.items() if k != 'event_sha256'}
        )
        path.unlink()
        (directory / (event['event_sha256'] + '.json')).write_text(json.dumps(event))
        self.assertEqual(answer(self.root, self.request['question'])['status'], 'answered')
        self.assertEqual(answer(self.root, WORDINGS[0])['status'], 'unsupported_question')
