import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from zipfile import ZipFile

from knot.text import extract_text, segment_text


class TextTests(unittest.TestCase):
    def test_org_coverage_and_block_headings(self):
        text = '#+title: Note\r\n\r\n* Real\r\n:PROPERTIES:\r\n:ID: stable\r\n:END:\r\n#+begin_src text\r\n* Fake\r\n#+end_src\r\n** Next\r\nTail'
        segments = segment_text(text, 'org')
        self.assertEqual([s['title'] for s in segments], ['Preamble', 'Real', 'Next'])
        self.assertEqual(segments[1]['org_id'], 'stable')
        self.assertEqual(''.join(s['text'] for s in segments), text)
        self.assertEqual(
            [(s['start_line'], s['end_line']) for s in segments], [(1, 2), (3, 9), (10, 11)]
        )
        self.assertEqual(segments, segment_text(text, 'org'))

    def test_markdown_fences_repeated_headings_and_empty(self):
        text = '# Same\n````python\n# Fake\n```\n# Still fake\n````\n# Same\nlast\n'
        segments = segment_text(text, 'md')
        self.assertEqual(len(segments), 2)
        self.assertNotEqual(segments[0]['key'], segments[1]['key'])
        self.assertEqual(''.join(s['text'] for s in segments), text)
        self.assertEqual(segment_text('', 'org'), [])

    def test_quoted_org_property_drawer_does_not_assign_identity(self):
        text = '* Real\n#+begin_src org\n:PROPERTIES:\n:ID: fake\n:END:\n#+end_src\n'
        self.assertIsNone(segment_text(text, 'org')[0]['org_id'])

    def test_utf8_preserves_newlines_and_reports_bom(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'note.org'
            path.write_bytes(b'\xef\xbb\xbf* Caf\xc3\xa9\r\nbody\r\n')
            result = extract_text(path)
        self.assertEqual(result['text'], '* Café\r\nbody\r\n')
        self.assertEqual(result['locator_kind'], 'source_line')
        self.assertTrue(result['warnings'])

    def test_docx_reports_visual_and_auxiliary_parts(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'note.docx'
            with ZipFile(path, 'w') as archive:
                archive.writestr(
                    'word/document.xml', '<w:document xmlns:w="urn:word"><w:tbl/></w:document>'
                )
                archive.writestr('word/media/image1.png', b'image')
                archive.writestr('word/header1.xml', '<header/>')
            output = subprocess.CompletedProcess([], 0, stdout='# Converted\n', stderr='')
            with patch('knot.text.subprocess.run', return_value=output) as run:
                result = extract_text(path)
        self.assertEqual(result['text'], '# Converted\n')
        self.assertEqual(result['locator_kind'], 'extracted_line')
        self.assertTrue(any('1 embedded' in w for w in result['warnings']))
        self.assertTrue(any('1 table' in w for w in result['warnings']))
        self.assertTrue(any('header' in w for w in result['warnings']))
        self.assertNotIn('shell', run.call_args.kwargs)

    def test_pdf_retains_page_breaks_and_blank_page_warning(self):
        pages = [
            SimpleNamespace(extract_text=lambda: 'Page one'),
            SimpleNamespace(extract_text=lambda: ''),
        ]
        module = SimpleNamespace(
            PdfReader=lambda path: SimpleNamespace(pages=pages, is_encrypted=False)
        )
        with patch.dict(sys.modules, {'pypdf': module}):
            result = extract_text(Path('example.pdf'))
        self.assertEqual(result['text'], 'Page one\n\f\n')
        self.assertTrue(any('page 2' in w for w in result['warnings']))
        self.assertTrue(any('visual' in w for w in result['warnings']))

    def test_unsupported_and_invalid_utf8_fail_explicitly(self):
        with self.assertRaises(ValueError):
            extract_text(Path('unknown.bin'))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'note.md'
            path.write_bytes(b'\xff')
            with self.assertRaises(UnicodeDecodeError):
                extract_text(path)


if __name__ == '__main__':
    unittest.main()
