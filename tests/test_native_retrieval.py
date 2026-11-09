import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from retrieval_fixture import CLAIM, ROUTE, SEED, make_fixture

from knot.access import AccessScope
from knot.notes import create_note, index_note_revisions, read_note, save_note
from knot.query import load_store
from knot.rdf import DERIVED, RDF_TYPE, VOCAB, Dataset, one, values
from knot.retrieval import Policy, _Evidence, _prepare, _quotation, lookup, retrieve, serialise
from knot.review import decide
from knot.search import Limits


class NativeRetrievalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        make_fixture(self.root)
        self.policy = Policy(max_chars=24000)

    def scope(self, *notes, graph=False):
        pins = {n['revision']: n['body_sha256'] for n in notes}
        if graph:
            store = load_store(self.root / 'graph', include_notes=False)
            for aid in (CLAIM, ROUTE):
                for evidence in values(store, aid, DERIVED):
                    revision = one(store, evidence.value, VOCAB + 'revision').value
                    pins[revision] = one(store, revision, VOCAB + 'sha256').value
        return AccessScope(revisions=tuple(sorted(pins.items())))

    def get(self, question='What Orion dependencies remain unresolved?', *, seed=SEED, **kwargs):
        return retrieve(self.root, seed, self.policy, question=question, mode='hybrid', **kwargs)

    def native(self, result):
        return [s for s in result['sources'].values() if 'native_note' in s]

    def test_navigation_does_not_grant_linked_notes_or_denied_entity_declarations(self):
        hidden = create_note(self.root, 'Private target body', title='Secret target title')
        eid = 'urn:knot:entity:00000000-0000-4000-8000-000000000002'
        visible = create_note(
            self.root,
            'Visible concept reflection',
            title='Public reflection',
            navigation={
                'themes': [],
                'links': [{'note': hidden['note'], 'reason': 'Related thought'}],
                'declarations': [
                    {
                        'id': eid,
                        'label': 'Visible concept',
                        'type': 'Concept',
                        'quote': 'Visible concept',
                        'offset': 0,
                    }
                ],
            },
        )
        result = retrieve(self.root, visible['note'], self.policy, scope=self.scope(visible))
        text = json.dumps(result)
        self.assertNotIn('Private target body', text)
        self.assertNotIn('Secret target title', text)
        self.assertIn('Visible concept', text)
        self.assertEqual(
            lookup(self.root, 'Visible concept', scope=self.scope(hidden))['candidates'], []
        )
        self.assertIn(
            eid,
            [
                c['id']
                for c in lookup(self.root, 'Visible concept', scope=self.scope(visible))[
                    'candidates'
                ]
            ],
        )

    def test_associated_note_without_entity_words_combines_with_existing_graph(self):
        note = create_note(
            self.root,
            '# Investigation\nThe deployment dependency remains unresolved.\nHowever, the apparent fix is not independently verified.\n',
            entities=[SEED],
            title='Investigation',
            author='Test Author',
            kind='Hypothesis',
        )
        result = self.get(scope=self.scope(note, graph=True))
        self.assertIn(CLAIM, result['assertions'])
        source = next(s for s in self.native(result) if s['revision'] == note['revision'])
        self.assertIn('not independently verified', _quotation(result, source))
        self.assertEqual(source['sha256'], note['body_sha256'])
        self.assertEqual(source['manifest_sha256'], note['revision'].rsplit(':', 1)[1])
        self.assertEqual(source['native_note']['author'], 'Test Author')
        self.assertEqual(source['native_note']['kind'], 'Hypothesis')
        contexts = [
            c
            for eid, c in result['source_context'].items()
            if 'native_note' in result['sources'][eid]
        ]
        self.assertTrue(contexts)
        self.assertTrue(all(c['claim_review'] is None for c in contexts))
        self.assertTrue(all(c['entity_link'] == 'AuthorDeclaredNavigation' for c in contexts))

    def test_question_only_search_finds_unassociated_reading_and_personal_notes(self):
        reading = create_note(
            self.root,
            '* Reading\nThe book explains throughput and limiting constraints.\n',
            format='org',
            title='Reading notes',
        )
        personal = create_note(
            self.root,
            '# Reflection\nMy busyness was not the same as useful throughput.\n',
            kind='Thought',
            author='Test',
        )
        result = self.get(
            'What did reading and reflection teach me about throughput?',
            seed=None,
            scope=self.scope(reading, personal),
        )
        self.assertEqual(
            {s['revision'] for s in self.native(result)},
            {reading['revision'], personal['revision']},
        )
        self.assertFalse(result['assertions'])
        self.assertFalse(result['paths'])
        self.assertIsNone(result['seed'])

    def test_direct_note_and_historical_read_preserve_exact_bytes_and_metadata(self):
        body = '\ufeff# Reflection\r\nλ🙂 I thought the change was complete.\r\nHowever, acceptance was pending.\r\n'
        first = create_note(self.root, body, title='Early interpretation', author='A')
        latest = save_note(
            self.root,
            first['note'],
            '# Correction\nAcceptance failed; my earlier belief was wrong.\n',
            expected=first['revision'],
            title='Later correction',
            author='B',
        )
        current = retrieve(self.root, first['note'], self.policy)
        source = self.native(current)[0]
        self.assertEqual(source['revision'], latest['revision'])
        self.assertNotIn(first['revision'], serialise(current))
        historical = retrieve(
            self.root,
            first['note'],
            self.policy,
            note_revision=first['revision'],
            scope=self.scope(first),
        )
        old = self.native(historical)[0]
        self.assertEqual(_quotation(historical, old), body)
        self.assertEqual(old['native_note']['author'], 'A')
        self.assertEqual(old['native_note']['title'], 'Early interpretation')
        self.assertEqual(old['native_note']['modified_at'], first['modified_at'])
        self.assertEqual(old['locator']['characterOffset'], '0')
        self.assertNotIn(latest['revision'], serialise(historical))

    def test_latest_granted_revision_does_not_disclose_a_denied_head(self):
        first = create_note(
            self.root, 'Throughput remains uncertain.', title='Visible', entities=[SEED]
        )
        scope = self.scope(first)
        before = serialise(self.get('What throughput remains uncertain?', scope=scope))
        latest = save_note(
            self.root,
            first['note'],
            'Secret revised account.',
            expected=first['revision'],
            title='Secret head',
        )
        self.assertEqual(
            before, serialise(self.get('What throughput remains uncertain?', scope=scope))
        )
        (self.root / latest['body_path']).write_bytes(b'corrupt denied body')
        manifest = self.root / 'notes/revisions' / (latest['revision'].rsplit(':', 1)[1] + '.json')
        manifest.write_bytes(b'corrupt denied manifest')
        self.assertEqual(
            before, serialise(self.get('What throughput remains uncertain?', scope=scope))
        )
        self.assertNotIn('Secret', before)
        self.assertNotIn(latest['revision'], before)

    def test_hidden_notes_do_not_change_results_labels_scores_or_omissions(self):
        visible = create_note(
            self.root, 'A reading note about throughput constraints.', title='Visible reading'
        )
        scope = self.scope(visible)
        before = self.get('What are throughput constraints?', seed=None, scope=scope)
        found = lookup(self.root, 'Visible', scope=scope)
        hidden = create_note(
            self.root,
            visible['body'],
            title='Hidden duplicate',
            author='Hidden Author',
            entities=[SEED],
        )
        create_note(self.root, 'constraints throughput ' * 200, title='Keyword distraction')
        self.assertEqual(
            before, self.get('What are throughput constraints?', seed=None, scope=scope)
        )
        self.assertEqual(found, lookup(self.root, 'Visible', scope=scope))
        self.assertFalse(lookup(self.root, 'Hidden', scope=scope)['candidates'])
        (
            self.root / 'notes/revisions' / (hidden['revision'].rsplit(':', 1)[1] + '.json')
        ).write_bytes(b'bad hidden source')
        self.assertEqual(
            before, self.get('What are throughput constraints?', seed=None, scope=scope)
        )
        self.assertEqual({s['native_note']['id'] for s in self.native(before)}, {visible['note']})

    def test_denied_history_wrong_pin_and_uncommitted_revision_cannot_be_read(self):
        first = create_note(self.root, 'Earlier account.')
        latest = save_note(self.root, first['note'], 'Current account.', expected=first['revision'])
        with self.assertRaises(ValueError):
            retrieve(
                self.root,
                first['note'],
                self.policy,
                note_revision=first['revision'],
                scope=self.scope(latest),
            )
        wrong = AccessScope(revisions=((latest['revision'], '0' * 64),))
        with self.assertRaises(ValueError):
            retrieve(self.root, first['note'], self.policy, scope=wrong)
        with self.assertRaises(ValueError):
            retrieve(self.root, first['note'], self.policy, scope=AccessScope())
        with patch('knot.notes.atomic_json', side_effect=OSError('Interrupted publication')):
            with self.assertRaises(OSError):
                save_note(
                    self.root,
                    first['note'],
                    'Uncommitted private draft.',
                    expected=latest['revision'],
                )
        committed = {first['revision'], latest['revision']}
        orphan = next(
            p
            for p in (self.root / 'notes/revisions').glob('*.json')
            if 'urn:knot:note-revision:' + p.stem not in committed
        )
        manifest = json.loads(orphan.read_bytes())
        revision = 'urn:knot:note-revision:' + orphan.stem
        grant = AccessScope(revisions=((revision, manifest['body_sha256']),))
        with self.assertRaises(ValueError):
            retrieve(self.root, first['note'], self.policy, note_revision=revision, scope=grant)

    def test_entity_note_browse_uses_whole_complete_notes_without_a_question(self):
        note = create_note(
            self.root,
            '# Decision\nA possible approach.\n\n# Qualification\nHowever, acceptance is still pending.\n',
            entities=[SEED],
        )
        result = retrieve(self.root, SEED, self.policy, mode='text', scope=self.scope(note))
        self.assertEqual({_quotation(result, s) for s in self.native(result)}, {note['body']})
        self.assertFalse(result['paths'])
        self.assertFalse(result['assertions'])

    def test_conflicting_current_reflections_remain_attributed_source_accounts(self):
        first = create_note(
            self.root,
            '# Personal reflection\nDelegation helped my workload. However, the evidence is anecdotal.\n',
            author='A',
            kind='Thought',
        )
        second = create_note(
            self.root,
            '* Reading reflection\nDelegation did not reduce my workload. I remain uncertain.\n',
            author='B',
            kind='Assessment',
            format='org',
        )
        result = self.get(
            'What did my reflections say about delegation and workload?',
            seed=None,
            scope=self.scope(first, second),
        )
        self.assertEqual({s['native_note']['author'] for s in self.native(result)}, {'A', 'B'})
        self.assertFalse(result['assertions'])
        self.assertTrue(all(c['claim_review'] is None for c in result['source_context'].values()))

    def test_shared_scan_caps_count_only_visible_native_sources(self):
        first = create_note(
            self.root,
            '# Reading\nThroughput constraints remain uncertain.\n\n# Later\nA separate thought.\n',
        )
        second = create_note(self.root, 'More reading about throughput constraints.')
        scope = self.scope(first, second)
        limits = Limits(max_source_revisions=1, max_source_sections=1, max_candidates=1)
        before = self.get(
            'What reading concerns throughput constraints?', seed=None, scope=scope, limits=limits
        )
        self.assertEqual(before['usage']['source_revisions'], 1)
        self.assertLessEqual(before['usage']['source_sections'], 1)
        self.assertEqual(before['omissions']['limits']['source_revisions'], 1)
        create_note(self.root, 'Hidden throughput constraints.' * 100, title='Denied')
        self.assertEqual(
            before,
            self.get(
                'What reading concerns throughput constraints?',
                seed=None,
                scope=scope,
                limits=limits,
            ),
        )

    def test_native_questions_and_history_work_with_a_note_seed(self):
        first = create_note(self.root, 'A retry dependency is unresolved.')
        later = save_note(
            self.root,
            first['note'],
            'The retry dependency was resolved.',
            expected=first['revision'],
        )
        current = retrieve(
            self.root,
            first['note'],
            self.policy,
            question='What retry dependency was resolved?',
            scope=self.scope(later),
        )
        self.assertEqual({s['revision'] for s in self.native(current)}, {later['revision']})
        historical = retrieve(
            self.root,
            policy=self.policy,
            question='What retry dependency was unresolved?',
            note_revision=first['revision'],
            scope=self.scope(first),
        )
        self.assertEqual({s['revision'] for s in self.native(historical)}, {first['revision']})

    def test_historical_rdf_registration_does_not_bypass_native_defaults_or_pins(self):
        first = create_note(
            self.root,
            '\ufeffOld reading about throughput.',
            title='Earlier',
            author='Historical author',
        )
        latest = save_note(
            self.root,
            first['note'],
            'Current reading about throughput.',
            expected=first['revision'],
        )
        registration = Dataset()
        registration.add(first['revision'], VOCAB + 'sha256', first['body_sha256'], literal=True)
        registration.add(
            first['revision'], VOCAB + 'snapshotPath', first['body_path'], literal=True
        )
        registration.add(first['note'], RDF_TYPE, VOCAB + 'Document')
        registration.add(first['note'], VOCAB + 'revision', first['revision'])
        (self.root / 'graph/native-source.trig').write_text(registration.text())
        result = self.get(
            'What reading concerns throughput?', seed=None, scope=self.scope(first, latest)
        )
        self.assertEqual({s['revision'] for s in result['sources'].values()}, {latest['revision']})
        prepared = _prepare(self.root, scope=self.scope(first, latest))
        text, citation = _Evidence(self.root, prepared[0]).revision(first['revision'])
        self.assertEqual(text, first['body'])
        self.assertEqual(citation['native_note']['author'], 'Historical author')
        self.assertEqual(citation['native_note']['currentness'], 'EvidenceRevision')
        historical = retrieve(
            self.root,
            policy=self.policy,
            note_revision=first['revision'],
            scope=self.scope(first, latest),
        )
        self.assertEqual({s['revision'] for s in self.native(historical)}, {first['revision']})
        wrong = AccessScope(
            revisions=((first['revision'], '0' * 64), (latest['revision'], latest['body_sha256']))
        )
        with self.assertRaises(ValueError):
            self.get('What reading concerns throughput?', seed=None, scope=wrong)

    def test_foreign_rdf_document_links_cannot_leak_shared_native_body_metadata(self):
        visible = create_note(self.root, 'A reading insight about throughput.', title='Visible')
        hidden = create_note(self.root, visible['body'], title='Private writing')
        scope = self.scope(visible)
        before = self.get('What reading insight concerns throughput?', seed=None, scope=scope)
        foreign = Dataset()
        foreign.add(hidden['note'], RDF_TYPE, VOCAB + 'Document')
        foreign.add(hidden['note'], VOCAB + 'revision', visible['revision'])
        foreign.add(hidden['note'], VOCAB + 'archive', 'private-location.zip', literal=True)
        foreign.add(
            visible['revision'],
            VOCAB + 'warning',
            'Private annotation outside the native manifest',
            literal=True,
        )
        (self.root / 'graph/foreign-native-ref.trig').write_text(foreign.text())
        after = self.get('What reading insight concerns throughput?', seed=None, scope=scope)
        self.assertEqual(before, after)
        self.assertNotIn(hidden['note'], serialise(after))
        self.assertNotIn('Private', serialise(after))

    def test_superseded_assertion_is_not_restored_by_the_original_note_text(self):
        note = create_note(
            self.root,
            'The survey feed is missing. However, this may be an old interpretation.',
            entities=[SEED],
        )
        decide(
            self.root,
            CLAIM,
            'correct',
            reviewer='Test',
            reason='Explicit correction',
            replacement={
                'subject': 'urn:work:recovery',
                'predicate': VOCAB + 'dependsOn',
                'object': 'urn:dependency:new-feed',
                'subject_label': 'Recovery',
                'object_label': 'New feed',
                'rationale': 'Replacement remains unreviewed',
            },
        )
        result = self.get(scope=self.scope(note, graph=True))
        self.assertNotIn(CLAIM, result['assertions'])
        self.assertTrue(self.native(result))
        self.assertTrue(
            all(
                c['claim_review'] is None
                for eid, c in result['source_context'].items()
                if 'native_note' in result['sources'][eid]
            )
        )

    def test_source_corruption_is_reported_and_never_returned_as_verified(self):
        note = create_note(self.root, 'A technical dependency remains unresolved.', entities=[SEED])
        (self.root / note['body_path']).write_bytes(b'corrupt')
        result = self.get(scope=self.scope(note))
        self.assertFalse(self.native(result))
        self.assertGreater(result['omissions']['invalid_citations'], 0)
        self.assertIn('ChangedFile', result['omissions']['citation_errors'])

    def test_note_source_never_reactivates_rejected_assertion_or_accepted_status(self):
        note = create_note(
            self.root,
            'The survey feed is missing. However this report may be wrong.',
            entities=[SEED],
            kind='Thought',
        )
        decide(self.root, CLAIM, 'reject', reviewer='Test', reason='Known rejected assertion')
        result = self.get(scope=self.scope(note, graph=True))
        self.assertNotIn(CLAIM, result['assertions'])
        self.assertTrue(self.native(result))
        accepted = retrieve(
            self.root,
            SEED,
            Policy(max_chars=24000, accepted_only=True),
            question='What dependencies remain?',
            mode='hybrid',
            scope=self.scope(note, graph=True),
        )
        self.assertFalse(self.native(accepted))
        self.assertTrue(accepted['omissions']['source_only_excluded'])

    def test_native_sources_share_limits_and_deterministic_selection(self):
        note = create_note(
            self.root,
            '# Reading\nA throughput constraint.\n\n# Reflection\nHowever, its meaning is uncertain.\n',
            entities=[SEED],
        )
        for budget in (4000, 8000, 12000, 24000):
            policy = Policy(max_chars=budget, max_passages=1)
            first = retrieve(
                self.root,
                SEED,
                policy,
                question='What throughput constraints are uncertain?',
                mode='hybrid',
                scope=self.scope(note, graph=True),
            )
            second = retrieve(
                self.root,
                SEED,
                policy,
                question='What throughput constraints are uncertain?',
                mode='hybrid',
                scope=self.scope(note, graph=True),
            )
            self.assertEqual(serialise(first), serialise(second))
            self.assertLessEqual(len(serialise(first)), budget)
            self.assertLessEqual(len(first['passages']), 1)
            for source in self.native(first):
                quote = _quotation(first, source)
                offset = int(source['locator']['characterOffset'])
                self.assertEqual(note['body'][offset : offset + len(quote)], quote)

    def test_notes_only_dataset_supports_lookup_search_and_explicit_history(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            note = create_note(root, 'Reading about limiting constraints.', title='Reading')
            self.assertEqual(lookup(root, 'Reading')['candidates'][0]['id'], note['note'])
            result = retrieve(
                root, question='What did I read about constraints?', mode='text', policy=self.policy
            )
            self.assertEqual(self.native(result)[0]['revision'], note['revision'])

    def test_legacy_registry_indexing_is_explicit_and_preserves_evidence(self):
        first = create_note(self.root, 'Original reading.')
        latest = save_note(self.root, first['note'], 'Revised reading.', expected=first['revision'])
        registry = self.root / 'notes/registry.json'
        registry.write_text(
            json.dumps({'schema_version': 1, 'notes': {first['note']: latest['revision']}})
        )
        sources = {p: p.read_bytes() for p in (self.root / 'sources').rglob('*') if p.is_file()}
        self.assertEqual(read_note(self.root, first['note'])['revision'], latest['revision'])
        with self.assertRaisesRegex(ValueError, 'index_note_revisions'):
            retrieve(self.root, first['note'], self.policy, scope=self.scope(first))
        index_note_revisions(self.root)
        result = retrieve(
            self.root,
            first['note'],
            self.policy,
            note_revision=first['revision'],
            scope=self.scope(first),
        )
        self.assertEqual(self.native(result)[0]['revision'], first['revision'])
        self.assertTrue(all(p.read_bytes() == raw for p, raw in sources.items()))
