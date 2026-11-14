import json
import os
import tempfile
import unittest
from pathlib import Path
from uuid import uuid4

from test_mcp_server import HAS_MCP

from knot.access import AccessScope
from knot.notes import list_notes

if HAS_MCP:
    from mcp import Client, StdioServerParameters

    from knot.mcp_server import create_server


def setUpModule():
    if HAS_MCP:
        from knot.mcp_server import check_asyncio_support

        check_asyncio_support()


@unittest.skipUnless(HAS_MCP, 'MCP SDK is not installed')
class MCPAuthoringTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    async def call(self, client, name, arguments, *, error=False):
        result = await client.call_tool(name, arguments)
        self.assertEqual(bool(result.is_error), error, str(result.content))
        return result.content[0].text if error else json.loads(result.content[0].text)

    def test_write_mode_requires_whole_dataset_and_review_requires_write(self):
        with self.assertRaises(ValueError):
            create_server(self.root, AccessScope(), allow_write=True)
        with self.assertRaises(ValueError):
            create_server(self.root, AccessScope.all(), allow_review=True)

    async def test_create_read_update_and_retry_over_real_stdio(self):
        project = Path.cwd()
        target = StdioServerParameters(
            command=str(project / '.venv/bin/python'),
            args=[
                '-m',
                'knot.mcp_server',
                '--data-root',
                str(self.root),
                '--allow-all',
                '--allow-write',
            ],
            env={**os.environ, 'PYTHONPATH': str(project / 'src')},
        )
        async with Client(target, cache=None, read_timeout_seconds=10) as client:
            tools = {t.name: t for t in (await client.list_tools()).tools}
            self.assertIn('knot_note_create', tools)
            self.assertNotIn('knot_review_decide', tools)
            self.assertFalse(tools['knot_note_create'].annotations.read_only_hint)
            request = {
                'note': 'urn:knot:note:' + str(uuid4()),
                'body': 'A first thought.\n',
                'agent': 'Test agent',
                'metadata': {'title': 'Test', 'author': 'Writer'},
            }
            first = await self.call(client, 'knot_note_create', request)
            again = await self.call(client, 'knot_note_create', request)
            self.assertEqual(first['revision'], again['revision'])
            self.assertEqual(len(list_notes(self.root)), 1)
            read = await self.call(client, 'knot_note_read', {'note': first['note'], 'limit': 4})
            self.assertEqual(read['body'], 'A fi')
            self.assertEqual(read['next_offset'], 4)
            saved = await self.call(
                client,
                'knot_note_update',
                {
                    'note': first['note'],
                    'expected': first['revision'],
                    'body': 'A changed thought.',
                    'agent': 'Test agent',
                    'metadata': {'kind': 'Thought'},
                },
            )
            self.assertNotEqual(saved['revision'], first['revision'])
            await self.call(
                client,
                'knot_note_update',
                {
                    'note': first['note'],
                    'expected': first['revision'],
                    'body': 'Stale',
                    'agent': 'Test agent',
                },
                error=True,
            )
            await self.call(
                client, 'knot_note_create', {**request, 'body': 'Conflicting retry'}, error=True
            )
            history = await self.call(client, 'knot_note_history', {'note': first['note']})
            self.assertEqual(len(history['items']), 2)

    async def test_navigation_entity_creation_retry_and_curated_provenance(self):
        server = create_server(self.root, AccessScope.all(), allow_write=True)
        async with Client(server, cache=None, read_timeout_seconds=10) as client:
            ids = await self.call(client, 'knot_identifiers', {})
            request = {
                'note': ids['note'],
                'body': 'Test concept is provisional.',
                'agent': 'Test',
                'metadata': {
                    'navigation': {
                        'themes': [],
                        'links': [],
                        'declarations': [
                            {
                                'id': ids['entity'],
                                'label': 'Test concept',
                                'type': 'Concept',
                                'quote': 'Test concept',
                                'offset': 0,
                            }
                        ],
                    }
                },
            }
            source = await self.call(client, 'knot_note_create', request)
            replay = await self.call(client, 'knot_note_create', request)
            self.assertEqual(replay, source)
            found = await self.call(client, 'knot_lookup', {'query': 'Test concept'})
            self.assertIn(ids['entity'], [c['id'] for c in found['candidates']])
            pin = await self.call(
                client,
                'knot_source_pin',
                {'revision': source['revision'], 'quote': request['body'], 'character_offset': 0},
            )
            curated = await self.call(
                client,
                'knot_note_create',
                {
                    'note': 'urn:knot:note:' + str(uuid4()),
                    'body': 'This concept remains tentative.',
                    'agent': 'Test',
                    'metadata': {
                        'author': 'Test',
                        'title': 'Tentative concept',
                        'derivation': {
                            'method': 'faithful_restatement',
                            'qualification': 'The source is provisional.',
                            'sources': [pin],
                        },
                    },
                },
            )
            current = await self.call(client, 'knot_note_read', {'note': source['note']})
            self.assertEqual(current['revision'], source['revision'])
            self.assertNotEqual(curated['note'], source['note'])

    async def test_chunks_respect_wire_budget_and_reject_metadata_paths(self):
        from knot.mcp_server import result_size

        server = create_server(self.root, AccessScope.all(), allow_write=True, max_chars=2048)
        async with Client(server, cache=None, read_timeout_seconds=10) as client:
            body = 'Quoted "text" \\ and λ\n' * 300
            note = await self.call(
                client,
                'knot_note_create',
                {'note': 'urn:knot:note:' + str(uuid4()), 'body': body, 'agent': 'Test'},
            )
            offset, chunks = 0, []
            while offset is not None:
                result = await client.call_tool(
                    'knot_note_read',
                    {
                        'note': note['note'],
                        'revision': note['revision'],
                        'offset': offset,
                        'limit': 65536,
                        'include_metadata': False,
                    },
                )
                self.assertFalse(result.is_error)
                result.meta = None
                self.assertLessEqual(result_size(result), 2048)
                chunk = json.loads(result.content[0].text)
                chunks.append(chunk['body'])
                offset = chunk['next_offset']
            self.assertEqual(''.join(chunks), body)
            await self.call(
                client,
                'knot_note_create',
                {
                    'note': 'urn:knot:note:' + str(uuid4()),
                    'body': 'Denied',
                    'agent': 'Test',
                    'metadata': {'data_root': '/tmp/other'},
                },
                error=True,
            )
            self.assertEqual(len(list_notes(self.root)), 1)

    async def test_source_backed_relationship_review_and_scope_controls(self):
        server = create_server(self.root, AccessScope.all(), allow_write=True, allow_review=True)
        async with Client(server, cache=None, read_timeout_seconds=10) as client:
            note = await self.call(
                client,
                'knot_note_create',
                {
                    'note': 'urn:knot:note:' + str(uuid4()),
                    'body': 'Learning relates to practice.',
                    'agent': 'Test agent',
                },
            )
            pin = await self.call(
                client,
                'knot_source_pin',
                {
                    'revision': note['revision'],
                    'quote': 'Learning relates to practice.',
                    'character_offset': 0,
                },
            )
            candidate = {
                'id': 'urn:knot:assertion:' + str(uuid4()),
                'subject': {'id': 'urn:test:learning', 'label': 'Learning'},
                'predicate': 'urn:knot:vocab:relatedTo',
                'object': {'id': 'urn:test:practice', 'label': 'Practice'},
                'origin': 'Explicit',
                'rationale': 'The note states this association.',
                'agent': 'urn:knot:agent:test',
                'generated_at': '2026-11-06T12:00:00Z',
                'sources': [pin],
            }
            checked = await self.call(client, 'knot_candidate_check', {'candidate': candidate})
            self.assertFalse(checked['already_published'])
            self.assertFalse((self.root / 'graph/additions.trig').exists())
            published = await self.call(client, 'knot_candidate_publish', {'candidate': candidate})
            self.assertTrue(published['created'])
            replay = await self.call(client, 'knot_candidate_publish', {'candidate': candidate})
            self.assertFalse(replay['created'])
            detail = await self.call(client, 'knot_assertion_read', {'assertion': candidate['id']})
            self.assertEqual(detail['status'], 'Unreviewed')
            await self.call(
                client,
                'knot_review_decide',
                {
                    'assertion': candidate['id'],
                    'action': 'accept',
                    'expected': detail['latest_event'],
                    'reviewer': 'Test reviewer',
                    'reason': 'Checked the original source.',
                },
            )
            detail = await self.call(client, 'knot_assertion_read', {'assertion': candidate['id']})
            self.assertEqual(detail['status'], 'Accepted')
            listing = await self.call(client, 'knot_assertions', {'status': 'Accepted'})
            self.assertEqual(listing['items'][0]['id'], candidate['id'])
            corrected = await self.call(
                client,
                'knot_review_decide',
                {
                    'assertion': candidate['id'],
                    'action': 'correct',
                    'expected': detail['latest_event'],
                    'reviewer': 'Test reviewer',
                    'reason': 'Qualify the original interpretation.',
                    'replacement': {
                        'subject': 'urn:test:learning',
                        'predicate': 'urn:knot:vocab:relatedTo',
                        'object': 'urn:test:practice',
                        'subject_label': 'Learning',
                        'object_label': 'Practice',
                        'rationale': 'Only an association is supported.',
                    },
                },
            )
            replacement = await self.call(
                client, 'knot_assertion_read', {'assertion': corrected['replacement_id']}
            )
            self.assertEqual(replacement['status'], 'Unreviewed')
            quality = await self.call(client, 'knot_quality', {})
            self.assertEqual(quality['counts']['errors'], 0)

        reader = create_server(self.root, AccessScope())
        async with Client(reader, cache=None, read_timeout_seconds=10) as client:
            self.assertEqual(
                {t.name for t in (await client.list_tools()).tools},
                {'knot_lookup', 'knot_retrieve', 'knot_evaluate', 'knot_explain', 'knot_answer'},
            )
            await self.call(client, 'knot_note_create', {'body': 'Denied'}, error=True)
