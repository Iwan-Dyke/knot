"""Source-first comparisons must not score supplied requests as language understanding."""

import contextlib
import copy
import io
import json
import unittest
from dataclasses import replace
from unittest.mock import patch

import test_evaluation as fixture

from knot.diagnostics.coverage_benchmark import _evidence_package, compare, main
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
