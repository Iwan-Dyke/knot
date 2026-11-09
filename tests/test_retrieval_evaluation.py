import unittest

from support import retrieval_evaluation as evaluation


class RetrievalEvaluationTests(unittest.TestCase):
    def test_frozen_questions_expose_unlinked_evidence_and_distractors(self):
        report = evaluation.evaluate(runs=1, include_context=True)
        linked, unlinked, distractor = report['cases']
        self.assertEqual(linked['methods']['graph']['recall'], 1)
        self.assertEqual(unlinked['methods']['graph']['recall'], 0)
        self.assertEqual(unlinked['methods']['full_text']['recall'], 1)
        self.assertEqual(unlinked['methods']['hybrid']['recall'], 1)
        self.assertTrue(distractor['methods']['full_text']['irrelevant_evidence'])
        self.assertFalse(report['review_effort']['independently_labelled'])
        for case in report['cases']:
            for method in case['methods'].values():
                self.assertLessEqual(method['characters'], report['max_chars'])
                self.assertLessEqual(method['context']['usage']['passages'], report['max_passages'])
                self.assertEqual(
                    method['citation_integrity']['valid'], method['citation_integrity']['checked']
                )
                self.assertIsNone(method['unsupported_conclusions'])


if __name__ == '__main__':
    unittest.main()
