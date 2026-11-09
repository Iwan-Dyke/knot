"""Render untrusted note text through an external converter and a small HTML allowlist."""

import re
import shutil
import subprocess
import tempfile
from html import escape
from html.parser import HTMLParser
from urllib.parse import urlsplit

TAGS = set(
    'p h1 h2 h3 h4 h5 h6 ul ol li strong em del sup sub blockquote pre code '
    'table thead tbody tfoot tr th td caption dl dt dd hr br a span'.split()
)
VOID = {'hr', 'br'}


class _SafeHTML(HTMLParser):
    """Re-serialize only inert markup; never pass converter attributes through."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.output = []
        self.stack = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'img':
            self.output.append(escape('[Image omitted: ' + attrs.get('alt', '') + ']'))
        if tag not in TAGS:
            return
        safe = ''
        identifier = attrs.get('id', '')
        if re.fullmatch(r'[\w.:-]+', identifier):
            safe += ' id="text-' + escape(identifier, quote=True) + '"'
        if tag == 'a':
            href = attrs.get('href', '')
            if href and not any(ord(c) <= 32 for c in href):
                try:
                    parsed = urlsplit(href)
                except ValueError:
                    parsed = urlsplit('')
                if parsed.scheme.lower() in {'http', 'https'} and parsed.netloc:
                    safe += (
                        ' href="'
                        + escape(href, quote=True)
                        + '" rel="noopener noreferrer" target="_blank"'
                    )
                elif href.startswith('urn:'):
                    safe += ' data-record="' + escape(href, quote=True) + '" href="#"'
                elif href.startswith('#') and re.fullmatch(r'[\w.:-]+', href[1:]):
                    safe += ' data-anchor="text-' + escape(href[1:], quote=True) + '" href="#"'
        self.output.append('<' + tag + safe + '>')
        if tag not in VOID:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if tag in self.stack:
            while self.stack:
                current = self.stack.pop()
                self.output.append('</' + current + '>')
                if current == tag:
                    break

    def handle_data(self, data):
        self.output.append(escape(data))

    def finish(self):
        while self.stack:
            self.output.append('</' + self.stack.pop() + '>')
        return ''.join(self.output)


def render_markup(body, format):
    executable = shutil.which('pandoc')
    if not executable:
        raise ValueError('Install Pandoc separately to generate Library snapshots (knot browse).')
    if format not in {'markdown', 'org'}:
        raise ValueError('Unsupported note format')
    source = 'commonmark_x-raw_html' if format == 'markdown' else 'org'
    # Empty working directory and sandbox deny Org includes and unrelated local resources.
    # No standalone templates, filters, configuration files or remote assets are requested.
    with tempfile.TemporaryDirectory(prefix='knot-markup-') as temporary:
        try:
            result = subprocess.run(
                [
                    executable,
                    '--sandbox',
                    '--from=' + source,
                    '--to=html5',
                    '--wrap=none',
                    '--no-highlight',
                ],
                input=body.encode('utf-8'),
                capture_output=True,
                timeout=15,
                cwd=temporary,
                check=False,
            )
        except subprocess.TimeoutExpired as error:
            raise ValueError('Note conversion exceeded the 15 second limit') from error
    if result.returncode:
        # Unsupported directives stay readable without widening the converter's file access.
        return (
            '<p>Formatted preview unavailable; exact source follows.</p><pre>'
            + escape(body)
            + '</pre>'
        )
    parser = _SafeHTML()
    parser.feed(result.stdout.decode('utf-8'))
    parser.close()
    return parser.finish()
