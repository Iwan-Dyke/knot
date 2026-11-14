"""The main launcher exposes the same checked route and receipt revalidation."""

import contextlib
import io
import json
import unittest

import test_explanations as fixture

from knot.evaluation import explanations
from knot.interfaces.note_cli import main


class TestAnswerCLI(unittest.TestCase):
    def test_unsupported_question_navigation_is_readonly(self):
        f = fixture.TestExplanations()
        f.setUp()
        self.addCleanup(f.doCleanups)
        wording = 'Why did we choose batching?'
        explanations.approve(
            f.root,
            explanations.prepare(f.root, f.request, wordings=[wording]),
            reviewer='Synthetic reviewer',
            reason='Checked meaning.',
        )
        before = {p: p.read_bytes() for p in f.root.rglob('*') if p.is_file()}
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            main(
                ['--data-root', str(f.root), 'answer', '--question', 'Explain the batching choice']
            )
        result = json.loads(output.getvalue())
        self.assertEqual(result['status'], 'unsupported_question')
        self.assertEqual(result['alternatives'][0]['question'], wording)
        self.assertNotIn('answer', result)
        self.assertEqual(before, {p: p.read_bytes() for p in f.root.rglob('*') if p.is_file()})

    def test_answer_and_revalidate_through_launcher(self):
        f = fixture.TestExplanations()
        f.setUp()
        self.addCleanup(f.doCleanups)
        f.approve()

        def call(*args):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                main(['--data-root', str(f.root), 'answer', *map(str, args)])
            return json.loads(output.getvalue())

        result = call('--question', 'Why was decision "Batching choice" chosen?')
        self.assertEqual(result['answer'], f.note['body'])
        path = f.root / 'receipt.json'
        path.write_text(json.dumps(result))
        self.assertEqual(call('--revalidate', path)['status'], 'unchanged')
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            call('--revalidate', path, '--explanation-revision', f.note['revision'])
