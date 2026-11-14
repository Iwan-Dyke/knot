"""Scope-relative coverage must neither read nor describe denied evidence."""

import json
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import test_evaluation as fixture

from knot.curating.provenance import source_pin
from knot.evaluation import evaluate
from knot.graph.knowledge import build_organisation
from knot.graph.query import load_store
from knot.graph.rdf import VOCAB, one
from knot.interfaces.access import AccessScope
from knot.shared.storage import digest
from knot.writing.notes import create_note, save_note


class EvaluationScopeTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixture.CoverageTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root, self.request = self.fixture.root, self.fixture.request

    def scope(self, *revisions):
        store = load_store(self.root / 'graph', history=True, include_notes=False)
        return AccessScope(
            revisions=tuple((r, one(store, r, VOCAB + 'sha256').value) for r in revisions)
        )

    def complete_scope(self):
        return self.scope(fixture.REVISION, fixture.SUPPORT + ':revision')

    def test_visible_support_and_no_global_absence(self):
        result = evaluate(self.root, self.request, scope=self.complete_scope())
        self.assertEqual(self.fixture.states(result), ['support_found', 'unknown'])
        self.assertIn('scope_limited', result['criteria'][1]['reasons'])
        self.assertNotIn('input_files', result['manifest'])
        self.assertIn('view_sha256', result['manifest'])
        self.assertEqual(
            result['assertions'][fixture.SUPPORT]['attributed_to'], ['Synthetic curator']
        )
        for review in result['assertions'][fixture.SUPPORT]['reviews']:
            self.assertNotIn('previous', review)

    def test_denied_sources_are_not_read_or_returned(self):
        original = Path.read_bytes
        forbidden = self.root / ('sources/' + digest(fixture.SUPPORT.encode()) + '.txt')

        def guarded(path):
            if path == forbidden:
                self.fail('Denied body read')
            return original(path)

        with patch.object(Path, 'read_bytes', guarded):
            result = evaluate(self.root, self.request, scope=self.scope(fixture.REVISION))
        self.assertEqual(self.fixture.states(result), ['unknown', 'unknown'])
        encoded = json.dumps(result)
        self.assertNotIn(fixture.SUPPORT, encoded)
        self.assertNotIn(forbidden.name, encoded)
        self.assertNotIn('limited scope', encoded)

    def test_empty_scope_has_no_global_metadata(self):
        result = evaluate(self.root, self.request, scope=AccessScope())
        self.assertEqual(result['assertions'], {})
        self.assertEqual(self.fixture.states(result), ['unknown', 'unknown'])
        text = json.dumps(result)
        for secret in (
            'claims.trig',
            'reviews/events',
            'Synthetic reviewer',
            'Review changes carefully.',
        ):
            self.assertNotIn(secret, text)

    def test_hidden_changes_and_review_chain_do_not_change_receipt(self):
        scope = self.complete_scope()
        first = evaluate(self.root, self.request, scope=scope)
        aid = self.fixture.claim(
            'urn:example:hidden',
            'urn:example:secret-project',
            VOCAB + 'supports',
            fixture.CRITERIA[0],
            'Secret outcome',
        )
        self.fixture.save()
        self.fixture.accept(aid)
        hidden = create_note(self.root, 'Secret native body', title='Secret title')
        save_note(self.root, hidden['note'], 'Secret successor', expected=hidden['revision'])
        self.assertEqual(first, evaluate(self.root, self.request, scope=scope))

    def test_scope_revocation_recomputes_without_previous_witness(self):
        first = evaluate(self.root, self.request, scope=self.complete_scope())
        second = evaluate(self.root, self.request, scope=self.scope(fixture.REVISION))
        self.assertNotIn(fixture.SUPPORT, second['assertions'])
        self.assertNotEqual(first['receipt_sha256'], second['receipt_sha256'])

    def test_whole_dataset_scope_retains_bounded_absence(self):
        result = evaluate(self.root, self.request, scope=AccessScope.all())
        self.assertEqual(self.fixture.states(result), ['support_found', 'no_qualifying_support'])
        self.assertTrue(result['complete'])

    def test_grant_hash_mismatch_fails(self):
        with self.assertRaises(ValueError):
            evaluate(
                self.root,
                self.request,
                scope=AccessScope(revisions=((fixture.REVISION, '0' * 64),)),
            )

    def test_visible_change_during_evaluation_fails(self):
        from knot.evaluation.snapshot import Evidence

        citation = Evidence.citation
        changed = False

        def changing(reader, eid):
            nonlocal changed
            result = citation(reader, eid)
            if not changed:
                changed = True
                aid = self.fixture.claim(
                    'urn:example:new-visible',
                    fixture.PROJECT,
                    VOCAB + 'supports',
                    fixture.CRITERIA[1],
                    'Explain tradeoffs.',
                    revision=fixture.REVISION,
                )
                self.fixture.save()
                self.fixture.accept(aid)
            return result

        with (
            patch.object(Evidence, 'citation', changing),
            self.assertRaisesRegex(ValueError, 'Inputs changed'),
        ):
            evaluate(self.root, self.request, scope=self.complete_scope())

    def test_granted_native_witness_does_not_read_hidden_successor(self):
        quote = 'This is a qualified native assessment.'
        note = create_note(self.root, quote, author='Synthetic author')
        f = self.fixture
        f.data.add(note['revision'], VOCAB + 'snapshotPath', note['body_path'], literal=True)
        f.data.add(note['revision'], VOCAB + 'sha256', note['body_sha256'], literal=True)
        aid = f.claim(
            'urn:example:native-support',
            fixture.PROJECT,
            VOCAB + 'supports',
            fixture.CRITERIA[1],
            quote,
            revision=note['revision'],
        )
        f.save()
        f.accept(aid)
        scope = self.scope(fixture.REVISION, note['revision'])
        first = evaluate(self.root, self.request, scope=scope)
        successor = save_note(
            self.root,
            note['note'],
            'Hidden new body',
            expected=note['revision'],
            title='Hidden title',
        )
        original = Path.read_bytes
        denied = {
            self.root / successor['body_path'],
            self.root / 'notes/revisions' / (successor['revision'].rsplit(':', 1)[1] + '.json'),
        }

        def guarded(path):
            if path in denied:
                self.fail('Denied successor read')
            return original(path)

        with patch.object(Path, 'read_bytes', guarded):
            second = evaluate(self.root, self.request, scope=scope)
        self.assertEqual(first, second)
        self.assertEqual(second['criteria'][1]['outcome'], 'support_found')
        self.assertNotIn('Hidden title', json.dumps(second))

    def test_curated_witness_requires_all_ancestor_grants(self):
        f = self.fixture
        parent = create_note(self.root, 'An original account.')
        derived = create_note(
            self.root,
            'A derived assessment.',
            title='Derived',
            author='Codex',
            agent='Codex',
            derivation={
                'method': 'faithful_restatement',
                'qualification': 'Attributed interpretation.',
                'sources': [
                    {
                        'revision': parent['revision'],
                        'sha256': parent['body_sha256'],
                        'text_sha256': parent['body_sha256'],
                        'quote': 'An original account.',
                        'character_offset': 0,
                        'start_line': 1,
                    }
                ],
            },
        )
        f.data.add(derived['revision'], VOCAB + 'snapshotPath', derived['body_path'], literal=True)
        f.data.add(derived['revision'], VOCAB + 'sha256', derived['body_sha256'], literal=True)
        aid = f.claim(
            'urn:example:derived-support',
            fixture.PROJECT,
            VOCAB + 'supports',
            fixture.CRITERIA[1],
            'A derived assessment.',
            revision=derived['revision'],
        )
        f.save()
        f.accept(aid)
        partial = self.scope(fixture.REVISION, derived['revision'])
        original = Path.read_bytes

        def guarded(path):
            if path in {self.root / parent['body_path'], self.root / derived['body_path']}:
                self.fail('Body read without derivation closure')
            return original(path)

        with patch.object(Path, 'read_bytes', guarded):
            result = evaluate(self.root, self.request, scope=partial)
        self.assertNotIn(aid, json.dumps(result))
        allowed = AccessScope(
            revisions=partial.revisions + ((parent['revision'], parent['body_sha256']),)
        )
        self.assertEqual(
            evaluate(self.root, self.request, scope=allowed)['criteria'][1]['outcome'],
            'support_found',
        )

    def test_hidden_qualification_withholds_witness_until_all_pins_are_granted(self):
        f = self.fixture
        hidden = f.claim(
            'urn:example:account',
            'urn:example:other',
            VOCAB + 'supports',
            fixture.CRITERIA[0],
            'These accounts may overlap.',
        )
        f.save()
        f.accept(hidden)
        pins = [
            source_pin(
                self.root,
                fixture.SUPPORT + ':revision',
                'The reviewer considers this project supporting evidence, with limited scope.',
                0,
            ),
            source_pin(self.root, hidden + ':revision', 'These accounts may overlap.', 0),
        ]
        path = self.root / 'curation/evidence-accounts.json'
        path.parent.mkdir()
        path.write_text(
            json.dumps(
                {
                    'schema_version': 1,
                    'groups': [
                        {
                            'id': 'example-overlap',
                            'relationship': 'OverlapUnresolved',
                            'qualification': 'The two reports may describe the same work.',
                            'reviewer': 'Synthetic reviewer',
                            'assertions': [fixture.SUPPORT, hidden],
                            'sources': pins,
                        }
                    ],
                }
            )
        )
        original = Path.read_bytes
        denied = self.root / ('sources/' + digest(hidden.encode()) + '.txt')

        def guarded(path):
            if path == denied:
                self.fail('Denied qualification source read')
            return original(path)

        with patch.object(Path, 'read_bytes', guarded):
            partial = evaluate(self.root, self.request, scope=self.complete_scope())
        self.assertNotIn(fixture.SUPPORT, json.dumps(partial))
        self.assertNotIn('example-overlap', json.dumps(partial))
        full_scope = self.scope(
            fixture.REVISION, fixture.SUPPORT + ':revision', hidden + ':revision'
        )
        full = evaluate(self.root, self.request, scope=full_scope)
        premise = full['assertions'][fixture.SUPPORT]
        self.assertEqual(full['criteria'][0]['outcome'], 'support_found')
        self.assertIn('same work', premise['evidence_accounts'][0]['qualification'])
        self.assertEqual(premise['evidence_account_sources'][1]['quote'], pins[1]['quote'])
        limited = evaluate(self.root, replace(self.request, max_sources=2), scope=full_scope)
        self.assertIn('source_budget', limited['reasons'])
        self.assertTrue(all(row['outcome'] == 'unknown' for row in limited['criteria']))

    def test_unrelated_changes_do_not_promote_classified_thought_in_any_access_mode(self):
        store = load_store(self.root / 'graph', history=True, include_notes=False)
        organisation = build_organisation(
            store,
            {
                'themes': [],
                'overrides': {fixture.SUPPORT: {'kind': 'Thought'}},
            },
        )
        (self.root / 'graph/organisation.trig').write_bytes(organisation)
        scoped = evaluate(self.root, self.request, scope=self.complete_scope())
        self.assertNotIn(fixture.SUPPORT, scoped['assertions'])
        hidden = self.fixture.claim(
            'urn:example:hidden-kind',
            'urn:example:other',
            VOCAB + 'supports',
            fixture.CRITERIA[1],
            'Unrelated assertion.',
        )
        self.fixture.save()
        self.fixture.accept(hidden)
        self.assertEqual(scoped, evaluate(self.root, self.request, scope=self.complete_scope()))
        for scope in (None, AccessScope.all()):
            with self.subTest(scope=scope):
                result = evaluate(self.root, self.request, scope=scope)
                self.assertNotIn(fixture.SUPPORT, result['assertions'])
                self.assertEqual(result['excluded_assertions'][fixture.SUPPORT]['kind'], 'Thought')

    def test_scoped_source_mutation_fails_before_returning_receipt(self):
        from knot.evaluation.snapshot import Evidence

        citation = Evidence.citation

        def changing(reader, eid):
            result = citation(reader, eid)
            if eid == fixture.SUPPORT + ':evidence':
                (self.root / result[1]['snapshot']).write_text('Changed after verification')
            return result

        with patch.object(Evidence, 'citation', changing):
            with self.assertRaisesRegex(ValueError, 'Inputs changed'):
                evaluate(self.root, self.request, scope=self.complete_scope())


if __name__ == '__main__':
    unittest.main()
