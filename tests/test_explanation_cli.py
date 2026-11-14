"""Exercise owner preparation, explicit review and withdrawal through the launcher."""

import contextlib
import io
import json
import unittest

import test_explanations as fixture

from knot.interfaces.note_cli import main


class TestExplanationCLI(unittest.TestCase):
    def test_review_alternative_wordings_and_clear_them_explicitly(self):
        f = fixture.TestExplanations()
        f.setUp()
        self.addCleanup(f.doCleanups)
        request = f.root / 'request.json'
        request.write_text(json.dumps(f.request))

        def call(*args):
            stream = io.StringIO()
            with contextlib.redirect_stdout(stream):
                main(['--data-root', str(f.root), *map(str, args)])
            return json.loads(stream.getvalue())

        wordings = ['Why did we choose batching?', 'What made batching preferable?']
        preview = call(
            'explain', 'prepare', request, '--wording', wordings[0], '--wording', wordings[1]
        )
        self.assertEqual(preview['wordings'], wordings)
        path = f.root / 'preview.json'
        path.write_text(json.dumps(preview))
        self.assertEqual(
            call('answer', '--question', wordings[0])['status'], 'unsupported_question'
        )
        call(
            'explain',
            'approve',
            path,
            '--reviewer',
            'Synthetic reviewer',
            '--reason',
            'Checked meanings.',
        )
        self.assertEqual(call('answer', '--question', wordings[1])['answer'], f.note['body'])
        self.assertEqual(call('explain', 'prepare', request)['wordings'], wordings)
        cleared = call('explain', 'prepare', request, '--clear-wordings')
        self.assertEqual(cleared['wordings'], [])
        path.write_text(json.dumps(cleared))
        call(
            'explain',
            'approve',
            path,
            '--reviewer',
            'Synthetic reviewer',
            '--reason',
            'Retire wordings.',
        )
        self.assertEqual(
            call('answer', '--question', wordings[0])['status'], 'unsupported_question'
        )

    def test_complete_workflow_preserves_immutable_review_history(self):
        f = fixture.TestExplanations()
        f.setUp()
        self.addCleanup(f.doCleanups)
        request = f.root / 'request.json'
        request.write_text(json.dumps(f.request))

        def call(*args):
            stream = io.StringIO()
            with contextlib.redirect_stdout(stream):
                main(['--data-root', str(f.root), 'explain', *map(str, args)])
            return json.loads(stream.getvalue())

        preview = call('prepare', request)
        path = f.root / 'preview.json'
        path.write_text(json.dumps(preview))
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            call('approve', path)
        event = call(
            'approve',
            path,
            '--reviewer',
            'Synthetic reviewer',
            '--reason',
            'Checked the exact preview.',
        )
        answered = call('answer', request)
        self.assertEqual(answered['status'], 'approved')
        self.assertEqual(answered['answer'], f.note['body'])
        receipt = f.root / 'receipt.json'
        receipt.write_text(json.dumps(answered))
        self.assertEqual(call('revalidate', receipt)['status'], 'unchanged')
        call(
            'withdraw',
            request,
            '--expected',
            event['event_sha256'],
            '--reviewer',
            'Synthetic reviewer',
            '--reason',
            'Withdraw this wording.',
        )
        self.assertEqual(call('answer', request)['status'], 'unknown')
        self.assertEqual(len(call('history', request)), 2)
