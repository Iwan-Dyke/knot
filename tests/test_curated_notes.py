import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from knot.access import AccessScope
from knot.notes import create_note, note_history, read_note, save_note
from knot.rdf import DERIVED, RDF_TYPE, VOCAB, Dataset
from knot.retrieval import Policy, _prepare, lookup, retrieve, serialise


class CuratedNoteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = create_note(
            self.root, 'λ🙂 Please record that delivery remains a plan.\r\n', author='Owner'
        )
        self.derivation = {
            'method': 'faithful_restatement',
            'qualification': 'A plan, not evidence of completed delivery.',
            'sources': [
                {
                    'revision': self.source['revision'],
                    'sha256': self.source['body_sha256'],
                    'text_sha256': self.source['body_sha256'],
                    'quote': 'delivery remains a plan.',
                    'character_offset': 27,
                    'start_line': 1,
                }
            ],
        }
        self.derivation['sources'][0]['character_offset'] = self.source['body'].index('delivery')

    def curated(self, **kwargs):
        return create_note(
            self.root,
            'Delivery is planned. Completion has not been established.',
            title='Delivery remains planned',
            author='Codex',
            agent='Codex',
            kind='Statement',
            derivation=kwargs.pop('derivation', self.derivation),
            **kwargs,
        )

    def scope(self, *notes):
        return AccessScope(
            revisions=tuple(sorted((n['revision'], n['body_sha256']) for n in notes))
        )

    def test_curated_revision_preserves_original_and_pins_exact_quotation(self):
        original = {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        saved = self.curated()
        self.assertEqual(saved['schema_version'], 3)
        self.assertEqual(saved['derivation'], self.derivation)
        self.assertEqual(read_note(self.root, self.source['note']), self.source)
        self.assertEqual(len(note_history(self.root, self.source['note'])), 1)
        for path, content in original.items():
            if path.name != 'registry.json':
                self.assertEqual(path.read_bytes(), content)
        self.assertNotEqual(saved['note'], self.source['note'])
        self.assertFalse((self.root / 'reviews').exists())

    def test_invalid_pin_does_not_publish_or_write_note(self):
        before = {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        for field, value in [
            ('quote', 'Completion occurred.'),
            ('character_offset', 0),
            ('sha256', '0' * 64),
            ('start_line', 2),
        ]:
            derived = json.loads(json.dumps(self.derivation))
            derived['sources'][0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.curated(derivation=derived)
            self.assertEqual(
                before, {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
            )

    def test_edit_preserves_derivation_and_requires_existing_head(self):
        saved = self.curated()
        updated = save_note(
            self.root,
            saved['note'],
            'Delivery remains planned.',
            expected=saved['revision'],
            agent='Codex',
        )
        self.assertEqual(updated['derivation'], self.derivation)
        self.assertEqual(len(note_history(self.root, saved['note'])), 2)
        with self.assertRaisesRegex(ValueError, 'head changed'):
            save_note(self.root, saved['note'], 'Stale', expected=saved['revision'])

    def test_original_cannot_be_silently_converted_to_curated_note(self):
        with self.assertRaisesRegex(ValueError, 'separate'):
            save_note(
                self.root,
                self.source['note'],
                'A paraphrase.',
                expected=self.source['revision'],
                derivation=self.derivation,
                title='Plan',
                author='Codex',
                agent='Codex',
            )

    def test_grant_to_derivative_alone_cannot_disclose_it_or_read_original(self):
        saved = self.curated()
        original = Path.read_bytes
        denied = self.root / self.source['body_path']
        manifest = (
            self.root / 'notes/revisions' / (self.source['revision'].rsplit(':', 1)[1] + '.json')
        )

        def guarded(path):
            if path in (denied, manifest):
                raise AssertionError('Denied source was read')
            return original(path)

        with patch.object(Path, 'read_bytes', guarded):
            result = lookup(self.root, 'Delivery', scope=self.scope(saved))
            self.assertFalse(result['candidates'])
            response = retrieve(
                self.root,
                None,
                Policy(max_chars=24000),
                question='What delivery is planned?',
                mode='text',
                scope=self.scope(saved),
            )
            self.assertNotIn(saved['note'], serialise(response))
            self.assertNotIn(self.source['revision'], serialise(response))

    def test_full_grants_show_authorship_qualification_and_original_pins(self):
        saved = self.curated()
        response = retrieve(
            self.root, saved['note'], Policy(max_chars=24000), scope=self.scope(saved, self.source)
        )
        source = next(s for s in response['sources'].values() if s['revision'] == saved['revision'])
        self.assertEqual(source['native_note']['author'], 'Codex')
        self.assertEqual(source['native_note']['derivation'], self.derivation)
        self.assertEqual(source['representation'], 'CuratedKnowledge')
        self.assertEqual(source['independence'], 'DerivedAccount')

    def test_changed_original_invalidates_curated_evidence(self):
        saved = self.curated()
        (self.root / self.source['body_path']).write_bytes(b'Changed source')
        response = retrieve(self.root, saved['note'], Policy(max_chars=24000))
        self.assertFalse(response['sources'])
        self.assertGreater(response['omissions']['invalid_citations'], 0)

    def test_default_budget_fits_curated_provenance_and_explicit_small_budget_is_strict(self):
        saved = self.curated()
        result = retrieve(self.root, saved['note'])
        self.assertTrue(result['sources'])
        self.assertLessEqual(len(serialise(result)), Policy().max_chars)
        small = retrieve(self.root, saved['note'], Policy(max_chars=4000))
        self.assertLessEqual(len(serialise(small)), 4000)

    def test_transitive_source_grants_are_required(self):
        first = self.curated()
        derivative = {
            'method': 'synthesis',
            'qualification': 'Still only an interpretation.',
            'sources': [
                {
                    'revision': first['revision'],
                    'sha256': first['body_sha256'],
                    'text_sha256': first['body_sha256'],
                    'quote': first['body'],
                    'character_offset': 0,
                    'start_line': 1,
                }
            ],
        }
        second = self.curated(derivation=derivative)
        self.assertFalse(
            lookup(self.root, second['note'], scope=self.scope(first, second))['candidates']
        )
        self.assertTrue(
            lookup(self.root, second['note'], scope=self.scope(self.source, first, second))[
                'candidates'
            ]
        )

    def test_graph_claim_citing_derivative_requires_original_grant(self):
        saved = self.curated()
        data = Dataset()
        assertion, evidence = 'urn:test:derived-claim', 'urn:test:derived-evidence'
        data.add('urn:test:actor', VOCAB + 'relatedTo', 'urn:test:project', graph=assertion)
        data.add(assertion, RDF_TYPE, VOCAB + 'Assertion')
        data.add(assertion, DERIVED, evidence)
        for key, value in [
            ('reviewStatus', 'Unreviewed'),
            ('origin', 'Explicit'),
            ('lifecycle', 'Active'),
        ]:
            data.add(assertion, VOCAB + key, VOCAB + value)
        for key, value in [
            ('subjectLabel', 'Hidden actor'),
            ('objectLabel', 'Hidden project'),
            ('rationale', 'Derived claim'),
        ]:
            data.add(assertion, VOCAB + key, value, literal=True)
        data.add(evidence, VOCAB + 'revision', saved['revision'])
        data.add(evidence, VOCAB + 'quote', saved['body'], literal=True)
        data.add(evidence, VOCAB + 'characterOffset', 0, literal=True)
        data.add(evidence, VOCAB + 'startLine', 1, literal=True)
        data.add(saved['revision'], VOCAB + 'snapshotPath', saved['body_path'], literal=True)
        data.add(saved['revision'], VOCAB + 'sha256', saved['body_sha256'], literal=True)
        (self.root / 'graph').mkdir()
        (self.root / 'graph/additions.trig').write_text(data.text())
        denied = _prepare(self.root, scope=self.scope(saved))
        self.assertFalse(denied[2])
        self.assertFalse(denied[3])
        allowed = _prepare(self.root, scope=self.scope(saved, self.source))
        self.assertEqual([record['id'] for record in allowed[2]], [assertion])


if __name__ == '__main__':
    unittest.main()
