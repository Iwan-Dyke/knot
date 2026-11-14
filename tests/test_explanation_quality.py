"""Whole-dataset audits must not overlook damaged or misplaced artifact reviews."""

import json
import unittest

import test_explanations as fixture

from knot.diagnostics.quality import audit
from knot.evaluation import explanations
from knot.evaluation.snapshot import canonical_hash


class TestExplanationQuality(unittest.TestCase):
    def setUp(self):
        self.f = fixture.TestExplanations()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.event = self.f.approve()
        self.directory = explanations._directory(self.f.root, self.f.request)

    def errors(self):
        return [
            e for e in audit(self.f.root)['errors'] if e['code'] == 'invalid_explanation_reviews'
        ]

    def test_valid_history_is_counted_without_writes(self):
        before = {p: p.read_bytes() for p in self.f.root.rglob('*') if p.is_file()}
        report = audit(self.f.root)
        self.assertEqual(report['counts']['explanation_review_events'], 1)
        self.assertFalse(self.errors())
        self.assertEqual(before, {p: p.read_bytes() for p in self.f.root.rglob('*') if p.is_file()})

    def test_tampered_event_is_an_integrity_error(self):
        path = self.directory / (self.event['event_sha256'] + '.json')
        path.write_text(json.dumps({**self.event, 'reason': 'Changed after approval'}))
        self.assertEqual(len(self.errors()), 1)

    def test_misfiled_chain_is_an_integrity_error(self):
        self.directory.rename(self.directory.with_name('0' * 64))
        self.assertEqual(len(self.errors()), 1)

    def test_missing_predecessor_is_an_integrity_error(self):
        explanations.withdraw(
            self.f.root,
            self.f.request,
            expected=self.event['event_sha256'],
            reviewer='Synthetic reviewer',
            reason='Withdraw wording',
        )
        (self.directory / (self.event['event_sha256'] + '.json')).unlink()
        self.assertEqual(len(self.errors()), 1)

    def test_rehashed_invalid_wording_is_still_an_integrity_error(self):
        path = self.directory / (self.event['event_sha256'] + '.json')
        value = {**self.event, 'wordings': [self.f.request['question']]}
        value['event_sha256'] = canonical_hash(
            {k: v for k, v in value.items() if k != 'event_sha256'}
        )
        path.unlink()
        (self.directory / (value['event_sha256'] + '.json')).write_text(json.dumps(value))
        self.assertEqual(len(self.errors()), 1)
