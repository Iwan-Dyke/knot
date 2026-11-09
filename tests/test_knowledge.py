import json
import tempfile
import unittest
from pathlib import Path

from pyoxigraph import Literal, NamedNode, Quad, RdfFormat, Store

from knot.knowledge import _records, _signature, build_organisation, entries, rebuild
from knot.rdf import ATTRIBUTED, DERIVED, META, RDF_TYPE, VOCAB, Dataset
from knot.review import fingerprint
from knot.themes import definition_fingerprint


class KnowledgeTests(unittest.TestCase):
    def setUp(self):
        self.dataset = Dataset()
        for index, subject in enumerate(('urn:person:alex', 'urn:person:other')):
            aid = f'urn:assertion:{index}'
            evidence, revision = f'urn:evidence:{index}', f'urn:revision:{index}'
            self.dataset.add(subject, VOCAB + 'workedOn', f'urn:project:{index}', graph=aid)
            for key, value in [
                ('reviewStatus', 'Accepted'),
                ('origin', 'Explicit'),
                ('lifecycle', 'Active'),
            ]:
                self.dataset.add(aid, VOCAB + key, VOCAB + value)
            self.dataset.add(aid, RDF_TYPE, VOCAB + 'Assertion')
            self.dataset.add(aid, ATTRIBUTED, 'urn:agent:test')
            for key, value in [
                ('subjectLabel', 'Alex'),
                ('objectLabel', 'Atlas'),
                ('rationale', 'Source account'),
            ]:
                self.dataset.add(aid, VOCAB + key, value, literal=True)
            self.dataset.add(aid, DERIVED, evidence)
            self.dataset.add(
                evidence, VOCAB + 'quote', 'Learning Python through a project.', literal=True
            )
            self.dataset.add(evidence, VOCAB + 'revision', revision)
            self.dataset.add(revision, VOCAB + 'snapshotPath', 'source.md', literal=True)
            self.dataset.add(revision, VOCAB + 'sha256', 'synthetic', literal=True)
        self.store = Store()
        self.store.load(input=self.dataset.text(), format=RdfFormat.TRIG)
        self.catalogue = {
            'themes': [
                {'id': 'learning', 'label': 'Learning', 'keywords': ['learning']},
                {'id': 'software', 'label': 'Software', 'keywords': ['python']},
            ],
            'entity_types': {'Person': ['Alex'], 'Project': ['Atlas']},
            'overrides': {
                'urn:assertion:0': {'kind': 'Thought', 'themes': ['learning', 'software']}
            },
        }

    def test_shared_themes_preserve_identity_and_review_fingerprints(self):
        before = fingerprint(self.store, 'urn:assertion:0')
        content = build_organisation(self.store, self.catalogue)
        self.store.load(input=content, format=RdfFormat.TRIG)
        self.assertEqual(content, build_organisation(self.store, self.catalogue))
        self.assertEqual(before, fingerprint(self.store, 'urn:assertion:0'))
        rows = entries(self.store, themes=['learning'])
        self.assertEqual(len(rows), 2)
        self.assertEqual(len({r['subject']['id'] for r in rows}), 2)
        self.assertEqual(rows[0]['kind'], 'Thought')
        self.assertEqual(rows[0]['status'], 'Accepted')
        self.assertEqual(rows[0]['subject']['types'], ['Person'])
        self.assertEqual(len(rows[0]['themes']), 2)
        self.assertEqual(rows[0]['evidence'][0]['quote'], 'Learning Python through a project.')
        self.assertEqual(len(entries(self.store, kind='Thought')), 1)

    def test_invalid_classification_fails_explicitly(self):
        self.catalogue['overrides']['urn:assertion:0']['themes'] = ['missing']
        with self.assertRaisesRegex(ValueError, 'theme'):
            build_organisation(self.store, self.catalogue)
        self.catalogue['overrides'] = {'urn:missing': {'kind': 'Thought'}}
        with self.assertRaisesRegex(ValueError, 'Unknown assertion'):
            build_organisation(self.store, self.catalogue)

    def test_type_override_targets_identity_and_remains_unreviewed_navigation(self):
        before = fingerprint(self.store, 'urn:assertion:0')
        self.catalogue['entity_type_overrides'] = {'urn:project:0': ['Document']}
        content = build_organisation(self.store, self.catalogue)
        self.store.load(input=content, format=RdfFormat.TRIG)
        rows = entries(self.store)
        self.assertEqual(rows[0]['object']['types'], ['Document'])
        self.assertEqual(rows[1]['object']['types'], ['Project'])
        self.assertEqual(rows[0]['classification']['status'], 'Unreviewed')
        self.assertEqual(rows[0]['status'], 'Accepted')
        self.assertEqual(fingerprint(self.store, 'urn:assertion:0'), before)
        self.assertEqual(build_organisation(self.store, self.catalogue), content)

    def test_type_overrides_reject_unknown_identities_or_types(self):
        for overrides in (
            {'urn:absent': ['Tool']},
            {'urn:project:0': ['Spaceship']},
            {'urn:project:0': []},
            {'urn:project:0': ['Entity', 'Project']},
        ):
            with self.subTest(overrides=overrides):
                self.catalogue['entity_type_overrides'] = overrides
                with self.assertRaises(ValueError):
                    build_organisation(self.store, self.catalogue)

    def test_proposal_classification_does_not_imply_an_outcome_or_acceptance(self):
        self.catalogue['overrides'] = {}
        aid = NamedNode('urn:assertion:0')
        triple = next(self.store.quads_for_pattern(None, None, None, aid))
        self.store.remove(triple)
        self.store.add(Quad(triple.subject, NamedNode(VOCAB + 'proposed'), triple.object, aid))
        before = fingerprint(self.store, aid.value)
        self.store.load(input=build_organisation(self.store, self.catalogue), format=RdfFormat.TRIG)
        row = next(r for r in entries(self.store) if r['id'] == aid.value)
        self.assertEqual(row['kind'], 'Idea')
        self.assertNotIn('Outcome', row['object']['types'])
        self.assertEqual(row['classification']['status'], 'Unreviewed')
        self.assertEqual(fingerprint(self.store, aid.value), before)

    def test_theme_does_not_create_semantic_connections(self):
        self.store.load(input=build_organisation(self.store, self.catalogue), format=RdfFormat.TRIG)
        self.assertEqual(
            len(
                list(self.store.quads_for_pattern(None, NamedNode(VOCAB + 'relatedTo'), None, None))
            ),
            0,
        )
        with self.assertRaisesRegex(ValueError, 'Unknown theme'):
            entries(self.store, themes=['missing'])

    def test_unified_view_includes_frameworks_and_unclassified_records(self):
        self.store.add(
            Quad(
                NamedNode('urn:assertion:1'),
                NamedNode(VOCAB + 'recordKind'),
                NamedNode(VOCAB + 'FrameworkDefinition'),
                META,
            )
        )
        self.assertEqual(len(entries(self.store)), 2)
        self.assertEqual({r['kind'] for r in entries(self.store)}, {'Unspecified'})
        self.store.load(input=build_organisation(self.store, self.catalogue), format=RdfFormat.TRIG)
        self.assertEqual([r['kind'] for r in entries(self.store)], ['Thought', 'Definition'])

    def test_changed_identity_marks_classification_stale_without_hiding_record(self):
        self.store.load(input=build_organisation(self.store, self.catalogue), format=RdfFormat.TRIG)
        triple = next(self.store.quads_for_pattern(None, None, None, NamedNode('urn:assertion:0')))
        self.store.remove(triple)
        self.store.add(
            Quad(NamedNode('urn:person:new'), triple.predicate, triple.object, triple.graph_name)
        )
        rows = entries(self.store)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]['kind'], 'Unspecified')
        self.assertEqual(rows[0]['themes'], [])
        self.assertEqual(rows[0]['classification']['status'], 'Stale')

    def test_multiple_citations_are_retained_without_duplicate_records(self):
        self.store.add(
            Quad(NamedNode('urn:assertion:0'), NamedNode(DERIVED), NamedNode('urn:second'), META)
        )
        self.store.add(
            Quad(
                NamedNode('urn:second'),
                NamedNode(VOCAB + 'revision'),
                NamedNode('urn:revision:0'),
                META,
            )
        )
        self.store.add(
            Quad(
                NamedNode('urn:second'),
                NamedNode(VOCAB + 'quote'),
                Literal('Second passage.'),
                META,
            )
        )
        self.store.load(input=build_organisation(self.store, self.catalogue), format=RdfFormat.TRIG)
        rows = entries(self.store)
        self.assertEqual(len(rows), 2)
        self.assertEqual(len(rows[0]['evidence']), 2)

    def test_removed_premise_invalidates_shared_entity_classification(self):
        # Types are aggregated over incident assertions, so removing one premise
        # must invalidate annotations even on otherwise unchanged records.
        self.store.load(input=build_organisation(self.store, self.catalogue), format=RdfFormat.TRIG)
        self.store.remove(
            next(self.store.quads_for_pattern(None, None, None, NamedNode('urn:assertion:1')))
        )
        remaining = entries(self.store)
        self.assertEqual(len(remaining), 1)
        self.assertEqual(remaining[0]['classification']['status'], 'Stale')
        self.assertEqual(remaining[0]['subject']['types'], ['Entity'])

    def test_rebuild_is_idempotent_and_guards_edited_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'graph').mkdir()
            (root / 'organisation').mkdir()
            (root / 'graph/knowledge.trig').write_text(self.dataset.text())
            (root / 'organisation/catalogue.json').write_text(json.dumps(self.catalogue))
            first = rebuild(root)
            files = {p: p.read_bytes() for p in root.rglob('*') if p.is_file()}
            self.assertEqual(first, rebuild(root))
            self.assertEqual(files, {p: p.read_bytes() for p in files})
            output = root / 'graph/organisation.trig'
            edited = output.read_bytes() + b'\n# manual edit\n'
            output.write_bytes(edited)
            with self.assertRaisesRegex(ValueError, 'reconcile'):
                rebuild(root)
            self.assertEqual(output.read_bytes(), edited)

    def theme_reviews(self):
        return {
            'schema_version': 1,
            'reviewer': 'Test assistant',
            'reviewer_kind': 'Assistant',
            'reviewed_at': '2026-11-03',
            'theme_fingerprints': {
                t['id']: definition_fingerprint(t) for t in self.catalogue['themes']
            },
            'records': {
                'urn:assertion:0': {
                    'fingerprint': _signature(_records(self.store)[0]),
                    'decisions': {
                        'learning': {
                            'status': 'Accepted',
                            'rationale': 'Explicit learning activity.',
                        },
                        'software': {
                            'status': 'Rejected',
                            'rationale': 'Focus this example on learning.',
                        },
                    },
                }
            },
        }

    def test_theme_review_is_separate_and_survives_rebuild(self):
        reviews = self.theme_reviews()
        before = fingerprint(self.store, 'urn:assertion:0')
        output = build_organisation(self.store, self.catalogue, theme_reviews=reviews)
        self.store.load(input=output, format=RdfFormat.TRIG)
        self.assertEqual(
            output, build_organisation(self.store, self.catalogue, theme_reviews=reviews)
        )
        record = entries(self.store)[0]
        self.assertEqual(record['status'], 'Accepted')
        self.assertEqual(record['classification']['status'], 'Unreviewed')
        self.assertEqual(
            [(t['id'], t['status']) for t in record['themes']], [('learning', 'Accepted')]
        )
        self.assertEqual(record['theme_reviews'][1]['status'], 'Rejected')
        self.assertEqual(record['themes'][0]['reviewer_kind'], 'Assistant')
        self.assertEqual(fingerprint(self.store, 'urn:assertion:0'), before)
        self.assertEqual(entries(self.store)[1]['themes'][0]['status'], 'Unreviewed')

    def test_changed_theme_definition_cannot_reuse_acceptance(self):
        reviews = self.theme_reviews()
        self.catalogue['themes'][0]['description'] = 'A different scope.'
        self.store.load(
            input=build_organisation(self.store, self.catalogue, theme_reviews=reviews),
            format=RdfFormat.TRIG,
        )
        theme = entries(self.store)[0]['themes'][0]
        self.assertEqual(theme['status'], 'Unreviewed')
        self.assertEqual(theme['review_state'], 'Stale')

    def test_invalid_theme_review_fails_explicitly(self):
        reviews = self.theme_reviews()
        reviews['records']['urn:assertion:0']['decisions']['learning']['status'] = 'Probably'
        with self.assertRaisesRegex(ValueError, 'status'):
            build_organisation(self.store, self.catalogue, theme_reviews=reviews)

    def test_theme_review_survives_disk_rebuild_and_keyword_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'graph').mkdir()
            (root / 'organisation').mkdir()
            (root / 'graph/knowledge.trig').write_text(self.dataset.text())
            self.catalogue['themes'][0]['keywords'] = ['no longer matches']
            self.catalogue['overrides'] = {}
            (root / 'organisation/catalogue.json').write_text(json.dumps(self.catalogue))
            (root / 'organisation/theme-reviews.json').write_text(json.dumps(self.theme_reviews()))
            result = rebuild(root)
            content = (root / 'graph/organisation.trig').read_bytes()
            self.assertEqual(result, rebuild(root))
            self.assertEqual(content, (root / 'graph/organisation.trig').read_bytes())
            self.assertEqual(result['theme_review_status']['Accepted'], 1)
            self.assertEqual(result['theme_review_status']['Rejected'], 1)

    def test_changed_record_cannot_reuse_theme_acceptance(self):
        reviews = self.theme_reviews()
        triple = next(self.store.quads_for_pattern(None, None, None, NamedNode('urn:assertion:0')))
        self.store.remove(triple)
        self.store.add(
            Quad(NamedNode('urn:person:new'), triple.predicate, triple.object, triple.graph_name)
        )
        self.store.load(
            input=build_organisation(self.store, self.catalogue, theme_reviews=reviews),
            format=RdfFormat.TRIG,
        )
        self.assertTrue(all(t['status'] == 'Unreviewed' for t in entries(self.store)[0]['themes']))
        self.assertTrue(all(t['review_state'] == 'Stale' for t in entries(self.store)[0]['themes']))

    def test_individual_human_decision_does_not_relabel_assistant_reviews(self):
        reviews = self.theme_reviews()
        decision = reviews['records']['urn:assertion:0']['decisions']['software']
        decision.update(reviewer='Alex', reviewer_kind='Human', reviewed_at='2026-11-04')
        self.store.load(
            input=build_organisation(self.store, self.catalogue, theme_reviews=reviews),
            format=RdfFormat.TRIG,
        )
        checked = {t['id']: t for t in entries(self.store)[0]['theme_reviews']}
        self.assertEqual(checked['software']['reviewer_kind'], 'Human')
        self.assertEqual(checked['learning']['reviewer_kind'], 'Assistant')
