import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from retrieval_fixture import CLAIM, ROUTE, SOURCE_WORK, WORK, make_fixture

from knot.access import AccessScope
from knot.entity_labels import apply_entity_labels
from knot.rdf import DERIVED, VOCAB, one
from knot.retrieval import Policy, _prepare, lookup, retrieve
from knot.review import fingerprint


class EntityLabelTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        make_fixture(self.root)
        self.prepared = _prepare(self.root)
        store = self.prepared[0]
        evidence = one(store, ROUTE, DERIVED).value
        revision = one(store, evidence, VOCAB + 'revision').value
        sha = one(store, revision, VOCAB + 'sha256').value
        self.source = {
            'revision': revision,
            'sha256': sha,
            'text_sha256': sha,
            'quote': 'Recovery belongs to Orion.',
            'character_offset': 0,
            'start_line': 1,
        }
        self.profile = {
            'entity': WORK,
            'preferred_label': 'Orion recovery work',
            'aliases': ['Recovery activity'],
            'agent': 'Test',
            'reason': 'Make the existing work label independently understandable.',
            'sources': [self.source],
        }

    def write_profiles(self, profiles=None):
        path = self.root / 'curation/entity-labels.json'
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps({'schema_version': 1, 'profiles': profiles or [self.profile]}))

    def test_preferred_name_retains_original_labels_and_does_not_mutate_records(self):
        self.write_profiles()
        store, _, records, labels = self.prepared
        before = copy.deepcopy((records, labels))
        review_before = fingerprint(store, CLAIM)
        changed, names = apply_entity_labels(self.root, store, records, labels)
        subjects = [r['subject'] for r in changed if r['subject']['id'] == WORK]
        self.assertTrue(subjects)
        self.assertTrue(all(s['label'] == 'Orion recovery work' for s in subjects))
        self.assertTrue(all(s['original_label'] for s in subjects))
        self.assertIn('Recovery', names[WORK])
        self.assertIn('Recovery activity', names[WORK])
        self.assertIn('Orion recovery work', names[WORK])
        self.assertEqual((records, labels), before)
        self.assertEqual(fingerprint(store, CLAIM), review_before)

    def test_lookup_and_retrieval_use_preference_without_losing_source_names(self):
        self.write_profiles()
        found = lookup(self.root, 'Recovery activity')['candidates']
        self.assertEqual(found[0]['id'], WORK)
        self.assertIn('Recovery', found[0]['labels'])
        result = retrieve(self.root, WORK, Policy(max_chars=16000))
        self.assertEqual(result['entities'][WORK]['preferred_label'], 'Orion recovery work')
        self.assertIn('Recovery', result['entities'][WORK]['labels'])
        self.assertEqual(result['assertions'][CLAIM]['status'], 'Accepted')

    def test_denied_profile_neither_reads_sources_nor_changes_visible_output(self):
        scope = AccessScope(revisions=((self.source['revision'], self.source['sha256']),))
        before = lookup(self.root, 'Recovery', scope=scope)
        self.profile['sources'].append(
            {**self.source, 'revision': 'urn:revision:secret', 'sha256': 'a' * 64}
        )
        self.profile['preferred_label'] = 'Secret project name'
        self.write_profiles()
        with patch('knot.entity_labels._validate_sources') as validate:
            self.assertEqual(lookup(self.root, 'Recovery', scope=scope), before)
            self.assertFalse(lookup(self.root, 'Secret', scope=scope)['candidates'])
            validate.assert_not_called()

    def test_matching_grants_allow_overlay_and_wrong_hash_does_not(self):
        self.write_profiles()
        scope = AccessScope(revisions=((self.source['revision'], self.source['sha256']),))
        self.assertEqual(
            lookup(self.root, 'Recovery activity', scope=scope)['candidates'][0]['id'], WORK
        )
        store, _, records, labels = self.prepared
        wrong = AccessScope(revisions=((self.source['revision'], 'a' * 64),))
        with patch('knot.entity_labels._validate_sources') as validate:
            changed, names = apply_entity_labels(self.root, store, records, labels, scope=wrong)
            self.assertEqual(changed, records)
            self.assertEqual(names, labels)
            validate.assert_not_called()

    def test_exact_note_read_retains_permitted_overlay_provenance_only(self):
        from knot.notes import create_note, save_note
        from knot.rdf import values

        target = create_note(self.root, 'Earlier recovery decision.', entities=[WORK])
        save_note(self.root, target['note'], 'Later decision.', expected=target['revision'])
        evidence = create_note(self.root, 'Orion recovery work is the specific name.')
        self.profile['sources'] = [
            {
                'revision': evidence['revision'],
                'sha256': evidence['body_sha256'],
                'text_sha256': evidence['body_sha256'],
                'quote': evidence['body'],
                'character_offset': 0,
                'start_line': 1,
            }
        ]
        self.write_profiles()
        for scope in (
            None,
            AccessScope(
                revisions=tuple((n['revision'], n['body_sha256']) for n in (target, evidence))
            ),
        ):
            with self.subTest(scope=scope):
                result = retrieve(
                    self.root,
                    target['note'],
                    Policy(max_chars=24000),
                    scope=scope,
                    note_revision=target['revision'],
                )
                self.assertEqual(
                    {s['revision'] for s in result['sources'].values()}, {target['revision']}
                )
                store, _, _, labels = _prepare(
                    self.root, scope=scope, note_revision=target['revision']
                )
                self.assertIn('Orion recovery work', labels[WORK])
                self.assertEqual(
                    one(store, evidence['revision'], VOCAB + 'nativeTextEligible').value, 'false'
                )
        denied = AccessScope(revisions=((target['revision'], target['body_sha256']),))
        with patch('knot.entity_labels._validate_sources') as validate:
            store, _, _, labels = _prepare(
                self.root, scope=denied, note_revision=target['revision']
            )
            validate.assert_not_called()
            self.assertNotIn('Orion recovery work', labels[WORK])
            self.assertFalse(values(store, evidence['revision'], VOCAB + 'noteMetadata'))

    def test_duplicate_profiles_and_empty_names_are_rejected(self):
        self.write_profiles([self.profile, self.profile])
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            apply_entity_labels(self.root, self.prepared[0], self.prepared[2], self.prepared[3])
        self.profile['preferred_label'] = ' '
        self.write_profiles()
        with self.assertRaisesRegex(ValueError, 'label'):
            lookup(self.root, 'Recovery')

    def test_shared_preferred_names_keep_distinct_identities_ambiguous(self):
        other = {**self.profile, 'entity': 'urn:project:orion'}
        self.write_profiles([self.profile, other])
        candidates = lookup(self.root, 'Orion recovery work')['candidates']
        self.assertEqual({c['id'] for c in candidates}, {WORK, 'urn:project:orion'})

    def test_changed_citation_is_rejected_and_no_new_identity_is_manufactured(self):
        self.profile['sources'][0]['quote'] = 'Unsupported replacement quotation'
        self.write_profiles()
        with self.assertRaises(ValueError):
            lookup(self.root, 'Recovery')
        self.profile['entity'] = 'urn:entity:unknown'
        self.write_profiles()
        with patch('knot.entity_labels._validate_sources') as validate:
            self.assertFalse(lookup(self.root, 'Recovery activity')['candidates'])
            validate.assert_not_called()

    def test_accepted_source_profile_names_follow_identity_without_overriding_canonical_name(self):
        old = {
            **self.profile,
            'entity': SOURCE_WORK,
            'preferred_label': 'Earlier recovery name',
            'aliases': ['Historic recovery shorthand'],
        }
        self.write_profiles([old, self.profile])
        result = lookup(self.root, 'Historic recovery shorthand')
        self.assertEqual([c['id'] for c in result['candidates']], [WORK])
        result = retrieve(self.root, WORK, Policy(max_chars=16000))
        self.assertEqual(
            result['entities'][WORK]['preferred_label'], self.profile['preferred_label']
        )
        self.assertIn('Earlier recovery name', result['entities'][WORK]['labels'])

    def test_denied_accepted_source_profile_aliases_remain_hidden(self):
        self.profile['entity'] = SOURCE_WORK
        self.profile['sources'].append({**self.source, 'revision': 'urn:revision:secret'})
        self.write_profiles()
        scope = AccessScope(revisions=((self.source['revision'], self.source['sha256']),))
        with patch('knot.entity_labels._validate_sources') as validate:
            self.assertFalse(lookup(self.root, 'Recovery activity', scope=scope)['candidates'])
            validate.assert_not_called()


if __name__ == '__main__':
    unittest.main()
