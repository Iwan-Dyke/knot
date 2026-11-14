"""Checked routing retains its boundaries across the actual MCP transport."""

import importlib.util
import json
import os
import unittest
from pathlib import Path

import test_answering as fixture

from knot.evaluation import explanations
from knot.evaluation.answering import answer
from knot.interfaces.access import AccessScope

HAS_MCP = importlib.util.find_spec('mcp') is not None
if HAS_MCP:
    from mcp import Client, StdioServerParameters

    from knot.interfaces.mcp_server import check_asyncio_support, create_server, result_size


def setUpModule():
    if HAS_MCP:
        check_asyncio_support()


@unittest.skipUnless(HAS_MCP, 'MCP SDK is optional')
class TestMCPAnswering(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.f = fixture.TestAnswering()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.f.f.approve()

    async def test_navigation_requires_explicit_question_selection_and_respects_wire_budget(self):
        f = self.f.f
        suffix = ' Please retain the source qualifications and explain only the recorded decision, without assuming successful delivery.'
        wordings = [
            q + suffix
            for q in [
                'Why choose batching?',
                'Why was batching chosen?',
                'What makes batching preferable?',
                'Why prefer batching?',
                'Why use batching?',
                'What is the reason for batching?',
            ]
        ]
        self.f.approve_wordings(wordings=wordings)
        async with Client(
            create_server(f.root, AccessScope.all(), max_chars=32768), cache=None
        ) as client:
            response = await client.call_tool(
                'knot_answer', {'question': 'Explain the batching choice'}
            )
            self.assertFalse(response.is_error)
            result = json.loads(response.content[0].text)
            self.assertEqual(result['status'], 'unsupported_question')
            self.assertIsNone(result['request'])
            self.assertNotIn('answer', result)
            self.assertEqual(len(result['alternatives']), 5)
            selected = result['alternatives'][0]
            response = await client.call_tool(
                'knot_answer',
                {
                    'question': selected['question'],
                    'explanation_revision': selected['explanation_revision'],
                },
            )
            self.assertEqual(json.loads(response.content[0].text)['answer'], f.note['body'])
            response = await client.call_tool(
                'knot_answer', {'question': 'Explain the batching choice', 'max_chars': 2048}
            )
            self.assertFalse(response.is_error)
            self.assertLessEqual(result_size(response), 2048)
            small = json.loads(response.content[0].text)
            self.assertEqual(small['status'], 'unknown')
            self.assertEqual(small['reasons'], ['output_budget'])
            self.assertNotIn('alternatives', small)
            response = await client.call_tool('knot_answer', {'receipt': result, 'max_chars': 2048})
            checked = json.loads(response.content[0].text)
            self.assertEqual(checked['status'], 'not_comparable')
            self.assertNotIn('alternatives', checked['current'])

    async def test_revocation_does_not_echo_old_alternatives(self):
        self.f.approve_wordings()
        saved = answer(self.f.root, 'Explain the batching choice')
        self.assertTrue(saved['alternatives'])
        async with Client(
            create_server(self.f.root, AccessScope(), max_chars=32768), cache=None
        ) as client:
            response = await client.call_tool('knot_answer', {'receipt': saved})
            self.assertFalse(response.is_error)
            checked = json.loads(response.content[0].text)
            self.assertEqual(checked['current']['status'], 'unsupported_question')
            self.assertEqual(checked['current']['alternatives'], [])
            self.assertNotIn(self.f.f.note['revision'], response.content[0].text)

    async def test_reviewed_wording_budget_withdrawal_and_revalidation(self):
        f = self.f.f
        wording = 'Why did we choose batching?'
        event = explanations.approve(
            f.root,
            explanations.prepare(f.root, f.request, wordings=[wording]),
            reviewer='Synthetic reviewer',
            reason='Checked the full alternative question.',
        )
        async with Client(
            create_server(f.root, AccessScope.all(), max_chars=32768), cache=None
        ) as client:
            response = await client.call_tool('knot_answer', {'question': wording})
            self.assertFalse(response.is_error)
            saved = json.loads(response.content[0].text)
            self.assertEqual(saved['answer'], f.note['body'])
            self.assertEqual(saved['wording_review']['event_sha256'], event['event_sha256'])
            response = await client.call_tool(
                'knot_answer', {'question': wording, 'max_chars': 2048}
            )
            small = json.loads(response.content[0].text)
            self.assertEqual(small['status'], 'unknown')
            self.assertNotIn('answer', small)
            self.assertLessEqual(result_size(response), 2048)
            explanations.withdraw(
                f.root,
                f.request,
                expected=event['event_sha256'],
                reviewer='Synthetic reviewer',
                reason='Retire this mapping.',
            )
            response = await client.call_tool('knot_answer', {'receipt': saved})
            checked = json.loads(response.content[0].text)
            self.assertEqual(checked['status'], 'changed')
            self.assertEqual(checked['current']['status'], 'unknown')
            self.assertNotIn('answer', checked['current'])

    async def test_selection_revalidation_and_readonly_registration(self):
        f = self.f
        async with Client(
            create_server(f.root, AccessScope.all(), max_chars=32768), cache=None
        ) as client:
            tools = {t.name: t for t in (await client.list_tools()).tools}
            self.assertTrue(tools['knot_answer'].annotations.read_only_hint)
            response = await client.call_tool('knot_answer', {'question': f.question})
            self.assertFalse(response.is_error)
            saved = json.loads(response.content[0].text)
            self.assertEqual(saved['answer'], f.f.note['body'])
            other, _, _ = f.another()
            response = await client.call_tool('knot_answer', {'receipt': saved})
            checked = json.loads(response.content[0].text)
            self.assertEqual(checked['status'], 'changed')
            self.assertEqual(checked['current']['status'], 'needs_selection')
            self.assertNotIn('answer', checked['current'])
            response = await client.call_tool(
                'knot_answer', {'question': f.question, 'explanation_revision': other['revision']}
            )
            self.assertEqual(json.loads(response.content[0].text)['answer'], other['body'])

    async def test_budget_never_returns_partial_proof_or_comparable_abstention(self):
        f = self.f
        async with Client(
            create_server(f.root, AccessScope.all(), max_chars=32768), cache=None
        ) as client:
            response = await client.call_tool(
                'knot_answer', {'question': f.question, 'max_chars': 2048}
            )
            self.assertFalse(response.is_error)
            self.assertLessEqual(result_size(response), 2048)
            saved = json.loads(response.content[0].text)
            self.assertEqual(saved['status'], 'unknown')
            self.assertEqual(saved['reasons'], ['output_budget'])
            self.assertNotIn('answer', saved)
            response = await client.call_tool('knot_answer', {'receipt': saved})
            self.assertEqual(json.loads(response.content[0].text)['status'], 'not_comparable')
            full = answer(f.root, f.question)
            response = await client.call_tool('knot_answer', {'receipt': full, 'max_chars': 2048})
            checked = json.loads(response.content[0].text)
            self.assertEqual(checked['status'], 'not_comparable')
            self.assertNotIn('answer', checked['current'])

    async def test_revoked_scope_does_not_echo_saved_prose_or_reviews(self):
        f = self.f
        saved = answer(f.root, f.f.request['question'])
        async with Client(
            create_server(f.root, AccessScope(), max_chars=32768), cache=None
        ) as client:
            response = await client.call_tool('knot_answer', {'receipt': saved})
            self.assertFalse(response.is_error)
            text = response.content[0].text
            self.assertNotIn('Synthetic reviewer', text)
            self.assertNotIn(f.f.note['body'], text)
            self.assertNotIn(f.f.source['revision'], text)
            self.assertEqual(json.loads(text)['current']['status'], 'unknown')

    async def test_invalid_modes_and_unsupported_conditions(self):
        f = self.f
        async with Client(create_server(f.root, AccessScope.all()), cache=None) as client:
            for args in (
                {},
                {'question': f.question, 'receipt': {}},
                {'receipt': {}, 'explanation_revision': f.f.note['revision']},
                {'receipt': {'private-path': 'secret'}},
            ):
                response = await client.call_tool('knot_answer', args)
                self.assertTrue(response.is_error)
                self.assertNotIn('private-path', str(response.content))
            response = await client.call_tool(
                'knot_answer', {'question': f.question + ' Before 2024?'}
            )
            self.assertEqual(json.loads(response.content[0].text)['status'], 'unsupported_question')

    async def test_actual_stdio_selects_approved_artifact(self):
        wording = 'Why did we choose batching?'
        f = self.f.f
        explanations.approve(
            f.root,
            explanations.prepare(f.root, f.request, wordings=[wording]),
            reviewer='Synthetic reviewer',
            reason='Checked meaning.',
        )
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
                '32768',
            ],
            env={**os.environ, 'PYTHONPATH': str(project / 'src'), 'PYTHONDONTWRITEBYTECODE': '1'},
        )
        async with Client(params, cache=None) as client:
            for question in (self.f.question, wording):
                response = await client.call_tool('knot_answer', {'question': question})
                self.assertFalse(response.is_error)
                self.assertEqual(json.loads(response.content[0].text)['answer'], f.note['body'])
            response = await client.call_tool(
                'knot_answer', {'question': 'Explain the batching choice'}
            )
            self.assertFalse(response.is_error)
            result = json.loads(response.content[0].text)
            self.assertEqual(result['status'], 'unsupported_question')
            self.assertEqual(result['alternatives'][0]['question'], wording)
            self.assertNotIn('answer', result)
