"""Finite contract combinations and invariants, using invented evidence only."""

from __future__ import annotations

import unittest
from dataclasses import replace
from itertools import product

import test_evaluation as fixture

from knot.evaluation import evaluate
from knot.graph.query import load_store
from knot.graph.rdf import VOCAB, one
from knot.interfaces.access import AccessScope
from knot.reviewing.writer import decide


class CoverageMatrixTests(unittest.TestCase):
    def test_review_kind_origin_and_access_matrix(self):
        # Expected outcomes are derived from the declared states below, without
        # calling the evaluator's candidate selector or classification helpers.
        criterion = 'urn:example:matrix-criterion'
        definition = 'urn:example:matrix-definition'
        support = 'urn:example:matrix-support'
        checked = 0
        for definition_state, support_state, origin, kind in product(
            ('Absent', 'Unreviewed', 'Rejected', 'Accepted'),
            ('Unreviewed', 'Rejected', 'Accepted'),
            ('Explicit', 'Inferred'),
            ('Assessment', 'Thought'),
        ):
            f = fixture.CoverageTests()
            f.setUp()
            try:
                if definition_state != 'Absent':
                    f.claim(
                        definition,
                        criterion,
                        fixture.DEFINITION,
                        'Explain tradeoffs.',
                        'Explain tradeoffs.',
                        revision=fixture.REVISION,
                        literal=True,
                    )
                    f.data.add(definition, VOCAB + 'recordKind', VOCAB + 'FrameworkDefinition')
                    f.data.add(definition, VOCAB + 'framework', fixture.FRAMEWORK)
                f.claim(
                    support,
                    fixture.PROJECT,
                    VOCAB + 'supports',
                    criterion,
                    'Reported evidence supports one aspect only.',
                    origin=origin,
                    kind=kind,
                )
                f.save()
                for aid, state in ((definition, definition_state), (support, support_state)):
                    if state in ('Accepted', 'Rejected'):
                        decide(
                            f.root,
                            aid,
                            'accept' if state == 'Accepted' else 'reject',
                            reviewer='Synthetic reviewer',
                            reason='Synthetic state matrix',
                        )
                store = load_store(f.root / 'graph', history=True, include_notes=False)
                pins = tuple(
                    (revision, one(store, revision, VOCAB + 'sha256').value)
                    for revision in (fixture.REVISION, support + ':revision')
                )
                request = replace(f.request, criteria=(criterion,))
                scopes = {
                    'owner': None,
                    'whole': AccessScope.all(),
                    'both_sources': AccessScope(revisions=pins),
                    'definition_only': AccessScope(revisions=pins[:1]),
                    'empty': AccessScope(),
                }
                for access, scope in scopes.items():
                    with self.subTest(
                        definition=definition_state,
                        mapping=support_state,
                        origin=origin,
                        kind=kind,
                        access=access,
                    ):
                        can_read_definition = access != 'empty'
                        can_read_support = access in ('owner', 'whole', 'both_sources')
                        expected = 'unknown'
                        if definition_state == 'Accepted' and can_read_definition:
                            if (
                                support_state == 'Accepted'
                                and kind == 'Assessment'
                                and can_read_support
                            ):
                                expected = 'support_found'
                            elif access in ('owner', 'whole'):
                                expected = 'no_qualifying_support'
                        result = evaluate(f.root, request, scope=scope)
                        self.assertEqual(result['criteria'][0]['outcome'], expected)
                        self.assertEqual(result['complete'], expected != 'unknown')
                        if expected == 'support_found':
                            premise = result['assertions'][support]
                            self.assertEqual(premise['origin'], origin)
                            self.assertEqual(premise['meaning'], 'Assessment')
                            self.assertIn('one aspect only', premise['sources'][0]['quote'])
                        if not can_read_support:
                            self.assertNotIn(support, result['assertions'])
                        checked += 1
            finally:
                f.doCleanups()
        self.assertEqual(checked, 240)

    def test_criteria_order_and_partition_preserve_results_with_sufficient_budget(self):
        f = fixture.CoverageTests()
        f.setUp()
        self.addCleanup(f.doCleanups)
        store = load_store(f.root / 'graph', history=True, include_notes=False)
        pins = tuple(
            (revision, one(store, revision, VOCAB + 'sha256').value)
            for revision in (fixture.REVISION, fixture.SUPPORT + ':revision')
        )
        for scope in (None, AccessScope.all(), AccessScope(revisions=pins)):
            with self.subTest(scope=scope):
                full = evaluate(f.root, f.request, scope=scope)
                expected = {row['criterion']: row for row in full['criteria']}
                reverse = evaluate(
                    f.root,
                    replace(f.request, criteria=tuple(reversed(f.request.criteria))),
                    scope=scope,
                )
                self.assertEqual({row['criterion']: row for row in reverse['criteria']}, expected)
                for criterion in f.request.criteria:
                    result = evaluate(
                        f.root, replace(f.request, criteria=(criterion,)), scope=scope
                    )
                    self.assertEqual(result['criteria'], [expected[criterion]])
                    for aid, premise in result['assertions'].items():
                        self.assertEqual(premise, full['assertions'][aid])

    def test_other_predicates_and_reversed_edges_do_not_become_support(self):
        f = fixture.CoverageTests()
        f.setUp()
        self.addCleanup(f.doCleanups)
        for index, (subject, predicate, obj) in enumerate(
            (
                (fixture.PROJECT, 'demonstrates', fixture.CRITERIA[1]),
                (fixture.PROJECT, 'relatedTo', fixture.CRITERIA[1]),
                (fixture.CRITERIA[1], 'supports', fixture.PROJECT),
            )
        ):
            aid = 'urn:example:nonmapping:' + str(index)
            f.claim(aid, subject, VOCAB + predicate, obj, 'A different relationship.')
            f.save()
            f.accept(aid)
        for scope in (None, AccessScope.all()):
            with self.subTest(scope=scope):
                result = evaluate(
                    f.root, replace(f.request, criteria=(fixture.CRITERIA[1],)), scope=scope
                )
                self.assertEqual(result['criteria'][0]['outcome'], 'no_qualifying_support')
                self.assertEqual(result['criteria'][0]['support'], [])


if __name__ == '__main__':
    unittest.main()
