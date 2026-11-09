import copy
import unittest

from knot.retrieval_engine.response import _measure, serialise
from knot.retrieval_engine.wire import compact, expand


class CompactResponseTests(unittest.TestCase):
    def test_evidence_view_omits_only_diagnostics_and_preserves_input(self):
        from knot.retrieval_engine.wire import evidence_view

        result = self.fixture()
        result.update(
            ranking={'terms': ['outcome']},
            selection={'trials': 120},
            policy={'accepted_only': False, 'max_depth': 2},
            matches=[{'channel': 'text', 'source': 'e0', 'ranking': {'score': 2}}],
            source_context={'e0': {'claim_review': None, 'qualification': 'Not proven.'}},
        )
        result['usage'].update(source_revisions=64, passages=3)
        before = copy.deepcopy(result)
        view = evidence_view(result)
        self.assertEqual(result, before)
        for key in ('sources', 'passages', 'assertions', 'source_context', 'policy', 'omissions'):
            self.assertEqual(view[key], result[key])
        self.assertNotIn('ranking', view)
        self.assertNotIn('selection', view)
        self.assertNotIn('ranking', view['matches'][0])
        self.assertNotIn('source_revisions', view['usage'])
        self.assertEqual(view['usage']['passages'], 3)
        self.assertEqual(evidence_view(view), view)
        self.assertEqual(expand(compact(view)), view)

    def fixture(self):
        pin = {
            'revision': 'original',
            'sha256': 'a' * 64,
            'text_sha256': 'b' * 64,
            'quote': 'Reported, not independently verified. ' * 40,
            'character_offset': 7,
            'start_line': 2,
        }
        metadata = {
            'revision': 'derived',
            'sha256': 'c' * 64,
            'independence': 'DerivedAccount',
            'native_note': {
                'author': 'An assistant',
                'currentness': 'LatestGrantedRevision',
                'derivation': {'qualification': 'Outcome remains unknown', 'sources': [pin]},
            },
        }
        result = {
            'sources': {
                f'e{i}': dict(
                    copy.deepcopy(metadata), passage=f'p{i}', locator={'characterOffset': i}
                )
                for i in range(3)
            },
            'passages': {f'p{i}': 'Exact evidence ' + str(i) for i in range(3)},
            'omissions': {'further_unknown': True},
            'assertions': {'a': {'status': 'Unreviewed'}},
            'usage': {'characters': 0, 'utf8_bytes': 0},
        }
        _measure(result)
        return result

    def test_round_trip_preserves_every_field_and_input(self):
        result = self.fixture()
        before = copy.deepcopy(result)
        encoded = compact(result)
        self.assertLess(len(serialise(encoded)), len(serialise(result)))
        self.assertEqual(encoded['format'], 'shared-provenance-v1')
        self.assertEqual(expand(encoded), result)
        self.assertEqual(result, before)
        self.assertEqual(encoded['usage']['characters'], len(serialise(encoded)))
        self.assertEqual(encoded['usage']['utf8_bytes'], len(serialise(encoded).encode()))

    def test_same_revision_different_currentness_does_not_merge_metadata(self):
        result = self.fixture()
        result['sources']['e1']['native_note']['currentness'] = 'ExplicitHistoricalRevision'
        result['passages']['p1'] = 'λ😀 Qualification: no demonstrated outcome.'
        _measure(result)
        encoded = compact(result)
        self.assertEqual(len(encoded['source_metadata']), 2)
        self.assertEqual(expand(encoded), result)

    def test_falls_back_when_factoring_costs_more_and_is_idempotent(self):
        result = {'sources': {}, 'usage': {'characters': 0, 'utf8_bytes': 0}}
        _measure(result)
        self.assertEqual(compact(result), result)
        result = compact(self.fixture())
        self.assertEqual(compact(result), result)
        self.assertEqual(expand(expand(result)), expand(result))

    def test_unknown_format_or_missing_reference_is_rejected(self):
        result = compact(self.fixture())
        del result['source_metadata']['r1']
        with self.assertRaises(ValueError):
            expand(result)
        with self.assertRaises(ValueError):
            expand({'format': 'future'})
