"""Exercise evaluation through the actual MCP SDK and transport envelopes."""

import importlib.util
import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch

import test_evaluation as fixture

from knot.evaluation import evaluate
from knot.evaluation.revalidation import validate_receipt
from knot.evaluation.snapshot import canonical_hash
from knot.graph.query import load_store
from knot.graph.rdf import VOCAB, one
from knot.interfaces.access import AccessScope

HAS_MCP = importlib.util.find_spec('mcp') is not None
if HAS_MCP:
    from mcp import Client, StdioServerParameters

    from knot.interfaces.mcp_server import check_asyncio_support, create_server, result_size


def setUpModule():
    if HAS_MCP:
        check_asyncio_support()


@unittest.skipUnless(HAS_MCP, 'Install the mcp extra for protocol tests')
class EvaluationMCPTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.fixture = fixture.CoverageTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root, self.request = self.fixture.root, self.fixture.request.to_dict()
        store = load_store(self.root / 'graph', history=True, include_notes=False)
        self.scope = AccessScope(
            revisions=tuple(
                (r, one(store, r, VOCAB + 'sha256').value)
                for r in (fixture.REVISION, fixture.SUPPORT + ':revision')
            )
        )

    def question(self):
        return (
            f'Does project "{fixture.PROJECT}" have reviewed support for criterion '
            f'"{fixture.CRITERIA[0]}" in framework "{fixture.FRAMEWORK}" '
            f'at revision "{fixture.REVISION}"?'
        )

    async def test_receipt_mode_recomputes_both_envelopes_and_budget_abstains(self):
        async with Client(
            create_server(self.root, self.scope, max_chars=24000), cache=None
        ) as client:
            for args in ({'request': self.request}, {'question': self.question()}):
                response = await client.call_tool('knot_evaluate', args)
                self.assertFalse(response.is_error)
                saved = json.loads(response.content[0].text)
                response = await client.call_tool('knot_evaluate', {'receipt': saved})
                self.assertFalse(response.is_error)
                result = json.loads(response.content[0].text)
                self.assertEqual(result['status'], 'unchanged')
                self.assertTrue(result['outcomes_unchanged'])
                self.assertEqual(result['current'], saved)
                repeated = await client.call_tool('knot_evaluate', {'receipt': saved})
                self.assertEqual(repeated.content, response.content)
                bounded = await client.call_tool(
                    'knot_evaluate', {'receipt': saved, 'max_chars': 3000}
                )
                self.assertFalse(bounded.is_error)
                self.assertLessEqual(result_size(bounded), 3000)
                report = json.loads(bounded.content[0].text)
                self.assertEqual(report['status'], 'not_comparable')
                self.assertIsNone(report['outcomes_unchanged'])
                self.assertEqual(report['reasons'], ['output_budget'])
                current = report['current'].get('evaluation', report['current'])
                self.assertTrue(all(row['outcome'] == 'unknown' for row in current['criteria']))
                self.assertFalse(current['assertions'])
                # An output-budget receipt can be recomputed but cannot certify freshness.
                response = await client.call_tool('knot_evaluate', {'receipt': report['current']})
                self.assertFalse(response.is_error)
                result = json.loads(response.content[0].text)
                self.assertEqual(result['status'], 'not_comparable')
                self.assertEqual(result['reasons'], ['saved_abstention'])

    async def test_receipt_mode_does_not_restore_saved_access(self):
        saved = evaluate(self.root, self.fixture.request)
        async with Client(
            create_server(self.root, AccessScope(), max_chars=24000), cache=None
        ) as client:
            response = await client.call_tool('knot_evaluate', {'receipt': saved})
            self.assertFalse(response.is_error)
            result = json.loads(response.content[0].text)
            self.assertEqual(result['status'], 'changed')
            self.assertFalse(result['current']['assertions'])
            self.assertTrue(
                all(row['outcome'] == 'unknown' for row in result['current']['criteria'])
            )
            self.assertNotIn('limited scope', response.content[0].text)
            self.assertNotIn('claims.trig', response.content[0].text)

    async def test_receipt_mode_rejects_tampering_mixed_modes_and_execution_limit_bypass(self):
        saved = evaluate(self.root, self.fixture.request)
        async with Client(create_server(self.root, self.scope), cache=None) as client:
            for args in (
                {'receipt': saved, 'request': self.request},
                {'receipt': saved, 'question': self.question()},
                {'receipt': {**saved, 'receipt_sha256': 'private-invalid-hash'}},
            ):
                response = await client.call_tool('knot_evaluate', args)
                self.assertTrue(response.is_error)
                self.assertNotIn('private-invalid-hash', str(response.content))
            saved['request']['max_sources'] = 101
            saved['manifest']['request']['max_sources'] = 101
            saved['receipt_sha256'] = canonical_hash(
                {k: v for k, v in saved.items() if k != 'receipt_sha256'}
            )
            self.assertEqual(validate_receipt(saved).max_sources, 101)
            with patch('knot.interfaces.mcp_evaluation.revalidate') as run:
                response = await client.call_tool('knot_evaluate', {'receipt': saved})
                self.assertTrue(response.is_error)
                run.assert_not_called()

    async def test_question_mode_executes_and_renders_only_the_returned_receipt(self):
        async with Client(
            create_server(self.root, self.scope, max_chars=24000), cache=None
        ) as client:
            for budget in (2048, 24000):
                response = await client.call_tool(
                    'knot_evaluate', {'question': self.question(), 'max_chars': budget}
                )
                self.assertFalse(response.is_error)
                self.assertLessEqual(result_size(response), budget)
                result = json.loads(response.content[0].text)
                receipt = result['evaluation']
                self.assertEqual(result['request'], receipt['request'])
                self.assertEqual(result['question'], self.question())
                if budget == 2048:
                    self.assertEqual(receipt['criteria'][0]['outcome'], 'unknown')
                    self.assertIn('unknown', result['answer'])
                    self.assertNotIn('mapping was found', result['answer'])
                    self.assertFalse(receipt['assertions'])
                else:
                    self.assertEqual(receipt['criteria'][0]['outcome'], 'support_found')
                    self.assertIn('attributed assessment', result['answer'])
                    self.assertIn('limited scope', json.dumps(receipt['assertions']))

    async def test_question_mode_rejects_mixed_inputs_and_does_not_evaluate_unsupported_text(self):
        async with Client(create_server(self.root, self.scope), cache=None) as client:
            for args in ({}, {'request': self.request, 'question': self.question()}):
                response = await client.call_tool('knot_evaluate', args)
                self.assertTrue(response.is_error)
            response = await client.call_tool(
                'knot_evaluate', {'question': self.question() + ' Prove expertise.'}
            )
            self.assertFalse(response.is_error)
            result = json.loads(response.content[0].text)
            self.assertEqual(result['status'], 'unsupported_question')
            self.assertNotIn('evaluation', result)

    async def test_question_mode_empty_scope_and_integrity_failure_are_safe(self):
        async with Client(create_server(self.root, AccessScope()), cache=None) as client:
            response = await client.call_tool('knot_evaluate', {'question': self.question()})
            self.assertFalse(response.is_error)
            result = json.loads(response.content[0].text)
            self.assertIn('unknown', result['answer'])
            self.assertFalse(result['evaluation']['assertions'])
        async with Client(create_server(self.root, self.scope), cache=None) as client:
            with patch(
                'knot.interfaces.mcp_evaluation.answer_question',
                side_effect=ValueError('secret path'),
            ):
                response = await client.call_tool('knot_evaluate', {'question': self.question()})
                self.assertTrue(response.is_error)
                self.assertNotIn('secret path', str(response.content))

    async def test_readonly_registration_schema_and_scoped_result(self):
        server = create_server(self.root, self.scope, max_chars=24000)
        before = {
            p.relative_to(self.root): p.read_bytes() for p in self.root.rglob('*') if p.is_file()
        }
        async with Client(server, cache=None, read_timeout_seconds=15) as client:
            tools = {t.name: t for t in (await client.list_tools()).tools}
            self.assertTrue(tools['knot_evaluate'].annotations.read_only_hint)
            self.assertNotIn('knot_candidate_publish', tools)
            self.assertIn('knot_evaluate', client.instructions)
            response = await client.call_tool('knot_evaluate', {'request': self.request})
            self.assertFalse(response.is_error)
            payload = json.loads(response.content[0].text)
            self.assertEqual(
                [r['outcome'] for r in payload['criteria']], ['support_found', 'unknown']
            )
            self.assertIn('limited scope', json.dumps(payload['assertions'][fixture.SUPPORT]))
            self.assertLessEqual(result_size(response), 24000)
            second = await client.call_tool('knot_evaluate', {'request': self.request})
            self.assertEqual(response.content, second.content)
        after = {
            p.relative_to(self.root): p.read_bytes() for p in self.root.rglob('*') if p.is_file()
        }
        self.assertEqual(before, after)

    async def test_empty_grant_returns_unknown_without_source_metadata(self):
        async with Client(
            create_server(self.root, AccessScope()), cache=None, read_timeout_seconds=15
        ) as client:
            response = await client.call_tool('knot_evaluate', {'request': self.request})
            self.assertFalse(response.is_error)
            payload = json.loads(response.content[0].text)
            self.assertEqual(payload['assertions'], {})
            self.assertTrue(all(r['outcome'] == 'unknown' for r in payload['criteria']))
            self.assertNotIn('claims.trig', response.content[0].text)
            self.assertNotIn('Synthetic reviewer', response.content[0].text)

    async def test_temporal_abstention_does_not_claim_an_unchecked_definition_is_missing(self):
        async with Client(
            create_server(self.root, AccessScope.all()), cache=None, read_timeout_seconds=15
        ) as client:
            response = await client.call_tool(
                'knot_evaluate', {'request': {**self.request, 'as_of': '2025-01-01'}}
            )
            self.assertFalse(response.is_error)
            payload = json.loads(response.content[0].text)
            self.assertFalse(payload['complete'])
            for row in payload['criteria']:
                self.assertEqual(row['outcome'], 'unknown')
                self.assertEqual(row['reasons'], ['unsupported_temporal_scope'])

    async def test_output_budget_abstains_without_truncating_witnesses(self):
        async with Client(
            create_server(self.root, self.scope, max_chars=24000),
            cache=None,
            read_timeout_seconds=15,
        ) as client:
            for budget in (2048, 4000, 8000, 24000):
                with self.subTest(budget=budget):
                    response = await client.call_tool(
                        'knot_evaluate', {'request': self.request, 'max_chars': budget}
                    )
                    self.assertFalse(response.is_error)
                    self.assertLessEqual(result_size(response), budget)
                    payload = json.loads(response.content[0].text)
                    if 'output_budget' in payload['reasons']:
                        self.assertFalse(payload['complete'])
                        self.assertEqual(payload['assertions'], {})
                        self.assertTrue(
                            all(row['outcome'] == 'unknown' for row in payload['criteria'])
                        )
                    else:
                        self.assertIn(
                            'limited scope',
                            payload['assertions'][fixture.SUPPORT]['sources'][0]['quote'],
                        )
                    if budget == 2048:
                        self.assertIn('output_budget', payload['reasons'])

    async def test_invalid_requests_and_budget_cannot_widen_scope(self):
        async with Client(
            create_server(self.root, self.scope, max_chars=24000),
            cache=None,
            read_timeout_seconds=15,
        ) as client:
            for changes in (
                {'scope': {'whole_dataset': True}},
                {'question': 'Assess everything'},
                {'version': '2'},
                {'max_sources': True},
                {'max_sources': 101},
                {'criteria': []},
                {'criteria': [fixture.CRITERIA[0]] * 2},
                {'criteria': ['urn:example:' + str(i) for i in range(21)]},
            ):
                response = await client.call_tool(
                    'knot_evaluate', {'request': {**self.request, **changes}}
                )
                self.assertTrue(response.is_error, changes)
            response = await client.call_tool(
                'knot_evaluate', {'request': self.request, 'max_chars': 24001}
            )
            self.assertTrue(response.is_error)

    async def test_integrity_failures_are_generic(self):
        server = create_server(self.root, self.scope, max_chars=24000)
        async with Client(server, cache=None, read_timeout_seconds=15) as client:
            with patch(
                'knot.interfaces.mcp_evaluation.evaluate',
                side_effect=ValueError('private-path / secret revision'),
            ):
                response = await client.call_tool('knot_evaluate', {'request': self.request})
            self.assertTrue(response.is_error)
            text = str(response.content)
            self.assertNotIn('private-path', text)
            self.assertNotIn('secret revision', text)

    async def test_whole_dataset_mode_preserves_rule_semantics(self):
        async with Client(
            create_server(self.root, AccessScope.all(), max_chars=24000),
            cache=None,
            read_timeout_seconds=15,
        ) as client:
            response = await client.call_tool('knot_evaluate', {'request': self.request})
            self.assertFalse(response.is_error)
            payload = json.loads(response.content[0].text)
            self.assertTrue(payload['complete'])
            self.assertEqual(
                [r['outcome'] for r in payload['criteria']],
                ['support_found', 'no_qualifying_support'],
            )

    async def test_twenty_criteria_at_exact_execution_limits(self):
        f = self.fixture
        criteria = list(fixture.CRITERIA)
        added = []
        for index in range(2, 20):
            criterion = 'urn:example:criterion:boundary:' + str(index)
            aid = 'urn:example:definition:boundary:' + str(index)
            criteria.append(criterion)
            added.append(aid)
            f.claim(
                aid,
                criterion,
                fixture.DEFINITION,
                'Explain tradeoffs.',
                'Explain tradeoffs.',
                revision=fixture.REVISION,
                literal=True,
            )
            f.data.add(aid, VOCAB + 'recordKind', VOCAB + 'FrameworkDefinition')
            f.data.add(aid, VOCAB + 'framework', fixture.FRAMEWORK)
        f.save()
        for aid in added:
            f.accept(aid)
        request = {**self.request, 'criteria': criteria, 'max_assertions': 21, 'max_sources': 2}
        async with Client(
            create_server(self.root, AccessScope.all(), max_chars=131072),
            cache=None,
            read_timeout_seconds=15,
        ) as client:
            response = await client.call_tool('knot_evaluate', {'request': request})
            self.assertFalse(response.is_error)
            result = json.loads(response.content[0].text)
            self.assertTrue(result['complete'])
            self.assertEqual(len(result['criteria']), 20)
            self.assertEqual(result['criteria'][0]['outcome'], 'support_found')
            self.assertTrue(
                all(r['outcome'] == 'no_qualifying_support' for r in result['criteria'][1:])
            )
            self.assertLessEqual(result_size(response), 131072)
            limited = await client.call_tool(
                'knot_evaluate', {'request': {**request, 'max_assertions': 20}}
            )
            self.assertFalse(limited.is_error)
            for row in json.loads(limited.content[0].text)['criteria']:
                self.assertEqual(row['outcome'], 'unknown')
                self.assertEqual(row['reasons'], ['assertion_budget'])

    async def test_evaluation_over_stdio_uses_operator_grants(self):
        grant = self.root / 'scope.json'
        grant.write_text(json.dumps({'revisions': dict(self.scope.revisions)}))
        project = Path.cwd()
        target = StdioServerParameters(
            command=str(project / '.venv/bin/python'),
            args=[
                '-m',
                'knot.interfaces.mcp_server',
                '--data-root',
                str(self.root),
                '--scope',
                str(grant),
                '--max-chars',
                '24000',
            ],
            env={**os.environ, 'PYTHONPATH': str(project / 'src')},
        )
        async with Client(target, cache=None, read_timeout_seconds=15) as client:
            result = await client.call_tool('knot_evaluate', {'request': self.request})
            self.assertFalse(result.is_error)
            payload = json.loads(result.content[0].text)
            self.assertEqual(
                [r['outcome'] for r in payload['criteria']], ['support_found', 'unknown']
            )
            self.assertEqual(payload['manifest']['access'], 'granted-source-view')

    async def test_oversized_request_cannot_return_partial_conclusions(self):
        request = {
            **self.request,
            'criteria': ['urn:example:' + 'x' * 500 + str(i) for i in range(20)],
        }
        async with Client(create_server(self.root, self.scope), cache=None) as client:
            result = await client.call_tool(
                'knot_evaluate', {'request': request, 'max_chars': 2048}
            )
            self.assertTrue(result.is_error)
            self.assertIn('fewer criteria', result.content[0].text)
            self.assertLessEqual(result_size(result), 2048)

    async def test_real_source_and_review_corruption_are_generic_errors(self):
        from knot.shared.storage import digest

        server = create_server(self.root, self.scope)
        path = self.root / ('sources/' + digest(fixture.SUPPORT.encode()) + '.txt')
        path.write_text('Tampered source')
        async with Client(server, cache=None) as client:
            result = await client.call_tool('knot_evaluate', {'request': self.request})
            self.assertTrue(result.is_error)
            self.assertNotIn(path.name, result.content[0].text)
            self.assertNotIn(fixture.SUPPORT, result.content[0].text)
            self.fixture.data.add(
                fixture.SUPPORT, VOCAB + 'extraMetadata', 'Tampered', literal=True
            )
            self.fixture.save()
            review_error = await client.call_tool('knot_evaluate', {'request': self.request})
            self.assertTrue(review_error.is_error)
            self.assertEqual(result.content, review_error.content)


if __name__ == '__main__':
    unittest.main()
