"""The transport cannot approve prose or retain conclusions after withholding evidence."""

import importlib.util
import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch

import test_explanations as fixture

from knot.interfaces.access import AccessScope

HAS_MCP = importlib.util.find_spec('mcp') is not None
if HAS_MCP:
    from mcp import Client, StdioServerParameters

    from knot.interfaces.mcp_server import check_asyncio_support, create_server, result_size


def setUpModule():
    if HAS_MCP:
        check_asyncio_support()


@unittest.skipUnless(HAS_MCP, 'MCP SDK is optional')
class TestMCPExplanations(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.f = fixture.TestExplanations()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.f.approve()

    async def test_readonly_registration_exact_answer_and_revalidation(self):
        f = self.f
        before = {p: p.read_bytes() for p in f.root.rglob('*') if p.is_file()}
        async with Client(
            create_server(f.root, f.scope(f.note, f.source), max_chars=24000), cache=None
        ) as client:
            tools = {t.name: t for t in (await client.list_tools()).tools}
            self.assertTrue(tools['knot_explain'].annotations.read_only_hint)
            self.assertFalse(any('approve' in name or 'withdraw' in name for name in tools))
            response = await client.call_tool('knot_explain', {'request': f.request})
            self.assertFalse(response.is_error)
            saved = json.loads(response.content[0].text)
            self.assertEqual(saved['answer'], f.note['body'])
            response = await client.call_tool('knot_explain', {'receipt': saved})
            self.assertFalse(response.is_error)
            report = json.loads(response.content[0].text)
            self.assertEqual(report['status'], 'unchanged')
            self.assertEqual(report['current'], saved)
        self.assertEqual(before, {p: p.read_bytes() for p in f.root.rglob('*') if p.is_file()})

    async def test_budget_abstains_and_cannot_claim_revalidation_unchanged(self):
        async with Client(
            create_server(self.f.root, AccessScope.all(), max_chars=24000), cache=None
        ) as client:
            response = await client.call_tool('knot_explain', {'request': self.f.request})
            saved = json.loads(response.content[0].text)
            for args in ({'request': self.f.request}, {'receipt': saved}):
                response = await client.call_tool('knot_explain', {**args, 'max_chars': 2048})
                self.assertFalse(response.is_error)
                self.assertLessEqual(result_size(response), 2048)
                p = json.loads(response.content[0].text)
                if 'receipt' in args:
                    self.assertEqual(p['status'], 'not_comparable')
                    self.assertIsNone(p['outcomes_unchanged'])
                    p = p['current']
                self.assertEqual(p['status'], 'unknown')
                self.assertEqual(p['reasons'], ['output_budget'])
                self.assertNotIn('answer', p)

    async def test_revocation_cannot_echo_saved_answer_or_private_review(self):
        from knot.evaluation.explanations import answer

        saved = answer(self.f.root, self.f.request)
        async with Client(
            create_server(self.f.root, AccessScope(), max_chars=24000), cache=None
        ) as client:
            response = await client.call_tool('knot_explain', {'receipt': saved})
            self.assertFalse(response.is_error)
            self.assertNotIn('Synthetic reviewer', str(response.content))
            self.assertNotIn(self.f.source['revision'], str(response.content))
            self.assertNotIn('Batching was chosen', str(response.content))
            self.assertEqual(json.loads(response.content[0].text)['current']['status'], 'unknown')

    async def test_invalid_modes_unsupported_conditions_and_integrity_error_redaction(self):
        async with Client(create_server(self.f.root, AccessScope.all()), cache=None) as client:
            for args in (
                {},
                {'request': self.f.request, 'receipt': {}},
                {'request': {**self.f.request, 'approve': True}},
                {'receipt': {'private-path': 'secret'}},
            ):
                response = await client.call_tool('knot_explain', args)
                self.assertTrue(response.is_error)
                self.assertNotIn('private-path', str(response.content))
            response = await client.call_tool(
                'knot_explain',
                {
                    'request': {
                        **self.f.request,
                        'question': self.f.request['question'] + ' Prove success.',
                    }
                },
            )
            self.assertEqual(json.loads(response.content[0].text)['status'], 'unsupported_question')
            with patch(
                'knot.interfaces.mcp_explanations.answer', side_effect=ValueError('secret path')
            ):
                response = await client.call_tool('knot_explain', {'request': self.f.request})
                self.assertTrue(response.is_error)
                self.assertNotIn('secret path', str(response.content))

    async def test_actual_stdio_transport_uses_the_selected_synthetic_dataset(self):
        project = Path(__file__).resolve().parents[1]
        params = StdioServerParameters(
            command=str(project / '.venv/bin/python'),
            args=[
                '-m',
                'knot.interfaces.mcp_server',
                '--data-root',
                str(self.f.root),
                '--allow-all',
                '--max-chars',
                '24000',
            ],
            env={**os.environ, 'PYTHONPATH': str(project / 'src'), 'PYTHONDONTWRITEBYTECODE': '1'},
        )
        async with Client(params, cache=None) as client:
            response = await client.call_tool('knot_explain', {'request': self.f.request})
            self.assertFalse(response.is_error)
            self.assertEqual(json.loads(response.content[0].text)['answer'], self.f.note['body'])
