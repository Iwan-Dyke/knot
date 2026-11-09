import tempfile
import unittest
from pathlib import Path

from retrieval_fixture import SEED, make_fixture
from support import quality_evaluation as QUALITY

from knot.inventory import digest


class QualityBenchmarkTests(unittest.TestCase):
    def test_candidate_positions_distinguish_generation_retention_and_budget_loss(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            make_fixture(root)
            path = root / 'sources/unlinked.md'
            text = path.read_text()
            quote = 'Retries remain untested.'
            start = text.index(quote)
            manifest = {
                'label_author': 'Synthetic test',
                'independently_reviewed': False,
                'questions': [
                    {
                        'id': 'retry',
                        'question': 'What Orion retries remain untested?',
                        'seed': SEED,
                        'judgements': [
                            {
                                'path': 'sources/unlinked.md',
                                'sha256': digest(path.read_bytes()),
                                'quote': quote,
                                'character_offset': start,
                                'start_line': text[:start].count('\n') + 1,
                                'judgement': 'Relevant',
                                'qualification': True,
                            }
                        ],
                    }
                ],
            }
            report = QUALITY.evaluate(root, manifest, runs=2, max_chars=2000)
            method = report['cases'][0]['methods']['text']
            position = method['candidate_positions']['text']['labels'][0]
            self.assertTrue(position['generated'])
            self.assertEqual(position['ranked'], [1])
            self.assertEqual(position['retained'], [1])
            self.assertEqual(method['retained_relevant_omitted'], [0])
            self.assertEqual(method['qualifications_missed'], [0])
            self.assertGreaterEqual(
                method['latency_with_diagnostics']['median_ms'], method['latency']['median_ms']
            )
