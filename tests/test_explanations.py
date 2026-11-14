"""Reviewed prose is revision-specific and cannot inherit permission or approval."""

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from knot.curating.provenance import source_pin
from knot.evaluation.explanations import answer, approve, history, prepare, revalidate, withdraw
from knot.evaluation.snapshot import canonical_hash
from knot.graph.rdf import LABEL, RDF_TYPE, VOCAB, Dataset
from knot.interfaces.access import AccessScope
from knot.writing.notes import create_note, save_note

DECISION = 'urn:example:decision:batching'


class TestExplanations(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        (self.root / 'graph').mkdir()
        graph = Dataset()
        graph.add(DECISION, LABEL, 'Batching choice', literal=True)
        graph.add(DECISION, RDF_TYPE, VOCAB + 'Decision')
        (self.root / 'graph/example.trig').write_text(graph.text())
        self.source = create_note(
            self.root,
            'We chose batching to reduce calls. Delivery is unconfirmed.\n',
            author='Source author',
        )
        self.pin = source_pin(self.root, self.source['revision'], self.source['body'], 0)
        self.note = create_note(
            self.root,
            'Batching was chosen to reduce calls.\r\nDelivery remains unconfirmed.\r\n',
            title='Batching rationale',
            author='Synthetic curator',
            agent='Synthetic curator',
            entities=[DECISION],
            derivation={
                'method': 'faithful_restatement',
                'qualification': 'An attributed decision, not a delivery claim.',
                'sources': [self.pin],
            },
        )
        self.request = {
            'decision': DECISION,
            'revision': self.note['revision'],
            'question': f'Why was decision "{DECISION}" chosen?',
        }

    def approve(self):
        return approve(
            self.root,
            prepare(self.root, self.request),
            reviewer='Synthetic reviewer',
            reason='Checked applicability, meaning and qualifications.',
        )

    def scope(self, *notes):
        return AccessScope(revisions=tuple((n['revision'], n['body_sha256']) for n in notes))

    def test_preview_is_readonly_and_approval_returns_exact_wording_and_authorship(self):
        before = {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        preview = prepare(self.root, self.request)
        self.assertEqual(preview['answer'], self.note['body'])
        self.assertEqual(before, {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()})
        self.assertEqual(answer(self.root, self.request)['status'], 'unknown')
        review = self.approve()
        result = answer(self.root, self.request)
        self.assertEqual(result['status'], 'approved')
        self.assertEqual(result['answer'], self.note['body'])
        self.assertEqual(result['author'], 'Synthetic curator')
        self.assertEqual(result['review']['reviewer'], 'Synthetic reviewer')
        self.assertEqual(result['review']['event_sha256'], review['event_sha256'])
        self.assertEqual(result, answer(self.root, self.request))
        self.assertEqual(result['sources'][0]['quote'], self.source['body'])
        self.assertIn('not a delivery claim', result['qualification'])

    def test_withdrawal_revalidation_does_not_restore_old_text(self):
        event = self.approve()
        saved = answer(self.root, self.request)
        self.assertEqual(revalidate(self.root, saved)['status'], 'unchanged')
        withdrawn = withdraw(
            self.root,
            self.request,
            expected=event['event_sha256'],
            reviewer='Synthetic reviewer',
            reason='Needs another review.',
        )
        self.assertEqual(withdrawn['action'], 'withdraw')
        result = revalidate(self.root, saved)
        self.assertEqual(result['status'], 'changed')
        self.assertEqual(result['current']['status'], 'unknown')
        self.assertNotIn(self.note['body'], json.dumps(result))
        self.assertEqual(len(list((self.root / 'reviews/explanations').rglob('*.json'))), 2)

    def test_note_edit_and_native_input_edit_require_fresh_review(self):
        self.approve()
        updated = save_note(
            self.root,
            self.note['note'],
            'A revised explanation.\n',
            expected=self.note['revision'],
            agent='Synthetic curator',
        )
        self.assertEqual(answer(self.root, self.request)['status'], 'unknown')
        newer = {**self.request, 'revision': updated['revision']}
        self.assertEqual(answer(self.root, newer)['status'], 'unknown')
        approve(
            self.root, prepare(self.root, newer), reviewer='Synthetic reviewer', reason='Rechecked.'
        )
        save_note(
            self.root,
            self.source['note'],
            'A correction to the account.\n',
            expected=self.source['revision'],
        )
        self.assertEqual(answer(self.root, newer)['status'], 'unknown')
        with self.assertRaises(ValueError):
            prepare(self.root, newer)

    def test_approval_requires_unaltered_current_preview_and_expected_review_state(self):
        preview = prepare(self.root, self.request)
        altered = copy.deepcopy(preview)
        altered['answer'] = 'Unreviewed replacement'
        with self.assertRaises(ValueError):
            approve(self.root, altered, reviewer='Synthetic reviewer', reason='Test')
        self.approve()
        with self.assertRaises(ValueError):
            approve(self.root, preview, reviewer='Synthetic reviewer', reason='Stale preview')
        with self.assertRaises(ValueError):
            withdraw(
                self.root,
                self.request,
                expected=None,
                reviewer='Synthetic reviewer',
                reason='Stale state',
            )

    def test_source_note_wrong_decision_and_extra_question_conditions_cannot_be_approved(self):
        for request in (
            {**self.request, 'revision': self.source['revision']},
            {**self.request, 'decision': 'urn:example:another'},
            {**self.request, 'question': self.request['question'] + ' Was it successful?'},
        ):
            with self.assertRaises(ValueError):
                prepare(self.root, request)
        self.assertEqual(
            answer(self.root, {**self.request, 'question': 'Why? Also prove delivery.'})['status'],
            'unsupported_question',
        )

    def test_grants_require_transitive_inputs_before_any_denied_body_read(self):
        self.approve()
        original = Path.read_bytes

        def guard(path):
            if path in (self.root / self.source['body_path'], self.root / self.note['body_path']):
                self.fail('Denied body read')
            return original(path)

        for scope in (AccessScope(), self.scope(self.note)):
            with patch.object(Path, 'read_bytes', guard):
                result = answer(self.root, self.request, scope=scope)
            self.assertEqual(result['status'], 'unknown')
            self.assertNotIn('Synthetic reviewer', json.dumps(result))
            self.assertNotIn(self.source['revision'], json.dumps(result))
        allowed = answer(self.root, self.request, scope=self.scope(self.note, self.source))
        self.assertEqual(allowed['status'], 'approved')
        self.assertEqual(
            allowed['freshness'], 'latest_granted_revisions; global_currentness_unknown'
        )

    def test_hidden_successor_does_not_leak_but_a_granted_successor_invalidates(self):
        self.approve()
        scope = self.scope(self.note, self.source)
        before = answer(self.root, self.request, scope=scope)
        updated = save_note(
            self.root, self.source['note'], 'Later correction.\n', expected=self.source['revision']
        )
        self.assertEqual(before, answer(self.root, self.request, scope=scope))
        after = answer(self.root, self.request, scope=self.scope(self.note, self.source, updated))
        self.assertEqual(after['status'], 'unknown')

    def test_corrupt_body_or_review_fails_without_saved_answer_fallback(self):
        event = self.approve()
        saved = answer(self.root, self.request)
        path = next((self.root / 'reviews/explanations').rglob('*.json'))
        value = json.loads(path.read_text())
        value['reason'] = 'Changed'
        path.write_text(json.dumps(value))
        with self.assertRaises(ValueError):
            revalidate(self.root, saved)
        path.write_text(json.dumps(event))
        (self.root / self.source['body_path']).write_text('Changed source bytes')
        with self.assertRaises(ValueError):
            answer(self.root, self.request)

    def test_nested_derivation_needs_every_grant_and_current_native_input(self):
        pin = source_pin(self.root, self.note['revision'], self.note['body'], 0)
        nested = create_note(
            self.root,
            'The recorded choice was intended to reduce calls; delivery is unconfirmed.\n',
            title='Nested explanation',
            author='Synthetic curator',
            agent='Synthetic curator',
            entities=[DECISION],
            derivation={
                'method': 'synthesis',
                'qualification': 'Restates an attributed choice only.',
                'sources': [pin],
            },
        )
        request = {**self.request, 'revision': nested['revision']}
        approve(
            self.root,
            prepare(self.root, request),
            reviewer='Synthetic reviewer',
            reason='Verified full chain.',
        )
        self.assertEqual(
            answer(self.root, request, scope=self.scope(nested, self.note))['status'], 'unknown'
        )
        self.assertEqual(
            answer(self.root, request, scope=self.scope(nested, self.note, self.source))['status'],
            'approved',
        )
        save_note(
            self.root, self.source['note'], 'Corrected original.', expected=self.source['revision']
        )
        self.assertEqual(answer(self.root, request)['status'], 'unknown')

    def test_rehashed_preview_cannot_change_wording_and_malformed_chains_fail(self):
        preview = prepare(self.root, self.request)
        preview['answer'] = 'Fabricated replacement'
        preview['preview_sha256'] = canonical_hash(
            {k: v for k, v in preview.items() if k != 'preview_sha256'}
        )
        with self.assertRaises(ValueError):
            approve(self.root, preview, reviewer='Synthetic reviewer', reason='Test')
        event = self.approve()
        path = next((self.root / 'reviews/explanations').rglob('*.json'))
        fork = {**event, 'reason': 'A competing event'}
        fork['event_sha256'] = canonical_hash(
            {k: v for k, v in fork.items() if k != 'event_sha256'}
        )
        duplicate = path.parent / (fork['event_sha256'] + '.json')
        duplicate.write_text(json.dumps(fork))
        with self.assertRaisesRegex(ValueError, 'branched'):
            history(self.root, self.request)
        duplicate.unlink()
        withdraw(
            self.root,
            self.request,
            expected=event['event_sha256'],
            reviewer='Synthetic reviewer',
            reason='Stop reuse',
        )
        path.unlink()
        with self.assertRaisesRegex(ValueError, 'Incomplete'):
            history(self.root, self.request)

    def test_withdrawal_during_read_prevents_returning_a_stale_answer(self):
        from knot.evaluation.access import ScopedSnapshot

        event = self.approve()
        original = ScopedSnapshot.verify

        def changed(snapshot):
            original(snapshot)
            withdraw(
                self.root,
                self.request,
                expected=event['event_sha256'],
                reviewer='Synthetic reviewer',
                reason='Concurrent withdrawal',
            )

        with patch.object(ScopedSnapshot, 'verify', changed):
            with self.assertRaisesRegex(ValueError, 'reviews changed'):
                answer(self.root, self.request)
