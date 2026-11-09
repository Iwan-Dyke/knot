import tempfile
import unittest
from pathlib import Path

from knot.inventory import digest
from knot.notes import create_note, save_note
from knot.provenance import source_pin
from knot.query import load_store
from knot.rdf import DERIVED, RDF_TYPE, VOCAB, Dataset, one
from knot.review import decide, fingerprint, inspect_assertion, read_events

ASSERTION = 'urn:assertion:source-validation'
EVIDENCE = 'urn:evidence:source-validation'


class ReviewProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def fixture(self, *, offset=8, line=2, transcription=False, native=False, evidence=True):
        text = '# Note\r\nλ🙂 Work remains planned.\r\n'
        quote = 'λ🙂 Work remains planned.'
        if native:
            note = create_note(self.root, text, author='Original author')
            revision, sha, snapshot = note['revision'], note['body_sha256'], note['body_path']
            save_note(self.root, note['note'], 'New head.', expected=revision)
        else:
            raw = b'Preserved notebook archive' if transcription else text.encode()
            snapshot = 'sources/original.rmdoc' if transcription else 'sources/original.md'
            (self.root / 'sources').mkdir(exist_ok=True)
            (self.root / snapshot).write_bytes(raw)
            sha = digest(raw)
            revision = 'urn:revision:' + sha
        data = Dataset()
        data.add('urn:person:author', VOCAB + 'workedOn', 'urn:project:example', graph=ASSERTION)
        data.add(ASSERTION, RDF_TYPE, VOCAB + 'Assertion')
        for key, value in (
            ('reviewStatus', 'Unreviewed'),
            ('lifecycle', 'Active'),
            ('origin', 'Explicit'),
        ):
            data.add(ASSERTION, VOCAB + key, VOCAB + value)
        for key, value in (
            ('subjectLabel', 'Author'),
            ('objectLabel', 'Example'),
            ('rationale', 'Reported plan.'),
        ):
            data.add(ASSERTION, VOCAB + key, value, literal=True)
        if evidence:
            data.add(ASSERTION, DERIVED, EVIDENCE)
            data.add(EVIDENCE, VOCAB + 'revision', revision)
            data.add(EVIDENCE, VOCAB + 'quote', quote, literal=True)
            data.add(EVIDENCE, VOCAB + 'characterOffset', offset, literal=True)
            data.add(EVIDENCE, VOCAB + 'startLine', line, literal=True)
        data.add(revision, VOCAB + 'snapshotPath', snapshot, literal=True)
        data.add(revision, VOCAB + 'sha256', sha, literal=True)
        if transcription:
            path = 'sources/transcription.md'
            (self.root / path).write_bytes(text.encode())
            data.add(revision, VOCAB + 'transcriptionPath', path, literal=True)
            data.add(revision, VOCAB + 'transcriptionSha256', digest(text.encode()), literal=True)
        (self.root / 'graph').mkdir(exist_ok=True)
        (self.root / 'graph/additions.trig').write_text(data.text())
        return revision

    def decide(self, action='accept', **kwargs):
        return decide(
            self.root, ASSERTION, action, reviewer='Reviewer', reason='Checked source.', **kwargs
        )

    def rejected_accept(self):
        with self.assertRaises(ValueError):
            self.decide()
        self.assertFalse(read_events(self.root))

    def test_acceptance_rejects_wrong_unicode_offset_even_when_quote_occurs(self):
        self.fixture(offset=9)
        self.rejected_accept()

    def test_acceptance_rejects_wrong_line_even_when_quote_occurs(self):
        self.fixture(line=1)
        self.rejected_accept()

    def test_acceptance_rejects_changed_transcription_with_unchanged_notebook(self):
        self.fixture(transcription=True)
        (self.root / 'sources/transcription.md').write_text('Changed transcription.')
        self.rejected_accept()

    def test_native_historical_acceptance_keeps_original_fingerprint_replayable(self):
        revision = self.fixture(native=True)
        before = (self.root / 'graph/additions.trig').read_bytes()
        store = load_store(self.root / 'graph', history=True, include_notes=False)
        expected = fingerprint(store, ASSERTION)
        event = self.decide()
        self.assertEqual(event['fingerprint'], expected)
        self.assertEqual((self.root / 'graph/additions.trig').read_bytes(), before)
        replayed = load_store(self.root / 'graph', history=True, include_notes=False)
        self.assertEqual(fingerprint(replayed, ASSERTION), expected)
        self.assertEqual(inspect_assertion(replayed, ASSERTION)['status'], 'Accepted')
        self.assertEqual(one(replayed, EVIDENCE, VOCAB + 'revision').value, revision)

    def test_rejection_still_allows_a_wrong_locator_with_valid_original_text(self):
        self.fixture(offset=9)
        self.decide('reject')
        replayed = load_store(self.root / 'graph', history=True, include_notes=False)
        self.assertEqual(inspect_assertion(replayed, ASSERTION)['status'], 'Rejected')

    def test_assertion_without_evidence_cannot_be_accepted(self):
        self.fixture(evidence=False)
        self.rejected_accept()

    def test_accepted_replacement_requires_the_same_exact_citation_checks(self):
        self.fixture(line=1)
        with self.assertRaises(ValueError):
            self.decide(
                'correct',
                accept_replacement=True,
                replacement={
                    'subject': 'urn:person:author',
                    'predicate': VOCAB + 'relatedTo',
                    'object': 'urn:project:example',
                    'subject_label': 'Author',
                    'object_label': 'Example',
                    'rationale': 'Corrected relation.',
                },
            )
        self.assertFalse(read_events(self.root))

    def replacement(self, **changes):
        return {
            'subject': 'urn:person:author',
            'predicate': VOCAB + 'proposed',
            'object': 'urn:project:example',
            'subject_label': 'Author',
            'object_label': 'Example',
            'rationale': 'The work is still a proposal.',
            **changes,
        }

    def test_unreviewed_correction_also_rejects_an_invalid_original_locator(self):
        self.fixture(line=1)
        with self.assertRaises(ValueError):
            self.decide('correct', replacement=self.replacement())
        self.assertFalse(read_events(self.root))

    def test_correction_can_add_exact_context_from_an_existing_revision(self):
        revision = self.fixture(native=True)
        old = load_store(self.root / 'graph', history=True, include_notes=False)
        before = fingerprint(old, ASSERTION)
        quote = '# Note\r\nλ🙂 Work remains planned.\r\n'
        pin = source_pin(self.root, revision, quote, 0)
        event = self.decide('correct', replacement=self.replacement(additional_sources=[pin]))
        store = load_store(self.root / 'graph', history=True, include_notes=False)
        self.assertEqual(fingerprint(store, ASSERTION), before)
        result = inspect_assertion(store, event['replacement_id'])
        self.assertEqual(result['status'], 'Unreviewed')
        self.assertEqual(
            {e['quote'] for e in result['evidence']}, {'λ🙂 Work remains planned.', quote}
        )
        self.assertEqual(inspect_assertion(store, ASSERTION)['lifecycle'], 'Superseded')

    def test_additional_context_cannot_invent_or_ingest_a_revision(self):
        revision = self.fixture()
        pin = source_pin(self.root, revision, 'λ🙂 Work remains planned.', 8)
        pin['revision'] = 'urn:revision:unregistered'
        with self.assertRaises(ValueError):
            self.decide('correct', replacement=self.replacement(additional_sources=[pin]))
        self.assertFalse(read_events(self.root))

    def test_additional_context_requires_a_list_even_when_empty(self):
        self.fixture()
        for invalid in (None, {}, '', False):
            with self.subTest(value=invalid), self.assertRaises(ValueError):
                self.decide('correct', replacement=self.replacement(additional_sources=invalid))
        self.assertFalse(read_events(self.root))


if __name__ == '__main__':
    unittest.main()
