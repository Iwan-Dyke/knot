"""Source-first comparisons must not score supplied requests as language understanding."""

import contextlib
import copy
import io
import json
import unittest
from dataclasses import replace
from unittest.mock import patch

import test_evaluation as fixture
import test_explanations as explanation_fixture

from knot.diagnostics.coverage_benchmark import _evidence_package, compare, main
from knot.evaluation import explanations
from knot.evaluation.snapshot import canonical_hash
from knot.graph.rdf import LABEL
from knot.retrieval_engine.context import _prepare
from knot.shared.storage import digest


class TestCompare(unittest.TestCase):
    def setUp(self):
        self.f = fixture.CoverageTests()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.root = self.f.root
        self.f.data.add(fixture.PROJECT, LABEL, 'Falcon', literal=True)
        self.f.data.add(fixture.CRITERIA[0], LABEL, 'Safe changes', literal=True)
        self.f.save()
        path = 'sources/' + digest(fixture.SUPPORT.encode()) + '.txt'
        raw = (self.root / path).read_bytes()
        self.label = {
            'path': path,
            'sha256': digest(raw),
            'quote': raw.decode().strip(),
            'character_offset': 0,
            'start_line': 1,
            'judgement': 'Relevant',
            'qualification': True,
        }
        self.request = replace(self.f.request, criteria=(fixture.CRITERIA[0],)).to_dict()
        self.manifest = {
            'version': 1,
            'label_author': 'Synthetic labels',
            'independently_reviewed': False,
            'selection': 'Invented positive and unsupported questions; not held out.',
            'questions': [
                {
                    'id': 'checked',
                    'category': 'coverage',
                    'question': 'Does project "Falcon" have reviewed support for criterion "Safe changes"?',
                    'judgements': [self.label],
                    'expected': {
                        'question_status': 'evaluated',
                        'request': self.request,
                        'outcomes': ['support_found'],
                        'rationale': 'Reviewed synthetic mapping.',
                    },
                },
                {
                    'id': 'ordinary',
                    'category': 'coverage',
                    'question': 'What supports Falcon for Safe changes?',
                    'judgements': [self.label],
                    'expected': {
                        'question_status': 'unsupported_question',
                        'request': self.request,
                        'outcomes': ['support_found'],
                        'rationale': 'Same mapping, unsupported wording.',
                    },
                },
            ],
        }

    def test_compares_routes_without_claiming_retrieval_or_supplied_request_answers_prose(self):
        before = {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        original = copy.deepcopy(self.manifest)
        report = compare(self.root, self.manifest, runs=2, max_chars=24000)
        self.assertEqual(report['manifest_sha256'], canonical_hash(original))
        checked, ordinary = report['cases']
        self.assertTrue(checked['methods']['checked_question']['contract_match'])
        self.assertTrue(checked['methods']['checked_question']['interpretation_match'])
        self.assertTrue(checked['methods']['checked_question']['conclusive_answer'])
        self.assertEqual(ordinary['methods']['checked_question']['status'], 'unsupported_question')
        self.assertFalse(ordinary['methods']['checked_question']['conclusive_answer'])
        self.assertTrue(ordinary['methods']['structured_request']['conclusive_answer'])
        self.assertIsNone(ordinary['methods']['hybrid']['contract_match'])
        self.assertFalse(ordinary['methods']['hybrid']['conclusive_answer'])
        self.assertEqual(checked['methods']['structured_request']['labelled_recall'], 1)
        self.assertEqual(checked['methods']['structured_request']['qualification_recall'], 1)
        self.assertTrue(report['summary']['checked_question']['repeat_identical'])
        self.assertEqual(report['summary']['checked_question']['conclusive_answers'], 1)
        self.assertEqual(report['summary']['structured_request']['conclusive_answers'], 2)
        self.assertEqual(self.manifest, original)
        self.assertEqual(before, {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()})

    def test_wrong_expected_outcome_is_reported_not_rewritten(self):
        self.manifest['questions'][0]['expected']['outcomes'] = ['no_qualifying_support']
        report = compare(self.root, self.manifest, runs=1)
        row = report['cases'][0]['methods']['checked_question']
        self.assertFalse(row['contract_match'])
        self.assertFalse(row['outcomes_match'])
        self.assertEqual(report['summary']['checked_question']['contract_failures'], 1)

    def test_version_two_checks_coverage_through_current_router(self):
        self.manifest['version'] = 2
        for case in self.manifest['questions']:
            expected = case['expected']
            supported = expected.pop('question_status') == 'evaluated'
            expected.update(
                status='answered' if supported else 'unsupported_question',
                route='framework_coverage' if supported else None,
                answer=None,
            )
            if not supported:
                expected.update(request=None, outcomes=None)
        report = compare(self.root, self.manifest, runs=1)
        checked = report['cases'][0]['methods']['checked_answer']
        self.assertTrue(checked['contract_match'])
        self.assertTrue(checked['conclusive_answer'])
        self.assertEqual(checked['labelled_recall'], 1)
        self.assertEqual(checked['outcomes'], ['support_found'])
        self.assertEqual(report['summary']['checked_answer']['contract_failures'], 0)
        self.manifest['questions'][0]['expected']['outcomes'] = ['no_qualifying_support']
        report = compare(self.root, self.manifest, runs=1)
        self.assertFalse(report['cases'][0]['methods']['checked_answer']['outcomes_match'])

    def test_unknown_and_absence_are_distinguished_from_support_and_unsupported(self):
        self.manifest['questions'] = []
        for criterion, outcome in (
            (fixture.CRITERIA[1], 'no_qualifying_support'),
            ('urn:example:missing', 'unknown'),
        ):
            request = replace(self.f.request, criteria=(criterion,)).to_dict()
            self.manifest['questions'].append(
                {
                    'id': outcome,
                    'category': 'boundary',
                    'question': f'Does project "{fixture.PROJECT}" have reviewed support for criterion "{criterion}" in framework "{fixture.FRAMEWORK}" at revision "{fixture.REVISION}"?',
                    'judgements': [],
                    'expected': {
                        'question_status': 'evaluated',
                        'request': request,
                        'outcomes': [outcome],
                        'rationale': 'Synthetic definition/mapping state.',
                    },
                }
            )
        report = compare(self.root, self.manifest, runs=1)
        self.assertEqual(report['summary']['checked_question']['conclusive_answers'], 1)
        self.assertEqual(report['summary']['checked_question']['unknown_answers'], 1)
        self.assertEqual(report['summary']['checked_question']['contract_failures'], 0)

    def test_budget_excess_cannot_count_as_an_answer(self):
        report = compare(self.root, self.manifest, runs=1, max_chars=2048)
        row = report['cases'][0]['methods']['checked_question']
        self.assertEqual(row['status'], 'output_budget')
        self.assertFalse(row['conclusive_answer'])
        self.assertIsNone(row['contract_match'])
        self.assertNotIn('context', row)
        self.assertEqual(row['citation_integrity']['checked'], 0)

    def test_corrupt_labels_duplicate_ids_and_missing_expectations_fail_before_execution(self):
        for modify in (
            lambda m: m['questions'].append(m['questions'][0]),
            lambda m: m['questions'][0].pop('expected'),
            lambda m: m['questions'][0]['judgements'][0].update(quote='invented'),
        ):
            manifest = copy.deepcopy(self.manifest)
            modify(manifest)
            with patch('knot.diagnostics.coverage_benchmark.retrieve') as run:
                with self.assertRaises((ValueError, KeyError)):
                    compare(self.root, manifest, runs=1)
                run.assert_not_called()

    def test_different_repeat_and_changed_inputs_fail_explicitly(self):
        from knot.evaluation import answer_question

        count = 0

        def varying(*args, **kwargs):
            nonlocal count
            count += 1
            result = answer_question(*args, **kwargs)
            result['extra'] = count
            return result

        with patch('knot.diagnostics.coverage_benchmark.answer_question', side_effect=varying):
            with self.assertRaisesRegex(ValueError, 'repeat'):
                compare(self.root, self.manifest, runs=2)

        def changing(*args, **kwargs):
            result = answer_question(*args, **kwargs)
            (self.root / 'curation').mkdir(exist_ok=True)
            (self.root / 'curation/benchmark-change.json').write_text(json.dumps({'changed': True}))
            return result

        with patch('knot.diagnostics.coverage_benchmark.answer_question', side_effect=changing):
            with self.assertRaisesRegex(ValueError, 'Inputs changed'):
                compare(self.root, self.manifest, runs=1)

    def test_cli_keeps_reports_outside_the_dataset_and_preserves_the_manifest(self):
        path = self.root / 'questions.json'
        path.write_text(json.dumps(self.manifest))
        original = path.read_bytes()
        for output in (path, self.root / 'report.json'):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                main(
                    [
                        '--data-root',
                        str(self.root),
                        '--questions',
                        str(path),
                        '--output',
                        str(output),
                    ]
                )
        self.assertEqual(path.read_bytes(), original)
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            main(['--data-root', str(self.root), '--questions', str(path), '--runs', '1'])
        report = json.loads(stream.getvalue())
        self.assertIsNone(report['summary']['hybrid']['repeat_identical'])

    def test_evidence_account_qualifications_are_checked_and_included_in_recall(self):
        span = {
            'revision': fixture.SUPPORT + ':revision',
            'sha256': self.label['sha256'],
            'text_sha256': self.label['sha256'],
            'start': 0,
            'end': len(self.label['quote']),
            'quote': self.label['quote'],
        }
        receipt = {'assertions': {'a': {'sources': [], 'evidence_account_sources': [span]}}}
        store = _prepare(self.root)[0]
        package = _evidence_package(self.root, store, receipt)
        self.assertEqual(list(package['passages'].values()), [self.label['quote']])
        span['sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'evidence-account'):
            _evidence_package(self.root, store, receipt)


class TestCheckedAnswerCompare(unittest.TestCase):
    def setUp(self):
        self.f = explanation_fixture.TestExplanations()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.root = self.f.root
        self.wording = 'Why did we choose batching?'
        explanations.approve(
            self.root,
            explanations.prepare(self.root, self.f.request, wordings=[self.wording]),
            reviewer='Synthetic reviewer',
            reason='Check the question and qualified answer against the source.',
        )
        self.manifest = {
            'version': 2,
            'label_author': 'Synthetic labels',
            'independently_reviewed': False,
            'selection': 'Constructed development cases, not independent or representative.',
            'questions': [],
        }
        for index, question in enumerate(
            (
                self.wording,
                'Explain the batching choice',
                self.wording + ' Did it succeed?',
                'What should I cook for dinner?',
            )
        ):
            self.manifest['questions'].append(
                {
                    'id': str(index),
                    'category': 'decision',
                    'question': question,
                    'judgements': [
                        {
                            'path': self.f.source['body_path'],
                            'sha256': self.f.source['body_sha256'],
                            'quote': self.f.source['body'],
                            'character_offset': 0,
                            'start_line': 1,
                            'judgement': 'Relevant',
                            'qualification': True,
                        }
                    ]
                    if index < 3
                    else [],
                    'expected': {
                        'status': 'answered' if index == 0 else 'unsupported_question',
                        'route': 'decision_explanation' if index == 0 else None,
                        'request': self.f.request if index == 0 else None,
                        'outcomes': None,
                        'answer': self.f.note['body'] if index == 0 else None,
                        'rationale': 'Only the complete registered wording has an approved answer; '
                        'the source does not establish delivery.',
                    },
                }
            )

    def test_measures_current_router_without_counting_or_executing_navigation_as_answers(self):
        before = {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        original = copy.deepcopy(self.manifest)
        report = compare(self.root, self.manifest, runs=2, include_context=True)
        self.assertEqual(report['benchmark_version'], 2)
        summary = report['summary']['checked_answer']
        self.assertEqual(summary['cases'], 4)
        self.assertEqual(summary['conclusive_answers'], 1)
        self.assertEqual(summary['correct_conclusive_answers'], 1)
        self.assertEqual(summary['contract_failures'], 0)
        self.assertEqual(summary['questions_with_alternatives'], 2)
        self.assertEqual(summary['alternatives_offered'], 2)
        self.assertTrue(summary['repeat_identical'])
        self.assertNotIn('checked_question', report['summary'])
        row = report['cases'][0]['methods']['checked_answer']
        self.assertTrue(row['answer_match'])
        self.assertEqual(row['labelled_recall'], 1)
        self.assertEqual(row['qualification_recall'], 1)
        self.assertEqual(row['citation_integrity']['checked'], 1)
        for case in report['cases'][1:]:
            row = case['methods']['checked_answer']
            self.assertFalse(row['conclusive_answer'])
            self.assertNotIn('answer', row['context'])
            self.assertEqual(row['citation_integrity']['checked'], 0)
        self.assertEqual(report['manifest_sha256'], canonical_hash(original))
        self.assertEqual(self.manifest, original)
        self.assertEqual(before, {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()})

    def test_wrong_answer_or_interpretation_is_a_mismatch_not_a_rewritten_label(self):
        self.manifest['questions'] = self.manifest['questions'][:1]
        expected = self.manifest['questions'][0]['expected']
        expected['answer'] = 'Batching was delivered successfully.\n'
        report = compare(self.root, self.manifest, runs=1)
        self.assertFalse(report['cases'][0]['methods']['checked_answer']['answer_match'])
        self.assertEqual(report['summary']['checked_answer']['correct_conclusive_answers'], 0)
        self.assertEqual(report['cases'][0]['expected'], expected)
        expected['answer'] = self.f.note['body']
        expected['request']['decision'] = 'urn:example:other'
        expected['request']['question'] = 'Why was decision "urn:example:other" chosen?'
        report = compare(self.root, self.manifest, runs=1)
        self.assertFalse(report['cases'][0]['methods']['checked_answer']['interpretation_match'])
        self.assertEqual(report['summary']['checked_answer']['contract_failures'], 1)

    def test_budget_hides_answer_evidence_and_navigation_and_does_not_claim_a_match(self):
        report = compare(self.root, self.manifest, runs=1, max_chars=2048, include_context=True)
        row = report['cases'][0]['methods']['checked_answer']
        self.assertEqual(row['status'], 'output_budget')
        self.assertFalse(row['conclusive_answer'])
        self.assertIsNone(row['answer_match'])
        self.assertIsNone(row['contract_match'])
        self.assertNotIn('context', row)
        self.assertEqual(row['citation_integrity']['checked'], 0)
        self.assertEqual(row['alternatives_offered'], 0)

    def test_independent_review_requires_attribution_and_does_not_infer_it_from_approval(self):
        self.manifest['independently_reviewed'] = True
        with patch('knot.diagnostics.coverage_benchmark.retrieve') as run:
            with self.assertRaisesRegex(ValueError, 'reviewer'):
                compare(self.root, self.manifest, runs=1)
            run.assert_not_called()
        self.manifest['independent_reviewer'] = 'Another synthetic reviewer'
        report = compare(self.root, self.manifest, runs=1)
        self.assertEqual(report['independent_reviewer'], 'Another synthetic reviewer')

    def test_missing_answer_and_invalid_expectations_fail_before_execution(self):
        for update in (
            {'answer': None},
            {'route': None},
            {'status': 'evaluated'},
            {'outcomes': ['support_found']},
        ):
            manifest = copy.deepcopy(self.manifest)
            manifest['questions'][0]['expected'].update(update)
            with patch('knot.diagnostics.coverage_benchmark.retrieve') as run:
                with self.assertRaises(ValueError):
                    compare(self.root, manifest, runs=1)
                run.assert_not_called()

    def test_returned_explanation_citation_is_verified_independently(self):
        from knot.evaluation.answering import answer

        self.manifest['questions'] = self.manifest['questions'][:1]

        def corrupt(*args, **kwargs):
            result = answer(*args, **kwargs)
            result['result']['sources'][0]['locator']['characterOffset'] = '1'
            return result

        with patch('knot.diagnostics.coverage_benchmark.answering.answer', side_effect=corrupt):
            with self.assertRaisesRegex(ValueError, 'invalid character locator'):
                compare(self.root, self.manifest, runs=1)

    def test_oversized_navigation_is_not_counted_or_retained(self):
        from knot.evaluation.answering import answer

        self.manifest['questions'] = self.manifest['questions'][1:2]

        def oversized(*args, **kwargs):
            result = answer(*args, **kwargs)
            self.assertTrue(result['alternatives'])
            result['padding'] = 'x' * 2048
            return result

        with patch('knot.diagnostics.coverage_benchmark.answering.answer', side_effect=oversized):
            report = compare(self.root, self.manifest, runs=1, max_chars=2048, include_context=True)
        row = report['cases'][0]['methods']['checked_answer']
        self.assertEqual(row['status'], 'output_budget')
        self.assertEqual(row['alternatives_offered'], 0)
        self.assertIsNone(row['contract_match'])
        self.assertNotIn('context', row)

    def test_unapproved_explanation_is_unknown_not_an_answer(self):
        event = explanations.history(self.root, self.f.request)[-1]
        explanations.withdraw(
            self.root,
            self.f.request,
            expected=event['event_sha256'],
            reviewer='Synthetic reviewer',
            reason='Reconsider applicability.',
        )
        self.manifest['questions'] = self.manifest['questions'][:1]
        self.manifest['questions'][0]['expected'].update(
            status='unknown', request=None, answer=None
        )
        report = compare(self.root, self.manifest, runs=1)
        summary = report['summary']['checked_answer']
        self.assertEqual(summary['unknown_answers'], 1)
        self.assertEqual(summary['conclusive_answers'], 0)
        self.assertEqual(summary['contract_failures'], 0)
