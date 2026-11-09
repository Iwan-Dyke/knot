import json
import subprocess
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from pyoxigraph import Literal, NamedNode, Quad, RdfFormat, Store
from retrieval_fixture import CLAIM, CLAIM_SOURCE, ROUTE, SEED, SOURCE_WORK, WORK, make_fixture

from knot.inventory import digest
from knot.rdf import DERIVED, LABEL, META, VOCAB, one
from knot.retrieval import Policy, lookup, retrieve, serialise
from knot.review import decide


class RetrievalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.dataset = make_fixture(self.root)
        self.policy = Policy(max_chars=30000)

    def retrieve(self, seed=SEED, **changes):
        return retrieve(self.root, seed, replace(self.policy, **changes))

    def edit(self, change):
        path = self.root / 'graph/claims.trig'
        store = Store()
        store.load(path=path, format=RdfFormat.TRIG)
        change(store)
        path.write_bytes(store.dump(format=RdfFormat.TRIG))

    def clone(self, aid, new_id, *, subject=None, obj=None):
        def change(store):
            triple = next(store.quads_for_pattern(None, None, None, NamedNode(aid)))
            store.add(
                Quad(
                    NamedNode(subject) if subject else triple.subject,
                    triple.predicate,
                    NamedNode(obj) if obj else triple.object,
                    NamedNode(new_id),
                )
            )
            for quad in list(store.quads_for_pattern(NamedNode(aid), None, None, META)):
                store.add(Quad(NamedNode(new_id), quad.predicate, quad.object, META))

        self.edit(change)

    def test_two_hop_path_retains_source_identity_direction_and_state(self):
        result = self.retrieve()
        self.assertEqual(set(result['assertions']), {ROUTE, CLAIM})
        path = next(p for p in result['paths'] if len(p) == 2)
        self.assertEqual(
            path,
            [
                {'assertion': ROUTE, 'direction': 'incoming'},
                {'assertion': CLAIM, 'direction': 'outgoing'},
            ],
        )
        claim = result['assertions'][CLAIM]
        self.assertEqual(claim['subject'], WORK)
        self.assertEqual(claim['source_subject'], CLAIM_SOURCE)
        self.assertEqual(claim['status'], 'Accepted')
        self.assertEqual(claim['kind'], 'Thought')
        self.assertEqual(result['assertions'][ROUTE]['status'], 'Unreviewed')
        self.assertEqual(result['identities']['urn:mapping:recovery']['reviewer'], None)
        self.assertEqual(
            result['sources'][next(iter(claim['sources']))]['citation_status'], 'Verified'
        )

    def test_unreviewed_identity_cannot_join_different_source_mentions(self):
        def withdraw(store):
            mid = NamedNode('urn:mapping:dependency')
            predicate = NamedNode('urn:knot:vocab:reviewStatus')
            store.remove(Quad(mid, predicate, NamedNode(VOCAB + 'Accepted'), META))
            store.add(Quad(mid, predicate, NamedNode(VOCAB + 'Unreviewed'), META))

        self.edit(withdraw)
        result = self.retrieve()
        self.assertIn(ROUTE, result['assertions'])
        self.assertNotIn(CLAIM, result['assertions'])

    def test_accepted_only_checks_every_hop_and_replays_reviews(self):
        self.assertFalse(self.retrieve(accepted_only=True)['paths'])
        decide(self.root, ROUTE, 'accept', reviewer='Test', reason='Checked source')
        self.assertIn(CLAIM, self.retrieve(accepted_only=True)['assertions'])
        decide(self.root, ROUTE, 'reject', reviewer='Test', reason='Withdraw routing')
        self.assertFalse(self.retrieve()['paths'])

    def test_correction_removes_original_route_and_does_not_accept_replacement(self):
        decide(
            self.root,
            ROUTE,
            'correct',
            reviewer='Test',
            reason='Wrong project',
            replacement={
                'subject': SOURCE_WORK,
                'predicate': 'urn:knot:vocab:relatedTo',
                'object': 'urn:project:other',
                'subject_label': 'Recovery',
                'object_label': 'Orion telescope',
                'rationale': 'Corrected project',
            },
        )
        self.assertFalse(self.retrieve()['paths'])

    def test_actor_free_decision_is_retrievable_from_its_subject_without_inventing_a_chooser(self):
        old = 'urn:assertion:distractor'
        event = decide(
            self.root,
            old,
            'correct',
            reviewer='Test',
            reason='The source identifies context, not an actor.',
            replacement={
                'subject': 'urn:decision:budget',
                'predicate': VOCAB + 'decisionAbout',
                'object': 'urn:project:other',
                'subject_label': 'Budget decision',
                'object_label': 'Telescope',
                'rationale': 'Decision context; deciding actor is unknown.',
            },
        )
        result = self.retrieve('urn:project:other')
        claim = result['assertions'][event['replacement_id']]
        self.assertEqual(claim['predicate'], VOCAB + 'decisionAbout')
        self.assertEqual(claim['status'], 'Unreviewed')
        self.assertEqual(claim['subject'], 'urn:decision:budget')
        self.assertNotIn(old, result['assertions'])
        self.assertFalse(
            any(a['predicate'] == VOCAB + 'madeDecision' for a in result['assertions'].values())
        )
        self.assertFalse(self.retrieve('urn:project:other', accepted_only=True)['assertions'])

    def test_lookup_returns_ambiguity_and_confirmed_aliases_without_merging(self):
        candidates = lookup(self.root, 'Orion')['candidates']
        self.assertEqual([c['id'] for c in candidates], ['urn:project:orion', 'urn:project:other'])
        self.assertEqual(lookup(self.root, 'Recovery')['candidates'][0]['id'], WORK)
        self.assertTrue(lookup(self.root, 'Orion', limit=1)['truncated'])
        self.assertEqual(lookup(self.root, 'recover')['candidates'][0]['match'], 'lexical')
        with self.assertRaisesRegex(ValueError, 'canonical IRI'):
            self.retrieve('Orion')
        with self.assertRaisesRegex(ValueError, 'canonical IRI'):
            self.retrieve(SOURCE_WORK)

    def test_author_theme_and_framework_metadata_cannot_route(self):
        self.assertNotIn('urn:project:other', self.retrieve()['entities'])
        result = self.retrieve(incoming=('relatedTo', 'workedOn'))
        self.assertNotIn('urn:assertion:other-work', result['assertions'])
        self.assertGreater(result['omissions']['hubs'], 0)
        self.assertFalse(self.retrieve('urn:competency:review')['assertions'])
        framework = self.retrieve('urn:competency:review', include_frameworks=True)
        self.assertIn('urn:assertion:framework', framework['assertions'])
        literal = framework['assertions']['urn:assertion:framework']
        self.assertTrue(literal['object_literal'])

    def test_missing_changed_and_unsafe_citations_cannot_route(self):
        for content in (None, 'changed'):
            with self.subTest(content=content):
                path = self.root / 'sources/association.md'
                if content is None:
                    path.unlink()
                else:
                    path.write_text(content)
                result = self.retrieve()
                self.assertFalse(result['paths'])
                self.assertEqual(result['omissions']['invalid_citations'], 1)
        self.assertTrue(result['omissions']['further_unknown'])

    def test_complete_serialised_budget_and_determinism(self):
        result = self.retrieve()
        text = serialise(result)
        self.assertEqual(result['usage']['characters'], len(text))
        self.assertEqual(result['usage']['utf8_bytes'], len(text.encode()))
        self.assertEqual(text, serialise(self.retrieve()))
        self.assertLessEqual(len(serialise(self.retrieve(max_chars=4000))), 4000)
        budget = len(text)
        budget = len(serialise(self.retrieve(max_chars=budget)))
        self.assertEqual(set(self.retrieve(max_chars=budget)['assertions']), {ROUTE, CLAIM})
        smaller = self.retrieve(max_chars=budget - 1)
        self.assertLessEqual(len(serialise(smaller)), budget - 1)
        self.assertNotEqual(set(smaller['assertions']), {ROUTE, CLAIM})
        with self.assertRaisesRegex(ValueError, 'envelope'):
            self.retrieve(max_chars=10)

    def test_frontier_degree_and_high_degree_seed_limits(self):
        self.clone(ROUTE, 'urn:assertion:association2', subject='urn:work:second')
        self.clone(CLAIM, 'urn:assertion:dependency2', subject='urn:work:second')
        degree = self.retrieve(max_degree=1)
        self.assertEqual(degree['omissions']['limits']['degree'], 1)
        self.assertNotIn('urn:assertion:association2', degree['assertions'])
        frontier = self.retrieve(max_frontier=1)
        self.assertEqual(frontier['usage']['frontier_peak'], 1)
        self.assertGreater(frontier['omissions']['limits']['frontier'], 0)
        hub = self.retrieve(hub_degree=1, seed_hub_degree=1)
        self.assertEqual(hub['usage']['expanded'], 1)
        self.assertGreater(hub['omissions']['hubs'], 0)
        self.assertTrue(hub['omissions']['further_unknown'])

    def test_dependency_precedes_navigation_with_a_single_passage_budget(self):
        self.clone(ROUTE, 'urn:assertion:navigation', subject='urn:work:neighbour', obj=WORK)
        result = self.retrieve(WORK, max_passages=1)
        self.assertIn(CLAIM, result['assertions'])
        self.assertNotIn('urn:assertion:navigation', result['assertions'])

    def test_person_seed_is_allowed_with_stricter_degree_cap(self):
        result = self.retrieve('urn:person:alex', seed_hub_degree=1)
        self.assertEqual(result['omissions']['limits']['degree'], 1)
        self.assertIn('urn:assertion:author', result['assertions'])

    def test_cyclic_route_is_finite_and_complete(self):
        self.clone(CLAIM, 'urn:assertion:cycle', obj=SEED)
        result = self.retrieve(max_depth=20)
        self.assertEqual(result['usage']['expanded'], 2)
        self.assertIn('urn:assertion:cycle', result['assertions'])
        self.assertGreater(result['omissions']['alternate_routes'], 0)

    def test_literal_labels_are_not_seed_entities(self):
        self.assertFalse(lookup(self.root, 'Review evidence')['candidates'])
        with self.assertRaisesRegex(ValueError, 'canonical IRI'):
            self.retrieve('Review evidence carefully.')

    def test_unicode_and_oversized_evidence_are_counted_without_clipping(self):
        self.edit(
            lambda s: s.add(Quad(NamedNode(SEED), NamedNode(LABEL), Literal('Orion λ 🔎'), META))
        )
        result = self.retrieve()
        self.assertGreater(result['usage']['utf8_bytes'], result['usage']['characters'])
        for budget in (1500, 2000, 3000, 4000):
            limited = self.retrieve(max_chars=budget)
            self.assertLessEqual(len(serialise(limited)), budget)
            self.assertTrue(
                all(q in result['passages'].values() for q in limited['passages'].values())
            )

    def test_unsafe_snapshot_and_wrong_quote_locator_are_reported(self):
        def unsafe(store):
            rev = one(store, ROUTE + ':evidence', VOCAB + 'revision')
            old = one(store, rev.value, VOCAB + 'snapshotPath')
            store.remove(Quad(rev, NamedNode(VOCAB + 'snapshotPath'), old, META))
            store.add(Quad(rev, NamedNode(VOCAB + 'snapshotPath'), Literal('../outside.md'), META))

        self.edit(unsafe)
        self.assertEqual(self.retrieve()['omissions']['citation_errors'], {'UnsafePath': 1})

    def test_changed_quote_locator_is_reported(self):
        def wrong_offset(store):
            eid = NamedNode(ROUTE + ':evidence')
            old = one(store, eid.value, VOCAB + 'characterOffset')
            store.remove(Quad(eid, NamedNode(VOCAB + 'characterOffset'), old, META))
            store.add(Quad(eid, NamedNode(VOCAB + 'characterOffset'), Literal(1), META))

        self.edit(wrong_offset)
        self.assertEqual(self.retrieve()['omissions']['citation_errors'], {'ChangedLocator': 1})

    def test_extracted_text_requires_its_recorded_hash(self):
        original = (self.root / 'sources/association.md').read_text()
        (self.root / 'sources/container.bin').write_bytes(b'original container')
        (self.root / 'sources/extracted.txt').write_text(original)
        (self.root / 'migration').mkdir()
        ledger = self.root / 'migration/conversion.json'
        ledger.write_text(
            json.dumps({'outputs': {'sources/extracted.txt': digest(original.encode())}})
        )

        def derived(store):
            revision = one(store, ROUTE + ':evidence', VOCAB + 'revision')
            for key, value in [
                ('snapshotPath', 'sources/container.bin'),
                ('sha256', digest(b'original container')),
            ]:
                old = one(store, revision.value, VOCAB + key)
                store.remove(Quad(revision, NamedNode(VOCAB + key), old, META))
                store.add(Quad(revision, NamedNode(VOCAB + key), Literal(value), META))
            store.add(
                Quad(
                    revision, NamedNode(VOCAB + 'textPath'), Literal('sources/extracted.txt'), META
                )
            )

        self.edit(derived)
        result = self.retrieve()
        self.assertEqual(result['sources'][ROUTE + ':evidence']['verification'], 'ExtractedText')
        (self.root / 'sources/extracted.txt').write_text('changed')
        self.assertEqual(self.retrieve()['omissions']['citation_errors'], {'ChangedFile': 1})
        ledger.write_text('{"outputs": {}}')
        self.assertEqual(self.retrieve()['omissions']['citation_errors'], {'MissingHash': 1})

    def test_empty_result_envelope_has_an_exact_minimum_budget(self):
        budget = len(serialise(self.retrieve(accepted_only=True)))
        budget = len(serialise(self.retrieve(accepted_only=True, max_chars=budget)))
        result = self.retrieve(accepted_only=True, max_chars=budget)
        self.assertEqual(len(serialise(result)), budget)
        with self.assertRaisesRegex(ValueError, 'envelope'):
            self.retrieve(accepted_only=True, max_chars=budget - 1)

    def test_retrieval_does_not_write_data_or_promote_inference(self):
        def inferred(store):
            aid = NamedNode(CLAIM)
            key = NamedNode(VOCAB + 'origin')
            store.remove(Quad(aid, key, NamedNode(VOCAB + 'Explicit'), META))
            store.add(Quad(aid, key, NamedNode(VOCAB + 'Inferred'), META))

        self.edit(inferred)
        before = {
            p.relative_to(self.root): p.read_bytes() for p in self.root.rglob('*') if p.is_file()
        }
        result = self.retrieve()
        self.assertEqual(result['assertions'][CLAIM]['origin'], 'Inferred')
        self.assertEqual(result['assertions'][CLAIM]['status'], 'Accepted')
        lookup(self.root, 'Orion')
        after = {
            p.relative_to(self.root): p.read_bytes() for p in self.root.rglob('*') if p.is_file()
        }
        self.assertEqual(before, after)

    def test_duplicate_occurrences_and_revisions_retain_sources_and_share_quote(self):
        quote = 'The survey feed is missing.'
        second = '# Orion recovery, revised\n' + quote + '\n'
        (self.root / 'sources/revised.md').write_text(second)

        def duplicate(store):
            evidence = NamedNode(CLAIM + ':second-evidence')
            revision = NamedNode('urn:revision:second')
            first = one(store, CLAIM + ':evidence', VOCAB + 'revision')
            store.add(Quad(NamedNode(CLAIM), NamedNode(DERIVED), evidence, META))
            for subject, key, obj in [
                (evidence, 'revision', revision),
                (evidence, 'quote', Literal(quote)),
                (revision, 'snapshotPath', Literal('sources/revised.md')),
                (revision, 'sha256', Literal(digest(second.encode()))),
                (NamedNode('urn:document:dependency.md'), 'revision', revision),
            ]:
                store.add(Quad(subject, NamedNode(VOCAB + key), obj, META))
            for index in range(2):
                occurrence = NamedNode('urn:occurrence:' + str(index))
                store.add(Quad(occurrence, NamedNode(VOCAB + 'revision'), first, META))
                store.add(
                    Quad(
                        occurrence, NamedNode(VOCAB + 'archive'), Literal(str(index) + '.zip'), META
                    )
                )

        self.edit(duplicate)
        result = self.retrieve()
        self.assertEqual(len(result['passages']), 2)
        citations = [result['sources'][e] for e in result['assertions'][CLAIM]['sources']]
        self.assertEqual(len({c['revision'] for c in citations}), 2)
        self.assertTrue(all(c['documents'] == ['urn:document:dependency.md'] for c in citations))
        self.assertEqual(max(len(c['occurrences']) for c in citations), 2)
        self.assertTrue(all(c['independence'] == 'Unknown' for c in citations))

    def test_overlapping_images_verify_transcriptions_without_inventing_independence(self):
        quote = 'The survey feed is missing.'
        for index in range(2):
            (self.root / f'sources/image{index}.jpg').write_bytes(b'photo' + bytes([index]))
            (self.root / f'sources/image{index}.txt').write_text(quote)

        def images(store):
            aid = NamedNode(CLAIM)
            for old in list(store.quads_for_pattern(aid, NamedNode(DERIVED), None, META)):
                store.remove(old)
            for index in range(2):
                revision = NamedNode(f'urn:revision:image{index}')
                eid = NamedNode(f'urn:evidence:image{index}')
                store.add(Quad(aid, NamedNode(DERIVED), eid, META))
                for subject, key, obj in [
                    (eid, 'revision', revision),
                    (eid, 'quote', Literal(quote)),
                    (revision, 'snapshotPath', Literal(f'sources/image{index}.jpg')),
                    (revision, 'sha256', Literal(digest(b'photo' + bytes([index])))),
                    (revision, 'transcriptionPath', Literal(f'sources/image{index}.txt')),
                    (revision, 'transcriptionSha256', Literal(digest(quote.encode()))),
                    (revision, 'sourceWeek', Literal('2026-W42')),
                ]:
                    store.add(Quad(subject, NamedNode(VOCAB + key), obj, META))

        self.edit(images)
        result = self.retrieve()
        self.assertEqual(len(result['passages']), 2)
        citations = [result['sources'][e] for e in result['assertions'][CLAIM]['sources']]
        self.assertEqual(len(citations), 2)
        self.assertTrue(all(c['verification'] == 'StoredTranscription' for c in citations))
        self.assertTrue(all(c['overlap_group'] == ['2026-W42'] for c in citations))
        (self.root / 'sources/image1.txt').write_text('changed')
        result = self.retrieve()
        self.assertNotIn(CLAIM, result['assertions'])
        self.assertEqual(result['omissions']['citation_errors'], {'ChangedFile': 1})

    def test_all_limits_are_enforced_without_orphaned_paths(self):
        for change in [
            dict(max_depth=1),
            dict(max_assertions=1),
            dict(max_passages=1),
            dict(max_expanded=1),
        ]:
            with self.subTest(change=change):
                result = self.retrieve(**change)
                self.assertNotIn(CLAIM, result['assertions'])
                self.assertTrue(result['omissions']['further_unknown'])
                for path in result['paths']:
                    self.assertTrue(all(step['assertion'] in result['assertions'] for step in path))
        for field in (
            'max_depth',
            'max_assertions',
            'max_passages',
            'max_expanded',
            'max_frontier',
            'max_degree',
            'hub_degree',
        ):
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.retrieve(**{field: 0})

    def test_cli_returns_the_same_bounded_json(self):
        process = subprocess.run(
            [
                '.venv/bin/python',
                '-m',
                'knot.retrieval',
                'get',
                SEED,
                '--data-root',
                str(self.root),
                '--max-chars',
                '30000',
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertEqual(process.stdout, serialise(self.retrieve()))
        self.assertEqual(json.loads(process.stdout)['seed'], SEED)

    def test_just_preserves_multiword_seed_and_data_path(self):
        root = self.root / 'dataset with spaces'
        root.mkdir()
        make_fixture(root)
        process = subprocess.run(
            ['just', 'retrieval', 'lookup', 'Orion telescope', '--data-root', str(root)],
            capture_output=True,
            text=True,
        )
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(json.loads(process.stdout), lookup(root, 'Orion telescope'))


if __name__ == '__main__':
    unittest.main()
