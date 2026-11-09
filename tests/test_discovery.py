import tempfile
import unittest
from pathlib import Path

from retrieval_fixture import CLAIM, ROUTE, SEED, make_fixture

from knot.access import AccessScope
from knot.discovery import discover, gather
from knot.discovery_score import DiscoveryQuestion
from knot.inventory import digest
from knot.notes import create_note, save_note
from knot.rdf import LABEL, META, VOCAB
from knot.retrieval import Policy, _Evidence, _prepare, retrieve, serialise
from knot.review import decide
from knot.search import Limits


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.dataset = make_fixture(self.root)
        self.policy = Policy(max_chars=24000)

    def source(self, name, text):
        path = 'sources/' + name + '.md'
        (self.root / path).write_text(text)
        revision = 'urn:revision:' + name
        self.dataset.add(revision, VOCAB + 'snapshotPath', path, literal=True)
        self.dataset.add(revision, VOCAB + 'sha256', digest(text.encode()), literal=True)
        return revision

    def save(self):
        (self.root / 'graph/claims.trig').write_text(self.dataset.text())

    def test_relevant_late_revision_is_selected_before_complete_load_cutoff(self):
        for i in range(5):
            self.source(f'aaa-{i}', '# Background\nUnrelated discussion.\n')
        revision = self.source('zzzz', '# Reading\nThermal bottlenecks constrain throughput.\n')
        self.save()
        result = retrieve(
            self.root,
            policy=self.policy,
            question='Thermal bottlenecks and throughput',
            mode='text',
            limits=Limits(max_source_revisions=1),
        )
        self.assertIn(revision, {s['revision'] for s in result['sources'].values()})
        self.assertLessEqual(result['usage']['source_revisions'], 1)

    def test_question_discovers_graph_subjects_and_unassociated_native_notes(self):
        note = create_note(self.root, '# Reflection\nA constraint limits useful throughput.\n')
        result = discover(
            self.root,
            'What constraint and missing survey feed affected useful work?',
            max_chars=7000,
        )
        ids = {c['id'] for c in result['candidates']}
        self.assertIn(SEED, ids)
        self.assertIn(note['note'], ids)
        self.assertEqual(
            {o['id'] for o in result['objectives']}, {'relationships', 'context', 'qualifications'}
        )
        self.assertLessEqual(len(serialise(result)), 7000)
        compact = discover(
            self.root, 'What constraint and missing survey feed affected useful work?'
        )
        self.assertLessEqual(len(serialise(compact)), 4000)
        self.assertEqual(len(serialise(result)), result['usage']['characters'])

    def test_sources_without_assertions_are_selectable_and_stay_source_only(self):
        revision = self.source(
            'zzzz',
            '# Investigation\nThermal drift remains unexplained.\nHowever, calibration is uncertain.\n',
        )
        self.save()
        result = discover(self.root, 'What thermal drift remains unexplained?')
        unit = next(
            c['id'] for c in result['candidates'] if c['id'].startswith(revision + '#knot-unit=')
        )
        evidence = gather(
            self.root, [unit], 'Read the selected account and its limitations.', self.policy
        )
        self.assertFalse(evidence['assertions'])
        self.assertIn('calibration is uncertain', ' '.join(evidence['passages'].values()))
        self.assertTrue(all(c['claim_review'] is None for c in evidence['source_context'].values()))

    def test_multiple_selected_subjects_share_budget_and_deduplicate_packages(self):
        note = create_note(self.root, '# Reading\nThe survey constraint remains uncertain.\n')
        result = gather(
            self.root,
            [SEED, note['note'], SEED],
            'What survey constraint remains uncertain?',
            self.policy,
        )
        self.assertIn(CLAIM, result['assertions'])
        self.assertEqual(len(result['subjects']), 2)
        self.assertLessEqual(len(serialise(result)), self.policy.max_chars)
        handles = [m['handle'] for m in result['matches']]
        self.assertEqual(len(handles), len(set(handles)))
        again = gather(
            self.root,
            [SEED, note['note']],
            'What survey constraint remains uncertain?',
            self.policy,
            exclude=handles,
        )
        self.assertFalse(set(handles) & {m['handle'] for m in again['matches']})

    def test_denied_notes_cannot_influence_discovery_or_sampling(self):
        visible = create_note(
            self.root, '# Reading\nA constraint limits throughput.\n', title='Visible'
        )
        scope = AccessScope(revisions=((visible['revision'], visible['body_sha256']),))
        before = discover(self.root, 'What constraint limits throughput?', scope=scope)
        hidden = create_note(
            self.root, visible['body'], title='Hidden alias', author='Hidden author'
        )
        (self.root / hidden['body_path']).write_text('corrupt shared snapshot')
        # Shared bytes are a genuine corruption of the granted note too. Restore
        # them, then corrupt only the denied manifest.
        (self.root / hidden['body_path']).write_text(visible['body'])
        manifest = self.root / 'notes/revisions' / (hidden['revision'].rsplit(':', 1)[1] + '.json')
        manifest.write_text('corrupt denied manifest')
        after = discover(self.root, 'What constraint limits throughput?', scope=scope)
        self.assertEqual(serialise(before), serialise(after))
        self.assertNotIn('Hidden', serialise(after))

    def test_review_replay_and_accepted_only_do_not_promote_original_text(self):
        decide(self.root, ROUTE, 'reject', reviewer='Test', reason='Wrong association')
        found = discover(self.root, 'What survey feed is missing?', accepted_only=True)
        for c in found['candidates']:
            self.assertTrue(all(s == 'Accepted' for s in c['review_statuses']))
        result = gather(
            self.root,
            [SEED],
            'What survey feed is missing?',
            Policy(max_chars=12000, accepted_only=True),
        )
        self.assertNotIn(ROUTE, result['assertions'])
        self.assertFalse(result['source_context'])

    def test_discovery_references_verify_exact_source_locations(self):
        result = discover(self.root, 'What survey feed is missing?')
        reader = _Evidence(self.root, _prepare(self.root)[0])
        for source in result['sources'].values():
            text, citation = reader.revision(source['revision'])
            loc = source['locator']
            quote = text[loc['character_offset'] : loc['character_offset'] + loc['length']]
            self.assertEqual(digest(quote.encode()), source['quote_sha256'])
            self.assertEqual(citation['text_sha256'], source['text_sha256'])

    def test_history_and_invalid_bounds_are_explicit(self):
        first = create_note(self.root, 'Earlier hypothesis about a constraint.')
        latest = save_note(
            self.root,
            first['note'],
            'Later correction: a different constraint.',
            expected=first['revision'],
        )
        found = discover(self.root, 'What constraint changed?')
        revisions = {s['revision'] for s in found['sources'].values()}
        self.assertNotIn(first['revision'], revisions)
        self.assertIn(latest['revision'], revisions)
        with self.assertRaises(ValueError):
            gather(self.root, ['unknown'], 'What changed?', self.policy)
        with self.assertRaises(ValueError):
            gather(self.root, [SEED] * 5, 'What changed?', self.policy)
        with self.assertRaises(ValueError):
            discover(self.root, 'What changed?', max_chars=10)

    def test_shared_work_limits_do_not_multiply_with_selected_subjects(self):
        note = create_note(self.root, 'A missing survey feed remains uncertain.')
        result = gather(
            self.root,
            [SEED, note['note']],
            'What survey feed is missing?',
            Policy(max_chars=16000, max_expanded=1),
            limits=Limits(max_source_revisions=1, max_source_sections=1, max_candidates=1),
        )
        self.assertLessEqual(result['usage']['expanded'], 1)
        self.assertLessEqual(result['usage']['source_revisions'], 1)
        self.assertLessEqual(result['usage']['revision_reads'], 1)
        self.assertLessEqual(result['usage']['candidates'], 1)
        self.assertEqual(result['omissions']['limits']['subjects'], 1)

    def test_sampling_is_byte_bounded_and_cannot_read_outside_dataset(self):
        revision = self.source('sample', 'A large sample.\n' * 5000)
        self.dataset.add(
            'urn:revision:unsafe', VOCAB + 'snapshotPath', '../outside.txt', literal=True
        )
        self.dataset.add('urn:revision:unsafe', VOCAB + 'sha256', 'a' * 64, literal=True)
        self.save()
        reader = _Evidence(self.root, _prepare(self.root)[0])
        for size in (1, 3, 8, 8192):
            _, used = reader.preview(revision, size)
            self.assertLessEqual(used, size)
        with self.assertRaisesRegex(ValueError, 'UnsafePath'):
            reader.preview('urn:revision:unsafe', 100)

    def test_matching_labels_do_not_merge_distinct_entities(self):
        for entity in (SEED, 'urn:project:other'):
            self.dataset.add(entity, LABEL, 'Shared name', literal=True)
        self.save()
        result = discover(
            self.root, 'What survey feed and budget constraints were recorded?', max_chars=12000
        )
        matching = {c['id'] for c in result['candidates'] if 'Shared name' in c['labels']}
        self.assertEqual(matching, {SEED, 'urn:project:other'})

    def test_excluding_a_context_match_preserves_required_qualifications(self):
        text = '# Orion\nThe survey feed is missing.\nHowever, the conclusion remains uncertain.\n'
        revision = self.source('qualified', text)
        self.dataset.graphs[META.value] = {
            line
            for line in self.dataset.graphs[META.value]
            if not line.startswith(
                (
                    f'<{CLAIM}:evidence> <{VOCAB}revision>',
                    f'<{CLAIM}:evidence> <{VOCAB}characterOffset>',
                )
            )
        }
        self.dataset.add(CLAIM + ':evidence', VOCAB + 'revision', revision)
        self.dataset.add(
            CLAIM + ':evidence',
            VOCAB + 'characterOffset',
            text.index('The survey feed is missing.'),
            literal=True,
        )
        self.save()
        first = gather(self.root, [SEED], 'What survey feed is missing?', self.policy)
        contexts = [m['handle'] for m in first['matches'] if m['channel'] == 'text']
        again = gather(
            self.root, [SEED], 'What survey feed is missing?', self.policy, exclude=contexts
        )
        self.assertIn(CLAIM, again['assertions'])
        self.assertIn('conclusion remains uncertain', ' '.join(again['passages'].values()))
        self.assertFalse(set(contexts) & {m['handle'] for m in again['matches']})

    def test_source_unit_selector_cannot_shorten_away_a_qualification(self):
        text = '# Account\nA useful result.\nHowever, acceptance is pending.\n'
        revision = self.source('unit', text)
        self.save()
        quote = 'A useful result.'
        forged = (
            revision
            + '#knot-unit='
            + str(text.index(quote))
            + ':'
            + str(len(quote))
            + ':'
            + digest(quote.encode())
        )
        with self.assertRaisesRegex(ValueError, 'UnknownSourceUnit'):
            gather(self.root, [forged], 'Read this source.', self.policy)

    def test_corrupt_evidence_never_becomes_a_discovery_reference(self):
        (self.root / 'sources/dependency.md').write_text('corrupt bytes')
        result = discover(self.root, 'What survey feed is missing?', max_chars=12000)
        self.assertGreater(result['omissions']['invalid_citations'], 0)
        self.assertFalse(
            any(s['text_path'].endswith('dependency.md') for s in result['sources'].values())
        )

    def test_objectives_filter_matches_and_repeated_requests_are_deterministic(self):
        note = create_note(
            self.root, '# Reflection\nA constraint matters. However, the outcome is uncertain.\n'
        )
        first = gather(
            self.root,
            [SEED, note['note']],
            'What constraint matters?',
            self.policy,
            objectives=['qualifications'],
        )
        second = gather(
            self.root,
            [SEED, note['note']],
            'What constraint matters?',
            self.policy,
            objectives=['qualifications'],
        )
        self.assertEqual(serialise(first), serialise(second))
        self.assertTrue(all(m['channel'] == 'text' for m in first['matches']))

    def test_discovery_cosine_uses_consistent_weights_for_unseen_metadata(self):
        scorer = DiscoveryQuestion('Ocean currents')
        scorer.fit(['Survey data.', 'Reading books.'])
        self.assertLessEqual(scorer.score('Ocean currents', labels='Observation')['score'], 1)

    def test_discovery_searches_native_titles_and_visible_entity_aliases(self):
        note = create_note(self.root, 'A short independent observation.', title='Thermal notebooks')
        self.dataset.add(SEED, LABEL, 'Orbital recovery', literal=True)
        self.save()
        found = discover(self.root, 'Thermal notebooks', max_chars=12000)
        self.assertIn(note['note'], {c['id'] for c in found['candidates']})
        found = discover(self.root, 'Orbital recovery', max_chars=12000)
        self.assertIn(SEED, {c['id'] for c in found['candidates']})
