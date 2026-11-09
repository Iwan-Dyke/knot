import tempfile
import unittest
from pathlib import Path

from pyoxigraph import RdfFormat, Store

from knot.frameworks import build_frameworks
from knot.inventory import digest
from knot.query import assertion_query


class FrameworkTests(unittest.TestCase):
    def test_separate_frameworks_exact_evidence_and_requirements(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            text = 'Mentoring means supporting learning.\nExpert: develops mentors.\nMentoring n/a Expert\n'
            (root / 'source.md').write_text(text)
            frameworks = []
            for name in ('product', 'platform'):
                frameworks.append(
                    {
                        'key': name,
                        'title': name,
                        'sha256': digest(text.encode()),
                        'snapshot': 'source.md',
                        'skills': [
                            {
                                'name': 'Mentoring',
                                'quote': text.splitlines()[0],
                                'levels': {'Expert': text.splitlines()[1]},
                                'requirements': {'EO': 'n/a', 'G7': 'Expert'},
                                'requirements_quote': text.splitlines()[2],
                            }
                        ],
                    }
                )
            catalog = {'active_framework': 'product', 'frameworks': frameworks}
            content = build_frameworks(root, catalog)
            self.assertEqual(content, build_frameworks(root, catalog))
            store = Store()
            store.load(input=content, format=RdfFormat.TRIG)
            self.assertEqual(len(list(store.query(assertion_query()))), 0)
            self.assertEqual(len(list(store.query(assertion_query(frameworks=True)))), 10)
            skills = list(
                store.query(
                    'SELECT ?s WHERE { GRAPH <urn:knot:metadata> { ?s a <urn:knot:vocab:Competency> }}'
                )
            )
            self.assertEqual(len(skills), 2)
            self.assertNotEqual(skills[0]['s'], skills[1]['s'])
            requirements = list(
                store.query('SELECT ?s ?o WHERE { GRAPH ?a { ?s <urn:knot:vocab:requires> ?o }}')
            )
            self.assertEqual(len(requirements), 2)  # n/a is not a required skill level.
            self.assertEqual(
                len(
                    list(
                        store.query(
                            'SELECT ?f WHERE { GRAPH <urn:knot:metadata> { <urn:knot:assessment-policy> <urn:knot:vocab:currentFramework> ?f }}'
                        )
                    )
                ),
                1,
            )
            frameworks[0]['skills'][0]['levels']['Expert'] = 'Invented criterion'
            with self.assertRaisesRegex(ValueError, 'quotation'):
                build_frameworks(root, catalog)
            frameworks[0]['skills'][0]['levels']['Expert'] = text.splitlines()[1]
            (root / 'source.md').write_text('changed')
            with self.assertRaisesRegex(ValueError, 'hash'):
                build_frameworks(root, catalog)
