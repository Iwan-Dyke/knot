import copy
import unittest
from unittest.mock import patch

from knot.retrieval import Policy, _envelope, _measure, _prune, _quotation, _resize, serialise
from knot.selection import _features, _select, merge


class SelectionTests(unittest.TestCase):
    def setUp(self):
        self.policy = Policy(max_chars=7000, max_passages=4)
        self.base = _envelope('urn:seed', self.policy, [], [])
        self.base.update(matches=[], source_context={}, ranking={'terms': ['design', 'result']})

    def package(self, name, quote, relevance, terms, *, offset=0, revision=None):
        envelope = copy.deepcopy(self.base)
        envelope['passages']['p1'] = quote
        envelope['sources'][name] = {
            'revision': revision or name,
            'text_path': revision or name,
            'text_sha256': 'a' * 64,
            'passage': 'p1',
            'locator': {'characterOffset': str(offset)},
        }
        envelope['source_context'][name] = {'claim_review': None, 'entity_link': 'LexicalOnly'}
        envelope['matches'].append(
            {'channel': 'text', 'source': name, 'ranking': {'matched': terms}}
        )
        return {'envelope': envelope, 'relevance': relevance, 'terms': terms, 'key': name}

    def test_best_combination_can_displace_expensive_highest_rank(self):
        packages = [
            self.package('large', 'Design background. ' * 240, 1, ['design']),
            self.package('choice', 'Different design choice. ' * 65, 0.85, ['design']),
            self.package('result', 'An observed result. ' * 65, 0.85, ['result']),
        ]
        result = _select(self.base, packages, self.policy, {'design': 1, 'result': 1})
        self.assertIn('choice', result['source_context'])
        self.assertIn('result', result['source_context'])
        self.assertNotIn('large', result['source_context'])
        self.assertLessEqual(len(serialise(result)), self.policy.max_chars)

    def test_overlap_shares_storage_without_changing_citation_quotations(self):
        text = 'A documented outcome. Caveat: attribution remains uncertain.\n'
        short = 'A documented outcome.'
        packages = [
            self.package('short', short, 1, ['result'], revision='same'),
            self.package('context', text, 1, ['result'], revision='same'),
        ]
        result = merge(self.base, packages)
        self.assertEqual(len(result['passages']), 1)
        self.assertEqual(_quotation(result, result['sources']['short']), short)
        self.assertEqual(_quotation(result, result['sources']['context']), text)
        self.assertEqual(result['sources']['short']['locator']['characterOffset'], '0')
        other = self.package('other', text, 1, ['result'], revision='different')
        result = merge(self.base, [packages[0], other])
        self.assertEqual(len(result['passages']), 2)

    def test_relevance_first_retains_complete_primary_evidence_before_cheaper_context(self):
        quote = 'The capacity limit is three per workflow; adoption is unmeasured. ' * 60
        packages = [
            self.package('clarification', quote, 1, ['design', 'result']),
            self.package('background', 'Different design background. ' * 35, 0.85, ['design']),
            self.package('example', 'An unrelated result. ' * 35, 0.85, ['result']),
        ]
        result = _select(
            self.base,
            packages,
            self.policy,
            {'design': 1, 'result': 1},
            strategy='relevance_first',
        )
        self.assertIn('clarification', result['sources'])
        self.assertEqual(_quotation(result, result['sources']['clarification']), quote)
        self.assertLessEqual(len(serialise(result)), self.policy.max_chars)

    def test_relevance_first_skips_unfit_evidence_and_retains_complementary_context(self):
        packages = [
            self.package('oversized', 'Full context. ' * 1000, 1, ['design', 'result']),
            self.package('first', 'A documented design choice.', 0.9, ['design']),
            self.package('echo', 'A documented design choice.', 0.89, ['design']),
            self.package('outcome', 'The result remains untested.', 0.8, ['result']),
        ]
        result = _select(
            self.base,
            packages,
            Policy(max_chars=4000, max_passages=2),
            {'design': 1, 'result': 1},
            strategy='relevance_first',
        )
        self.assertEqual(set(result['sources']), {'first', 'outcome'})
        self.assertLessEqual(result['usage']['characters'], 4000)

    def test_redundant_accounts_do_not_displace_a_different_question_facet(self):
        packages = [
            self.package('first', 'A design choice was documented.', 1, ['design']),
            self.package('echo', 'A design choice was documented.', 0.99, ['design']),
            self.package('result', 'The result remains untested.', 0.8, ['result']),
        ]
        result = _select(
            self.base, packages, Policy(max_chars=4000, max_passages=2), {'design': 1, 'result': 1}
        )
        self.assertIn('result', result['source_context'])
        self.assertFalse({'first', 'echo'} <= result['source_context'].keys())

    def test_brevity_does_not_beat_a_more_useful_complete_package(self):
        important = self.package(
            'complete', 'Design result with necessary context. ' * 95, 1, ['design', 'result']
        )
        small = self.package('small', 'Design only.', 0.1, ['design'])
        result = _select(self.base, [important, small], self.policy, {'design': 1, 'result': 1})
        self.assertIn('complete', result['source_context'])
        self.assertEqual(
            _quotation(result, result['sources']['complete']),
            important['envelope']['passages']['p1'],
        )

    def test_complete_qualified_account_can_beat_unqualified_variations(self):
        claim = ' '.join(f'Observation {i} records an outcome.' for i in range(60))
        packages = [
            self.package('claim', claim, 1, ['result']),
            self.package(
                'qualified',
                claim + ' However, the outcome is not independently verified.',
                0.99,
                ['result'],
            ),
            self.package(
                'other', ' '.join(f'Another {i} result.' for i in range(25)), 0.9, ['result']
            ),
        ]
        result = _select(
            self.base, packages, Policy(max_chars=12000, max_passages=2), {'result': 1}
        )
        self.assertIn('qualified', result['source_context'])

    def test_tiny_edits_to_long_accounts_have_little_marginal_content(self):
        text = ' '.join(f'Observation {i} records an outcome.' for i in range(200))
        first = _features(self.package('first', text, 1, ['result']), {'result': 1})
        edited = _features(
            self.package('edited', text + ' An editorial note.', 1, ['result']), {'result': 1}
        )
        novel = sum(
            max(0, weight - first.get(feature, 0))
            for feature, weight in edited.items()
            if feature[0] == 'text'
        )
        self.assertLess(novel, 0.1)

    def test_spare_character_budget_does_not_double_charge_a_passage(self):
        large = self.package(
            'complete', ' '.join(f'Long evidence detail {i}.' for i in range(210)), 1, ['result']
        )
        smaller = [
            self.package(
                f'short-{j}',
                ' '.join(f'Account {j} detail {i}.' for i in range(20)),
                0.8,
                ['result'],
            )
            for j in range(4)
        ]
        result = _select(
            self.base, [large, *smaller], Policy(max_chars=24000, max_passages=4), {'result': 1}
        )
        self.assertIn('complete', result['source_context'])
        self.assertEqual(len(result['source_context']), 4)

    def test_qualification_dependency_survives_removing_its_separate_match(self):
        package = self.package('context', 'Outcome. However, acceptance is pending.', 1, ['result'])
        result = package['envelope']
        result['matches'].insert(
            0,
            {
                'channel': 'graph',
                'path': 0,
                'ranking': {'matched': ['result']},
                'context_sources': copy.deepcopy(result['source_context']),
            },
        )
        result['paths'] = [[{'assertion': 'claim', 'direction': 'outgoing'}]]
        result['assertions']['claim'] = {
            'sources': [],
            'identities': [],
            'subject': 'urn:seed',
            'object': 'outcome',
            'object_literal': True,
        }
        result['entities']['urn:seed'] = {}
        result['matches'].pop()
        result['source_context'].pop('context')
        _prune(result)
        self.assertIn('context', result['sources'])
        self.assertIsNone(result['source_context']['context']['claim_review'])
        result['matches'].pop()
        result['paths'].pop()
        _prune(result)
        self.assertFalse(result['passages'])

    def test_pruning_unselected_context_does_not_expand_the_remaining_citation(self):
        short = self.package('short', 'A recorded result.', 1, ['result'], revision='same')
        context = self.package(
            'context',
            'A recorded result. Additional source context.',
            1,
            ['result'],
            revision='same',
        )
        result = merge(self.base, [short, context])
        result['matches'] = [m for m in result['matches'] if m['source'] == 'short']
        result['source_context'].pop('context')
        _prune(result)
        self.assertEqual(list(result['passages'].values()), ['A recorded result.'])
        self.assertNotIn('passage_span', result['sources']['short'])

    def test_package_can_become_feasible_after_containing_context_is_selected(self):
        first = self.package('first', 'Start. Shared evidence.', 1, ['result'], revision='same')
        second = self.package(
            'second', 'Shared evidence. End.', 1, ['result'], offset=7, revision='same'
        )
        graph = merge(self.base, [first, second])
        graph['source_context'] = {}
        graph['matches'] = [{'channel': 'graph', 'path': 0, 'ranking': {'matched': ['result']}}]
        graph['paths'] = [[{'assertion': 'claim', 'direction': 'outgoing'}]]
        graph['assertions']['claim'] = {
            'subject': 'urn:seed',
            'predicate': 'urn:predicate',
            'object': 'urn:outcome',
            'object_literal': False,
            'role': 'substantive',
            'sources': ['first', 'second'],
            'identities': [],
        }
        graph['entities'] = {'urn:seed': {}, 'urn:outcome': {}}
        packages = [
            {'envelope': graph, 'relevance': 1, 'terms': ['result'], 'key': 'graph'},
            self.package(
                'context', 'Start. Shared evidence. End.', 0.95, ['result'], revision='same'
            ),
        ]
        result = _select(self.base, packages, Policy(max_chars=6000, max_passages=1), {'result': 1})
        self.assertIn('claim', result['assertions'])
        self.assertEqual(len(result['passages']), 1)

    def test_determinism_complete_envelope_and_unfit_packages(self):
        packages = [
            self.package('large', 'x' * 10000, 1, ['design']),
            self.package('small', 'A result.', 0.5, ['result']),
        ]
        first = _select(self.base, packages, self.policy, {'design': 1, 'result': 1})
        self.assertEqual(
            serialise(first),
            serialise(_select(self.base, packages, self.policy, {'design': 1, 'result': 1})),
        )
        self.assertNotIn('large', first['source_context'])
        self.assertEqual(_measure(first), first['usage']['characters'])
        self.assertGreater(first['omissions']['limits'].get('characters', 0), 0)
        self.assertLessEqual(first['selection']['trials'], first['selection']['trial_limit'])

    def test_final_metadata_does_not_reserve_space_for_unused_omission_keys(self):
        package = self.package(
            'complete', 'A qualified result. However, acceptance is pending.', 1, ['result']
        )
        # Find the exact wire size with the package selected, then require it to
        # fit at that boundary. Policy values below have the same number of digits.
        result = _select(self.base, [package], Policy(max_chars=4000), {'result': 1})
        budget = len(serialise(result))
        result = _select(self.base, [package], Policy(max_chars=budget), {'result': 1})
        self.assertIn('complete', result['sources'])
        self.assertLessEqual(len(serialise(result)), budget)

    def test_measure_serializes_once_even_when_counter_digit_widths_change(self):
        result = self.package('unicode', 'λ🙂\\"\n' * 1900, 1, ['result'])['envelope']
        with patch('knot.retrieval_engine.response.serialise', wraps=serialise) as encode:
            _measure(result)
        self.assertEqual(encode.call_count, 1)
        self.assertEqual(result['usage']['characters'], len(serialise(result)))
        self.assertEqual(result['usage']['utf8_bytes'], len(serialise(result).encode()))

    def test_ascii_metadata_deltas_keep_exact_unicode_wire_sizes(self):
        result = self.package('unicode', 'λ🙂\\"\n' * 1900, 1, ['result'])['envelope']
        _measure(result)
        for limits in ({'characters': 100, 'passages': 2}, {}, {'assertions': 9999}):
            old_size = len(serialise(result['omissions']))
            result['omissions']['limits'] = limits
            delta = len(serialise(result['omissions'])) - old_size
            usage = result['usage']
            _resize(result, (usage['characters'] + delta, usage['utf8_bytes'] + delta))
            self.assertEqual(usage['characters'], len(serialise(result)))
            self.assertEqual(usage['utf8_bytes'], len(serialise(result).encode()))

    def test_boundary_fit_includes_actual_omissions_and_preserves_the_whole_package(self):
        packages = [
            self.package(
                'complete', 'A result. However, acceptance remains pending.', 1, ['result']
            ),
            self.package('oversized', 'x' * 10000, 1, ['result']),
        ]
        result = _select(self.base, packages, Policy(max_chars=4000), {'result': 1})
        budget = len(serialise(result))
        exact = _select(self.base, packages, Policy(max_chars=budget), {'result': 1})
        self.assertEqual(
            _quotation(exact, exact['sources']['complete']),
            packages[0]['envelope']['passages']['p1'],
        )
        self.assertEqual(exact['omissions']['limits']['characters'], 1)
        self.assertLessEqual(len(serialise(exact)), budget)
        self.assertLessEqual(exact['selection']['trials'], exact['selection']['trial_limit'])
        too_small = _select(self.base, packages, Policy(max_chars=budget - 1), {'result': 1})
        self.assertNotIn('complete', too_small['sources'])
        self.assertLessEqual(len(serialise(too_small)), budget - 1)

    def test_incremental_merge_matches_complete_merge_and_does_not_mutate_inputs(self):
        packages = [
            self.package('short', 'An outcome.', 1, ['result'], revision='same'),
            self.package(
                'context',
                'An outcome. However, attribution is uncertain.',
                1,
                ['result'],
                revision='same',
            ),
        ]
        before = copy.deepcopy((self.base, packages))
        incremental = merge(merge(self.base, packages[:1]), packages[1:])
        self.assertEqual(incremental, merge(self.base, packages))
        result = _select(self.base, packages, self.policy, {'result': 1})
        result['source_context']['short']['claim_review'] = 'Changed by caller'
        self.assertEqual((self.base, packages), before)

    def test_shared_ranges_use_unicode_characters_and_reject_invalid_ranges(self):
        text = 'λ🙂 A result. However, confidence remains limited.\n'
        short = self.package('short', 'A result.', 1, ['result'], offset=3, revision='same')
        context = self.package('context', text, 1, ['result'], revision='same')
        result = merge(self.base, [short, context])
        self.assertEqual(_quotation(result, result['sources']['short']), 'A result.')
        self.assertEqual(result['sources']['short']['passage_span'], [3, 12])
        _measure(result)
        self.assertEqual(result['usage']['utf8_bytes'], len(serialise(result).encode()))
        result['sources']['short']['passage_span'] = [0, 10000]
        with self.assertRaisesRegex(ValueError, 'quotation range'):
            _quotation(result, result['sources']['short'])
