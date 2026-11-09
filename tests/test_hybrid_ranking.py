import unittest
from types import SimpleNamespace
from unittest.mock import patch

from knot.search import _fuse, _Question


class HybridRankingTests(unittest.TestCase):
    def setUp(self):
        self.scorer = _Question('What measurable outcomes?', [])

    def text(self, name, score, *, revision=None, quote='A documented account.'):
        return {
            'channel': 'text',
            'id': name,
            'quote': quote,
            'citation': {'revision': revision or name, 'locator': {'characterOffset': '0'}},
            'ranking': {'score': score, 'matched': ['outcome'], 'concepts': []},
        }

    def graph(self, name, score):
        return {
            'channel': 'graph',
            'path': [{'assertion': name, 'direction': 'outgoing'}],
            'ranking': {'score': score, 'matched': [], 'concepts': []},
        }

    def test_fusion_preserves_relative_scores_instead_of_recounting_keywords(self):
        strong, incidental = self.text('strong', 10), self.text('incidental', 1)
        fused = _fuse([], [strong, incidental], None, None, self.scorer)
        self.assertAlmostEqual(fused[1]['fusion_score'] / fused[0]['fusion_score'], 0.1 * 61 / 62)

    def test_predicate_relevance_survives_without_literal_question_words(self):
        candidate = self.graph('claim', 6)
        evidence = SimpleNamespace(citation=lambda _: ('An observation.', {}))
        with patch(
            'knot.retrieval_engine.search.values', return_value=[SimpleNamespace(value='evidence')]
        ):
            fused = _fuse([candidate], [], None, evidence, self.scorer)
        self.assertGreater(fused[0]['fusion_score'], 0)

    def test_exact_containing_context_can_explain_a_short_claims_relevance(self):
        graph = [self.graph('other', 10), self.graph('short', 1)]
        context = self.text(
            'context', 8, revision='short', quote='Result. However, scope is limited.'
        )
        unrelated = self.text('unrelated', 10)

        def citation(name):
            return 'Result.', {'revision': name, 'locator': {'characterOffset': '0'}}

        evidence = SimpleNamespace(citation=citation)
        with patch(
            'knot.retrieval_engine.search.values',
            side_effect=lambda _, aid, __: [SimpleNamespace(value=aid)],
        ):
            fused = _fuse(graph, [unrelated, context], None, evidence, self.scorer)
        short = next(c for c in fused if c.get('path') == graph[1]['path'])
        other = next(c for c in fused if c.get('path') == graph[0]['path'])
        self.assertGreater(short['fusion_score'], other['fusion_score'])
        for revision, offset, quote in (
            ('different', '0', 'Result. However, scope is limited.'),
            ('short', '10', 'Result. However, scope is limited.'),
            ('short', '0', 'Result. Further background.'),
        ):
            with self.subTest(revision=revision, offset=offset, quote=quote):
                context['citation'].update(revision=revision, locator={'characterOffset': offset})
                context['quote'] = quote
                with patch(
                    'knot.retrieval_engine.search.values',
                    side_effect=lambda _, aid, __: [SimpleNamespace(value=aid)],
                ):
                    fused = _fuse(graph, [unrelated, context], None, evidence, self.scorer)
                short = next(c for c in fused if c.get('path') == graph[1]['path'])
                other = next(c for c in fused if c.get('path') == graph[0]['path'])
                self.assertLess(short['fusion_score'], other['fusion_score'])

    def test_measurement_intent_recognises_targets_and_recorded_completion(self):
        scorer = _Question('What measurable outcomes did the reading experiment have?', [])
        result = scorer.score('The target was ten books; twelve were completed.')
        proposal = scorer.score('We proposed a framework for future measurement.')
        self.assertIn('measurement', scorer.intents)
        self.assertGreater(result['score'], proposal['score'])

    def test_other_questions_retain_the_established_fusion(self):
        strong, incidental = self.text('strong', 10), self.text('incidental', 1)
        fused = _fuse([], [strong, incidental], None, None, _Question('What outcome?', []))
        self.assertAlmostEqual(fused[1]['fusion_score'] / fused[0]['fusion_score'], 61 / 62)
