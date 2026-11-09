import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pyoxigraph import Store

from knot.inventory import digest
from knot.notes import create_note, save_note
from knot.provenance import MAX_DERIVATION_DEPTH, source_pin, validate_derivation, validate_sources
from knot.rdf import VOCAB, Dataset


class ProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def source(self, text='First line.\nλ🙂 Exact evidence.\n', *, transcription=False):
        self.root.joinpath('sources').mkdir(exist_ok=True)
        raw = b'preserved binary notebook' if transcription else text.encode('utf-8')
        path = 'sources/original.rmdoc' if transcription else 'sources/original.md'
        self.root.joinpath(path).write_bytes(raw)
        revision = 'urn:revision:' + digest(raw)
        data = Dataset()
        data.add(revision, VOCAB + 'snapshotPath', path, literal=True)
        data.add(revision, VOCAB + 'sha256', digest(raw), literal=True)
        if transcription:
            self.root.joinpath('sources/transcription.md').write_bytes(text.encode('utf-8'))
            data.add(
                revision, VOCAB + 'transcriptionPath', 'sources/transcription.md', literal=True
            )
            data.add(revision, VOCAB + 'transcriptionSha256', digest(text.encode()), literal=True)
        self.root.joinpath('graph').mkdir(exist_ok=True)
        self.root.joinpath('graph/knowledge.trig').write_text(data.text())
        return revision, text

    def test_pin_preserves_exact_unicode_quote_and_line(self):
        revision, text = self.source()
        quote = 'λ🙂 Exact evidence.'
        pin = source_pin(self.root, revision, quote, text.index(quote))
        self.assertEqual(pin['quote'], quote)
        self.assertEqual(pin['character_offset'], 12)
        self.assertEqual(pin['start_line'], 2)
        self.assertEqual(pin['sha256'], digest(text.encode()))
        self.assertEqual(pin['text_sha256'], pin['sha256'])
        before = {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        validate_sources(self.root, [pin])
        self.assertEqual(before, {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()})

    def test_structure_rejects_unknown_fields_bad_hashes_and_boolean_offsets(self):
        revision, text = self.source()
        pin = source_pin(self.root, revision, 'Exact evidence.', text.index('Exact'))
        derivation = {
            'method': 'faithful_restatement',
            'qualification': 'Attributed.',
            'sources': [pin],
        }
        validate_derivation(None)
        validate_derivation(derivation)
        invalid = [
            {},
            {**derivation, 'method': 'verified_fact'},
            {**derivation, 'qualification': ' '},
            {**derivation, 'extra': 'ignored'},
            {**derivation, 'sources': []},
            {**derivation, 'sources': 'not a list'},
        ]
        for field, value in (
            ('revision', 'relative'),
            ('sha256', 'f' * 63),
            ('text_sha256', None),
            ('quote', ''),
            ('character_offset', True),
            ('character_offset', -1),
            ('start_line', 0),
            ('start_line', 1.0),
            ('ignored', 'value'),
        ):
            invalid.append({**derivation, 'sources': [{**pin, field: value}]})
        with patch.object(Path, 'read_bytes', side_effect=AssertionError('Structural check read')):
            for value in invalid:
                with self.subTest(value=value), self.assertRaises(ValueError):
                    validate_derivation(value)

    def test_rejects_paraphrase_wrong_offset_wrong_line_and_wrong_hash(self):
        revision, text = self.source()
        pin = source_pin(self.root, revision, 'Exact evidence.', text.index('Exact'))
        for field, value in (
            ('quote', 'A clear paraphrase.'),
            ('character_offset', 0),
            ('start_line', 1),
            ('sha256', '0' * 64),
            ('text_sha256', '0' * 64),
        ):
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_sources(self.root, [{**pin, field: value}])
        with self.assertRaises(ValueError):
            source_pin(self.root, revision, 'A clear paraphrase.', 0)

    def test_snapshot_and_transcription_hashes_are_independently_pinned(self):
        revision, text = self.source(transcription=True)
        pin = source_pin(self.root, revision, 'Exact evidence.', text.index('Exact'))
        self.assertNotEqual(pin['sha256'], pin['text_sha256'])
        validate_sources(self.root, [pin])
        self.root.joinpath('sources/transcription.md').write_text('Changed transcription.')
        with self.assertRaises(ValueError):
            validate_sources(self.root, [pin])
        self.root.joinpath('sources/transcription.md').write_bytes(text.encode())
        self.root.joinpath('sources/original.rmdoc').write_bytes(b'Changed source')
        with self.assertRaises(ValueError):
            validate_sources(self.root, [pin])

    def test_native_historical_revision_survives_a_new_head(self):
        first = create_note(
            self.root, '\ufeffOriginal.\r\nExact evidence.\r\n', author='Source Author'
        )
        latest = save_note(self.root, first['note'], 'New version.', expected=first['revision'])
        pin = source_pin(self.root, first['revision'], 'Exact evidence.', 12)
        self.assertEqual(pin['sha256'], first['body_sha256'])
        self.assertNotEqual(pin['sha256'], latest['body_sha256'])
        self.assertEqual(pin['start_line'], 2)
        validate_sources(self.root, [pin])

    def test_unpublished_native_revision_is_not_a_source(self):
        note = create_note(self.root, 'Exact evidence.')
        unknown = 'urn:knot:note-revision:' + '0' * 64
        with self.assertRaises(ValueError):
            source_pin(self.root, unknown, note['body'], 0)

    def test_supplied_store_is_an_access_boundary_and_is_not_expanded(self):
        note = create_note(self.root, 'Denied native evidence.')
        pin = source_pin(self.root, note['revision'], note['body'], 0)
        allowed = Store()
        with patch('knot.note_sources.add_note_sources', side_effect=AssertionError('Denied read')):
            with self.assertRaises(ValueError):
                validate_sources(self.root, [pin], store=allowed)
        self.assertEqual(len(allowed), 0)

    def test_multiple_spans_from_one_source_do_not_require_duplicate_revisions(self):
        revision, text = self.source()
        first = source_pin(self.root, revision, 'First line.', 0)
        second = source_pin(self.root, revision, 'Exact evidence.', text.index('Exact'))
        validate_sources(self.root, [first, second])
        self.assertEqual(first['revision'], second['revision'])

    def test_nested_derivation_checks_the_original_and_detects_cycles(self):
        revision, text = self.source()
        source = source_pin(self.root, revision, 'Exact evidence.', text.index('Exact'))
        derived_revision = 'urn:revision:derived'
        derived_text = 'Readable interpretation.'
        derivation = {
            'method': 'synthesis',
            'qualification': 'Interpretation.',
            'sources': [source],
        }
        derived = {
            'revision': derived_revision,
            'sha256': digest(derived_text.encode()),
            'text_sha256': digest(derived_text.encode()),
            'quote': derived_text,
            'character_offset': 0,
            'start_line': 1,
        }
        answers = {
            revision: (text, {**source}),
            derived_revision: (
                derived_text,
                {**derived, 'native_note': {'derivation': derivation}},
            ),
        }
        from knot.retrieval import _Evidence

        with patch.object(_Evidence, 'revision', side_effect=lambda key, **kwargs: answers[key]):
            self.assertEqual(
                validate_sources(self.root, [derived], store=Store()), [source['sha256']]
            )
            answers[revision][1]['sha256'] = '0' * 64
            with self.assertRaises(ValueError):
                validate_sources(self.root, [derived], store=Store())
            answers[revision][1]['sha256'] = source['sha256']
            derivation['sources'] = [copy.deepcopy(derived)]
            with self.assertRaisesRegex(ValueError, 'Cycl'):
                validate_sources(self.root, [derived], store=Store())

    def test_retrieval_reader_shares_revision_budget_and_does_not_read_excess_sources(self):
        from knot.retrieval import _Evidence, _prepare

        notes = [create_note(self.root, f'Original source {i}.') for i in range(3)]
        pins = [source_pin(self.root, note['revision'], note['body'], 0) for note in notes]
        store = _prepare(self.root)[0]
        reader = _Evidence(self.root, store, max_revisions=2)
        denied_body = self.root / notes[-1]['body_path']
        original = Path.read_bytes

        def guarded(path):
            if path == denied_body:
                raise AssertionError('Source beyond the revision budget was read')
            return original(path)

        with patch.object(Path, 'read_bytes', guarded):
            with self.assertRaisesRegex(ValueError, 'SourceRevisionBudget'):
                validate_sources(self.root, pins, reader=reader)
        self.assertEqual(len(reader.attempted), 2)
        self.assertNotIn(notes[-1]['revision'], reader.cache)

    def test_shared_reader_reuses_verified_source_bytes_and_returns_leaf_accounts(self):
        from knot.retrieval import _Evidence, _prepare

        note = create_note(self.root, 'Original source.')
        pin = source_pin(self.root, note['revision'], note['body'], 0)
        store = _prepare(self.root)[0]
        reader = _Evidence(self.root, store, max_revisions=1)
        first = validate_sources(self.root, [pin], reader=reader)
        with patch.object(Path, 'read_bytes', side_effect=AssertionError('Verified source reread')):
            second = validate_sources(self.root, [pin, pin], reader=reader)
        self.assertEqual(first, [note['body_sha256']])
        self.assertEqual(first, second)
        with self.assertRaisesRegex(ValueError, 'eligible store'):
            validate_sources(self.root, [pin], store=Store(), reader=reader)

    def test_deep_derivation_fails_explicitly_before_python_recursion_limit(self):
        from knot.retrieval import _Evidence

        answers, pins, previous = {}, [], None
        for index in range(MAX_DERIVATION_DEPTH + 1):
            text = f'Account {index}.'
            pin = {
                'revision': f'urn:revision:{index}',
                'sha256': digest(text.encode()),
                'text_sha256': digest(text.encode()),
                'quote': text,
                'character_offset': 0,
                'start_line': 1,
            }
            metadata = {**pin}
            if previous is not None:
                metadata['native_note'] = {
                    'derivation': {
                        'method': 'synthesis',
                        'qualification': 'Derived account.',
                        'sources': [previous],
                    }
                }
            answers[pin['revision']] = (text, metadata)
            pins.append(pin)
            previous = pin
        with patch.object(_Evidence, 'revision', side_effect=lambda key, **kwargs: answers[key]):
            self.assertEqual(
                validate_sources(self.root, [pins[-2]], store=Store()), [pins[0]['sha256']]
            )
            with self.assertRaisesRegex(ValueError, 'maximum depth'):
                validate_sources(self.root, [pin], store=Store())
            # Ascending inputs cache each ancestor before its descendants. The
            # same depth bound must hold regardless of this traversal order.
            with self.assertRaisesRegex(ValueError, 'maximum depth'):
                validate_sources(self.root, pins, store=Store())

    def test_scoped_closure_uses_the_same_input_edge_boundary(self):
        from knot.access import AccessScope
        from knot.note_sources import curated_scope

        saved, history, sources = {}, {}, []
        for index in range(MAX_DERIVATION_DEPTH + 2):
            revision = 'urn:knot:note-revision:' + f'{index:064x}'
            body_hash = digest(f'Account {index}.'.encode())
            value = {'body_sha256': body_hash}
            if sources:
                value['derivation'] = {
                    'method': 'synthesis',
                    'qualification': 'Attributed.',
                    'sources': [sources[-1]],
                }
            sources.append({'revision': revision, 'sha256': body_hash})
            saved[revision] = value
            history[f'urn:note:{index}'] = [revision]

        registry = {'schema_version': 2, 'history': history}
        boundary = AccessScope(revisions=tuple((p['revision'], p['sha256']) for p in sources[:-1]))
        beyond = AccessScope(revisions=tuple((p['revision'], p['sha256']) for p in sources))
        with (
            patch('knot.note_sources._registry', return_value=registry),
            patch(
                'knot.note_sources._read_revision',
                side_effect=lambda root, note, rev, **kw: saved[rev],
            ),
        ):
            self.assertEqual(curated_scope(self.root, boundary), boundary)
            with self.assertRaisesRegex(ValueError, '32 input edges'):
                curated_scope(self.root, beyond)


if __name__ == '__main__':
    unittest.main()
