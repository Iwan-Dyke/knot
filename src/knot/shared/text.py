"""Loss-aware local text extraction and exact, non-executing passage segmentation."""

import hashlib
import logging
import re
import subprocess
from pathlib import Path
from xml.etree import ElementTree
from zipfile import ZipFile


class _PdfWarnings(logging.Handler):
    def __init__(self, warnings):
        super().__init__(logging.WARNING)
        self.warnings = warnings

    def emit(self, record):
        self.warnings.append('pypdf: ' + record.getMessage())


def extract_text(path):
    path = Path(path)
    format_name = path.suffix.lower().lstrip('.')
    warnings = []
    locator_kind = 'extracted_line'
    if format_name in ('org', 'md'):
        raw = path.read_bytes()
        text = raw.decode('utf-8-sig')
        if raw.startswith(b'\xef\xbb\xbf'):
            warnings.append(
                'UTF-8 BOM removed from decoded text; original bytes remain in snapshot.'
            )
        method = 'utf-8-sig'
        locator_kind = 'source_line'
    elif format_name == 'docx':
        with ZipFile(path) as archive:
            names = archive.namelist()
            images = sum(
                name.startswith('word/media/') and not name.endswith('/') for name in names
            )
            document = ElementTree.fromstring(archive.read('word/document.xml'))
            tables = sum(element.tag.rsplit('}', 1)[-1] == 'tbl' for element in document.iter())
            auxiliary = [
                name
                for name in names
                if re.match(r'word/(header|footer|footnotes|endnotes).*\.xml$', name)
            ]
        result = subprocess.run(
            ['pandoc', '--from=docx', '--to=markdown', '--wrap=none'],
            input=path.read_bytes(),
            capture_output=True,
            timeout=120,
            check=True,
        )
        text = result.stdout.decode('utf-8') if isinstance(result.stdout, bytes) else result.stdout
        stderr = (
            result.stderr.decode('utf-8') if isinstance(result.stderr, bytes) else result.stderr
        )
        warnings.append(
            'DOCX text conversion requires visual review; layout and formatting are not preserved.'
        )
        if images:
            warnings.append(
                f'{images} embedded media resources require separate visual review; image text was not extracted.'
            )
        if tables:
            warnings.append(f'{tables} tables require structure review after Markdown conversion.')
        if auxiliary:
            warnings.append(
                'Auxiliary parts require coverage review (may be omitted or rearranged): '
                + ', '.join(auxiliary)
            )
        if stderr.strip():
            warnings.append('Pandoc: ' + stderr.strip())
        method = 'pandoc-docx-to-markdown'
    elif format_name == 'pdf':
        from pypdf import PdfReader

        logger = logging.getLogger('pypdf')
        handler = _PdfWarnings(warnings)
        logger.addHandler(handler)
        try:
            reader = PdfReader(path)
            if reader.is_encrypted:
                raise ValueError('Encrypted PDF requires explicit decryption before extraction')
            pages = []
            for number, page in enumerate(reader.pages, 1):
                page_text = page.extract_text() or ''
                pages.append(page_text)
                if not page_text.strip():
                    warnings.append(
                        f'PDF page {number} has no extracted text; OCR or visual review required.'
                    )
        finally:
            logger.removeHandler(handler)
        text = '\n\f\n'.join(pages)
        warnings.append(
            'PDF extraction requires visual review for images, reading order and tables; no OCR performed.'
        )
        method = 'pypdf-extract-text'
    else:
        raise ValueError(f'Unsupported source format: {format_name or "no extension"}')
    if not text.strip():
        warnings.append(
            'No non-whitespace text extracted; semantic processing cannot be considered complete.'
        )
    return {
        'text': text,
        'format': format_name,
        'locator_kind': locator_kind,
        'warnings': warnings,
        'method': method,
    }


def segment_text(text, format):
    """Partition all lines, retaining delimiters so joining passages recovers text."""
    lines = text.splitlines(keepends=True)
    if not lines:
        return []
    headings = []
    block = None
    fence = None
    for index, line in enumerate(lines):
        if format == 'org':
            if block:
                if re.match(r'^\s*#\+end_' + re.escape(block) + r'\s*$', line, re.I):
                    block = None
                continue
            begin = re.match(r'^\s*#\+begin_(\S+)', line, re.I)
            if begin:
                block = begin.group(1)
                continue
            heading = re.match(r'^(\*+)\s+(.+?)\s*$', line)
        elif format in ('md', 'markdown', 'docx'):
            delimiter = re.match(r'^ {0,3}(`{3,}|~{3,})(.*)$', line)
            if fence:
                if (
                    delimiter
                    and delimiter[1][0] == fence[0]
                    and len(delimiter[1]) >= len(fence)
                    and not delimiter[2].strip()
                ):
                    fence = None
                continue
            if delimiter:
                fence = delimiter[1]
                continue
            heading = re.match(r'^ {0,3}(#{1,6})\s+(.+?)\s*$', line)
        else:
            heading = None
        if heading:
            headings.append((index, heading[2]))
    if not headings or headings[0][0] != 0:
        headings.insert(0, (0, 'Preamble'))
    segments = []
    for ordinal, (start, title) in enumerate(headings):
        end = headings[ordinal + 1][0] if ordinal + 1 < len(headings) else len(lines)
        content = ''.join(lines[start:end])
        org_id = None
        if format == 'org' and re.match(r'^\*+\s', lines[start]):
            # Only the heading's initial property drawer defines its identity;
            # drawers quoted later in source blocks are evidence, not metadata.
            drawer = re.match(
                r'^\*+[^\r\n]*\r?\n(?:(?:CLOSED|SCHEDULED|DEADLINE):[^\r\n]*\r?\n)?[ \t]*:PROPERTIES:[ \t]*\r?\n(.*?)^:END:[ \t]*\r?$',
                content,
                re.M | re.S | re.I,
            )
            if drawer:
                found = re.search(r'^:ID:\s*(\S+)\s*$', drawer[1], re.M | re.I)
                org_id = found[1] if found else None
        key = hashlib.sha256(f'{ordinal}\0{content}'.encode('utf-8')).hexdigest()
        segments.append(
            {
                'key': key,
                'title': title,
                'org_id': org_id,
                'start_line': start + 1,
                'end_line': end,
                'text': content,
                'kind': 'preamble' if start == 0 and title == 'Preamble' else 'heading',
            }
        )
    return segments
