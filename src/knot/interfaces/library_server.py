"""Serve the owner-local Library with explicitly enabled ordinary-note editing."""

from __future__ import annotations

import argparse
import json
import secrets
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from uuid import UUID

from knot.presentation.browser import open_url
from knot.presentation.library import render_snapshot
from knot.presentation.library_snapshot import build_snapshot, input_signature
from knot.presentation.markup import render_markup
from knot.presentation.styles import selected_theme
from knot.shared.datasets import cli_data_root
from knot.writing.notes import create_note, read_note, save_note

MAX_REQUEST = 1024 * 1024
AGENT = 'knot-library'


class RequestError(ValueError):
    def __init__(self, status: int, message: str, *, current: dict | None = None):
        super().__init__(message)
        self.status = status
        self.current = current


def _fields(
    data: dict, required: set[str], optional: set[str] | frozenset[str] = frozenset()
) -> None:
    if (
        not isinstance(data, dict)
        or not required <= data.keys()
        or data.keys() - required - optional
    ):
        raise RequestError(400, 'Unexpected or missing request fields')
    for key, value in data.items():
        if not isinstance(value, str) and not (key in {'title', 'author'} and value is None):
            raise RequestError(400, f'{key} must be text')


def _note_id(value: str) -> str:
    prefix = 'urn:knot:note:'
    try:
        if not value.startswith(prefix) or str(UUID(value[len(prefix) :])) != value[len(prefix) :]:
            raise ValueError
    except (ValueError, AttributeError) as error:
        raise RequestError(400, 'Select a logical native note') from error
    return value


def _editable(note: dict) -> dict:
    if note.get('derivation') is not None:
        raise RequestError(422, 'Curated notes use the source-backed curation workflow')
    return {key: note[key] for key in ('note', 'revision', 'title', 'body', 'format', 'author')}


def _receipt(note: dict) -> dict:
    return {key: note[key] for key in ('note', 'revision')}


def _conflict(note: dict) -> RequestError:
    return RequestError(
        409, 'This note changed. Your draft has not been saved.', current=_editable(note)
    )


class LibraryServer(ThreadingHTTPServer):
    """One short-lived owner session; never a general filesystem or remote server."""

    daemon_threads = True

    def __init__(self, root: Path, *, port: int = 0, visual_theme: str = 'matrix'):
        self.root = Path(root).resolve(strict=True)
        if not self.root.is_dir():
            raise ValueError('Select a dataset directory')
        self.visual_theme = visual_theme
        self.token = secrets.token_urlsafe(32)
        self.base = '/' + self.token + '/'
        self.lock = threading.Lock()
        self.cached: dict | None = None
        super().__init__(('127.0.0.1', port), LibraryHandler)
        self.origin = f'http://127.0.0.1:{self.server_port}'

    def snapshot(self) -> dict:
        before = input_signature(self.root)
        if self.cached is not None and self.cached['manifest']['fingerprint'] == before:
            return self.cached
        model = build_snapshot(self.root)
        if input_signature(self.root) != before:
            raise RequestError(409, 'Knowledge changed while refreshing. Refresh again.')
        model['manifest']['fingerprint'] = before
        self.cached = model
        return model

    def create(self, data: dict) -> dict:
        _fields(data, {'note', 'body', 'format'}, {'title', 'author'})
        note_id = _note_id(data['note'])
        fields = {key: data.get(key) for key in ('title', 'author', 'format')}
        try:
            saved = create_note(
                self.root,
                data['body'],
                note_id=note_id,
                agent=AGENT,
                reason='Created in Library',
                **fields,
            )
        except ValueError as error:
            if str(error) != 'Note identifier already exists':
                raise
            saved = read_note(self.root, note_id)
            # A lost response must not turn a retry into a second logical note.
            if (
                saved['parent'] is not None
                or saved['agent'] != AGENT
                or any(
                    saved[key] != value for key, value in {**fields, 'body': data['body']}.items()
                )
            ):
                raise _conflict(saved) from error
        return _receipt(saved)

    def save(self, data: dict) -> dict:
        _fields(data, {'note', 'expected', 'body', 'title'})
        current = read_note(self.root, _note_id(data['note']))
        _editable(current)
        if current['revision'] != data['expected']:
            if (
                current['parent'] == data['expected']
                and current['agent'] == AGENT
                and all(current[key] == data[key] for key in ('title', 'body'))
            ):
                return _receipt(current)
            raise _conflict(current)
        try:
            saved = save_note(
                self.root,
                data['note'],
                data['body'],
                title=data['title'],
                expected=data['expected'],
                agent=AGENT,
                reason='Edited in Library',
            )
        except ValueError as error:
            if str(error) == 'Note head changed; reload before saving':
                raise _conflict(read_note(self.root, data['note'])) from error
            raise
        return _receipt(saved)


