import json
import tempfile
import unittest
from pathlib import Path

from retrieval_fixture import CLAIM, ROUTE, SEED, make_fixture

from knot.access import AccessScope
from knot.inventory import digest
from knot.query import load_store
from knot.rdf import DERIVED, LABEL, RDF_TYPE, VOCAB, one, values
from knot.retrieval import Policy, lookup, retrieve, serialise
from knot.review import decide


class AccessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.dataset = make_fixture(self.root)
        store = load_store(self.root / 'graph')
        self.pins = {}
        for aid in (ROUTE, CLAIM):
            for eid in values(store, aid, DERIVED):
                revision = one(store, eid.value, VOCAB + 'revision').value
                self.pins[revision] = one(store, revision, VOCAB + 'sha256').value
        self.scope = AccessScope(revisions=tuple(sorted(self.pins.items())))
        self.policy = Policy(max_chars=30000)

    def test_default_denies_and_whole_dataset_requires_explicit_grant(self):
        self.assertFalse(lookup(self.root, 'Orion', scope=AccessScope())['candidates'])
        self.assertEqual(
            lookup(self.root, 'Orion', scope=AccessScope.all()), lookup(self.root, 'Orion')
        )
        with self.assertRaisesRegex(ValueError, 'canonical IRI'):
            retrieve(self.root, SEED, self.policy, scope=AccessScope())

    def test_scope_filters_before_traversal_ranking_and_source_scanning(self):
        result = retrieve(self.root, SEED, self.policy, scope=self.scope)
        self.assertEqual(set(result['assertions']), {ROUTE, CLAIM})
        self.assertEqual(result['omissions']['hubs'], 0)
        self.assertFalse(result['omissions']['further_unknown'])
        ranked = retrieve(
            self.root,
            SEED,
            self.policy,
            question='What Orion retries and dependencies are recorded?',
            mode='hybrid',
            scope=self.scope,
        )
        self.assertTrue(all(s['revision'] in self.pins for s in ranked['sources'].values()))
        self.assertEqual(ranked['usage']['source_revisions'], 2)
        self.assertNotIn('unlinked.md', serialise(ranked))
        self.assertEqual(ranked['assertions'][CLAIM]['kind'], 'Thought')

    def test_hidden_alias_and_entity_ids_do_not_leak_through_shared_canonical_node(self):
        self.dataset.add('urn:mention:hidden', LABEL, 'Secret project nickname', literal=True)
        self.dataset.add('urn:mapping:hidden', VOCAB + 'sourceEntity', 'urn:mention:hidden')
        self.dataset.add('urn:mapping:hidden', VOCAB + 'entity', SEED)
        self.dataset.add('urn:mapping:hidden', VOCAB + 'reviewStatus', VOCAB + 'Accepted')
        (self.root / 'graph/claims.trig').write_text(self.dataset.text())
        self.assertTrue(lookup(self.root, 'Secret project nickname')['candidates'])
        self.assertFalse(
            lookup(self.root, 'Secret project nickname', scope=self.scope)['candidates']
        )
        response = serialise(retrieve(self.root, SEED, self.policy, scope=self.scope))
        self.assertNotIn('Secret', response)
        self.assertNotIn('urn:mapping:hidden', response)
        self.assertNotIn('urn:project:other', response)

    def test_mixed_evidence_assertion_is_excluded_instead_of_partially_redacted(self):
        self.dataset.add(CLAIM, DERIVED, 'urn:assertion:unlinked:evidence')
        (self.root / 'graph/claims.trig').write_text(self.dataset.text())
        result = retrieve(self.root, SEED, self.policy, scope=self.scope)
        self.assertNotIn(CLAIM, result['assertions'])
        self.assertNotIn('unlinked.md', serialise(result))

    def test_review_replay_still_controls_accepted_only_paths(self):
        self.assertFalse(
            retrieve(self.root, SEED, self.policy, scope=self.scope)['assertions'][ROUTE]['status']
            == 'Accepted'
        )
        decide(self.root, ROUTE, 'accept', reviewer='Test', reason='Checked')
        result = retrieve(
            self.root, SEED, Policy(max_chars=30000, accepted_only=True), scope=self.scope
        )
        self.assertIn(CLAIM, result['assertions'])
        decide(self.root, ROUTE, 'reject', reviewer='Test', reason='Withdrawn')
        self.assertFalse(lookup(self.root, SEED, scope=self.scope)['candidates'])

    def test_scope_schema_and_hash_pins_fail_closed(self):
        path = self.root / 'scope.json'
        path.write_text(json.dumps({'revisions': self.pins}))
        self.assertEqual(AccessScope.from_file(path), self.scope)
        with self.assertRaises(ValueError):
            AccessScope(revisions=((next(iter(self.pins)), '0' * 64),)).apply(*self.prepared())
        path.write_text('{"themes": ["shared"]}')
        with self.assertRaises(ValueError):
            AccessScope.from_file(path)

    def test_granted_source_only_record_does_not_include_a_denied_document_revision(self):
        text = '# urn:project:orion\nMissing feed dependency remains unresolved.\n'
        (self.root / 'sources/granted.md').write_text(text)
        revision = 'urn:revision:granted'
        self.dataset.add(revision, VOCAB + 'snapshotPath', 'sources/granted.md', literal=True)
        self.dataset.add(revision, VOCAB + 'sha256', digest(text.encode()), literal=True)
        self.dataset.add('urn:document:shared', RDF_TYPE, VOCAB + 'Document')
        self.dataset.add('urn:document:shared', VOCAB + 'revision', revision)
        store = load_store(self.root / 'graph')
        other = one(store, 'urn:assertion:unlinked:evidence', VOCAB + 'revision').value
        self.dataset.add('urn:document:shared', VOCAB + 'revision', other)
        (self.root / 'graph/claims.trig').write_text(self.dataset.text())
        scope = AccessScope(
            revisions=tuple(sorted({**self.pins, revision: digest(text.encode())}.items()))
        )
        result = retrieve(
            self.root,
            SEED,
            self.policy,
            question='What unresolved feed dependencies threaten Orion?',
            mode='hybrid',
            scope=scope,
        )
        self.assertTrue(
            any(s['snapshot'] == 'sources/granted.md' for s in result['sources'].values())
        )
        self.assertNotIn('unlinked.md', serialise(result))
        self.assertNotIn(other, serialise(result))

    def test_hidden_neighbours_do_not_change_visible_degree_counts(self):
        ranked = retrieve(
            self.root,
            SEED,
            self.policy,
            scope=self.scope,
            question='What unresolved Orion feed dependencies are recorded?',
            mode='hybrid',
        )
        for index in range(30):
            aid = 'urn:hidden:' + str(index)
            self.dataset.add(
                'urn:hidden:entity:' + str(index), VOCAB + 'relatedTo', SEED, graph=aid
            )
            self.dataset.add(aid, RDF_TYPE, VOCAB + 'Assertion')
            self.dataset.add(aid, DERIVED, 'urn:assertion:unlinked:evidence')
            for key, value in [
                ('reviewStatus', 'Unreviewed'),
                ('origin', 'Explicit'),
                ('lifecycle', 'Active'),
            ]:
                self.dataset.add(aid, VOCAB + key, VOCAB + value)
            for key in ('subjectLabel', 'objectLabel', 'rationale'):
                self.dataset.add(aid, VOCAB + key, 'Hidden', literal=True)
        (self.root / 'graph/claims.trig').write_text(self.dataset.text())
        result = retrieve(self.root, SEED, self.policy, scope=self.scope)
        self.assertFalse(result['omissions']['limits'])
        self.assertEqual(set(result['assertions']), {ROUTE, CLAIM})
        after = retrieve(
            self.root,
            SEED,
            self.policy,
            scope=self.scope,
            question='What unresolved Orion feed dependencies are recorded?',
            mode='hybrid',
        )
        # Editing the dataset invalidates the global classification fingerprint;
        # compare the scoped ranking and evidence, independent of that status.
        for key in ('ranking', 'matches', 'passages', 'paths', 'source_context', 'omissions'):
            self.assertEqual(ranked[key], after[key])

    def prepared(self):
        from knot.retrieval import _prepare

        return _prepare(self.root)


if __name__ == '__main__':
    unittest.main()
