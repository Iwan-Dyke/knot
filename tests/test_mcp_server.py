import importlib.util
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from retrieval_fixture import CLAIM, SEED, make_fixture

from knot.access import AccessScope
from knot.notes import create_note, save_note
from knot.query import load_store
from knot.rdf import DERIVED, VOCAB, one, values

HAS_MCP = importlib.util.find_spec('mcp') is not None
if HAS_MCP:
    from mcp import Client, StdioServerParameters

    from knot.mcp_server import create_server, result_size


def setUpModule():
    if HAS_MCP:
        from knot.mcp_server import check_asyncio_support

        check_asyncio_support()


@unittest.skipUnless(HAS_MCP, 'Install the dev or mcp extra to run SDK protocol tests')
class MCPTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        make_fixture(self.root)

    async def test_unknown_explicit_subject_preserves_constraint_without_diagnostics(self):
        async with Client(
            create_server(self.root, AccessScope.all(), max_chars=12000), cache=None
        ) as client:
            response = await client.call_tool(
                'knot_retrieve',
                {
                    'question': 'What dependencies threaten UNKNOWN-731?',
                    'mode': 'hybrid',
                    'max_chars': 4000,
                    'diagnostics': False,
                    'compact': True,
                },
            )
            self.assertFalse(response.is_error)
            self.assertLessEqual(result_size(response), 4000)
            result = json.loads(response.content[0].text)
            self.assertFalse(result['matches'])
            self.assertFalse(result['sources'])
            self.assertFalse(result['assertions'])
            self.assertEqual(result['subject_constraint']['mentions'], ['unknown-731'])
            self.assertTrue(result['subject_constraint']['absence_not_established'])

    async def test_question_only_hybrid_delivers_existing_support_within_transport_budget(self):
        from test_question_retrieval import QuestionRetrievalTests

        from knot.retrieval_engine.response import _quotation

        fixture = QuestionRetrievalTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        aid = 'urn:assertion:release-support'
        quote = 'Falcon release engineering was reported, not independently verified.'
        fixture.claim(
            aid,
            'urn:project:falcon',
            'supports',
            'urn:criterion:release-engineering',
            quote,
            status='Unreviewed',
        )
        fixture.save()
        for scope in (AccessScope.all(), AccessScope()):
            async with Client(
                create_server(fixture.root, scope, max_chars=12000),
                cache=None,
                read_timeout_seconds=15,
            ) as client:
                for budget in (4000, 12000):
                    response = await client.call_tool(
                        'knot_retrieve',
                        {
                            'question': 'What supports my release engineering skills?',
                            'mode': 'hybrid',
                            'max_chars': budget,
                            'diagnostics': False,
                        },
                    )
                    self.assertFalse(response.is_error)
                    self.assertLessEqual(result_size(response), budget)
                    result = json.loads(response.content[0].text)
                    if not scope.whole_dataset:
                        self.assertNotIn(aid, result['assertions'])
                        self.assertNotIn(quote, response.content[0].text)
                    elif budget == 12000:
                        self.assertIn(aid, result['assertions'])
                        self.assertEqual(result['assertions'][aid]['status'], 'Unreviewed')
                        source = result['sources'][result['assertions'][aid]['sources'][0]]
                        self.assertEqual(_quotation(result, source), quote)

    async def test_investigation_guidance_is_sent_on_initialization_in_both_modes(self):
        for scope, owner in ((AccessScope(), False), (AccessScope.all(), True)):
            with self.subTest(owner=owner):
                server = create_server(self.root, scope, allow_write=owner)
                async with Client(server, cache=None, read_timeout_seconds=15) as client:
                    guidance = client.instructions
                    for required in (
                        'straightforward factual questions',
                        'bounded investigation',
                        'motivations, beliefs or reasoning',
                        'source-backed interpretations',
                        '6 tool calls',
                        '60,000 returned characters',
                        'each selected source unit, revision or note',
                        'two sources in one call count as two',
                        'Stop when sufficient evidence exists',
                        'Do not widen access',
                    ):
                        self.assertIn(required, guidance)
                    if not owner:
                        self.assertEqual(
                            {t.name for t in (await client.list_tools()).tools},
                            {
                                'knot_lookup',
                                'knot_retrieve',
                                'knot_evaluate',
                                'knot_explain',
                                'knot_answer',
                            },
                        )

    async def test_leadership_change_guard_and_continuity_evidence_reach_client(self):
        # A later success can demonstrate an established method, not its adoption.
        note = create_note(
            self.root,
            'Week 1: I needed to prioritise better.\n'
            'Week 8: My apprentice solved the problem after diagnostic prompts.\n'
            'I have coached this way for two years; this was not a new method.\n',
            author='Test owner',
        )
        scope = AccessScope(revisions=((note['revision'], note['body_sha256']),))
        async with Client(create_server(self.root, scope), cache=None) as client:
            for required in (
                'event chronology, corrections and continuity',
                'earlier concern followed by later success does not establish a change',
                'section_complete=false',
                'withhold the change claim',
            ):
                self.assertIn(required, client.instructions)
            result = await client.call_tool('knot_retrieve', {'seed': note['note'], 'mode': 'text'})
            self.assertFalse(result.is_error)
            payload = json.loads(result.content[0].text)
            self.assertIn(note['body'], payload['passages'].values())
            source = next(iter(payload['sources'].values()))
            self.assertEqual(source['revision'], note['revision'])
            self.assertEqual(source['citation_status'], 'Verified')
            self.assertFalse(payload['assertions'])

    async def test_optional_evidence_view_preserves_scope_policy_and_mcp_budgets(self):
        from knot.retrieval_engine.response import _quotation
        from knot.retrieval_engine.wire import expand

        server = create_server(self.root, AccessScope.all(), max_chars=24000)
        async with Client(server, cache=None, read_timeout_seconds=15) as client:
            for budget in (4000, 8000, 12000, 24000):
                arguments = {'seed': SEED, 'max_chars': budget}
                original = await client.call_tool('knot_retrieve', arguments)
                self.assertFalse(original.is_error)
                full = json.loads(original.content[0].text)
                for compact in (False, True):
                    arguments.update(diagnostics=False, compact=compact)
                    first = await client.call_tool('knot_retrieve', arguments)
                    second = await client.call_tool('knot_retrieve', arguments)
                    self.assertFalse(first.is_error)
                    self.assertEqual(first.content, second.content)
                    self.assertLessEqual(result_size(first), budget)
                    result = expand(json.loads(first.content[0].text))
                    self.assertEqual(result['policy'], full['policy'])
                    self.assertIn('diagnostics_omitted', result)
                    self.assertNotIn('selection', result)
                    for eid, source in full['sources'].items():
                        self.assertEqual(
                            _quotation(result, result['sources'][eid]), _quotation(full, source)
                        )
        denied = create_server(self.root, AccessScope())
        async with Client(denied, cache=None, read_timeout_seconds=15) as client:
            response = await client.call_tool(
                'knot_retrieve', {'seed': SEED, 'diagnostics': False, 'compact': True}
            )
            self.assertTrue(response.is_error)

    async def test_shared_provenance_fits_transport_without_dropping_citations(self):
        from mcp.server.mcpserver.exceptions import ToolError

        from knot.interfaces.mcp_server import _bounded
        from knot.retrieval_engine.response import _measure
        from knot.retrieval_engine.wire import expand

        payload = {
            'sources': {
                f'e{i}': {
                    'revision': 'revision-one',
                    'warnings': ['Unconfirmed account. ' * 100],
                    'locator': {'characterOffset': i},
                    'passage': 'p1',
                }
                for i in range(3)
            },
            'passages': {'p1': 'Exact retained evidence.'},
            'usage': {'characters': 0, 'utf8_bytes': 0},
        }
        _measure(payload)
        encoded = json.loads(_bounded(payload, 4096, compact_response=True))
        self.assertEqual(encoded['format'], 'shared-provenance-v1')
        self.assertEqual(expand(encoded), payload)
        self.assertEqual(len(encoded['sources']), 3)
        with self.assertRaises(ToolError):
            _bounded(payload, 4096)

    async def test_compact_response_preserves_evidence_and_denied_scope(self):
        from knot.retrieval_engine.wire import expand

        server = create_server(self.root, AccessScope.all())
        async with Client(server, cache=None, read_timeout_seconds=15) as client:
            responses = []
            for compact in (False, True):
                response = await client.call_tool(
                    'knot_retrieve', {'seed': SEED, 'compact': compact}
                )
                self.assertFalse(response.is_error)
                response.meta = None
                self.assertLessEqual(result_size(response), 12000)
                payload = json.loads(response.content[0].text)
                self.assertEqual(payload['usage']['characters'], len(response.content[0].text))
                responses.append(expand(payload))
            self.assertEqual(*responses)
        denied = create_server(self.root, AccessScope())
        async with Client(denied, cache=None, read_timeout_seconds=15) as client:
            response = await client.call_tool('knot_retrieve', {'seed': SEED, 'compact': True})
            self.assertTrue(response.is_error)
            self.assertNotIn(SEED, response.content[0].text)

    async def test_discovery_and_retrieval_use_one_bounded_read_only_text_result(self):
        server = create_server(self.root, AccessScope.all())
        async with Client(
            server, raise_exceptions=True, cache=None, read_timeout_seconds=15
        ) as client:
            listed = await client.list_tools()
            self.assertEqual(
                {t.name for t in listed.tools},
                {'knot_lookup', 'knot_retrieve', 'knot_evaluate', 'knot_explain', 'knot_answer'},
            )
            self.assertTrue(all(t.annotations.read_only_hint for t in listed.tools))
            self.assertTrue(all(t.annotations.open_world_hint is False for t in listed.tools))
            found = await client.call_tool('knot_lookup', {'query': 'Recovery'})
            self.assertFalse(found.is_error)
            self.assertEqual(len(found.content), 1)
            self.assertIsNone(found.structured_content)
            result = await client.call_tool(
                'knot_retrieve',
                {
                    'seed': SEED,
                    'question': 'What unresolved dependencies threaten Orion?',
                    'mode': 'hybrid',
                    'max_chars': 7000,
                },
            )
            self.assertFalse(result.is_error)
            self.assertIsNone(result.structured_content)
            payload = json.loads(result.content[0].text)
            self.assertIn(CLAIM, payload['assertions'])
            result.meta = None
            self.assertLessEqual(result_size(result), 7000)
            self.assertEqual(payload['usage']['characters'], len(result.content[0].text))
            accepted = await client.call_tool(
                'knot_retrieve', {'seed': SEED, 'accepted_only': True}
            )
            self.assertFalse(json.loads(accepted.content[0].text)['paths'])

    async def test_broad_discovery_and_selected_subjects_use_the_existing_two_tools(self):
        server = create_server(self.root, AccessScope.all(), max_chars=12000)
        async with Client(server, cache=None, read_timeout_seconds=15) as client:
            response = await client.call_tool(
                'knot_lookup',
                {
                    'query': 'What survey feed is missing?',
                    'mode': 'discovery',
                    'max_chars': 7000,
                },
            )
            self.assertFalse(response.is_error)
            discovery = json.loads(response.content[0].text)
            self.assertIn(SEED, {c['id'] for c in discovery['candidates']})
            self.assertEqual(
                {o['id'] for o in discovery['objectives']},
                {'relationships', 'context', 'qualifications'},
            )
            response.meta = None
            self.assertLessEqual(result_size(response), 7000)
            response = await client.call_tool(
                'knot_retrieve',
                {
                    'subjects': [SEED],
                    'question': 'What survey feed is missing?',
                    'max_chars': 12000,
                },
            )
            self.assertFalse(response.is_error)
            evidence = json.loads(response.content[0].text)
            self.assertIn(CLAIM, evidence['assertions'])
            self.assertTrue(all('handle' in m for m in evidence['matches']))
            self.assertEqual(len((await client.list_tools()).tools), 5)

    async def test_broad_discovery_does_not_expose_denied_subjects(self):
        server = create_server(self.root, AccessScope())
        async with Client(server, cache=None, read_timeout_seconds=15) as client:
            response = await client.call_tool(
                'knot_lookup',
                {
                    'query': 'What survey feed is missing?',
                    'mode': 'discovery',
                },
            )
            payload = json.loads(response.content[0].text)
            self.assertFalse(payload['candidates'])
            self.assertFalse(payload['sources'])
            messages = []
            for subject in (SEED, 'urn:unknown:private'):
                response = await client.call_tool(
                    'knot_retrieve',
                    {
                        'subjects': [subject],
                        'question': 'What survey feed is missing?',
                    },
                )
                self.assertTrue(response.is_error)
                messages.append(response.content[0].text)
            self.assertEqual(messages[0], messages[1])

    async def test_denied_and_unknown_seeds_return_the_same_sanitised_error(self):
        server = create_server(self.root, AccessScope())
        async with Client(
            server, raise_exceptions=True, cache=None, read_timeout_seconds=15
        ) as client:
            found = await client.call_tool('knot_lookup', {'query': 'Orion'})
            self.assertFalse(json.loads(found.content[0].text)['candidates'])
            messages = []
            for seed in (SEED, 'urn:secret:does-not-exist'):
                result = await client.call_tool('knot_retrieve', {'seed': seed})
                self.assertTrue(result.is_error)
                messages.append(result.content[0].text)
                self.assertNotIn(seed, result.content[0].text)
            self.assertEqual(messages[0], messages[1])

    async def test_clients_cannot_select_paths_or_exceed_server_limits(self):
        server = create_server(self.root, AccessScope.all(), max_chars=7000)
        async with Client(
            server, raise_exceptions=True, cache=None, read_timeout_seconds=15
        ) as client:
            for arguments in (
                {'seed': SEED, 'max_chars': 7001},
                {'seed': SEED, 'max_chars': True},
                {'seed': SEED, 'question': 'x' * 2001},
            ):
                result = await client.call_tool('knot_retrieve', arguments)
                self.assertTrue(result.is_error)
            schema = (await client.list_tools()).tools
            retrieve_schema = next(t.input_schema for t in schema if t.name == 'knot_retrieve')
            self.assertNotIn('data_root', retrieve_schema['properties'])
            self.assertNotIn('scope', retrieve_schema['properties'])

    async def test_scope_changes_do_not_leak_in_errors_or_payloads(self):
        store = load_store(self.root / 'graph')
        eid = values(store, CLAIM, DERIVED)[0]
        revision = one(store, eid.value, VOCAB + 'revision').value
        sha = one(store, revision, VOCAB + 'sha256').value
        server = create_server(self.root, AccessScope(revisions=((revision, sha),)))
        async with Client(
            server, raise_exceptions=True, cache=None, read_timeout_seconds=15
        ) as client:
            result = await client.call_tool('knot_lookup', {'query': 'Orion'})
            self.assertFalse(json.loads(result.content[0].text)['candidates'])
            # A malformed dataset error must not echo source paths or hidden IDs.
            (self.root / 'graph/claims.trig').write_text('broken private:source:hidden')
            result = await client.call_tool('knot_lookup', {'query': 'Recovery'})
            self.assertTrue(result.is_error)
            self.assertNotIn('private', result.content[0].text)

    async def test_real_stdio_subprocess_discovers_tools_and_serves_calls(self):
        project = Path.cwd()
        target = StdioServerParameters(
            command=str(project / '.venv/bin/python'),
            args=['-m', 'knot.mcp_server', '--data-root', str(self.root), '--allow-all'],
            env={**os.environ, 'PYTHONPATH': str(project / 'src')},
        )
        async with Client(target, cache=None, read_timeout_seconds=15) as client:
            self.assertIn('bounded investigation', client.instructions)
            self.assertIn('withhold the change claim', client.instructions)
            self.assertEqual(
                {t.name for t in (await client.list_tools()).tools},
                {'knot_lookup', 'knot_retrieve', 'knot_evaluate', 'knot_explain', 'knot_answer'},
            )
            result = await client.call_tool('knot_lookup', {'query': 'Recovery'})
            self.assertFalse(result.is_error)
            self.assertEqual(
                json.loads(result.content[0].text)['candidates'][0]['id'], 'urn:work:recovery'
            )

    async def test_legacy_client_can_call_the_same_tools(self):
        server = create_server(self.root, AccessScope.all())
        async with Client(server, mode='legacy', cache=None, read_timeout_seconds=15) as client:
            self.assertIn('bounded investigation', client.instructions)
            result = await client.call_tool('knot_lookup', {'query': 'Recovery'})
            self.assertFalse(result.is_error)
            self.assertIsNone(result.structured_content)
            self.assertEqual(
                json.loads(result.content[0].text)['candidates'][0]['id'], 'urn:work:recovery'
            )

    async def test_native_question_search_direct_read_and_history_use_existing_tools(self):
        first = create_note(
            self.root,
            '* Reading\nThroughput is limited by a constraint.\nHowever, my interpretation remains uncertain.\n',
            format='org',
            author='Test Author',
            title='Reading reflection',
        )
        latest = save_note(
            self.root,
            first['note'],
            'Later reflection: the constraint was misunderstood.\n',
            expected=first['revision'],
        )
        scope = AccessScope(
            revisions=(
                (first['revision'], first['body_sha256']),
                (latest['revision'], latest['body_sha256']),
            )
        )
        server = create_server(self.root, scope)
        async with Client(server, cache=None, read_timeout_seconds=15) as client:
            tools = (await client.list_tools()).tools
            self.assertEqual(
                {t.name for t in tools},
                {'knot_lookup', 'knot_retrieve', 'knot_evaluate', 'knot_explain', 'knot_answer'},
            )
            found = await client.call_tool('knot_lookup', {'query': 'Reading reflection'})
            self.assertEqual(
                json.loads(found.content[0].text)['candidates'][0]['id'], first['note']
            )
            search = await client.call_tool(
                'knot_retrieve',
                {'question': 'How did my reflection about a constraint change?', 'max_chars': 8000},
            )
            self.assertFalse(search.is_error)
            payload = json.loads(search.content[0].text)
            self.assertEqual(
                {s['revision'] for s in payload['sources'].values()}, {latest['revision']}
            )
            history = await client.call_tool(
                'knot_retrieve',
                {'seed': first['note'], 'note_revision': first['revision'], 'max_chars': 8000},
            )
            self.assertFalse(history.is_error)
            old = json.loads(history.content[0].text)
            self.assertEqual(set(old['passages'].values()), {first['body']})
            self.assertTrue(all(c['claim_review'] is None for c in old['source_context'].values()))
            self.assertEqual(
                next(iter(old['sources'].values()))['native_note']['author'], 'Test Author'
            )
            self.assertFalse(old['assertions'])
            self.assertIsNone(history.structured_content)
            history.meta = None
            self.assertLessEqual(result_size(history), 8000)

    async def test_native_revision_denials_and_shared_bodies_do_not_leak(self):
        note = create_note(self.root, 'A personal reflection on uncertainty.', title='Visible')
        hidden = create_note(self.root, note['body'], title='Hidden title', author='Hidden author')
        scope = AccessScope(revisions=((note['revision'], note['body_sha256']),))
        server = create_server(self.root, scope)
        async with Client(server, cache=None, read_timeout_seconds=15) as client:
            visible = await client.call_tool(
                'knot_retrieve', {'question': 'What personal uncertainty did I reflect on?'}
            )
            self.assertFalse(visible.is_error)
            wire = visible.content[0].text
            self.assertIn(note['revision'], wire)
            self.assertNotIn(hidden['note'], wire)
            self.assertNotIn('Hidden', wire)
            messages = []
            for revision in (hidden['revision'], 'urn:knot:note-revision:' + '0' * 64):
                denied = await client.call_tool(
                    'knot_retrieve', {'seed': note['note'], 'note_revision': revision}
                )
                self.assertTrue(denied.is_error)
                messages.append(denied.content[0].text)
            self.assertEqual(messages[0], messages[1])
            (self.root / note['body_path']).write_bytes(b'corrupt visible body')
            invalid = await client.call_tool('knot_retrieve', {'seed': note['note']})
            self.assertFalse(invalid.is_error)
            result = json.loads(invalid.content[0].text)
            self.assertFalse(result['sources'])
            self.assertGreater(result['omissions']['invalid_citations'], 0)

    async def test_native_notes_are_available_over_the_actual_stdio_transport(self):
        note = create_note(
            self.root,
            'Technical investigation: retry validation remains incomplete.',
            entities=[SEED],
            author='Test',
        )
        grant = self.root / 'native-scope.json'
        grant.write_text(json.dumps({'revisions': {note['revision']: note['body_sha256']}}))
        project = Path.cwd()
        target = StdioServerParameters(
            command=str(project / '.venv/bin/python'),
            args=['-m', 'knot.mcp_server', '--data-root', str(self.root), '--scope', str(grant)],
            env={**os.environ, 'PYTHONPATH': str(project / 'src')},
        )
        async with Client(target, cache=None, read_timeout_seconds=15) as client:
            result = await client.call_tool(
                'knot_retrieve',
                {
                    'seed': SEED,
                    'question': 'What retry validation remains incomplete?',
                    'mode': 'hybrid',
                },
            )
            self.assertFalse(result.is_error)
            payload = json.loads(result.content[0].text)
            self.assertEqual(
                {s['revision'] for s in payload['sources'].values()}, {note['revision']}
            )
            self.assertFalse(payload['assertions'])

    async def test_native_framing_preserves_complete_text_or_reports_omission(self):
        from knot.retrieval import _quotation

        note = create_note(
            self.root,
            'A "quoted" uncertain result.\n' * 28 + 'However, acceptance remains unverified.\n',
        )
        server = create_server(
            self.root, AccessScope(revisions=((note['revision'], note['body_sha256']),))
        )
        async with Client(server, cache=None, read_timeout_seconds=15) as client:
            for budget in (4000, 8000):
                result = await client.call_tool(
                    'knot_retrieve', {'seed': note['note'], 'max_chars': budget}
                )
                self.assertFalse(result.is_error)
                payload = json.loads(result.content[0].text)
                result.meta = None
                self.assertLessEqual(result_size(result), budget)
                if payload['sources']:
                    self.assertEqual(
                        {_quotation(payload, s) for s in payload['sources'].values()},
                        {note['body']},
                    )
                else:
                    self.assertTrue(payload['omissions']['further_unknown'])
                if budget == 8000:
                    self.assertTrue(payload['sources'])

    async def test_mcp_framing_removes_complete_packages_when_inner_json_alone_fits(self):
        server = create_server(self.root, AccessScope.all())
        async with Client(server, cache=None, read_timeout_seconds=15) as client:
            result = await client.call_tool('knot_retrieve', {'seed': SEED, 'max_chars': 4000})
            self.assertFalse(result.is_error)
            payload = json.loads(result.content[0].text)
            self.assertGreater(payload['omissions']['limits']['mcp_characters'], 0)
            result.meta = None
            self.assertLessEqual(result_size(result), 4000)
            for path in payload['paths']:
                self.assertTrue(all(step['assertion'] in payload['assertions'] for step in path))

    def test_cli_requires_an_explicit_access_grant_and_lists_local_source_pins(self):
        command = ['.venv/bin/python', '-m', 'knot.mcp_server']
        denied = subprocess.run(
            command + ['--data-root', str(self.root)], capture_output=True, text=True
        )
        self.assertNotEqual(denied.returncode, 0)
        self.assertFalse(denied.stdout)
        sources = subprocess.run(
            command + ['sources', '--data-root', str(self.root)],
            capture_output=True,
            text=True,
            check=True,
        )
        rows = json.loads(sources.stdout)
        self.assertTrue(rows)
        self.assertTrue(
            all(len(row['sha256']) == 64 and row['revision'].startswith('urn:') for row in rows)
        )


if __name__ == '__main__':
    unittest.main()
