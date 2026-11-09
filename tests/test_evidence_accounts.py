import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pyoxigraph import Literal, NamedNode, Quad

from knot.access import AccessScope
from knot.evidence_accounts import annotate_accounts
from knot.inventory import digest
from knot.knowledge import entries
from knot.query import load_store
from knot.rdf import DERIVED, META, RDF_TYPE, VOCAB, Dataset
from knot.retrieval import Policy, _Evidence, retrieve
from knot.review import fingerprint
from knot.search import _packages

FIRST, SECOND, OTHER = 'urn:assertion:first', 'urn:assertion:second', 'urn:assertion:other'


class EvidenceAccountTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'graph').mkdir()
        (self.root / 'sources').mkdir()
        data = Dataset()
        self.pins = {}
        quote = 'Alex used Orion.'
        for aid, heading in ((FIRST, 'First account'), (SECOND, 'Retelling'), (OTHER, 'Unrelated')):
            text = f'# {heading}\n{quote}\n{quote}\n'
            sha = digest(text.encode())
            revision, evidence = 'urn:revision:' + sha, aid + ':evidence'
            path = 'sources/' + sha + '.txt'
            (self.root / path).write_text(text)
            data.add('urn:person:alex', VOCAB + 'used', 'urn:tool:orion', graph=aid)
            data.add(aid, RDF_TYPE, VOCAB + 'Assertion')
            for field, value in (
                ('reviewStatus', 'Unreviewed' if aid == SECOND else 'Accepted'),
                ('lifecycle', 'Active'),
                ('origin', 'Explicit'),
            ):
                data.add(aid, VOCAB + field, VOCAB + value)
            for field, value in (
                ('subjectLabel', 'Alex'),
                ('objectLabel', 'Orion'),
                ('rationale', 'Reported use'),
            ):
                data.add(aid, VOCAB + field, value, literal=True)
            data.add(aid, DERIVED, evidence)
            data.add(evidence, VOCAB + 'revision', revision)
            data.add(evidence, VOCAB + 'quote', quote, literal=True)
            data.add(evidence, VOCAB + 'characterOffset', text.index(quote), literal=True)
            data.add(revision, VOCAB + 'snapshotPath', path, literal=True)
            data.add(revision, VOCAB + 'sha256', sha, literal=True)
            self.pins[aid] = {
                'revision': revision,
                'sha256': sha,
                'text_sha256': sha,
                'quote': text,
                'character_offset': 0,
                'start_line': 1,
            }
        (self.root / 'graph/claims.trig').write_text(data.text())
        self.store = load_store(self.root / 'graph')
        self.records = entries(self.store)
        self.group = {
            'id': 'account-1',
            'assertions': [FIRST, SECOND],
            'relationship': 'RepeatedAccount',
            'qualification': 'Two retellings of a reported use; no independent corroboration.',
            'reviewer': 'Test reviewer',
            'sources': [self.pins[FIRST], self.pins[SECOND]],
        }

    def write_groups(self, groups=None):
        path = self.root / 'curation/evidence-accounts.json'
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps({'schema_version': 1, 'groups': groups or [self.group]}))

    def test_graph_and_hybrid_retrieval_preserve_account_qualification_and_scope(self):
        self.write_groups()
        for mode in ('graph', 'text', 'hybrid'):
            with self.subTest(mode=mode):
                kwargs = {'question': 'Alex used Orion'} if mode != 'graph' else {}
                result = retrieve(
                    self.root, 'urn:person:alex', Policy(max_chars=30000), mode=mode, **kwargs
                )
                contexts = [
                    *result['assertions'].values(),
                    *result.get('source_context', {}).values(),
                ]
                qualified = [a for a in contexts if a.get('evidence_accounts')]
                self.assertTrue(qualified)
                self.assertTrue(
                    all(
                        a['evidence_accounts'][0]['relationship'] == 'RepeatedAccount'
                        for a in qualified
                    )
                )
                self.assertNotIn('_evidence_account_spans', json.dumps(result))
        pin = self.pins[FIRST]
        scoped = retrieve(
            self.root,
            'urn:person:alex',
            Policy(max_chars=30000),
            scope=AccessScope(revisions=((pin['revision'], pin['sha256']),)),
        )
        self.assertEqual(set(scoped['assertions']), {FIRST})
        self.assertNotIn('evidence_accounts', scoped['assertions'][FIRST])

    def source_packages(self, records, spans):
        reader = _Evidence(self.root, self.store)
        text, citation = reader.revision(self.pins[FIRST]['revision'])
        candidates = [
            {
                'id': f'urn:source:section:{index}',
                'channel': 'text',
                'quote': text[start:end],
                'citation': {**citation, 'locator': {'characterOffset': str(start)}},
                'seed_context': 'QuestionOnly',
                'ranking': {'score': 1, 'matched': ['used']},
            }
            for index, (start, end) in enumerate(spans)
        ]
        base = {key: {} for key in ('assertions', 'sources', 'passages', 'source_context')}
        base.update(paths=[], matches=[])
        with patch.object(reader, 'revision', side_effect=AssertionError('extra source read')):
            return _packages(base, candidates, records, self.store, self.store, {}, {}, reader)

    def test_text_account_matching_requires_containment_at_the_verified_location(self):
        pin = self.pins[FIRST]
        quote = 'Alex used Orion.'
        start = pin['quote'].index(quote)
        self.group['sources'][0] = {
            **pin,
            'quote': quote,
            'character_offset': start,
            'start_line': 2,
        }
        self.write_groups()
        records = annotate_accounts(self.root, self.store, self.records)
        spans = [
            (start + 5, start + 9),  # Verified text within the pin.
            (0, len(pin['quote'])),  # A complete containing source section.
            (pin['quote'].rindex(quote), len(pin['quote']) - 1),  # Same words, different location.
            (start - 1, start + len(quote) - 1),  # Partial overlap is insufficient.
        ]
        packages = self.source_packages(records, spans)
        for index, package in enumerate(packages):
            context = next(iter(package['envelope']['source_context'].values()))
            self.assertIsNone(context['claim_review'])
            self.assertEqual(bool(context.get('evidence_accounts')), index < 2)
            if index < 2:
                self.assertEqual(context['evidence_accounts'][0]['id'], self.group['id'])
                self.assertEqual(len(context['evidence_accounts']), 1)
                self.assertEqual(
                    set(context['evidence_accounts'][0]),
                    {'id', 'relationship', 'qualification', 'reviewer'},
                )

        first = self.pins[FIRST]
        with patch('knot.evidence_accounts.validate_sources') as check:
            scoped = annotate_accounts(
                self.root,
                self.store,
                records,
                scope=AccessScope(revisions=((first['revision'], first['sha256']),)),
            )
            check.assert_not_called()
        for package in self.source_packages(scoped, spans):
            context = next(iter(package['envelope']['source_context'].values()))
            self.assertNotIn('evidence_accounts', context)

    def test_explicit_groups_annotate_without_merging_or_changing_review(self):
        self.write_groups()
        before = copy.deepcopy(self.records)
        fingerprints = {r['id']: fingerprint(self.store, r['id']) for r in before}
        result = annotate_accounts(self.root, self.store, self.records)
        self.assertEqual(self.records, before)
        self.assertEqual(len(result), len(before))
        for row in result:
            self.assertEqual(fingerprint(self.store, row['id']), fingerprints[row['id']])
            saved = next(r for r in before if r['id'] == row['id'])
            self.assertEqual(
                {
                    k: v
                    for k, v in row.items()
                    if k not in ('evidence_accounts', '_evidence_account_spans')
                },
                saved,
            )
            if row['id'] == OTHER:
                self.assertNotIn('evidence_accounts', row)
            else:
                self.assertEqual(
                    row['evidence_accounts'],
                    [
                        {
                            k: self.group[k]
                            for k in ('id', 'relationship', 'qualification', 'reviewer')
                        }
                    ],
                )
                self.assertNotIn('assertions', row['evidence_accounts'][0])

    def test_absent_catalogue_does_not_group_coincidentally_equal_quotes(self):
        result = annotate_accounts(self.root, self.store, self.records)
        self.assertEqual(result, self.records)
        self.assertIsNot(result, self.records)
        self.assertTrue(all(a is not b for a, b in zip(result, self.records)))

    def test_changed_source_pin_is_rejected(self):
        self.group['sources'][0] = {**self.pins[FIRST], 'quote': 'Unsupported quotation'}
        self.write_groups()
        with self.assertRaisesRegex(ValueError, 'quotation'):
            annotate_accounts(self.root, self.store, self.records)

    def test_pin_must_cover_the_actual_citation_occurrence(self):
        source = self.pins[FIRST]
        quote = 'Alex used Orion.'
        second_offset = source['quote'].rindex(quote)
        self.group['sources'][0] = {
            **source,
            'quote': quote,
            'character_offset': second_offset,
            'start_line': 3,
        }
        self.write_groups()
        with self.assertRaisesRegex(ValueError, 'citation'):
            annotate_accounts(self.root, self.store, self.records)

    def test_repeated_quote_without_a_locator_cannot_establish_account_coverage(self):
        pin = self.pins[FIRST]
        quote = 'Alex used Orion.'
        self.group['sources'][0] = {
            **pin,
            'quote': quote,
            'character_offset': pin['quote'].index(quote),
            'start_line': 2,
        }
        evidence = NamedNode(FIRST + ':evidence')
        for quad in list(
            self.store.quads_for_pattern(evidence, NamedNode(VOCAB + 'characterOffset'), None, META)
        ):
            self.store.remove(quad)
        self.write_groups()
        with self.assertRaisesRegex(ValueError, 'citation'):
            annotate_accounts(self.root, self.store, self.records)

    def test_unique_quote_without_a_locator_can_establish_account_coverage(self):
        evidence = NamedNode(FIRST + ':evidence')
        for quad in list(self.store.quads_for_pattern(evidence, None, None, META)):
            if quad.predicate.value == VOCAB + 'characterOffset':
                self.store.remove(quad)
            elif quad.predicate.value == VOCAB + 'quote':
                self.store.remove(quad)
                self.store.add(Quad(evidence, quad.predicate, Literal('# First account'), META))
        self.write_groups()
        result = annotate_accounts(self.root, self.store, self.records)
        record = next(row for row in result if row['id'] == FIRST)
        self.assertEqual(record['evidence_accounts'][0]['id'], self.group['id'])

    def test_partial_or_wrong_hash_grants_hide_whole_annotation_without_reads(self):
        self.write_groups()
        first = self.pins[FIRST]
        scopes = [
            AccessScope(revisions=((first['revision'], first['sha256']),)),
            AccessScope(revisions=tuple((p['revision'], 'a' * 64) for p in self.group['sources'])),
        ]
        for scope in scopes:
            with (
                self.subTest(scope=scope),
                patch('knot.evidence_accounts.validate_sources') as check,
            ):
                with patch('knot.retrieval._Evidence.revision', side_effect=AssertionError('read')):
                    self.assertEqual(
                        annotate_accounts(self.root, self.store, self.records, scope=scope),
                        self.records,
                    )
                check.assert_not_called()

    def test_invisible_group_is_not_read_or_exposed(self):
        self.write_groups()
        visible = [r for r in self.records if r['id'] == OTHER]
        scope = AccessScope(
            revisions=tuple((p['revision'], p['sha256']) for p in self.pins.values())
        )
        with patch('knot.evidence_accounts.validate_sources') as check:
            self.assertEqual(
                annotate_accounts(self.root, self.store, visible, scope=scope), visible
            )
            check.assert_not_called()

    def test_reannotation_drops_context_when_grants_are_withdrawn(self):
        self.write_groups()
        annotated = annotate_accounts(self.root, self.store, self.records)
        self.assertTrue(any('evidence_accounts' in row for row in annotated))
        with patch('knot.evidence_accounts.validate_sources') as check:
            result = annotate_accounts(self.root, self.store, annotated, scope=AccessScope())
            self.assertEqual(result, self.records)
            check.assert_not_called()

    def test_granted_pins_can_annotate_visible_member_without_exposing_hidden_members(self):
        self.write_groups()
        visible = [r for r in self.records if r['id'] == FIRST]
        for quad in list(self.store.quads_for_pattern(NamedNode(SECOND), None, None, META)):
            self.store.remove(quad)
        scope = AccessScope(
            revisions=tuple((p['revision'], p['sha256']) for p in self.group['sources'])
        )
        result = annotate_accounts(self.root, self.store, visible, scope=scope)
        self.assertIn('evidence_accounts', result[0])
        self.assertNotIn(SECOND, json.dumps(result))

    def test_owner_rejects_unknown_members_and_duplicate_groups(self):
        for groups, error in (
            ([{**self.group, 'assertions': [FIRST, 'urn:assertion:missing']}], 'Unknown'),
            ([self.group, self.group], 'Duplicate'),
            ([{**self.group, 'assertions': [FIRST, FIRST]}], 'unique'),
            ([{**self.group, 'relationship': 'IndependentCorroboration'}], 'relationship'),
        ):
            with self.subTest(error=error):
                self.write_groups(groups)
                with self.assertRaisesRegex(ValueError, error):
                    annotate_accounts(self.root, self.store, self.records)


if __name__ == '__main__':
    unittest.main()
