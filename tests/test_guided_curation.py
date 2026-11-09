import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from uuid import uuid4

from knot.curating.provenance import validate_sources
from knot.curating.rules import DOMAIN_PREDICATES
from knot.graph.query import load_store
from knot.graph.rdf import VOCAB, Dataset
from knot.reviewing.state import inspect_assertion
from knot.shared.storage import digest
from knot.shared.vocabulary import TYPES
from knot.writing.notes import create_note, list_notes, note_history, read_note, save_note


class GuidedCurationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / 'dataset'

    def cli(self, *arguments, answers='', success=True):
        result = subprocess.run(
            [
                sys.executable,
                '-m',
                'knot.interfaces.note_cli',
                '--data-root',
                str(self.root),
                *arguments,
            ],
            input=answers,
            text=True,
            capture_output=True,
            env={**os.environ, 'KNOT_CONFIG': str(Path(self.tmp.name) / 'config.json')},
        )
        self.assertEqual(result.returncode == 0, success, result.stderr)
        self.assertNotIn('Traceback', result.stderr)
        return result

    def source(self):
        return create_note(
            self.root,
            'Introduction.\r\nλ🙂 Practice remains a proposal.\r\nPractice remains a proposal.\r\n',
            title='Learning proposal',
            author='Source writer',
        )

    def writing(self, method=1):
        return (
            f'{method}\nA proposal, without an established outcome.\nPractice proposal\nCurator\n\n'
            'Practice is proposed; no outcome is established.\n/done\n'
        )

    def selected_source(self):
        return 'Learning proposal\n1\n1\n2\nn\n\n'

    def test_curate_creates_entity_and_exact_pins_without_changing_original(self):
        source = self.source()
        concept = sorted(TYPES).index('Concept') + 1
        result = self.cli(
            'curate',
            answers=(
                'Learning proposal\n1\n2\nPractice remains a proposal.\n2\nn\n\n'
                + self.writing()
                + f'3\n3\nPlanned practice\n1\nPlanned practice\n{concept}\n'
                'Practice is proposed\n\n9\ny\n'
            ),
        )
        saved = json.loads(result.stdout)
        current = read_note(self.root, saved['note'])
        self.assertNotEqual(saved['note'], source['note'])
        self.assertEqual(read_note(self.root, source['note']), source)
        self.assertEqual(len(note_history(self.root, source['note'])), 1)
        self.assertEqual(current['author'], 'Curator')
        self.assertEqual(current['agent'], 'knot-cli')
        self.assertEqual(current['navigation']['declarations'][0]['label'], 'Planned practice')
        pin = current['derivation']['sources'][0]
        self.assertEqual(pin['revision'], source['revision'])
        self.assertEqual(pin['character_offset'], source['body'].rindex('Practice'))
        self.assertEqual(pin['start_line'], 3)
        self.assertEqual(validate_sources(self.root, [pin]), [source['body_sha256']])
        self.assertIn('Source writer', result.stderr)
        self.assertIn('A proposal, without an established outcome.', result.stderr)
        self.assertIn('knot view', result.stderr)
        self.assertEqual(saved['assertions'], [])

    def test_interrupted_source_selection_resumes_with_pinned_old_revision(self):
        source = self.source()
        self.cli('curate', answers='Learning proposal\n1\n1\n2-3\nn\n', success=False)
        (draft_path,) = (self.root / 'drafts').glob('*.json')
        draft = json.loads(draft_path.read_text())
        self.assertEqual(len(list_notes(self.root)), 1)
        saved_source = save_note(
            self.root, source['note'], 'A later account.', expected=source['revision']
        )
        result = self.cli('resume', str(draft_path), answers='\n' + self.writing() + '9\ny\n')
        saved = json.loads(result.stdout)
        self.assertEqual(saved['note'], draft['note'])
        pin = saved['derivation']['sources'][0]
        self.assertEqual(pin['revision'], source['revision'])
        self.assertEqual(pin['quote'], ''.join(source['body'].splitlines(keepends=True)[1:]))
        self.assertEqual(pin['start_line'], 2)
        self.assertEqual(read_note(self.root, source['note']), saved_source)
        again = self.cli('resume', str(draft_path), answers='9\ny\n')
        self.assertEqual(json.loads(again.stdout)['revision'], saved['revision'])
        self.assertEqual(len(list_notes(self.root)), 2)

    def test_registered_transcription_keeps_original_and_text_hashes_distinct(self):
        (self.root / 'sources').mkdir(parents=True)
        (self.root / 'graph').mkdir()
        original, text = b'Preserved synthetic document', 'A practice proposal.\nNo outcome yet.\n'
        (self.root / 'sources/report.bin').write_bytes(original)
        (self.root / 'sources/transcription.txt').write_bytes(text.encode())
        revision = 'urn:revision:' + digest(original)
        data = Dataset()
        for key, value in (
            ('snapshotPath', 'sources/report.bin'),
            ('sha256', digest(original)),
            ('transcriptionPath', 'sources/transcription.txt'),
            ('transcriptionSha256', digest(text.encode())),
        ):
            data.add(revision, VOCAB + key, value, literal=True)
        (self.root / 'graph/source.trig').write_text(data.text())
        result = self.cli(
            'curate', answers='report.bin\n1\n1\n1-2\nn\n\n' + self.writing() + '3\n9\ny\n'
        )
        saved = json.loads(result.stdout)
        pin = saved['derivation']['sources'][0]
        self.assertEqual(pin['quote'], text)
        self.assertEqual(pin['sha256'], digest(original))
        self.assertEqual(pin['text_sha256'], digest(text.encode()))
        self.assertIn('StoredTranscription', result.stderr)
        self.assertEqual((self.root / 'sources/report.bin').read_bytes(), original)

    def test_empty_dataset_explains_how_to_capture_a_source(self):
        result = self.cli('curate', success=False)
        self.assertIn('No saved sources', result.stderr)
        self.assertIn('knot add', result.stderr)
        self.assertEqual(list_notes(self.root), [])

    def test_unreadable_imported_source_can_be_skipped_without_losing_the_draft(self):
        source = self.source()
        body = b'Synthetic image with no registered transcription'
        (self.root / 'sources/image.bin').write_bytes(body)
        (self.root / 'graph').mkdir()
        data = Dataset()
        revision = 'urn:revision:' + digest(body)
        data.add(revision, VOCAB + 'snapshotPath', 'sources/image.bin', literal=True)
        data.add(revision, VOCAB + 'sha256', digest(body), literal=True)
        (self.root / 'graph/source.trig').write_text(data.text())
        result = self.cli(
            'curate',
            answers='image.bin\n1\n' + self.selected_source() + self.writing() + '3\n9\ny\n',
        )
        self.assertIn('Cannot use this source', result.stderr)
        saved = json.loads(result.stdout)
        self.assertEqual(
            [p['revision'] for p in saved['derivation']['sources']], [source['revision']]
        )

    def test_multiple_sources_deduplicate_passages_and_reuse_entities(self):
        source = self.source()
        other = create_note(self.root, 'Practice may help.', title='Another proposal')
        entity = 'urn:knot:entity:' + str(uuid4())
        create_note(
            self.root,
            'Practice concept',
            navigation={
                'themes': [],
                'links': [],
                'declarations': [
                    {
                        'id': entity,
                        'label': 'Practice concept',
                        'type': 'Concept',
                        'quote': 'Practice concept',
                        'offset': 0,
                    },
                ],
            },
        )
        (self.root / 'organisation').mkdir()
        (self.root / 'organisation/catalogue.json').write_text(
            json.dumps(
                {
                    'themes': [{'id': 'learning', 'label': 'Learning', 'keywords': []}],
                }
            )
        )
        result = self.cli(
            'curate',
            answers=(
                'Learning proposal\n1\n1\n2\ny\n1\n2\nn\n'
                'Another proposal\n1\n1\n1\nn\n\n'
                + self.writing(method=2)
                + '1\n1\nLearning proposal\n1\nProvides the original account\n'
                'Practice concept\n1\n\nn\n9\ny\n'
            ),
        )
        saved = json.loads(result.stdout)
        self.assertEqual(saved['derivation']['method'], 'synthesis')
        self.assertEqual(len(saved['derivation']['sources']), 2)
        self.assertEqual(
            {p['revision'] for p in saved['derivation']['sources']},
            {source['revision'], other['revision']},
        )
        self.assertEqual(saved['entities'], [entity])
        self.assertEqual(saved['navigation']['links'][0]['note'], source['note'])
        self.assertEqual(saved['navigation']['themes'][0]['id'], 'learning')
        self.assertEqual(read_note(self.root, source['note']), source)

    def test_invalid_passages_and_declined_save_leave_only_a_draft(self):
        source = self.source()
        result = self.cli(
            'curate',
            answers=(
                'Learning proposal\n1\n1\n0\n3-2\n999\n2\ny\n2\nInvented outcome\n'
                'Practice remains a proposal.\n1\nn\n\n' + self.writing() + '3\n9\nn\n10\n'
            ),
        )
        self.assertFalse(json.loads(result.stdout)['published'])
        self.assertIn('Choose an existing line', result.stderr)
        self.assertIn('That passage is not in the source', result.stderr)
        self.assertNotIn('knot view', result.stderr)
        self.assertEqual(list_notes(self.root), [source])

    def test_sources_and_qualification_can_be_changed_before_save(self):
        source = self.source()
        result = self.cli(
            'curate',
            answers=(
                self.selected_source()
                + self.writing()
                + '3\n11\n/remove\n1\nLearning proposal\n1\n1\n3\nn\n\n\n'
                'The proposal is still untested.\n9\ny\n'
            ),
        )
        saved = json.loads(result.stdout)
        self.assertEqual(saved['derivation']['qualification'], 'The proposal is still untested.')
        self.assertEqual(len(saved['derivation']['sources']), 1)
        self.assertEqual(saved['derivation']['sources'][0]['start_line'], 3)
        self.assertEqual(read_note(self.root, source['note']), source)

    def test_tampered_pin_cannot_publish_a_resumed_draft(self):
        source = self.source()
        result = self.cli('curate', answers=self.selected_source() + self.writing() + '3\n10\n')
        path = Path(json.loads(result.stdout)['draft'])
        draft = json.loads(path.read_text())
        draft['metadata']['derivation']['sources'][0]['sha256'] = '0' * 64
        path.write_text(json.dumps(draft))
        result = self.cli('resume', str(path), answers='9\n10\n')
        self.assertIn('Provenance source hash mismatch', result.stderr)
        self.assertFalse(json.loads(result.stdout)['published'])
        self.assertEqual(list_notes(self.root), [source])

    def test_curated_relationship_keeps_transitive_sources_and_unreviewed_status(self):
        source = self.source()
        concept = sorted(TYPES).index('Concept') + 1
        predicate = sorted(DOMAIN_PREDICATES - {'eventCount', 'occurredOn'}).index('relatedTo') + 1
        result = self.cli(
            'curate',
            answers=(
                self.selected_source()
                + self.writing()
                + f'3\n3\nPlanned practice\n1\nPlanned practice\n{concept}\n'
                'Practice is proposed\n\n4\ny\n1\n'
                + f'{predicate}\n2\nPractice is proposed\n1\nThis note discusses the proposal.\n\ny\nn\n9\ny\n'
            ),
        )
        saved = json.loads(result.stdout)
        (assertion,) = saved['assertions']
        detail = inspect_assertion(load_store(self.root / 'graph'), assertion['assertion'])
        self.assertEqual(detail['status'], 'Unreviewed')
        self.assertEqual(assertion['source_accounts'], [source['body_sha256']])
        self.assertEqual(read_note(self.root, source['note']), source)
        before = (self.root / 'graph/additions.trig').read_bytes()
        again = self.cli('resume', saved['draft'], answers='9\ny\n')
        self.assertEqual(json.loads(again.stdout)['revision'], saved['revision'])
        self.assertEqual((self.root / 'graph/additions.trig').read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