class LibraryHandler(BaseHTTPRequestHandler):
    server: LibraryServer
    timeout = 10

    def log_message(self, format: str, *args: object) -> None:
        # Paths contain a session capability; request bodies can contain private notes.
        pass

    def respond(self, status: int, data: dict | str, *, html: bool = False) -> None:
        body = (data if html else json.dumps(data, ensure_ascii=False)).encode('utf-8')
        self.send_response(status)
        self.send_header(
            'Content-Type',
            'text/html; charset=utf-8' if html else 'application/json; charset=utf-8',
        )
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Content-Security-Policy', "frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(body)

    def send_error(self, code: int, message: str | None = None, explain: str | None = None) -> None:
        self.respond(code, {'error': 'Unsupported or malformed request'})

    def _route(self) -> tuple[str, dict]:
        if self.headers.get_all('Host') != [self.server.origin.removeprefix('http://')]:
            raise RequestError(403, 'Invalid local host')
        if self.headers.get('Sec-Fetch-Site') not in (None, 'none', 'same-origin'):
            raise RequestError(403, 'Cross-site requests are not allowed')
        origin = self.headers.get('Origin')
        if origin is not None and self.headers.get_all('Origin') != [self.server.origin]:
            raise RequestError(403, 'Invalid request origin')
        if not self.path.startswith(self.server.base):
            raise RequestError(404, 'Unknown session or route')
        parts = urlsplit(self.path)
        route = parts.path[len(self.server.base) :]
        tokens = self.headers.get_all('X-Knot-Session', [])
        if route and (
            len(tokens) != 1
            or not secrets.compare_digest(
                tokens[0].encode('utf-8'), self.server.token.encode('ascii')
            )
        ):
            raise RequestError(403, 'Session access required')
        if self.command == 'POST' and origin != self.server.origin:
            raise RequestError(403, 'Same-origin requests are required')
        return route, parse_qs(parts.query, strict_parsing=True)

    def _json(self) -> dict:
        if self.headers.get('Content-Type') != 'application/json':
            raise RequestError(415, 'Send application/json')
        lengths = self.headers.get_all('Content-Length', [])
        if len(lengths) != 1 or not lengths[0].isdigit() or self.headers.get('Transfer-Encoding'):
            raise RequestError(400, 'A single content length is required')
        size = int(lengths[0])
        if size > MAX_REQUEST:
            raise RequestError(413, 'This editor accepts requests up to 1 MiB')
        body = self.rfile.read(size)
        if len(body) != size:
            raise RequestError(400, 'Incomplete request body')
        return json.loads(body.decode('utf-8'))

    def _handle(self) -> None:
        try:
            route, query = self._route()
            data = self._json() if self.command == 'POST' else None
            with self.server.lock:
                if self.command == 'GET' and route == '' and not query:
                    model = {
                        **self.server.snapshot(),
                        'authoring': {
                            'base': self.server.base + 'api/',
                            'token': self.server.token,
                        },
                    }
                    self.respond(
                        200,
                        render_snapshot(model, visual_theme=self.server.visual_theme),
                        html=True,
                    )
                    return
                if self.command == 'GET' and route == 'api/snapshot' and not query:
                    result = self.server.snapshot()
                elif (
                    self.command == 'GET'
                    and route == 'api/note'
                    and set(query) == {'note'}
                    and len(query['note']) == 1
                ):
                    result = _editable(read_note(self.server.root, _note_id(query['note'][0])))
                elif self.command == 'POST' and not query and route in {'api/create', 'api/save'}:
                    result = (self.server.create if route == 'api/create' else self.server.save)(
                        data
                    )
                elif self.command == 'POST' and route == 'api/preview' and not query:
                    _fields(data, {'body', 'format'})
                    result = {'html': render_markup(data['body'], data['format'])}
                else:
                    raise RequestError(404, 'Unknown route')
                self.respond(200, result)
        except RequestError as error:
            self.respond(
                error.status,
                {'error': str(error), **({'current': error.current} if error.current else {})},
            )
        except (UnicodeError, json.JSONDecodeError):
            self.respond(400, {'error': 'Send valid UTF-8 JSON'})
        except ValueError as error:
            self.respond(422, {'error': str(error)})
        except (BrokenPipeError, ConnectionResetError):
            # The client may have lost a successful response; note retries are idempotent.
            return
        except OSError:
            self.respond(
                503, {'error': 'The local operation could not finish. Keep your draft and retry.'}
            )

    do_GET = _handle
    do_POST = _handle

    def do_OPTIONS(self) -> None:
        self.respond(405, {'error': 'Cross-origin access is not supported'})


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-root', type=Path)
    parser.add_argument(
        '--port', type=int, default=0, help='Loopback port; default selects a free port'
    )
    parser.add_argument('--visual-theme')
    parser.add_argument(
        '--no-open', action='store_true', help='Print the private URL without opening a browser'
    )
    args = parser.parse_args(argv)
    if not 0 <= args.port <= 65535:
        parser.error('Port must be between 0 and 65535')
    root = cli_data_root(parser, args.data_root)
    try:
        with LibraryServer(
            root, port=args.port, visual_theme=args.visual_theme or selected_theme()
        ) as server:
            server.snapshot()
            url = server.origin + server.base + '#view=library'
            print(
                f'Library editing for {root}. Keep this session URL private. Stop with Ctrl+C.',
                flush=True,
            )
            print(url, flush=True)
            if not args.no_open:
                try:
                    open_url(url)
                except (OSError, RuntimeError, subprocess.SubprocessError):
                    print(
                        'Browser launch failed; open the private URL above manually.',
                        file=sys.stderr,
                    )
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                print('\nLibrary session stopped.')
    except (ValueError, OSError, RuntimeError) as error:
        parser.error(str(error))


if __name__ == '__main__':
    main()
