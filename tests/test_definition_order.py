"""Opt-in definition ordering preserves default retrieval and access boundaries."""

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from knot.interfaces.access import AccessScope
from knot.retrieval_engine.definition_order import reorder
from knot.retrieval_engine.policy import Policy
from knot.retrieval_engine.service import retrieve
from knot.writing.notes import create_note

HAS_MCP = importlib.util.find_spec('mcp') is not None
if HAS_MCP:
    from mcp import Client

    from knot.interfaces.mcp_server import create_server, result_size


@unittest.skipUnless(HAS_MCP, 'Install the dev or mcp extra for SDK integration tests')
class DefinitionIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_optional_mcp_path_budgets_default_compatibility_and_scope(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            body = 'Lyra working criterion requires reporting errors. A definition, not proof of performance. λ😀'
            original = create_note(root, body, author='Owner')
            derivation = {
                'method': 'faithful_restatement',
                'qualification': 'Definition, not evidence of demonstrated performance.',
                'sources': [
                    {
                        'revision': original['revision'],
                        'sha256': original['body_sha256'],
                        'text_sha256': original['body_sha256'],
                        'quote': body,
                        'character_offset': 0,
                        'start_line': 1,
                    }
                ],
            }
            for title in ('Lyra', 'Lyra Working'):
                create_note(
                    root,
                    body,
                    title=title,
                    kind='Definition',
                    author='Codex',
                    agent='Codex',
                    derivation=derivation,
                )
            question = 'What does Lyra Working require?'
            with patch('knot.retrieval_engine.definition_order.reorder', wraps=reorder) as order:
                server = create_server(root, AccessScope.all(), max_chars=24000)
                async with Client(server, cache=None) as client:
                    for budget in (4000, 8000, 12000, 24000):
                        args = {'question': question, 'mode': 'hybrid', 'max_chars': budget}
                        default = await client.call_tool('knot_retrieve', args)
                        explicit_default = await client.call_tool(
                            'knot_retrieve', {**args, 'definition_order': False}
                        )
                        self.assertEqual(default.content, explicit_default.content)
                        count = order.call_count
                        first = await client.call_tool(
                            'knot_retrieve', {**args, 'definition_order': True}
                        )
                        second = await client.call_tool(
                            'knot_retrieve', {**args, 'definition_order': True}
                        )
                        self.assertFalse(first.is_error)
                        self.assertEqual(first.content, second.content)
                        self.assertEqual(order.call_count, count + 2)
                        self.assertLessEqual(result_size(first), budget)
                    for extra in (
                        {'seed': original['note']},
                        {'note_revision': original['revision']},
                        {'subjects': [original['note']]},
                        {'definition_order': 'true'},
                    ):
                        bad = await client.call_tool(
                            'knot_retrieve', {**args, 'definition_order': True, **extra}
                        )
                        self.assertTrue(bad.is_error)
                denied = create_server(root, AccessScope(), max_chars=24000)
                async with Client(denied, cache=None) as client:
                    result = await client.call_tool(
                        'knot_retrieve', {**args, 'definition_order': True}
                    )
                    self.assertFalse(result.is_error)
                    value = json.loads(result.content[0].text)
                    self.assertEqual(value['sources'], {})
                    self.assertNotIn(original['revision'], result.content[0].text)

    def test_python_option_rejects_unsupported_requests_before_reads(self):
        for kwargs in (
            {'definition_order': 1},
            {'definition_order': True},
            {'definition_order': True, 'seed': 'x', 'question': 'test'},
        ):
            with self.assertRaises(ValueError):
                retrieve(Path('does-not-exist'), policy=Policy(), **kwargs)


if __name__ == '__main__':
    unittest.main()
