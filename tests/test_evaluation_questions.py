"""Checked question interpretation and fixed answers over the coverage rule."""

import contextlib
import io
import json
import unittest
from unittest.mock import patch

import test_evaluation as fixture

from knot.evaluation.questions import answer_question
from knot.graph.rdf import LABEL, VOCAB
from knot.interfaces.access import AccessScope
from knot.interfaces.note_cli import main


class TestAnswerQuestion(unittest.TestCase):
    def setUp(self):
        self.f = fixture.CoverageTests()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.root = self.f.root
        self.f.data.add(fixture.PROJECT, LABEL, 'Falcon', literal=True)
        self.f.data.add(fixture.CRITERIA[0], LABEL, 'Safe changes', literal=True)
        self.f.save()
        self.question = 'Does project "Falcon" have reviewed support for criterion "Safe changes"?'

    def test_question_resolves_exact_request_and_renders_attributed_support(self):
        before = {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        result = answer_question(self.root, self.question)
        self.assertEqual(result['status'], 'evaluated')
        self.assertEqual(result['question'], self.question)
        self.assertEqual(result['request']['subject'], fixture.PROJECT)
        self.assertEqual(result['request']['criteria'], [fixture.CRITERIA[0]])
        self.assertEqual(result['request']['framework_revision'], fixture.REVISION)
        self.assertEqual(result['request'], result['evaluation']['request'])
        self.assertEqual(result['evaluation']['criteria'][0]['outcome'], 'support_found')
        self.assertIn('attributed assessment', result['answer'])
        self.assertIn('not proof of capability', result['answer'])
        self.assertIn('limited scope', json.dumps(result['evaluation']['assertions']))
        from knot.evaluation.snapshot import canonical_hash

        self.assertEqual(
            result['answer_sha256'],
            canonical_hash({key: value for key, value in result.items() if key != 'answer_sha256'}),
        )
        self.assertEqual(result, answer_question(self.root, self.question))
        self.assertEqual(before, {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()})

    def test_unsupported_wording_or_extra_conditions_never_run_the_evaluator(self):
        for question in (
            'What evidence supports my skills?',
            self.question[:-1] + ' before 2024?',
            self.question + ' Also prove that I am an expert.',
            self.question.replace('reviewed support', 'independently verified competence'),
        ):
            with (
                self.subTest(question=question),
                patch('knot.evaluation.questions.evaluate') as run,
            ):
                result = answer_question(self.root / 'does-not-exist', question)
                self.assertEqual(result['status'], 'unsupported_question')
                self.assertIsNone(result['request'])
                self.assertNotIn('evaluation', result)
                run.assert_not_called()

    def test_ambiguous_and_missing_labels_do_not_guess_or_execute(self):
        self.f.data.add(fixture.CRITERIA[1], LABEL, 'Safe changes', literal=True)
        self.f.save()
        with patch('knot.evaluation.questions.evaluate') as run:
            ambiguous = answer_question(self.root, self.question)
            missing = answer_question(self.root, self.question.replace('Falcon', 'Unknown'))
            run.assert_not_called()
        self.assertEqual(ambiguous['status'], 'needs_selection')
        self.assertEqual(ambiguous['choices']['criterion'], list(fixture.CRITERIA))
        self.assertEqual(missing['status'], 'needs_selection')
        self.assertEqual(missing['choices']['subject'], [])
        self.assertIsNone(missing['request'])

    def test_multiple_framework_revisions_require_explicit_selection(self):
        aid = self.f.claim(
            'urn:example:definition:new',
            fixture.CRITERIA[0],
            fixture.DEFINITION,
            'A changed definition.',
            'A changed definition.',
            literal=True,
        )
        self.f.data.add(aid, VOCAB + 'recordKind', VOCAB + 'FrameworkDefinition')
        self.f.data.add(aid, VOCAB + 'framework', fixture.FRAMEWORK)
        self.f.save()
        self.f.accept(aid)
        ambiguous = answer_question(self.root, self.question)
        self.assertEqual(ambiguous['status'], 'needs_selection')
        self.assertEqual(len(ambiguous['choices']['framework_revision']), 2)
        selected = self.question[:-1] + (
            f' in framework "{fixture.FRAMEWORK}" at revision "{fixture.REVISION}"?'
        )
        result = answer_question(self.root, selected)
        self.assertEqual(result['status'], 'evaluated')
        self.assertEqual(result['request']['framework_revision'], fixture.REVISION)

    def test_empty_scope_discloses_no_resolution_choices_or_hidden_changes(self):
        before = answer_question(self.root, self.question, scope=AccessScope())
        self.assertEqual(before['choices'], {'subject': [], 'criterion': []})
        self.assertNotIn(fixture.PROJECT, json.dumps(before))
        self.f.data.add('urn:example:hidden', LABEL, 'Falcon', literal=True)
        self.f.save()
        self.assertEqual(before, answer_question(self.root, self.question, scope=AccessScope()))

    def test_explicit_iris_can_return_scoped_unknown_without_resolution_leaks(self):
        question = (
            f'Does project "{fixture.PROJECT}" have reviewed support for criterion '
            f'"{fixture.CRITERIA[0]}" in framework "{fixture.FRAMEWORK}" '
            f'at revision "{fixture.REVISION}"?'
        )
        result = answer_question(self.root, question, scope=AccessScope())
        self.assertEqual(result['status'], 'evaluated')
        self.assertEqual(result['evaluation']['criteria'][0]['outcome'], 'unknown')
        self.assertIn('unknown', result['answer'])
        self.assertFalse(result['evaluation']['assertions'])

    def test_cli_question_path_prints_interpretation_and_complete_receipt(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            main(['--data-root', str(self.root), 'evaluate', '--question', self.question])
        result = json.loads(output.getvalue())
        self.assertEqual(result['status'], 'evaluated')
        self.assertEqual(result['request']['subject'], fixture.PROJECT)
        self.assertIn(fixture.SUPPORT, result['evaluation']['assertions'])

    def test_no_mapping_answer_retains_scope_and_does_not_claim_incapability(self):
        question = (
            f'What reviewed support does project "{fixture.PROJECT}" have for criterion '
            f'"{fixture.CRITERIA[1]}"?'
        )
        result = answer_question(self.root, question)
        self.assertEqual(result['evaluation']['criteria'][0]['outcome'], 'no_qualifying_support')
        self.assertIn('evaluated scope', result['answer'])
        self.assertIn('does not establish lack of capability', result['answer'])

    def test_resolution_change_during_execution_fails_instead_of_returning_stale_interpretation(
        self,
    ):
        from knot.evaluation.engine import evaluate

        def mutate(root, request, *, scope):
            result = evaluate(root, request, scope=scope)
            self.f.data.add(fixture.CRITERIA[1], LABEL, 'Safe changes', literal=True)
            self.f.save()
            return result

        with patch('knot.evaluation.questions.evaluate', side_effect=mutate):
            with self.assertRaisesRegex(ValueError, 'Inputs changed'):
                answer_question(self.root, self.question)

    def test_corrupt_evidence_fails_without_a_fixed_positive_answer(self):
        (self.root / 'sources/framework.txt').write_text('Changed source')
        with self.assertRaisesRegex(ValueError, 'ChangedFile'):
            answer_question(self.root, self.question)

    def test_text_output_preserves_interpretation_and_the_complete_receipt(self):
        from knot.evaluation.render import render

        result = answer_question(self.root, self.question)
        text = render(result)
        self.assertTrue(text.startswith(result['answer']))
        self.assertEqual(json.loads(text.split('\n\n', 1)[1]), result)
