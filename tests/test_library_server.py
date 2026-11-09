import http.client
import json
import tempfile
import threading
import unittest
from html import escape
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlencode
from uuid import uuid4

from knot.curating.candidates import publish_candidate
from knot.curating.provenance import source_pin
from knot.graph.rdf import VOCAB
from knot.interfaces.library_server import MAX_REQUEST, LibraryServer
from knot.reviewing.writer import decide
from knot.writing.notes import create_note, list_notes, note_history, read_note, save_note


class LibraryServerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.original = create_note(
            self.root, 'First paragraph.\r\n\r\nSecond café.', author='Writer'
        )
        for module in ('knot.presentation.library_snapshot', 'knot.interfaces.library_server'):
            renderer = patch(
                module + '.render_markup',
                side_effect=lambda body, _: '<pre>' + escape(body) + '</pre>',
            )
            renderer.start()
            self.addCleanup(renderer.stop)
        self.server = LibraryServer(self.root)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop)

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def request(self, route='', *, payload=None, headers=None, method=None, absolute=False):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=10)
        self.addCleanup(connection.close)
        selected = {'X-Knot-Session': self.server.token}
        body = None
        if payload is not None:
            selected.update({'Origin': self.server.origin, 'Content-Type': 'application/json'})
            body = json.dumps(payload).encode()
        selected.update(headers or {})
        connection.request(
            method or ('POST' if payload is not None else 'GET'),
            route if absolute else self.server.base + route,
            body,
            selected,
        )
        response = connection.getresponse()
        data = response.read()
        result = (
            json.loads(data)
            if response.getheader('Content-Type', '').startswith('application/json')
            else data.decode()
        )
        return response.status, result, dict(response.getheaders())

    def files(self):
        return {
            str(p.relative_to(self.root)): p.read_bytes()
            for p in self.root.rglob('*')
            if p.is_file() and not p.name.endswith('.lock')
        }

    def test_loopback_page_requires_session_and_never_serves_files(self):
        self.assertEqual(self.server.server_address[0], '127.0.0.1')
        before = self.files()
        for path in (
            '/',
            '/wrong/',
            self.server.base + '../notes/registry.json',
            self.server.base + 'notes/registry.json',
        ):
            self.assertNotEqual(self.request(path, absolute=True)[0], 200)
        status, html, headers = self.request()
        self.assertEqual(status, 200)
        self.assertIn('LibraryAuthoring', html)
        self.assertIn("connect-src 'self'", html)
        self.assertEqual(headers['Cache-Control'], 'no-store')
        self.assertEqual(headers['Referrer-Policy'], 'no-referrer')
        self.assertEqual(headers['X-Frame-Options'], 'DENY')
        self.assertNotIn('Access-Control-Allow-Origin', headers)
        self.assertEqual(self.files(), before)

    def test_host_origin_session_and_fetch_metadata_are_checked_before_writes(self):
        data = {
            'note': 'urn:knot:note:' + str(uuid4()),
            'body': 'No writes',
            'title': None,
            'author': None,
            'format': 'markdown',
        }
        before = self.files()
        for headers in (
            {'Host': 'untrusted.example'},
            {'Host': 'localhost'},
            {'Origin': 'https://untrusted.example'},
            {'Origin': 'null'},
            {'Origin': ''},
            {'X-Knot-Session': ''},
            {'X-Knot-Session': 'wrong'},
            {'X-Knot-Session': 'é'},
            {'Sec-Fetch-Site': 'cross-site'},
            {'Content-Type': 'text/plain'},
            {'Transfer-Encoding': 'chunked'},
        ):
            with self.subTest(headers=headers):
                self.assertIn(
                    self.request('api/create', payload=data, headers=headers)[0], (400, 403, 415)
                )
        self.assertEqual(self.files(), before)
        self.assertEqual(self.request('api/snapshot', headers={'X-Knot-Session': ''})[0], 403)
        self.assertEqual(self.request(headers={'Sec-Fetch-Site': 'cross-site'})[0], 403)

    def test_payload_limits_unknown_fields_and_read_methods_cannot_write(self):
        before = self.files()
        for payload in ([], {'body': 'x', 'root': '/another-dataset'}):
            self.assertIn(self.request('api/create', payload=payload)[0], (400, 413))
        self.assertEqual(
            self.request(
                'api/create',
                method='POST',
                headers={
                    'Origin': self.server.origin,
                    'Content-Type': 'application/json',
                    'Content-Length': str(MAX_REQUEST + 1),
                },
            )[0],
            413,
        )
        self.assertEqual(self.request('api/create')[0], 404)
        self.assertEqual(self.request('api/create', method='OPTIONS')[0], 405)
        self.assertEqual(self.files(), before)

    def test_create_retry_and_edit_preserve_identity_and_immutable_history(self):
        payload = {
            'note': 'urn:knot:note:' + str(uuid4()),
            'title': 'A thought',
            'body': 'Two lines.\n\nCafé 🌿',
            'format': 'markdown',
            'author': 'Writer',
        }
        status, created, _ = self.request('api/create', payload=payload)
        self.assertEqual(status, 200, created)
        self.assertEqual(self.request('api/create', payload=payload)[1], created)
        self.assertEqual(len(list_notes(self.root)), 2)
        self.assertEqual(
            self.request('api/create', payload={**payload, 'body': 'Different'})[0], 409
        )
        saved_files = self.files()
        changed = {
            'note': created['note'],
            'expected': created['revision'],
            'title': 'Clearer thought',
            'body': 'Revised 🌿\n\nStill qualified.',
        }
        status, edited, _ = self.request('api/save', payload=changed)
        self.assertEqual(status, 200, edited)
        self.assertEqual(self.request('api/save', payload=changed)[1], edited)
        history = note_history(self.root, created['note'])
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0]['body'], payload['body'])
        self.assertEqual(history[1]['author'], 'Writer')
        self.assertEqual(history[1]['agent'], 'knot-library')
        for path, content in saved_files.items():
            if path != 'notes/registry.json':
                self.assertEqual(self.files()[path], content)
        status, snapshot, _ = self.request('api/snapshot')
        self.assertEqual(status, 200)
        self.assertEqual(snapshot['notes'][created['note']]['title'], 'Clearer thought')
        self.assertEqual(snapshot['bodies'][history[-1]['body_sha256']]['text'], changed['body'])

    def test_conflict_keeps_the_other_writers_revision(self):
        other = save_note(
            self.root, self.original['note'], 'Other writer.', expected=self.original['revision']
        )
        before = self.files()
        status, error, _ = self.request(
            'api/save',
            payload={
                'note': self.original['note'],
                'expected': self.original['revision'],
                'title': None,
                'body': 'My draft.',
            },
        )
        self.assertEqual(status, 409)
        self.assertEqual(error['current']['revision'], other['revision'])
        self.assertEqual(error['current']['body'], 'Other writer.')
        self.assertEqual(self.files(), before)

    def test_note_read_preserves_bytes_and_edits_retain_metadata(self):
        target = create_note(self.root, 'A related note.')
        note = create_note(
            self.root,
            '* Heading\nBody',
            format='org',
            title='Org',
            author='Writer',
            kind='Thought',
            navigation={
                'themes': [],
                'links': [{'note': target['note'], 'reason': 'Context'}],
                'declarations': [],
            },
        )
        status, current, _ = self.request('api/note?' + urlencode({'note': self.original['note']}))
        self.assertEqual(status, 200)
        self.assertEqual(current['body'], self.original['body'])
        self.assertEqual(
            self.request(
                'api/save',
                payload={
                    'note': note['note'],
                    'expected': note['revision'],
                    'title': 'Renamed',
                    'body': '* Heading\nMore body',
                },
            )[0],
            200,
        )
        saved = read_note(self.root, note['note'])
        for field in ('format', 'author', 'kind', 'navigation', 'entities'):
            self.assertEqual(saved[field], note[field])
        self.assertEqual(
            self.request(
                'api/save',
                payload={
                    'note': note['note'],
                    'expected': saved['revision'],
                    'title': 'Renamed',
                    'body': saved['body'],
                    'author': 'Impersonation',
                },
            )[0],
            400,
        )

    def test_curated_and_historical_records_are_not_editor_targets(self):
        curated = create_note(
            self.root,
            'Restatement.',
            title='Curated',
            author='Curator',
            agent='Test',
            derivation={
                'method': 'faithful_restatement',
                'qualification': 'One source.',
                'sources': [
                    source_pin(self.root, self.original['revision'], 'First paragraph.', 0)
                ],
            },
        )
        before = self.files()
        self.assertEqual(self.request('api/note?' + urlencode({'note': curated['note']}))[0], 422)
        self.assertEqual(
            self.request('api/note?' + urlencode({'note': self.original['revision']}))[0], 400
        )
        self.assertEqual(
            self.request(
                'api/save',
                payload={
                    'note': curated['note'],
                    'expected': curated['revision'],
                    'title': 'Changed',
                    'body': 'Changed',
                },
            )[0],
            422,
        )
        self.assertEqual(self.files(), before)

    def test_preview_is_read_only_and_snapshot_detects_external_changes(self):
        before = self.files()
        status, preview, _ = self.request(
            'api/preview', payload={'body': '<script>bad()</script>\n\nText', 'format': 'markdown'}
        )
        self.assertEqual(status, 200)
        self.assertNotIn('<script>', preview['html'])
        self.assertEqual(self.files(), before)
        first = self.request('api/snapshot')[1]
        changed = save_note(
            self.root, self.original['note'], 'Fresh text.', expected=self.original['revision']
        )
        second = self.request('api/snapshot')[1]
        self.assertNotEqual(first['manifest']['fingerprint'], second['manifest']['fingerprint'])
        self.assertEqual(second['notes'][self.original['note']]['revision'], changed['revision'])

    def test_save_receipt_does_not_depend_on_snapshot_refresh(self):
        self.request('api/snapshot')
        with patch(
            'knot.interfaces.library_server.build_snapshot',
            side_effect=ValueError('Cannot verify snapshot'),
        ):
            status, saved, _ = self.request(
                'api/save',
                payload={
                    'note': self.original['note'],
                    'expected': self.original['revision'],
                    'body': 'Saved even if projection fails.',
                    'title': None,
                },
            )
            self.assertEqual(status, 200)
            self.assertEqual(read_note(self.root, saved['note'])['revision'], saved['revision'])
            self.assertNotEqual(self.request('api/snapshot')[0], 200)

    def test_external_writer_between_read_and_commit_still_causes_conflict(self):
        def competing_save(root, note, body, **metadata):
            save_note(root, note, 'A concurrent update.', expected=metadata['expected'])
            return save_note(root, note, body, **metadata)

        with patch('knot.interfaces.library_server.save_note', side_effect=competing_save):
            status, result, _ = self.request(
                'api/save',
                payload={
                    'note': self.original['note'],
                    'expected': self.original['revision'],
                    'body': 'A stale update.',
                    'title': None,
                },
            )
        self.assertEqual(status, 409)
        self.assertEqual(result['current']['body'], 'A concurrent update.')
        self.assertEqual(len(note_history(self.root, self.original['note'])), 2)

    def test_existing_claims_reviews_and_pinned_evidence_survive_source_edit(self):
        source = create_note(self.root, 'A team proposed a garden trial.', author='Writer')
        claim = 'urn:knot:assertion:example-proposal'
        publish_candidate(
            self.root,
            {
                'id': claim,
                'subject': {'id': 'urn:example:team', 'label': 'A team'},
                'predicate': VOCAB + 'proposed',
                'object': {'id': 'urn:example:trial', 'label': 'A garden trial'},
                'origin': 'Explicit',
                'rationale': 'A plan, not a completed trial.',
                'agent': 'urn:example:agent',
                'generated_at': '2026-01-01T12:00:00Z',
                'sources': [source_pin(self.root, source['revision'], source['body'], 0)],
            },
        )
        decide(self.root, claim, 'accept', reviewer='Example reviewer', reason='Checked source.')
        before = self.files()
        status, _, _ = self.request(
            'api/save',
            payload={
                'note': source['note'],
                'expected': source['revision'],
                'title': 'Current reflection',
                'body': 'A later reflection without rewriting the old account.',
            },
        )
        self.assertEqual(status, 200)
        for path, body in before.items():
            if path != 'notes/registry.json':
                self.assertEqual(self.files()[path], body)
        status, snapshot, _ = self.request('api/snapshot')
        self.assertEqual(status, 200)
        self.assertEqual(snapshot['claims'][claim]['status'], 'Accepted')
        self.assertEqual(
            snapshot['bodies'][snapshot['sources'][source['revision']]['body']]['text'],
            source['body'],
        )

    def test_invalidating_an_entity_declaration_requires_its_existing_workflow(self):
        source = create_note(
            self.root,
            'Garden project is a proposal.',
            navigation={
                'themes': [],
                'links': [],
                'declarations': [
                    {
                        'id': 'urn:knot:entity:00000000-0000-4000-8000-000000000301',
                        'label': 'Garden project',
                        'type': 'Project',
                        'quote': 'Garden project',
                        'offset': 0,
                    }
                ],
            },
        )
        before = self.files()
        status, _, _ = self.request(
            'api/save',
            payload={
                'note': source['note'],
                'expected': source['revision'],
                'title': None,
                'body': 'Removed the declaration evidence.',
            },
        )
        self.assertEqual(status, 422)
        self.assertEqual(self.files(), before)
