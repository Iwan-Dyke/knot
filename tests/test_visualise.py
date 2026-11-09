import io
import json
import shutil
import subprocess
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path
from unittest.mock import patch

from pyvis.network import Network

from knot.inventory import digest
from knot.rdf import DERIVED, RDF_TYPE, VOCAB, Dataset
from knot.visualise import add_claim, add_note_navigation, add_themes, main, open_view, write_view


def write_account_fixture(root):
    """Use the real catalogue/export path in unit and optional browser checks."""
    root = Path(root)
    for directory in ('graph', 'sources', 'curation'):
        (root / directory).mkdir(parents=True)
    data, pins = Dataset(), []
    for name, quote in (
        ('first', 'Alex reported 18 events in the Orion rollout.'),
        ('retelling', 'Alex reported 18 events in the Orion rollout.'),
        ('count', '18 pipelines were reported; overlap with Orion events is unresolved.'),
    ):
        aid = 'urn:assertion:' + name
        body = f'# {name}\n{quote}\n'
        sha = digest(body.encode())
        revision, evidence = 'urn:revision:' + sha, aid + ':evidence'
        snapshot = f'sources/{name}.txt'
        (root / snapshot).write_text(body)
        literal = name == 'count'
        data.add(
            'urn:outcome:orion' if literal else 'urn:person:alex',
            VOCAB + ('pipelineCount' if literal else 'reportedOutcome'),
            18 if literal else 'urn:outcome:orion',
            literal=literal,
            graph=aid,
        )
        data.add(aid, RDF_TYPE, VOCAB + 'Assertion')
        for key, value in (
            ('reviewStatus', 'Unreviewed' if literal else 'Accepted'),
            ('lifecycle', 'Active'),
            ('origin', 'Explicit'),
        ):
            data.add(aid, VOCAB + key, VOCAB + value)
        for key, value in (
            ('subjectLabel', 'Orion rollout outcome' if literal else 'Alex'),
            ('objectLabel', '18' if literal else 'Orion rollout outcome'),
            ('rationale', 'Reported measurements retain their units and attribution.'),
        ):
            data.add(aid, VOCAB + key, value, literal=True)
        data.add(aid, DERIVED, evidence)
        data.add(evidence, VOCAB + 'revision', revision)
        data.add(evidence, VOCAB + 'quote', quote, literal=True)
        data.add(evidence, VOCAB + 'characterOffset', body.index(quote), literal=True)
        data.add(revision, VOCAB + 'snapshotPath', snapshot, literal=True)
        data.add(revision, VOCAB + 'sha256', sha, literal=True)
        pins.append(
            dict(
                revision=revision,
                sha256=sha,
                text_sha256=sha,
                quote=body,
                character_offset=0,
                start_line=1,
            )
        )
    (root / 'graph/claims.trig').write_text(data.text())
    groups = [
        dict(
            id='orion-retelling',
            relationship='RepeatedAccount',
            qualification='A retelling is not independent corroboration. '
            '<img src=x onerror="window.accountInjected=true">',
            reviewer='Reviewer </script><script>window.accountInjected=true</script>',
            assertions=['urn:assertion:first', 'urn:assertion:retelling'],
            sources=pins[:2],
        ),
        dict(
            id='orion-counts',
            relationship='OverlapUnresolved',
            qualification='Events and pipelines may overlap; do not add their counts.',
            reviewer='Test reviewer',
            assertions=['urn:assertion:first', 'urn:assertion:count'],
            sources=[pins[0], pins[2]],
        ),
    ]
    (root / 'curation/evidence-accounts.json').write_text(
        json.dumps(dict(schema_version=1, groups=groups))
    )
    return groups


class Resources(HTMLParser):
    def __init__(self):
        super().__init__()
        self.external = []

    def handle_starttag(self, tag, attrs):
        for key, value in attrs:
            if tag in ('script', 'link') and key in ('src', 'href'):
                self.external.append(value)


