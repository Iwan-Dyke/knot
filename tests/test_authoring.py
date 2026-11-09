import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from knot.authoring import new_draft, publish_draft
from knot.inventory import atomic_json
from knot.notes import list_notes
from knot.retrieval import lookup


class AuthoringTests(unittest.TestCase):
    def test_defer_saves_note_and_pinned_agent_task_without_running_an_agent(self):
        answers = '\n\n\nA thought\n/done\n' + '2\ny\n'
        result = subprocess.run(
            [sys.executable, '-m', 'knot.note_cli', '--data-root', str(self.root), 'add'],
            input=answers,
            text=True,
            capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        saved = json.loads(result.stdout)
        self.assertEqual(len(list_notes(self.root)), 1)
        self.assertEqual(saved['assertions'], [])
        task = Path(saved['agent_task']).read_text()
        self.assertIn(saved['note'], task)
        self.assertIn(saved['revision'], task)
        self.assertIn(saved['body_sha256'], task)
        self.assertIn('Unreviewed', task)
        self.assertFalse((self.root / 'graph/additions.trig').exists())

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def draft(self):
        eid = 'urn:knot:entity:00000000-0000-4000-8000-000000000001'
        body = 'Learning connects to practice.'
        draft = new_draft(
            body,
            {
                'title': 'Learning',
                'author': 'Writer',
                'navigation': {
                    'themes': [],
                    'links': [],
                    'declarations': [
                        {
                            'id': eid,
                            'label': 'Learning',
                            'type': 'Concept',
                            'quote': 'Learning',
                            'offset': 0,
                        }
                    ],
                },
            },
            root=self.root,
        )
        draft['relationships'] = [
            {
                'id': 'urn:knot:assertion:00000000-0000-4000-8000-000000000001',
                'subject': {'id': eid, 'label': 'Learning'},
                'predicate': 'urn:knot:vocab:documentedIn',
                'object': {'id': draft['note'], 'label': 'Learning'},
                'origin': 'Explicit',
                'rationale': 'The note discusses learning.',
                'quote': body,
                'offset': 0,
                'generated_at': '2026-11-06T12:00:00+00:00',
            }
        ]
        path = self.root / 'draft.json'
        atomic_json(path, draft)
        return path

    def test_publication_is_resumable_without_duplicate_note_or_assertion(self):
        path = self.draft()
        with patch('knot.authoring.publish_candidate', side_effect=OSError('Interrupted')):
            with self.assertRaises(OSError):
                publish_draft(self.root, path)
        self.assertEqual(len(list_notes(self.root)), 1)
        saved = publish_draft(self.root, path)
        before = (self.root / 'graph/additions.trig').read_bytes()
        again = publish_draft(self.root, path)
        self.assertEqual(saved['note'], again['note'])
        self.assertEqual(len(list_notes(self.root)), 1)
        self.assertFalse(again['assertions'][0]['created'])
        self.assertEqual((self.root / 'graph/additions.trig').read_bytes(), before)
        self.assertTrue(lookup(self.root, 'Learning')['candidates'])
        self.assertIn(b'Unreviewed', before)

    def test_bad_quote_fails_before_note_is_saved(self):
        path = self.draft()
        draft = json.loads(path.read_bytes())
        draft['relationships'][0]['quote'] = 'An invented claim'
        atomic_json(path, draft)
        with self.assertRaises(ValueError):
            publish_draft(self.root, path)
        self.assertEqual(list_notes(self.root), [])

    def test_relationships_inherit_themes_and_are_filterable_after_publish(self):
        from knot.knowledge import entries
        from knot.query import load_store

        (self.root / 'organisation').mkdir()
        (self.root / 'organisation/catalogue.json').write_text(
            json.dumps({'themes': [{'id': 'learning', 'label': 'Learning', 'keywords': []}]})
        )
        path = self.draft()
        draft = json.loads(path.read_bytes())
        draft['metadata']['navigation']['themes'] = [{'id': 'learning', 'label': 'Learning'}]
        draft['metadata']['kind'] = 'Thought'
        atomic_json(path, draft)
        publish_draft(self.root, path)
        records = entries(load_store(self.root / 'graph'), themes=['learning'], kind='Thought')
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]['status'], 'Unreviewed')
        self.assertEqual(records[0]['themes'][0]['status'], 'Unreviewed')

    def test_resume_cannot_switch_dataset(self):
        path = self.draft()
        with self.assertRaises(ValueError):
            publish_draft(self.root / 'other', path)
        self.assertFalse((self.root / 'other/notes').exists())

    def test_resume_picker_selects_by_title_and_can_cancel(self):
        directory = self.root / 'drafts'
        directory.mkdir()
        for name in ('First thought', 'Second thought'):
            draft = new_draft(
                'Some writing',
                {
                    'title': name,
                    'entities': [],
                    'navigation': {'themes': [], 'links': [], 'declarations': []},
                },
                root=self.root,
            )
            atomic_json(directory / f'{name}.json', draft)
        command = [sys.executable, '-m', 'knot.note_cli', '--data-root', str(self.root), 'resume']
        result = subprocess.run(command, input='99\n1\n10\n', text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('First thought', result.stderr)
        self.assertIn('Second thought', result.stderr)
        self.assertIn('Use the displayed number', result.stderr)
        self.assertEqual(Path(json.loads(result.stdout)['draft']).name, 'Second thought.json')
        before = {p.name: p.read_bytes() for p in directory.iterdir()}
        result = subprocess.run(command, input='\n', text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(before, {p.name: p.read_bytes() for p in directory.iterdir()})
        self.assertEqual(list_notes(self.root), [])

    def test_resume_without_drafts_is_helpful(self):
        result = subprocess.run(
            [sys.executable, '-m', 'knot.note_cli', '--data-root', str(self.root), 'resume'],
            input='',
            text=True,
            capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('No drafts found', result.stderr)

    def test_skipping_organisation_opens_menu_without_guided_prompts(self):
        result = subprocess.run(
            [sys.executable, '-m', 'knot.note_cli', '--data-root', str(self.root), 'add'],
            input='A thought\n\n\nSome writing.\n/done\n\n10\n',
            text=True,
            capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn('Find a related note by title or text:', result.stderr)
        self.assertFalse(json.loads(result.stdout)['published'])
        self.assertNotIn('knot view', result.stderr)

    def test_skipping_themes_preserves_selection_and_review_is_readable(self):
        (self.root / 'organisation').mkdir()
        (self.root / 'organisation/catalogue.json').write_text(
            json.dumps({'themes': [{'id': 'learning', 'label': 'Learning', 'keywords': []}]})
        )
        result = subprocess.run(
            [sys.executable, '-m', 'knot.note_cli', '--data-root', str(self.root), 'add'],
            input='A thought\nWriter\nThought\nFirst paragraph.\n\nSecond paragraph.\n/done\n'
            '3\n1\n1\n1\n\n6\n10\n',
            text=True,
            capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        draft = json.loads(Path(json.loads(result.stdout)['draft']).read_text())
        self.assertEqual(
            draft['metadata']['navigation']['themes'], [{'id': 'learning', 'label': 'Learning'}]
        )
        review = result.stderr.split('Review your note')[-1]
        self.assertIn('Themes: Learning', review)
        self.assertIn('First paragraph.\n\nSecond paragraph.', review)
        self.assertNotIn('"metadata":', review)

    def test_full_cli_can_review_save_and_resume(self):
        answers = '\n\n\nA thought\n/done\n' + '3\n9\ny\n'
        result = subprocess.run(
            [sys.executable, '-m', 'knot.note_cli', '--data-root', str(self.root), 'add'],
            input=answers,
            text=True,
            capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('knot view', result.stderr)
        saved = json.loads(result.stdout)
        self.assertEqual(len(list_notes(self.root)), 1)
        result = subprocess.run(
            [
                sys.executable,
                '-m',
                'knot.note_cli',
                '--data-root',
                str(self.root),
                'resume',
                saved['draft'],
            ],
            input='9\ny\n',
            text=True,
            capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['note'], saved['note'])
        self.assertIn('knot view', result.stderr)

    def test_guided_cli_selects_theme_link_and_creates_entity(self):
        from knot.knowledge import TYPES
        from knot.notes import create_note, read_note

        (self.root / 'organisation').mkdir()
        (self.root / 'organisation/catalogue.json').write_text(
            json.dumps({'themes': [{'id': 'learning', 'label': 'Learning', 'keywords': []}]})
        )
        target = create_note(self.root, 'Earlier writing', title='Earlier')
        concept = sorted(TYPES).index('Concept') + 1
        answers = (
            'New thought\nWriter\nThought\nLearning is useful.\n/done\n'
            + '1\n1\nEarlier\n1\nExtends it\nLearning\n1\nLearning\n'
            + f'{concept}\nLearning\n\nn\n9\ny\n'
        )
        result = subprocess.run(
            [sys.executable, '-m', 'knot.note_cli', '--data-root', str(self.root), 'add'],
            input=answers,
            text=True,
            capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        saved = read_note(self.root, json.loads(result.stdout)['note'])
        self.assertEqual(saved['navigation']['themes'][0]['id'], 'learning')
        self.assertEqual(saved['navigation']['links'][0]['note'], target['note'])
        self.assertEqual(saved['navigation']['declarations'][0]['type'], 'Concept')
