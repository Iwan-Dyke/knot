"""The checked dispatcher selects artifacts, not an unconstrained client plan."""

import json
import unittest
from pathlib import Path
from unittest.mock import patch

import test_evaluation_questions as coverage_fixture
import test_explanations as fixture

from knot.evaluation import explanations
from knot.evaluation.answering import answer, revalidate
from knot.interfaces.access import AccessScope
from knot.writing.notes import create_note


class TestAnswering(unittest.TestCase):
    def setUp(self):
        self.f = fixture.TestExplanations()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.root = self.f.root
        self.question = 'Why was decision "Batching choice" chosen?'

    def another(self):
        note = create_note(
            self.root,
            'A second qualified explanation of batching.\n',
            title='Alternative explanation',
            author='Synthetic curator',
            agent='Synthetic curator',
            entities=[fixture.DECISION],
            derivation={
                'method': 'faithful_restatement',
                'qualification': 'Another account, not independent corroboration.',
                'sources': [self.f.pin],
            },
        )
        request = {**self.f.request, 'revision': note['revision']}
        event = explanations.approve(
            self.root,
            explanations.prepare(self.root, request),
            reviewer='Synthetic reviewer',
            reason='Checked the second account.',
        )
        return note, request, event

    def approve_wordings(self, request=None, wordings=None):
        return explanations.approve(
            self.root,
            explanations.prepare(
                self.root,
                request or self.f.request,
                wordings=wordings
                or ['Why did we choose batching?', 'What made batching the preferred option?'],
            ),
            reviewer='Synthetic reviewer',
            reason='Checked question applicability.',
        )

    def test_unsupported_question_offers_navigation_without_an_answer_or_interpretation(self):
        self.approve_wordings()
        question = 'Why was batching chosen?'
        result = answer(self.root, question)
        self.assertEqual(result['status'], 'unsupported_question')
        self.assertEqual(result['question'], question)
        self.assertIsNone(result['request'])
        self.assertIsNone(result['route'])
        self.assertNotIn('answer', result)
        self.assertNotIn('result', result)
        self.assertEqual(len(result['alternatives']), 2)
        self.assertIn('not verified paraphrases', result['alternatives_guidance'])
        self.assertEqual(result, answer(self.root, question))
        option = result['alternatives'][0]
        selected = answer(
            self.root, option['question'], explanation_revision=option['explanation_revision']
        )
        self.assertEqual(selected['answer'], self.f.note['body'])

    def test_conditions_are_not_silently_dropped_when_showing_alternatives(self):
        self.approve_wordings()
        result = answer(self.root, 'Why did we choose batching? Did it succeed?')
        self.assertEqual(result['status'], 'unsupported_question')
        self.assertIsNone(result['request'])
        self.assertNotIn('answer', result)
        self.assertTrue(result['alternatives'])
        self.assertTrue(all('succeed' not in a['question'] for a in result['alternatives']))
        self.assertIn('explicitly', result['alternatives_guidance'])

    def test_generic_question_words_do_not_suggest_an_unrelated_decision(self):
        self.approve_wordings()
        for question in ('Why did we choose streaming?', 'What should I cook for dinner?'):
            self.assertEqual(answer(self.root, question)['alternatives'], [])

    def test_stale_explanation_is_not_offered_as_an_available_alternative(self):
        from knot.writing.notes import save_note

        self.approve_wordings()
        save_note(
            self.root,
            self.f.source['note'],
            'Corrected source.',
            expected=self.f.source['revision'],
        )
        result = answer(self.root, 'Explain the batching choice')
        self.assertEqual(result['status'], 'unsupported_question')
        self.assertEqual(result['alternatives'], [])

    def test_revalidation_removes_withdrawn_alternatives_without_returning_an_answer(self):
        event = self.approve_wordings()
        saved = answer(self.root, 'Explain the batching choice')
        self.assertTrue(saved['alternatives'])
        explanations.withdraw(
            self.root,
            self.f.request,
            expected=event['event_sha256'],
            reviewer='Synthetic reviewer',
            reason='Withdraw this answer.',
        )
        current = revalidate(self.root, saved)
        self.assertEqual(current['status'], 'changed')
        self.assertEqual(current['current']['status'], 'unsupported_question')
        self.assertEqual(current['current']['alternatives'], [])
        self.assertNotIn('answer', current['current'])

    def test_hidden_alternatives_and_missing_grants_cannot_leak_through_navigation(self):
        self.approve_wordings()
        scope = self.f.scope(self.f.note, self.f.source)
        question = 'Explain the batching choice'
        saved = answer(self.root, question, scope=scope)
        _, hidden, _ = self.another()
        self.approve_wordings(hidden)
        original = explanations.history

        def guarded(root, request):
            self.assertNotEqual(request, hidden)
            return original(root, request)

        with patch('knot.evaluation.answering.explanations.history', side_effect=guarded):
            self.assertEqual(saved, answer(self.root, question, scope=scope))
        denied = answer(self.root, question, scope=self.f.scope(self.f.note))
        self.assertEqual(denied['alternatives'], [])
        self.assertNotIn(self.f.note['revision'], json.dumps(denied))

    def test_alternatives_are_bounded_and_report_possible_omissions(self):
        self.approve_wordings(
            wordings=[
                'Why choose batching?',
                'Why was batching chosen?',
                'What makes batching preferable?',
                'Why prefer batching?',
                'Why use batching?',
                'What is the reason for batching?',
            ]
        )
        result = answer(self.root, 'Explain the batching choice')
        self.assertEqual(len(result['alternatives']), 5)
        self.assertTrue(result['alternatives_truncated'])
        self.assertNotIn('answer', result)

    def test_changed_sources_during_alternative_checks_fail_instead_of_returning_stale_choices(
        self,
    ):
        self.approve_wordings()
        original = explanations.answer

        def changing(*args, **kwargs):
            result = original(*args, **kwargs)
            (self.root / self.f.source['body_path']).write_text('Changed during navigation')
            return result

        with patch('knot.evaluation.answering.explanations.answer', side_effect=changing):
            with self.assertRaisesRegex(ValueError, 'Inputs changed'):
                answer(self.root, 'Explain the batching choice')

    def test_alternative_validation_work_is_bounded_separately_from_results(self):
        self.approve_wordings()
        _, request, _ = self.another()
        self.approve_wordings(request)
        with (
            patch('knot.evaluation.answering.MAX_ALTERNATIVE_CHECKS', 1),
            patch(
                'knot.evaluation.answering.explanations.answer', wraps=explanations.answer
            ) as execute,
        ):
            result = answer(self.root, 'Explain the batching choice')
            self.assertEqual(execute.call_count, 1)
            self.assertTrue(result['alternatives_truncated'])
            self.assertTrue(result['alternatives'])
            self.assertIsNone(result['request'])

    def test_corrupt_candidate_evidence_is_not_silently_offered_or_skipped(self):
        self.approve_wordings()
        (self.root / self.f.source['body_path']).write_text('Corrupted source')
        with self.assertRaises(ValueError):
            answer(self.root, 'Explain the batching choice')

    def test_routes_visible_name_to_one_approved_revision_without_rephrasing(self):
        self.f.approve()
        result = answer(self.root, self.question)
        self.assertEqual(result['status'], 'answered')
        self.assertEqual(result['route'], 'decision_explanation')
        self.assertEqual(result['request'], self.f.request)
        self.assertEqual(result['answer'], self.f.note['body'])
        self.assertEqual(result['result']['answer'], result['answer'])
        self.assertEqual(result, answer(self.root, self.question))
        self.assertEqual(
            [s['check'] for s in result['steps']],
            [
                'question_contract',
                'decision_selection',
                'approved_artifact_selection',
                'artifact_execution',
            ],
        )

    def test_unapproved_and_denied_content_is_not_read_or_offered_as_an_answer(self):
        original = Path.read_bytes

        def guarded(path):
            if path in (
                self.root / self.f.note['body_path'],
                self.root / self.f.source['body_path'],
            ):
                self.fail('Unapproved or denied body read')
            return original(path)

        with patch.object(Path, 'read_bytes', guarded):
            result = answer(self.root, self.question)
        self.assertEqual(result['status'], 'unknown')
        self.assertNotIn('answer', result)
        self.f.approve()
        with patch.object(Path, 'read_bytes', guarded):
            result = answer(
                self.root, f'Why was decision "{fixture.DECISION}" chosen?', scope=AccessScope()
            )
        self.assertEqual(result['status'], 'unknown')
        self.assertNotIn(self.f.note['revision'], json.dumps(result))

    def test_multiple_approvals_require_selection_and_revalidation_resolves_again(self):
        self.f.approve()
        saved = answer(self.root, self.question)
        other, _, _ = self.another()
        current = answer(self.root, self.question)
        self.assertEqual(current['status'], 'needs_selection')
        self.assertEqual(len(current['choices']), 2)
        self.assertNotIn('answer', current)
        selected = answer(self.root, self.question, explanation_revision=other['revision'])
        self.assertEqual(selected['answer'], other['body'])
        checked = revalidate(self.root, saved)
        self.assertEqual(checked['status'], 'changed')
        self.assertIsNone(checked['outcomes_unchanged'])
        self.assertNotIn('answer', checked['current'])

    def test_hidden_artifact_does_not_change_scoped_result_or_reveal_its_reviews(self):
        self.f.approve()
        scope = self.f.scope(self.f.note, self.f.source)
        question = self.f.request['question']
        before = answer(self.root, question, scope=scope)
        self.assertEqual(before['status'], 'answered')
        hidden, request, _ = self.another()
        original = explanations.history

        def guarded(root, value):
            self.assertNotEqual(value, request)
            return original(root, value)

        with patch('knot.evaluation.answering.explanations.history', side_effect=guarded):
            self.assertEqual(before, answer(self.root, question, scope=scope))
        self.assertNotIn(hidden['revision'], json.dumps(before))

    def test_extra_conditions_cannot_execute_a_narrower_question(self):
        with patch('knot.evaluation.answering.explanations.answer') as run:
            for text in (
                self.question + ' Was delivery successful?',
                self.question[:-1] + ' before 2024?',
                'Which decision was best?',
            ):
                self.assertEqual(answer(self.root, text)['status'], 'unsupported_question')
            run.assert_not_called()

    def test_candidate_limit_cannot_choose_from_incomplete_enumeration(self):
        self.f.approve()
        self.another()
        with patch('knot.evaluation.answering.MAX_CANDIDATES', 1):
            result = answer(self.root, self.question)
        self.assertEqual(result['status'], 'unknown')
        self.assertEqual(result['reasons'], ['candidate_budget'])
        self.assertNotIn('answer', result)

    def test_review_changes_during_selection_prevent_stale_answers(self):
        self.f.approve()
        _, request, event = self.another()
        original = explanations.answer
        changed = False

        def changing(*args, **kwargs):
            nonlocal changed
            result = original(*args, **kwargs)
            if not changed:
                explanations.withdraw(
                    self.root,
                    request,
                    expected=event['event_sha256'],
                    reviewer='Synthetic reviewer',
                    reason='Concurrent withdrawal',
                )
                changed = True
            return result

        with patch('knot.evaluation.answering.explanations.answer', side_effect=changing):
            with self.assertRaisesRegex(ValueError, 'reviews changed'):
                answer(self.root, self.question)

    def test_corrupt_approved_artifact_is_not_silently_skipped(self):
        self.f.approve()
        (self.root / self.f.source['body_path']).write_text('Corrupt bytes')
        with self.assertRaises(ValueError):
            answer(self.root, self.question)

    def test_source_change_after_artifact_execution_prevents_returning_answer(self):
        self.f.approve()
        original = explanations.answer

        def changing(*args, **kwargs):
            result = original(*args, **kwargs)
            (self.root / self.f.source['body_path']).write_text('Changed during selection')
            return result

        with patch('knot.evaluation.answering.explanations.answer', side_effect=changing):
            with self.assertRaisesRegex(ValueError, 'Inputs changed'):
                answer(self.root, self.question)

    def test_coverage_routes_to_existing_interpretation_and_receipt(self):
        f = coverage_fixture.TestAnswerQuestion()
        f.setUp()
        self.addCleanup(f.doCleanups)
        result = answer(f.root, f.question)
        self.assertEqual(result['route'], 'framework_coverage')
        self.assertEqual(result['status'], 'answered')
        self.assertEqual(result['answer'], result['result']['answer'])
        self.assertEqual(result['request'], result['result']['request'])
        with self.assertRaises(ValueError):
            answer(f.root, f.question, explanation_revision=self.f.note['revision'])
