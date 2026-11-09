import io
import json
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path
from unittest.mock import patch

from pyoxigraph import NamedNode, RdfFormat
from pyvis.network import Network
from retrieval_fixture import SEED, WORK, make_fixture

from knot.note_sources import add_note_sources
from knot.notes import create_note, save_note
from knot.provenance import source_pin
from knot.query import load_store
from knot.rdf import LABEL, META, VOCAB, Dataset, values
from knot.visualise import add_note_navigation, curated_notes, main, write_view


class EmbeddedNotes(HTMLParser):
    def __init__(self):
        super().__init__()
        self.reading = False
        self.body = ''

    def handle_starttag(self, tag, attrs):
        self.reading = tag == 'script' and dict(attrs).get('id') == 'curated-notes'

    def handle_endtag(self, tag):
        if tag == 'script':
            self.reading = False

    def handle_data(self, data):
        if self.reading:
            self.body += data


class CuratedViewerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        make_fixture(self.root)
        self.original = create_note(
            self.root,
            'Please record that recovery remains planned.',
            author='Owner',
            entities=[SEED],
        )
        self.derivation = {
            'method': 'faithful_restatement',
            'qualification': 'No completed recovery established.',
            'sources': [source_pin(self.root, self.original['revision'], self.original['body'], 0)],
        }

    def note(self, body='Recovery is planned. Completion is not established.', **kwargs):
        return create_note(
            self.root,
            body,
            title=kwargs.pop('title', 'Recovery remains a plan'),
            author='Codex',
            agent='Codex',
            kind='Observation',
            entities=kwargs.pop('entities', [SEED, WORK]),
            derivation=self.derivation,
            **kwargs,
        )

    def export(self, *entities):
        store = load_store(self.root / 'graph', include_notes=False)
        add_note_sources(self.root, store, store, {})
        return curated_notes(self.root, store, entities)

    def test_shared_note_is_embedded_once_with_readable_body_and_original_evidence(self):
        saved = self.note()
        result = self.export(SEED, WORK)
        self.assertEqual(set(result['notes']), {saved['note']})
        self.assertEqual(result['entities'], {SEED: [saved['note']], WORK: [saved['note']]})
        note = result['notes'][saved['note']]
        self.assertEqual(note['body'], saved['body'])
        self.assertEqual(note['revision'], saved['revision'])
        self.assertEqual(note['author'], 'Codex')
        self.assertEqual(note['qualification'], self.derivation['qualification'])
        self.assertEqual(note['sources'][0]['quote'], self.original['body'])
        self.assertEqual(note['sources'][0]['snapshot'], self.original['body_path'])
        self.assertEqual(note['sources'][0]['revision'], self.original['revision'])
        self.assertEqual(note['sources'][0]['start_line'], 1)

    def test_only_current_curated_heads_are_exported(self):
        first = self.note()
        latest = save_note(
            self.root,
            first['note'],
            'The source still describes a plan.',
            expected=first['revision'],
            agent='Codex',
        )
        note = self.export(SEED)['notes'][first['note']]
        self.assertEqual(note['revision'], latest['revision'])
        self.assertEqual(note['body'], latest['body'])

    def test_unassociated_notes_and_entities_outside_export_are_not_added(self):
        self.note(entities=[])
        self.note(entities=[WORK])
        result = self.export(SEED)
        self.assertEqual(result, {'notes': {}, 'entities': {}})

    def test_same_label_does_not_create_a_note_association(self):
        data = Dataset()
        data.add('urn:project:unrelated', LABEL, 'Orion', literal=True)
        (self.root / 'graph/other.trig').write_text(data.text())
        self.note(entities=[SEED])
        result = self.export('urn:project:unrelated')
        self.assertFalse(result['notes'])

    def test_accepted_identity_projection_is_used_for_associations(self):
        saved = self.note(entities=[SEED])
        store = load_store(self.root / 'graph', include_notes=False)
        add_note_sources(self.root, store, store, {})
        # The adapter supplies the already-resolved navigation view. Export must
        # use it rather than the source revision's historical association list.
        current = values(store, saved['revision'], VOCAB + 'noteMetadata')[0]
        header = json.loads(current.value)
        header['navigation_entities'] = [WORK]
        for quad in list(
            store.quads_for_pattern(
                NamedNode(saved['revision']), NamedNode(VOCAB + 'noteMetadata'), None, META
            )
        ):
            store.remove(quad)
        data = Dataset()
        data.add(saved['revision'], VOCAB + 'noteMetadata', json.dumps(header), literal=True)
        store.load(input=data.text().encode(), format=RdfFormat.TRIG)
        result = curated_notes(self.root, store, [SEED, WORK])
        self.assertEqual(result['entities'], {WORK: [saved['note']]})

    def test_corrupt_original_is_not_presented_as_verified_curated_context(self):
        self.note()
        (self.root / self.original['body_path']).write_text('Changed original')
        with self.assertRaises(ValueError):
            self.export(SEED)

    def test_note_json_preserves_hostile_text_without_creating_html(self):
        body = '</script><script>window.injected=true</script>\n<img src=x onerror=alert(1)>'
        saved = self.note(body)
        payload = self.export(SEED)
        network = Network(directed=True, cdn_resources='in_line')
        network.add_node(SEED, label='Orion', role='entity', shape='dot')
        output = self.root / 'view.html'
        write_view(network, output, notes=payload)
        parser = EmbeddedNotes()
        parser.feed(output.read_text())
        self.assertEqual(json.loads(parser.body)['notes'][saved['note']]['body'], body)
        self.assertNotIn('</script>', parser.body)
        self.assertIn('window.injected=true', parser.body)

    def test_note_links_connect_free_writing_to_an_associated_entity(self):
        target = self.note()
        first = create_note(
            self.root,
            'My experience suggests a possible foundation.',
            title='AI reflection',
            author='Owner',
            navigation={
                'themes': [],
                'declarations': [],
                'links': [
                    {'note': target['note'], 'reason': 'Offers a possible answer, not proof.'}
                ],
            },
        )
        isolated = create_note(self.root, 'An unlinked idea.', title='Unlinked')
        store = load_store(self.root / 'graph')
        add_note_sources(self.root, store, store, {})
        payload = curated_notes(self.root, store, [], include_all=True)
        network = Network(directed=True)
        add_note_navigation(network, payload, {})
        by_id = {n['id']: n for n in network.nodes}
        self.assertEqual(by_id[first['note']]['role'], 'note')
        self.assertIn(isolated['note'], by_id)
        self.assertEqual(payload['notes'][first['note']]['body'], first['body'])
        links = [e for e in network.edges if e['from'] == first['note']]
        self.assertEqual(len(links), 1)
        self.assertEqual(links[0]['to'], target['note'])
        self.assertEqual(links[0]['detail']['rationale'], 'Offers a possible answer, not proof.')
        self.assertNotIn('status', links[0])
        self.assertTrue(any(e['from'] == target['note'] and e['to'] == SEED for e in network.edges))
        self.assertFalse(any(e['from'] == first['note'] and e['to'] == SEED for e in network.edges))

        focused = Network(directed=True)
        included = add_note_navigation(focused, payload, {}, focus=target['title'])
        self.assertIn(first['note'], included)
        self.assertIn(target['note'], included)
        self.assertNotIn(isolated['note'], included)

    def test_note_only_dataset_exports_without_claims(self):
        root = self.root / 'only-notes'
        note = create_note(root, 'Free writing survives without triples.', title='Free writing')
        output = self.root / 'only-notes.html'
        with (
            patch(
                'sys.argv', ['visualise', '--graph', str(root / 'graph'), '--output', str(output)]
            ),
            patch('sys.stdout', new=io.StringIO()),
            patch('knot.visualise.write_view', wraps=write_view) as export,
        ):
            main()
        network = export.call_args.args[0]
        self.assertEqual([n['id'] for n in network.nodes], [note['note']])
        self.assertEqual(network.edges, [])
        self.assertIn('Free writing survives without triples.', output.read_text())

    def test_accepted_only_export_does_not_promote_note_links(self):
        self.note()
        output = self.root / 'accepted.html'
        with (
            patch(
                'sys.argv',
                [
                    'visualise',
                    '--graph',
                    str(self.root / 'graph'),
                    '--output',
                    str(output),
                    '--accepted-only',
                ],
            ),
            patch('sys.stdout', new=io.StringIO()),
            patch('knot.visualise.write_view', wraps=write_view) as export,
        ):
            main()
        network = export.call_args.args[0]
        self.assertFalse(any(e.get('navigation') for e in network.edges))
        self.assertFalse(any(n.get('role') == 'note' for n in network.nodes))


if __name__ == '__main__':
    unittest.main()
