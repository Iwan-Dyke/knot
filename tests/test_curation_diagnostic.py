import copy
import tempfile
import unittest
from pathlib import Path

from retrieval_fixture import make_fixture

from knot.curating.provenance import source_pin
from knot.diagnostics.curation import diagnose
from knot.notes import create_note
from knot.retrieval_engine.policy import Policy
from knot.retrieval_engine.service import retrieve
from knot.shared.storage import digest


class CurationDiagnosticTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        make_fixture(self.root)
        self.quote = 'The trial succeeded, but only on the sampled inputs.'
        self.source = create_note(self.root, self.quote, title='Notes')
        pin = source_pin(self.root, self.source['revision'], self.quote, 0)
        self.label = {
            'path': self.source['body_path'],
            'sha256': pin['text_sha256'],
            'quote': self.quote,
            'character_offset': 0,
            'start_line': 1,
            'judgement': 'Relevant',
            'qualification': True,
        }
        self.manifest = {
            'questions': [
                {'id': key, 'question': text, 'judgements': [self.label]}
                for key, text in [('a', 'Trial succeeded?'), ('b', 'Scope?'), ('c', 'Limitations?')]
            ]
        }
        self.empty = {'passages': {}, 'sources': {}}
        self.results = [
            {'id': 'a', 'result': retrieve(self.root, self.source['note'], Policy())},
            {'id': 'b', 'result': self.empty},
            {'id': 'c', 'result': self.empty},
        ]

    def curate(self, quote):
        return create_note(
            self.root,
            'A trial account with a limited scope.',
            title='Trial context',
            author='Synthetic curator',
            agent='Test',
            derivation={
                'method': 'faithful_restatement',
                'qualification': 'An account, not independent validation.',
                'sources': [source_pin(self.root, self.source['revision'], quote, 0)],
            },
        )

    def inventory(self):
        return {
            p.relative_to(self.root).as_posix(): digest(p.read_bytes())
            for p in self.root.rglob('*')
            if p.is_file()
        }

    def test_verified_repeated_failures_produce_reviewable_read_only_recommendations(self):
        before = self.inventory()
        report = diagnose(self.root, self.manifest, self.results)
        self.assertEqual(before, self.inventory())
        self.assertEqual(report, diagnose(self.root, self.manifest, self.results))
        self.assertEqual(len(report['recommendations']), 1)
        item = report['recommendations'][0]
        self.assertEqual(item['evidence'], self.label)
        self.assertEqual(item['missed_questions'], ['b', 'c'])
        self.assertEqual(
            set(item['signals']),
            {
                'generic_title',
                'no_covering_curated_span',
                'repeated_failure',
                'wording_sensitivity',
            },
        )
        self.assertTrue(item['human_review_required'])
        self.assertTrue(item['why_retrieval_may_improve'])
        self.assertTrue(item['smallest_proposed_correction'])

    def test_partial_qualification_pin_is_review_prompt_not_semantic_verdict(self):
        self.curate('The trial succeeded')
        item = diagnose(self.root, self.manifest, self.results)['recommendations'][0]
        self.assertIn('partial_qualified_context', item['signals'])
        self.assertIn('not establish', item['limitations'])

    def test_existing_covering_description_prevents_redundant_summary_recommendation(self):
        self.curate(self.quote)
        item = diagnose(self.root, self.manifest, self.results)['recommendations'][0]
        self.assertNotIn('no_covering_curated_span', item['signals'])
        self.assertNotIn('partial_qualified_context', item['signals'])
        self.assertIn('existing', item['smallest_proposed_correction'])

    def test_a_labelled_curated_note_does_not_need_another_description_of_itself(self):
        curated = self.curate(self.quote)
        label = {
            **self.label,
            'path': curated['body_path'],
            'sha256': curated['body_sha256'],
            'quote': curated['body'],
        }
        manifest = copy.deepcopy(self.manifest)
        for question in manifest['questions']:
            question['judgements'] = [label]
        results = [{'id': q['id'], 'result': self.empty} for q in manifest['questions']]
        item = diagnose(self.root, manifest, results)['recommendations'][0]
        self.assertNotIn('no_covering_curated_span', item['signals'])
        self.assertIn('existing curated note', item['smallest_proposed_correction'])

    def test_unmeasured_and_successful_sources_do_not_trigger_curation_work(self):
        create_note(self.root, 'Unrelated personal note.', title='Notes')
        results = [
            {'id': q['id'], 'result': self.results[0]['result']} for q in self.manifest['questions']
        ]
        self.assertEqual(diagnose(self.root, self.manifest, results)['recommendations'], [])

    def test_partial_or_duplicated_runs_and_invalid_evidence_fail(self):
        for results in [self.results[:1], [*self.results, self.results[0]]]:
            with self.assertRaises(ValueError):
                diagnose(self.root, self.manifest, results)
        bad = copy.deepcopy(self.results)
        next(iter(bad[0]['result']['sources'].values()))['sha256'] = '0' * 64
        with self.assertRaises(ValueError):
            diagnose(self.root, self.manifest, bad)