class VisualiseTests(unittest.TestCase):
    def test_note_entities_and_associated_notes_have_distinct_shapes(self):
        network = Network(directed=True)
        network.add_node('entity-note', role='entity')
        network.add_node('subject', role='entity')
        network.add_edge('subject', 'entity-note', id='claim')
        notes = {
            id: {
                'title': id,
                'body': 'Saved writing',
                'kind': None,
                'entities': [],
                'revision': 'revision:' + id,
                'navigation': {'themes': [], 'links': []},
            }
            for id in ('entity-note', 'associated-note')
        }
        add_note_navigation(network, {'notes': notes, 'entities': {}}, {})
        self.assertEqual(network.get_node('entity-note')['shape'], 'ellipse')
        self.assertEqual(network.get_node('associated-note')['shape'], 'box')
        self.assertNotEqual(
            network.get_node('entity-note')['color'], network.get_node('associated-note')['color']
        )
        self.assertEqual(len(network.edges), 1)

    @unittest.skipUnless(shutil.which('node'), 'Viewer logic tests require Node.js')
    def test_live_filter_semantics(self):
        subprocess.run(
            ['node', str(Path(__file__).resolve().parents[1] / 'scripts/test_viewer.cjs')],
            check=True,
            capture_output=True,
            text=True,
        )

    def test_wsl_opens_windows_path_with_default_application(self):
        with (
            patch(
                'knot.presentation.browser.platform.release', return_value='microsoft-standard-WSL2'
            ),
            patch('knot.presentation.browser.shutil.which', return_value='/bin/powershell.exe'),
            patch(
                'knot.presentation.browser.subprocess.check_output',
                return_value='\\\\wsl.localhost\\Ubuntu\\graph.html\n',
            ),
            patch('knot.presentation.browser.subprocess.run') as run,
        ):
            open_view(Path('/tmp/graph.html'))
            self.assertIn('-EncodedCommand', run.call_args.args[0])
            self.assertTrue(run.call_args.kwargs['check'])

    def test_native_browser_failure_is_reported(self):
        with (
            patch('knot.presentation.browser.platform.release', return_value='Linux'),
            patch('knot.presentation.browser.webbrowser.open', return_value=False),
        ):
            with self.assertRaisesRegex(RuntimeError, 'browser'):
                open_view(Path('/tmp/graph.html'))

    def claim(self, **changes):
        return {
            'id': 'claim:1',
            'source': 'person:1',
            'target': 'project:1',
            'subject': 'Person',
            'object': 'Atlas',
            'relation': 'workedOn',
            'status': 'Unreviewed',
            'origin': 'Inferred',
            'quote': '<img src=x onerror=alert(1)>',
            'snapshot': 'sources/note.org',
            'rationale': 'Possible connection',
            **changes,
        }

    def test_status_evidence_and_distinct_occurrences(self):
        network = Network(directed=True)
        add_claim(network, self.claim())
        add_claim(network, self.claim(id='claim:2', status='Accepted', origin='Explicit'))
        self.assertEqual(len(network.nodes), 2)
        self.assertEqual(len(network.edges), 2)
        self.assertTrue(network.edges[0]['dashes'])
        self.assertFalse(network.edges[1]['dashes'])
        self.assertNotEqual(network.edges[0]['color'], network.edges[1]['color'])
        self.assertIn('&lt;img', network.edges[0]['title'])

    def test_filter_and_inspector_metadata_preserves_evidence(self):
        network = Network(directed=True)
        add_claim(
            network,
            self.claim(
                source_types=['Person'],
                target_types=['Project'],
                theme_ids=['learning'],
                kind='Question',
                evidence=[{'quote': 'Unanswered?', 'snapshot': 'sources/note.org'}],
            ),
        )
        self.assertEqual(network.nodes[0]['entityTypes'], ['Person'])
        edge = network.edges[0]
        self.assertEqual(edge['themeIds'], ['learning'])
        self.assertEqual(edge['status'], 'Unreviewed')
        self.assertEqual(edge['detail']['kind'], 'Question')
        self.assertEqual(edge['detail']['evidence'][0]['quote'], 'Unanswered?')

    def test_literal_is_an_evidence_bearing_attribute_not_a_graph_entity(self):
        network = Network(directed=True)
        claim = self.claim(
            object='18',
            target='literal:claim:1',
            literal=True,
            literal_value='18',
            relation='eventCount',
            object_datatype='http://www.w3.org/2001/XMLSchema#integer',
            source_aliases=['Original project name'],
        )
        add_claim(network, claim)
        self.assertEqual([n['id'] for n in network.nodes], ['person:1'])
        self.assertEqual(network.edges, [])
        attribute = network.nodes[0]['attributes'][0]
        self.assertEqual(attribute['id'], 'claim:1')
        self.assertEqual(attribute['detail']['literal_value'], '18')
        self.assertEqual(attribute['detail']['object_datatype'], claim['object_datatype'])
        self.assertEqual(attribute['detail']['evidence'][0]['quote'], claim['quote'])
        self.assertEqual(attribute['status'], 'Unreviewed')
        self.assertEqual(network.nodes[0]['aliases'], ['Original project name'])

    def test_numeric_named_referent_remains_an_entity(self):
        network = Network(directed=True)
        add_claim(network, self.claim(object='1984', target='urn:book:1984'))
        self.assertEqual(len(network.nodes), 2)
        self.assertEqual(network.nodes[1]['label'], '1984')
        self.assertEqual(len(network.edges), 1)

    def test_export_has_no_external_resources(self):
        network = Network(directed=True, cdn_resources='in_line', select_menu=True)
        add_claim(network, self.claim())
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'graph.html'
            write_view(network, path)
            html = path.read_text()
            parser = Resources()
            parser.feed(html)
            self.assertEqual(parser.external, [])
            self.assertIn('vis.Network', html)

    def test_account_catalogue_export_preserves_claims_values_and_qualifications(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            groups = write_account_fixture(root)
            original = {p: p.read_bytes() for p in root.rglob('*') if p.is_file()}
            output = root / 'accounts.html'
            with (
                patch(
                    'sys.argv',
                    [
                        'visualise',
                        '--graph',
                        str(root / 'graph'),
                        '--output',
                        str(output),
                        '--visual-theme',
                        'matrix',
                    ],
                ),
                patch('knot.visualise.write_view', wraps=write_view) as export,
                patch('sys.stdout', new=io.StringIO()),
            ):
                main()
            network = export.call_args.args[0]
            self.assertEqual(len(network.nodes), 2)
            self.assertEqual(len(network.edges), 2)
            claims = {edge['id']: edge for edge in network.edges}
            first = claims['urn:assertion:first']
            expected = [
                {k: group[k] for k in ('id', 'relationship', 'qualification', 'reviewer')}
                for group in groups
            ]
            self.assertEqual(first['detail']['evidence_accounts'], expected)
            self.assertEqual(
                claims['urn:assertion:retelling']['detail']['evidence_accounts'], expected[:1]
            )
            self.assertEqual(first['status'], 'Accepted')
            self.assertEqual(first['origin'], 'Explicit')
            self.assertEqual(
                first['detail']['evidence'][0]['quote'],
                'Alex reported 18 events in the Orion rollout.',
            )
            attribute = network.get_node('urn:outcome:orion')['attributes'][0]
            self.assertEqual(attribute['detail']['evidence_accounts'], expected[1:])
            self.assertEqual(attribute['detail']['literal_value'], '18')
            self.assertEqual(attribute['status'], 'Unreviewed')
            self.assertNotIn('_evidence_account_spans', json.dumps(network.edges + network.nodes))
            self.assertNotIn('<script>window.accountInjected=true</script>', output.read_text())
            for path, body in original.items():
                self.assertEqual(path.read_bytes(), body)

    def test_invalid_account_pin_prevents_viewer_export(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            groups = write_account_fixture(root)
            groups[0]['sources'][0]['quote'] = 'Invented source wording'
            (root / 'curation/evidence-accounts.json').write_text(
                json.dumps(dict(schema_version=1, groups=groups))
            )
            output = root / 'accounts.html'
            with (
                patch(
                    'sys.argv',
                    [
                        'visualise',
                        '--graph',
                        str(root / 'graph'),
                        '--output',
                        str(output),
                        '--visual-theme',
                        'matrix',
                    ],
                ),
                patch('sys.stderr', new=io.StringIO()) as error,
                self.assertRaises(SystemExit) as failed,
            ):
                main()
            self.assertEqual(failed.exception.code, 2)
            self.assertIn('quotation', error.getvalue())
            self.assertFalse(output.exists())

    def test_theme_links_are_separate_from_semantic_claims(self):
        network = Network(directed=True, cdn_resources='in_line')
        add_claim(network, self.claim())
        records = [
            {
                'subject': {'id': 'person:1'},
                'object': {'id': 'project:1'},
                'themes': [{'id': 'learning', 'label': 'Learning'}],
            }
        ]
        add_themes(network, records + records)
        self.assertEqual(len(network.edges), 3)
        links = [e for e in network.edges if e.get('organisation')]
        self.assertEqual(len(links), 2)
        self.assertTrue(all('not a factual relationship' in e['title'] for e in links))
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'graph.html'
            write_view(network, output)
            self.assertIn('002 ENTITIES / 001 CLAIMS / 1 THEMES', output.read_text())

    def test_theme_link_keeps_mixed_membership_statuses_visible(self):
        network = Network(directed=True)
        add_claim(network, self.claim())
        records = [
            {
                'id': aid,
                'subject': {'id': 'person:1'},
                'object': {'id': 'project:1'},
                'themes': [{'id': 'learning', 'label': 'Learning', 'status': status}],
            }
            for aid, status in [('one', 'Accepted'), ('two', 'Unreviewed')]
        ]
        add_themes(network, records)
        for edge in network.edges[1:]:
            self.assertIn('Accepted (1)', edge['title'])
            self.assertIn('Unreviewed (1)', edge['title'])
