"""Synthetic acceptance tests for the read-only coverage pilot."""

import contextlib
import io
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from knot.curating.provenance import source_pin
from knot.evaluation import CoverageRequest, evaluate, render
from knot.graph.rdf import ATTRIBUTED, DERIVED, RDF_TYPE, VOCAB, Dataset
from knot.interfaces.note_cli import main
from knot.retrieval_engine.policy import Policy
from knot.retrieval_engine.service import retrieve
from knot.reviewing.writer import decide
from knot.shared.storage import digest
from knot.writing.notes import create_note

PROJECT = 'urn:example:project'
FRAMEWORK = 'urn:example:framework'
REVISION = 'urn:example:framework-revision'
CRITERIA = ('urn:example:criterion:a', 'urn:example:criterion:b')
SUPPORT = 'urn:example:support'
DEFINITION = 'http://www.w3.org/2004/02/skos/core#definition'


class CoverageTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        (self.root / 'graph').mkdir()
        (self.root / 'sources').mkdir()
        self.data = Dataset()
        self.request = CoverageRequest(PROJECT, FRAMEWORK, REVISION, CRITERIA)
        text = 'Review changes carefully.\nExplain tradeoffs.\n'
        (self.root / 'sources/framework.txt').write_text(text)
        self.data.add(REVISION, VOCAB + 'snapshotPath', 'sources/framework.txt', literal=True)
        self.data.add(REVISION, VOCAB + 'sha256', digest(text.encode()), literal=True)
        for index, (criterion, quote) in enumerate(zip(CRITERIA, text.splitlines(), strict=True)):
            aid = f'urn:example:definition:{index}'
            self.claim(aid, criterion, DEFINITION, quote, quote, revision=REVISION, literal=True)
            self.data.add(aid, VOCAB + 'recordKind', VOCAB + 'FrameworkDefinition')
            self.data.add(aid, VOCAB + 'framework', FRAMEWORK)
        self.claim(
            SUPPORT,
            PROJECT,
            VOCAB + 'supports',
            CRITERIA[0],
            'The reviewer considers this project supporting evidence, with limited scope.',
        )
        self.save()
        for aid in ('urn:example:definition:0', 'urn:example:definition:1', SUPPORT):
            self.accept(aid)

    def claim(
        self,
        aid,
        subject,
        predicate,
        obj,
        quote,
        *,
        revision=None,
        literal=False,
        origin='Explicit',
        kind=None,
    ):
        if revision is None:
            revision = aid + ':revision'
            path = 'sources/' + digest(aid.encode()) + '.txt'
            (self.root / path).write_text(quote + '\n')
            self.data.add(revision, VOCAB + 'snapshotPath', path, literal=True)
            self.data.add(revision, VOCAB + 'sha256', digest((quote + '\n').encode()), literal=True)
        eid = aid + ':evidence'
        self.data.add(subject, predicate, obj, literal=literal, graph=aid)
        self.data.add(aid, RDF_TYPE, VOCAB + 'Assertion')
        self.data.add(aid, ATTRIBUTED, 'Synthetic curator', literal=True)
        for key, value in [
            ('reviewStatus', 'Unreviewed'),
            ('lifecycle', 'Active'),
            ('origin', origin),
        ]:
            self.data.add(aid, VOCAB + key, VOCAB + value)
        for key, value in [
            ('subjectLabel', subject),
            ('objectLabel', obj),
            ('rationale', 'Attributed assessment'),
        ]:
            self.data.add(aid, VOCAB + key, value, literal=True)
        self.data.add(aid, DERIVED, eid)
        if kind is not None:
            self.data.add(
                aid, VOCAB + 'authorClassification', json.dumps({'kind': kind}), literal=True
            )
        self.data.add(eid, VOCAB + 'revision', revision)
        self.data.add(eid, VOCAB + 'quote', quote, literal=True)
        text = (self.root / 'sources/framework.txt').read_text() if revision == REVISION else quote
        self.data.add(eid, VOCAB + 'characterOffset', text.index(quote), literal=True)
        self.data.add(
            eid, VOCAB + 'startLine', text[: text.index(quote)].count('\n') + 1, literal=True
        )
        return aid

    def save(self):
        (self.root / 'graph/claims.trig').write_text(self.data.text())

    def accept(self, aid):
        decide(
            self.root, aid, 'accept', reviewer='Synthetic reviewer', reason='Checked representation'
        )

    def states(self, result):
        return [row['outcome'] for row in result['criteria']]

    def test_support_and_bounded_absence_preserve_assessment_and_review(self):
        result = evaluate(self.root, self.request)
        self.assertEqual(self.states(result), ['support_found', 'no_qualifying_support'])
        self.assertTrue(result['complete'])
        premise = result['assertions'][SUPPORT]
        self.assertEqual(premise['meaning'], 'Assessment')
        self.assertEqual(premise['origin'], 'Explicit')
        self.assertEqual(premise['attributed_to'], ['Synthetic curator'])
        self.assertEqual(premise['reviews'][-1]['reviewer'], 'Synthetic reviewer')
        self.assertIn('limited scope', premise['sources'][0]['quote'])
        self.assertIn('recorded mapping coverage', render(result))
        self.assertIn(SUPPORT, render(result))

    def test_repeatability_and_no_dataset_writes(self):
        before = {
            p.relative_to(self.root): p.read_bytes() for p in self.root.rglob('*') if p.is_file()
        }
        first = evaluate(self.root, self.request)
        self.assertEqual(first, evaluate(self.root, self.request))
        after = {
            p.relative_to(self.root): p.read_bytes() for p in self.root.rglob('*') if p.is_file()
        }
        self.assertEqual(before, after)

    def test_unreviewed_mapping_is_not_support_and_new_acceptance_changes_receipt(self):
        aid = self.claim(
            'urn:example:new', PROJECT, VOCAB + 'supports', CRITERIA[1], 'Another assessment.'
        )
        self.save()
        first = evaluate(self.root, self.request)
        self.assertEqual(self.states(first)[1], 'no_qualifying_support')
        self.accept(aid)
        second = evaluate(self.root, self.request)
        self.assertEqual(self.states(second)[1], 'support_found')
        self.assertNotEqual(first['receipt_sha256'], second['receipt_sha256'])

    def test_rejected_mapping_is_not_support(self):
        decide(self.root, SUPPORT, 'reject', reviewer='Synthetic reviewer', reason='Withdrawn')
        self.assertEqual(self.states(evaluate(self.root, self.request))[0], 'no_qualifying_support')

    def test_unreviewed_definition_and_wrong_revision_are_unknown(self):
        decide(
            self.root,
            'urn:example:definition:1',
            'reject',
            reviewer='Synthetic reviewer',
            reason='Needs review',
        )
        self.assertEqual(self.states(evaluate(self.root, self.request))[1], 'unknown')
        self.assertIn(
            'missing_reviewed_definition',
            evaluate(self.root, self.request)['criteria'][1]['reasons'],
        )
        result = evaluate(self.root, replace(self.request, framework_revision='urn:example:wrong'))
        self.assertEqual(self.states(result), ['unknown', 'unknown'])

    def test_assertion_and_source_budgets_never_produce_absence(self):
        for request in (
            replace(self.request, max_assertions=1),
            replace(self.request, max_sources=1),
        ):
            with self.subTest(request=request):
                result = evaluate(self.root, request)
                self.assertFalse(result['complete'])
                self.assertNotIn('no_qualifying_support', self.states(result))
                for row in result['criteria']:
                    self.assertNotIn('missing_reviewed_definition', row['reasons'])

    def test_source_budget_before_definition_check_does_not_claim_missing_definition(self):
        aid = self.claim(
            'urn:example:aaa-support',
            PROJECT,
            VOCAB + 'supports',
            CRITERIA[0],
            'Another assessment, ordered before the definitions.',
        )
        self.save()
        self.accept(aid)
        result = evaluate(self.root, replace(self.request, max_sources=1))
        self.assertEqual(self.states(result), ['unknown', 'unknown'])
        for row in result['criteria']:
            self.assertEqual(row['reasons'], ['source_budget'])

    def test_temporal_request_abstains(self):
        result = evaluate(self.root, replace(self.request, as_of='2025-01-01'))
        self.assertEqual(self.states(result), ['unknown', 'unknown'])
        self.assertIn('unsupported_temporal_scope', result['reasons'])
        for row in result['criteria']:
            self.assertEqual(row['reasons'], ['unsupported_temporal_scope'])

    def test_scoped_access_is_rejected_before_reading(self):
        with patch('knot.evaluation.engine.load_store', side_effect=AssertionError('read')):
            with self.assertRaisesRegex(ValueError, 'owner-local'):
                evaluate(self.root, self.request, scope=object())

    def test_corrupt_source_and_review_fail_loudly(self):
        path = self.root / ('sources/' + digest(SUPPORT.encode()) + '.txt')
        path.write_text('Changed')
        with self.assertRaisesRegex(ValueError, 'ChangedFile'):
            evaluate(self.root, self.request)
        self.data.add(SUPPORT, VOCAB + 'extraMetadata', 'changed', literal=True)
        self.save()
        with self.assertRaisesRegex(ValueError, 'Reviewed assertion changed'):
            evaluate(self.root, self.request)

    def test_change_during_evaluation_fails(self):
        from knot.evaluation.engine import load_store

        def changing(*args, **kwargs):
            store = load_store(*args, **kwargs)
            (self.root / 'graph/new.trig').write_text('')
            return store

        with patch('knot.evaluation.engine.load_store', side_effect=changing):
            with self.assertRaisesRegex(ValueError, 'Inputs changed'):
                evaluate(self.root, self.request)

    def test_identity_projection_is_unknown(self):
        mapping = 'urn:example:identity'
        self.data.add(mapping, VOCAB + 'sourceEntity', 'urn:example:mention')
        self.data.add(mapping, VOCAB + 'entity', PROJECT)
        self.data.add(mapping, VOCAB + 'reviewStatus', VOCAB + 'Accepted')
        self.save()
        result = evaluate(self.root, self.request)
        self.assertEqual(self.states(result), ['unknown', 'unknown'])
        self.assertIn('identity_resolution_not_supported', result['reasons'])
        for row in result['criteria']:
            self.assertEqual(row['reasons'], ['identity_resolution_not_supported'])

    def test_request_validation_does_not_drop_unknown_fields(self):
        with self.assertRaisesRegex(ValueError, 'Unknown request fields'):
            CoverageRequest.from_dict({**self.request.to_dict(), 'conflict': True})
        for changes in (
            {'criteria': ()},
            {'criteria': (CRITERIA[0], CRITERIA[0])},
            {'max_sources': True},
            {'version': '2'},
            {'subject': 'a label'},
        ):
            with self.subTest(changes=changes), self.assertRaises((ValueError, TypeError)):
                replace(self.request, **changes)

    def test_cli_routes_and_prints_receipt(self):
        request_file = self.root / 'request.json'
        request_file.write_text(json.dumps(self.request.to_dict()))
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            main(['--data-root', str(self.root), 'evaluate', str(request_file)])
        self.assertEqual(
            self.states(json.loads(output.getvalue())), ['support_found', 'no_qualifying_support']
        )

    def test_native_evidence_keeps_author_and_verified_manifest(self):
        quote = 'This may support the second criterion, subject to review.'
        note = create_note(self.root, quote, author='Synthetic author', agent='Synthetic curator')
        self.data.add(note['revision'], VOCAB + 'snapshotPath', note['body_path'], literal=True)
        self.data.add(note['revision'], VOCAB + 'sha256', note['body_sha256'], literal=True)
        aid = self.claim(
            'urn:example:native',
            PROJECT,
            VOCAB + 'supports',
            CRITERIA[1],
            quote,
            revision=note['revision'],
            origin='Inferred',
        )
        self.save()
        self.accept(aid)
        result = evaluate(self.root, self.request)
        premise = result['assertions'][aid]
        self.assertEqual(premise['origin'], 'Inferred')
        self.assertEqual(premise['sources'][0]['native_note']['author'], 'Synthetic author')
        self.assertIn(premise['sources'][0]['manifest_path'], result['manifest']['verified_files'])

    def test_free_text_does_not_become_a_mapping(self):
        create_note(self.root, 'This project supports every criterion.', author='Synthetic author')
        self.assertEqual(self.states(evaluate(self.root, self.request))[1], 'no_qualifying_support')

    def test_thought_classification_is_not_promoted_to_assessment(self):
        aid = self.claim(
            'urn:example:thought',
            PROJECT,
            VOCAB + 'supports',
            CRITERIA[1],
            'Perhaps this would support the criterion.',
            kind='Thought',
        )
        self.save()
        self.accept(aid)
        result = evaluate(self.root, self.request)
        self.assertEqual(self.states(result)[1], 'no_qualifying_support')
        self.assertEqual(result['excluded_assertions'][aid]['kind'], 'Thought')

    def test_evidence_account_qualification_is_preserved_and_verified(self):
        quote = 'The reviewer considers this project supporting evidence, with limited scope.'
        pin = source_pin(self.root, SUPPORT + ':revision', quote, 0)
        path = self.root / 'curation/evidence-accounts.json'
        path.parent.mkdir()
        path.write_text(
            json.dumps(
                {
                    'schema_version': 1,
                    'groups': [
                        {
                            'id': 'synthetic-overlap',
                            'relationship': 'OverlapUnresolved',
                            'qualification': 'These reports may describe the same work.',
                            'reviewer': 'Synthetic reviewer',
                            'assertions': [SUPPORT],
                            'sources': [pin],
                        }
                    ],
                }
            )
        )
        result = evaluate(self.root, self.request)
        self.assertIn(
            'same work', result['assertions'][SUPPORT]['evidence_accounts'][0]['qualification']
        )
        self.assertIn(pin['sha256'], result['manifest']['verified_files'].values())
        data = json.loads(path.read_text())
        data['groups'][0]['sources'][0]['quote'] = 'Invented evidence'
        path.write_text(json.dumps(data))
        with self.assertRaises(ValueError):
            evaluate(self.root, self.request)

    def test_corrected_assertion_is_excluded_until_replacement_is_accepted(self):
        decide(
            self.root,
            SUPPORT,
            'correct',
            reviewer='Synthetic reviewer',
            reason='Correct the endpoint',
            replacement={
                'subject': PROJECT,
                'predicate': VOCAB + 'supports',
                'object': CRITERIA[1],
                'subject_label': 'Example project',
                'object_label': 'Second criterion',
                'rationale': 'Corrected assessment',
            },
        )
        result = evaluate(self.root, self.request)
        self.assertEqual(self.states(result), ['no_qualifying_support', 'no_qualifying_support'])
        self.assertNotIn(SUPPORT, result['assertions'])

    def test_indirect_support_is_not_joined_to_project(self):
        aid = self.claim(
            'urn:example:indirect',
            'urn:example:activity',
            VOCAB + 'supports',
            CRITERIA[1],
            'The activity supports this criterion.',
        )
        self.claim(
            'urn:example:association',
            'urn:example:activity',
            VOCAB + 'relatedTo',
            PROJECT,
            'The activity belongs to this project.',
        )
        self.save()
        self.accept(aid)
        self.accept('urn:example:association')
        self.assertEqual(self.states(evaluate(self.root, self.request))[1], 'no_qualifying_support')

    def test_legacy_accepted_flag_without_review_event_is_unknown(self):
        aid = self.claim(
            'urn:example:legacy', PROJECT, VOCAB + 'supports', CRITERIA[1], 'Legacy assessment.'
        )
        self.save()
        path = self.root / 'graph/claims.trig'
        path.write_text(
            path.read_text().replace(
                f'<{aid}> <{VOCAB}reviewStatus> <{VOCAB}Unreviewed>',
                f'<{aid}> <{VOCAB}reviewStatus> <{VOCAB}Accepted>',
            )
        )
        result = evaluate(self.root, self.request)
        self.assertEqual(self.states(result)[1], 'unknown')
        self.assertIn('missing_acceptance_event', result['criteria'][1]['reasons'])

    def test_evaluation_enumerates_evidence_that_bounded_retrieval_omits(self):
        aid = self.claim(
            'urn:example:second-support',
            PROJECT,
            VOCAB + 'supports',
            CRITERIA[1],
            'A second reviewed assessment.',
        )
        self.save()
        self.accept(aid)
        retrieved = retrieve(
            self.root, PROJECT, Policy(accepted_only=True, max_assertions=1, max_chars=24000)
        )
        self.assertEqual(len(retrieved['assertions']), 1)
        self.assertTrue(retrieved['omissions']['further_unknown'])
        result = evaluate(self.root, self.request)
        self.assertEqual(self.states(result), ['support_found', 'support_found'])
        self.assertTrue(result['complete'])

    def test_source_change_after_verification_fails_before_publication(self):
        from knot.evaluation.engine import Evidence

        citation = Evidence.citation

        def changing(reader, eid):
            quote, source = citation(reader, eid)
            if eid == SUPPORT + ':evidence':
                (self.root / source['snapshot']).write_text('Changed after the first read')
            return quote, source

        with patch.object(Evidence, 'citation', changing):
            with self.assertRaisesRegex(ValueError, 'Inputs changed'):
                evaluate(self.root, self.request)


if __name__ == '__main__':
    unittest.main()
