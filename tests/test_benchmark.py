import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pyoxigraph import RdfFormat, Store
from retrieval_fixture import make_fixture

from knot.benchmark import _assess, evaluate
from knot.diagnostics.benchmark import main
from knot.inventory import digest
from knot.rdf import VOCAB, Dataset


class BenchmarkTests(unittest.TestCase):
    def test_cli_requires_explicit_questions_instead_of_private_experiment_defaults(self):
        errors = io.StringIO()
        with (
            patch('sys.argv', ['benchmark']),
            patch('pathlib.Path.read_text', side_effect=FileNotFoundError('No question file')),
            contextlib.redirect_stderr(errors),
        ):
            with self.assertRaises(SystemExit) as stopped:
                main()
        self.assertEqual(stopped.exception.code, 2)
        self.assertIn('--questions', errors.getvalue())

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        make_fixture(self.root)
        self.manifest = {
            'label_author': 'Synthetic test labels',
            'independently_reviewed': False,
            'questions': [
                self.question(
                    'dependency',
                    'What Orion survey feed dependency is recorded?',
                    'dependency.md',
                    'The survey feed is missing.',
                ),
                self.question(
                    'retries',
                    'What Orion retries remain untested?',
                    'unlinked.md',
                    'Retries remain untested.',
                ),
            ],
        }

    def question(self, key, question, file, quote):
        raw = (self.root / 'sources' / file).read_bytes()
        text = raw.decode()
        start = text.index(quote)
        return {
            'id': key,
            'question': question,
            'seed_label': 'Orion',
            'seed': 'urn:project:orion',
            'judgements': [
                {
                    'path': 'sources/' + file,
                    'sha256': digest(raw),
                    'quote': quote,
                    'character_offset': start,
                    'start_line': text[:start].count('\n') + 1,
                    'judgement': 'Relevant',
                    'qualification': key == 'retries',
                }
            ],
        }

    def test_shared_budget_comparison_measures_source_evidence_and_qualifications(self):
        report = evaluate(self.root, self.manifest, runs=2)
        self.assertIn('retrieval_engine/search.py', report['implementation_sha256'])
        self.assertIn('writing/notes.py', report['implementation_sha256'])
        self.assertIn('graph/query.py', report['implementation_sha256'])
        self.assertFalse(report['independently_reviewed'])
        dependency, retries = report['cases']
        self.assertEqual(dependency['methods']['legacy_graph']['labelled_recall'], 1)
        self.assertGreater(dependency['methods']['legacy_graph']['unjudged_passages'], 0)
        self.assertEqual(dependency['methods']['legacy_graph']['judged_precision'], 1)
        self.assertEqual(retries['methods']['legacy_graph']['labelled_recall'], 0)
        self.assertEqual(retries['methods']['text']['qualification_recall'], 1)
        self.assertEqual(retries['methods']['hybrid']['labelled_recall'], 1)
        for case in report['cases']:
            self.assertEqual(set(case['methods']), {'legacy_graph', 'graph', 'text', 'hybrid'})
            for method in case['methods'].values():
                self.assertLessEqual(method['characters'], report['max_chars'])
                self.assertEqual(
                    method['citation_integrity']['valid'], method['citation_integrity']['checked']
                )
                self.assertIsNone(method['unsupported_conclusions'])

    def test_changed_or_invalid_source_judgements_stop_evaluation(self):
        (self.root / 'sources/dependency.md').write_text('changed')
        with self.assertRaisesRegex(ValueError, 'ChangedFile'):
            evaluate(self.root, self.manifest, runs=1)

    def test_duplicate_questions_and_ambiguous_seed_fail_explicitly(self):
        self.manifest['questions'].append(self.manifest['questions'][0])
        with self.assertRaisesRegex(ValueError, 'unique'):
            evaluate(self.root, self.manifest, runs=1)
        self.manifest['questions'].pop()
        self.manifest['questions'][0].pop('seed')
        with self.assertRaisesRegex(ValueError, 'explicit seed'):
            evaluate(self.root, self.manifest, runs=1)

    def test_repeated_quote_at_another_location_is_not_a_relevance_hit(self):
        quote = 'Outcome achieved.'
        text = '# Orion\n' + quote + '\n\n' + quote + '\n'
        (self.root / 'sources/repeated.md').write_text(text)
        data = Dataset()
        revision = 'urn:revision:repeated'
        sha = digest(text.encode())
        data.add(revision, VOCAB + 'snapshotPath', 'sources/repeated.md', literal=True)
        data.add(revision, VOCAB + 'sha256', sha, literal=True)
        store = Store()
        store.load(input=data.text(), format=RdfFormat.TRIG)
        question = {
            'judgements': [
                {
                    'path': 'sources/repeated.md',
                    'sha256': sha,
                    'quote': quote,
                    'character_offset': text.rindex(quote),
                    'judgement': 'Relevant',
                }
            ]
        }
        result = {
            'passages': {'p1': quote},
            'sources': {
                'e1': {
                    'revision': revision,
                    'sha256': sha,
                    'snapshot': 'sources/repeated.md',
                    'text_path': 'sources/repeated.md',
                    'text_sha256': sha,
                    'passage': 'p1',
                    'locator': {'characterOffset': str(text.index(quote))},
                }
            },
        }
        self.assertEqual(_assess(self.root, store, result, question)['labelled_recall'], 0)


if __name__ == '__main__':
    unittest.main()
