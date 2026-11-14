"""Recompute saved receipts without trusting old evidence or access."""

import contextlib
import copy
import io
import json
import unittest
from pathlib import Path
from unittest.mock import patch

import test_evaluation as fixture

from knot.evaluation import answer_question, evaluate
from knot.evaluation.revalidation import revalidate
from knot.evaluation.snapshot import canonical_hash, implementation
from knot.graph.query import load_store
from knot.graph.rdf import LABEL, VOCAB, one
from knot.interfaces.access import AccessScope
from knot.interfaces.note_cli import main
from knot.reviewing.writer import decide
from knot.shared.storage import digest


def reseal(value, field='receipt_sha256'):
    value[field] = canonical_hash({k: v for k, v in value.items() if k != field})
    return value


class TestRevalidate(unittest.TestCase):
    def setUp(self):
        self.f = fixture.CoverageTests()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.root, self.request = self.f.root, self.f.request

    def scope(self, *revisions):
        store = load_store(self.root / 'graph', history=True, include_notes=False)
        return AccessScope(
            revisions=tuple((r, one(store, r, VOCAB + 'sha256').value) for r in revisions)
        )

    def test_unchanged_receipt_is_recomputed_deterministically_without_writes(self):
        saved = evaluate(self.root, self.request)
        original = copy.deepcopy(saved)
        files = {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        result = revalidate(self.root, saved)
        self.assertEqual(result['status'], 'unchanged')
        self.assertTrue(result['outcomes_unchanged'])
        self.assertEqual(result['current'], saved)
        self.assertEqual(result, revalidate(self.root, saved))
        self.assertEqual(saved, original)
        self.assertEqual(files, {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()})

    def test_newly_accepted_mapping_invalidates_a_previous_absence(self):
        saved = evaluate(self.root, self.request)
        aid = self.f.claim(
            'urn:example:new-support',
            fixture.PROJECT,
            VOCAB + 'supports',
            fixture.CRITERIA[1],
            'A further qualified assessment.',
        )
        self.f.save()
        self.f.accept(aid)
        result = revalidate(self.root, saved)
        self.assertEqual(result['status'], 'changed')
        self.assertFalse(result['outcomes_unchanged'])
        self.assertIn('outcomes_changed', result['reasons'])
        self.assertEqual(self.f.states(result['current']), ['support_found', 'support_found'])

    def test_rejected_mapping_is_not_restored_from_saved_evidence(self):
        saved = evaluate(self.root, self.request)
        decide(
            self.root, fixture.SUPPORT, 'reject', reviewer='Synthetic reviewer', reason='Withdrawn'
        )
        result = revalidate(self.root, saved)
        self.assertEqual(result['status'], 'changed')
        self.assertFalse(result['outcomes_unchanged'])
        self.assertNotIn(fixture.SUPPORT, result['current']['assertions'])

    def test_implementation_change_is_distinct_from_unchanged_outcomes(self):
        saved = evaluate(self.root, self.request)
        changed = {**implementation(), 'code_sha256': '0' * 64}
        with patch('knot.evaluation.snapshot.implementation', return_value=changed):
            result = revalidate(self.root, saved)
        self.assertEqual(result['status'], 'changed')
        self.assertTrue(result['outcomes_unchanged'])
        self.assertIn('implementation_changed', result['reasons'])

    def test_tampered_hash_and_unsupported_rule_stop_before_execution(self):
        saved = evaluate(self.root, self.request)
        saved['criteria'][0]['outcome'] = 'unknown'
        with patch('knot.evaluation.revalidation.evaluate') as run:
            with self.assertRaises(ValueError):
                revalidate(self.root, saved)
            saved['request']['version'] = 'unsupported'
            reseal(saved)
            with self.assertRaises(ValueError):
                revalidate(self.root, saved)
            run.assert_not_called()

    def test_rehashed_fabricated_outcome_is_compared_against_fresh_execution(self):
        saved = evaluate(self.root, self.request)
        saved['criteria'][1]['outcome'] = 'support_found'
        reseal(saved)
        result = revalidate(self.root, saved)
        self.assertEqual(result['status'], 'changed')
        self.assertFalse(result['outcomes_unchanged'])
        self.assertEqual(result['current']['criteria'][1]['outcome'], 'no_qualifying_support')

    def test_saved_paths_are_never_followed_or_echoed(self):
        saved = evaluate(self.root, self.request)
        saved['manifest']['verified_files']['../never-read-private.txt'] = '0' * 64
        reseal(saved)
        original = Path.read_bytes

        def guarded(path):
            self.assertNotIn('never-read-private', str(path))
            return original(path)

        with patch.object(Path, 'read_bytes', guarded):
            result = revalidate(self.root, saved)
        self.assertEqual(result['status'], 'changed')
        self.assertNotIn('never-read-private', json.dumps(result))

    def test_revoked_grant_does_not_read_or_republish_old_witness(self):
        saved = evaluate(self.root, self.request)
        denied = 'sources/' + digest(fixture.SUPPORT.encode()) + '.txt'
        original = Path.read_bytes

        def guarded(path):
            self.assertNotEqual(path, self.root / denied)
            return original(path)

        with patch.object(Path, 'read_bytes', guarded):
            result = revalidate(self.root, saved, scope=self.scope(fixture.REVISION))
        self.assertEqual(result['status'], 'changed')
        self.assertEqual(self.f.states(result['current']), ['unknown', 'unknown'])
        self.assertNotIn('limited scope', json.dumps(result))
        self.assertNotIn(fixture.SUPPORT, result['current']['assertions'])

    def test_hidden_changes_do_not_change_scoped_revalidation(self):
        scope = self.scope(fixture.REVISION, fixture.SUPPORT + ':revision')
        saved = evaluate(self.root, self.request, scope=scope)
        before = revalidate(self.root, saved, scope=scope)
        aid = self.f.claim(
            'urn:example:hidden',
            'urn:example:hidden-project',
            VOCAB + 'supports',
            fixture.CRITERIA[0],
            'Hidden account.',
        )
        self.f.save()
        self.f.accept(aid)
        self.assertEqual(before, revalidate(self.root, saved, scope=scope))

    def test_question_names_are_resolved_again_and_ambiguity_abstains(self):
        self.f.data.add(fixture.PROJECT, LABEL, 'Falcon', literal=True)
        self.f.data.add(fixture.CRITERIA[0], LABEL, 'Safe changes', literal=True)
        self.f.save()
        question = 'Does project "Falcon" have reviewed support for criterion "Safe changes"?'
        saved = answer_question(self.root, question)
        self.assertEqual(revalidate(self.root, saved)['status'], 'unchanged')
        self.f.data.add(fixture.CRITERIA[1], LABEL, 'Safe changes', literal=True)
        self.f.save()
        result = revalidate(self.root, saved)
        self.assertEqual(result['status'], 'not_comparable')
        self.assertIsNone(result['outcomes_unchanged'])
        self.assertEqual(result['current']['status'], 'needs_selection')
        self.assertNotIn('evaluation', result['current'])

    def test_corrupt_current_source_fails_without_reusing_saved_result(self):
        saved = evaluate(self.root, self.request)
        (self.root / 'sources/framework.txt').write_text('Changed bytes')
        with self.assertRaisesRegex(ValueError, 'ChangedFile'):
            revalidate(self.root, saved)

    def test_cli_revalidates_and_text_retains_the_complete_report(self):
        saved = evaluate(self.root, self.request)
        path = self.root / 'receipt.json'
        path.write_text(json.dumps(saved))
        for format in ('json', 'text'):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                main(
                    [
                        '--data-root',
                        str(self.root),
                        'evaluate',
                        '--revalidate',
                        str(path),
                        '--format',
                        format,
                    ]
                )
            text = output.getvalue()
            result = json.loads(text[text.index('{') :])
            self.assertEqual(result['status'], 'unchanged')
            self.assertEqual(result['current'], saved)
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            main(['--data-root', str(self.root), 'evaluate', str(path), '--revalidate', str(path)])

    def test_question_wrapper_and_nested_receipt_must_agree(self):
        question = (
            f'Does project "{fixture.PROJECT}" have reviewed support for criterion '
            f'"{fixture.CRITERIA[0]}" in framework "{fixture.FRAMEWORK}" '
            f'at revision "{fixture.REVISION}"?'
        )
        saved = answer_question(self.root, question)
        saved['request'] = {**saved['request'], 'subject': 'urn:example:other'}
        reseal(saved, 'answer_sha256')
        with patch('knot.evaluation.revalidation.answer_question') as run:
            with self.assertRaises(ValueError):
                revalidate(self.root, saved)
            run.assert_not_called()
