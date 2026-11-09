import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from unittest.mock import patch

from pyoxigraph import NamedNode, RdfFormat, Store
from retrieval_fixture import CLAIM, CLAIM_SOURCE, ROUTE, SEED, SOURCE_WORK, WORK, make_fixture

from knot.access import AccessScope
from knot.inventory import digest
from knot.notes import build_note_projection, create_note, note_history, read_note, save_note
from knot.query import load_store
from knot.rdf import DERIVED, LABEL, RDF_TYPE, VOCAB, one, values
from knot.retrieval import Policy, lookup, retrieve, serialise
from knot.review import decide, fingerprint

CURRENT = NamedNode('urn:knot:notes')
HISTORY = NamedNode('urn:knot:note-history')
CONCEPT = 'urn:concept:constraints'


class NoteGraphTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.dataset = make_fixture(self.root)
        self.dataset.add(CONCEPT, RDF_TYPE, VOCAB + 'Concept')
        (self.root / 'graph/claims.trig').write_text(self.dataset.text())

    def files(self):
        return {
            p.relative_to(self.root): p.read_bytes() for p in self.root.rglob('*') if p.is_file()
        }

    def entities(self, store, subject, graph=CURRENT):
        return {v.value for v in values(store, subject, VOCAB + 'associatedEntity', graph)}

    def test_multiple_canonical_entities_share_one_body_and_no_assertion_status(self):
        original = self.files()
        initial = load_store(self.root / 'graph')
        assertions = set(
            initial.quads_for_pattern(
                None, NamedNode(RDF_TYPE), NamedNode(VOCAB + 'Assertion'), None
            )
        )
        body = 'A reflection on engineering and constraints.\r\nλ🙂\n'
        note = create_note(self.root, body, entities=[CONCEPT, SEED], kind='Thought')
        store = load_store(self.root / 'graph')
        self.assertEqual(self.entities(store, note['note']), {SEED, CONCEPT})
        self.assertEqual(note['entities'], sorted([SEED, CONCEPT]))
        self.assertEqual(
            one(store, note['note'], VOCAB + 'noteKind', CURRENT).value, VOCAB + 'Thought'
        )
        self.assertEqual(
            one(store, note['note'], VOCAB + 'currentRevision', CURRENT).value, note['revision']
        )
        found = list(
            store.query(f"""SELECT ?note WHERE {{
            GRAPH <urn:knot:notes> {{ ?note <{VOCAB}associatedEntity> <{CONCEPT}> , <{SEED}> }}
        }}""")
        )
        self.assertEqual([row['note'].value for row in found], [note['note']])
        self.assertEqual((self.root / note['body_path']).read_bytes(), body.encode())
        self.assertEqual(
            list((self.root / 'sources/revisions').glob('*/note.txt')),
            [self.root / note['body_path']],
        )
        self.assertTrue(
            all((self.root / path).read_bytes() == content for path, content in original.items())
        )
        for graph in (CURRENT, HISTORY):
            self.assertFalse(values(store, note['note'], VOCAB + 'reviewStatus', graph))
            self.assertFalse(values(store, note['revision'], VOCAB + 'reviewStatus', graph))
        self.assertNotIn(body, build_note_projection(self.root, store).decode())
        self.assertEqual(
            set(
                store.quads_for_pattern(
                    None, NamedNode(RDF_TYPE), NamedNode(VOCAB + 'Assertion'), None
                )
            ),
            assertions,
        )

    def test_note_only_dataset_supports_independent_unclassified_resources(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            note = create_note(root, 'No entity or classification required.')
            store = load_store(root / 'graph')
            self.assertEqual(note['entities'], [])
            self.assertIsNone(note['kind'])
            self.assertIn(NamedNode(VOCAB + 'Note'), values(store, note['note'], RDF_TYPE, CURRENT))
            self.assertFalse(self.entities(store, note['note']))
            self.assertFalse(values(store, note['note'], VOCAB + 'noteKind', CURRENT))
            self.assertFalse((root / 'graph').exists())

    def test_associations_and_classification_change_only_through_revisions(self):
        first = create_note(self.root, 'Same source.', entities=[SEED], kind='Hypothesis')
        first_path = self.root / 'notes/revisions' / (first['revision'].rsplit(':', 1)[1] + '.json')
        original = first_path.read_bytes()
        second = save_note(
            self.root,
            first['note'],
            first['body'],
            expected=first['revision'],
            entities=[SEED, CONCEPT],
        )
        third = save_note(
            self.root,
            first['note'],
            first['body'],
            expected=second['revision'],
            entities=[CONCEPT],
            kind=None,
        )
        self.assertEqual(first_path.read_bytes(), original)
        self.assertEqual(len({r['body_path'] for r in note_history(self.root, first['note'])}), 1)
        store = load_store(self.root / 'graph')
        self.assertEqual(self.entities(store, first['note']), {CONCEPT})
        self.assertEqual(self.entities(store, first['revision'], HISTORY), {SEED})
        self.assertEqual(self.entities(store, second['revision'], HISTORY), {SEED, CONCEPT})
        self.assertEqual(self.entities(store, third['revision'], HISTORY), {CONCEPT})
        self.assertFalse(values(store, first['note'], VOCAB + 'noteKind', CURRENT))
        self.assertEqual(
            one(store, first['revision'], VOCAB + 'noteKind', HISTORY).value, VOCAB + 'Hypothesis'
        )
        cleared = save_note(
            self.root, first['note'], first['body'], expected=third['revision'], entities=[]
        )
        self.assertFalse(self.entities(load_store(self.root / 'graph'), cleared['note']))

    def test_accepted_identity_mappings_are_reused_and_normalized_idempotently(self):
        note = create_note(
            self.root, 'Explicit identity.', entities=[SOURCE_WORK, CLAIM_SOURCE, WORK]
        )
        self.assertEqual(note['entities'], [WORK])
        before = self.files()
        same = save_note(
            self.root,
            note['note'],
            note['body'],
            expected=note['revision'],
            entities=[CLAIM_SOURCE, SOURCE_WORK],
        )
        self.assertEqual(same['revision'], note['revision'])
        self.assertEqual(self.files(), before)

    def test_labels_unknown_ids_and_unreviewed_identity_proposals_do_not_establish_identity(self):
        self.dataset.add('urn:mention:pending', LABEL, 'Orion', literal=True)
        self.dataset.add('urn:mapping:pending', VOCAB + 'sourceEntity', 'urn:mention:pending')
        self.dataset.add('urn:mapping:pending', VOCAB + 'entity', SEED)
        self.dataset.add('urn:mapping:pending', VOCAB + 'reviewStatus', VOCAB + 'Unreviewed')
        (self.root / 'graph/claims.trig').write_text(self.dataset.text())
        before = self.files()
        for entities in (
            ['Orion'],
            ['urn:entity:unknown'],
            ['urn:mention:pending'],
            'urn:project:orion',
        ):
            with self.subTest(entities=entities), self.assertRaises(ValueError):
                create_note(self.root, 'Not silently merged.', entities=entities)
            self.assertEqual(self.files(), before)
        for kind in ('Truth', [], False):
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                create_note(
                    self.root, 'Unclassified is allowed, invented kinds are not.', kind=kind
                )

    def test_same_label_entities_remain_distinct(self):
        note = create_note(
            self.root, 'Two different projects.', entities=[SEED, 'urn:project:other']
        )
        self.assertEqual(
            self.entities(load_store(self.root / 'graph'), note['note']),
            {SEED, 'urn:project:other'},
        )

    def test_invalid_updates_and_conflicting_accepted_identities_leave_notes_unchanged(self):
        note = create_note(self.root, 'Explicit association.', entities=[SEED], kind='Thought')
        before = self.files()
        for extra in ({'entities': ['urn:unknown']}, {'kind': 'ObjectiveTruth'}):
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                save_note(self.root, note['note'], note['body'], expected=note['revision'], **extra)
            self.assertEqual(self.files(), before)
        self.dataset.add('urn:mapping:conflict', VOCAB + 'sourceEntity', SOURCE_WORK)
        self.dataset.add('urn:mapping:conflict', VOCAB + 'entity', CONCEPT)
        self.dataset.add('urn:mapping:conflict', VOCAB + 'reviewStatus', VOCAB + 'Accepted')
        (self.root / 'graph/claims.trig').write_text(self.dataset.text())
        before = self.files()
        with self.assertRaisesRegex(ValueError, 'Conflicting accepted identity'):
            create_note(self.root, 'Cannot choose a mapping.', entities=[SOURCE_WORK])
        self.assertEqual(self.files(), before)

    def test_later_accepted_identity_is_projected_without_rewriting_declared_history(self):
        note = create_note(self.root, 'A declared association.', entities=[WORK])
        before = (self.root / 'notes/registry.json').read_bytes()
        self.dataset.add('urn:mapping:later', VOCAB + 'sourceEntity', WORK)
        self.dataset.add('urn:mapping:later', VOCAB + 'entity', CONCEPT)
        self.dataset.add('urn:mapping:later', VOCAB + 'reviewStatus', VOCAB + 'Accepted')
        (self.root / 'graph/claims.trig').write_text(self.dataset.text())
        store = load_store(self.root / 'graph')
        self.assertEqual(self.entities(store, note['note']), {CONCEPT})
        self.assertEqual(self.entities(store, note['revision'], HISTORY), {WORK})
        self.assertEqual(read_note(self.root, note['note'])['entities'], [WORK])
        self.assertEqual((self.root / 'notes/registry.json').read_bytes(), before)

    def test_later_identity_also_projects_declared_entities_but_retains_their_history(self):
        source = 'urn:knot:entity:00000000-0000-4000-8000-000000000105'
        note = create_note(
            self.root,
            'A declared concept.',
            navigation={
                'themes': [],
                'links': [],
                'declarations': [
                    {
                        'id': source,
                        'label': 'Declared concept',
                        'type': 'Concept',
                        'quote': 'declared concept',
                        'offset': 2,
                    }
                ],
            },
        )
        self.dataset.add('urn:mapping:declaration', VOCAB + 'sourceEntity', source)
        self.dataset.add('urn:mapping:declaration', VOCAB + 'entity', CONCEPT)
        self.dataset.add('urn:mapping:declaration', VOCAB + 'reviewStatus', VOCAB + 'Accepted')
        (self.root / 'graph/claims.trig').write_text(self.dataset.text())
        before = self.files()
        store = load_store(self.root / 'graph')
        self.assertEqual(self.entities(store, note['note']), {CONCEPT})
        self.assertEqual(self.entities(store, note['revision'], HISTORY), {source})
        self.assertEqual(self.files(), before)

    def test_projection_is_deterministic_verified_and_does_not_mutate_inputs(self):
        note = create_note(self.root, 'One unchanged source.', entities=[SEED, CONCEPT])
        create_note(self.root, 'Independent.', kind='Question')
        store = load_store(self.root / 'graph', include_notes=False)
        original = set(store)
        before = self.files()
        projection = build_note_projection(self.root, store)
        self.assertEqual(build_note_projection(self.root, store), projection)
        self.assertEqual(set(store), original)
        self.assertEqual(self.files(), before)
        parsed = Store()
        parsed.load(input=projection, format=RdfFormat.TRIG)
        self.assertEqual(
            one(parsed, note['revision'], VOCAB + 'sha256', HISTORY).value, note['body_sha256']
        )
        self.assertEqual(set(load_store(self.root / 'graph')), set(load_store(self.root / 'graph')))
        (self.root / note['body_path']).write_text('Corruption')
        with self.assertRaisesRegex(ValueError, 'hash'):
            build_note_projection(self.root, store)
        self.assertEqual(set(store), original)
        with self.assertRaises(ValueError):
            load_store(self.root / 'graph')

    def test_corrupt_revision_manifest_cannot_be_projected(self):
        note = create_note(self.root, 'A source.', entities=[SEED])
        manifest = self.root / 'notes/revisions' / (note['revision'].rsplit(':', 1)[1] + '.json')
        manifest.write_bytes(manifest.read_bytes() + b' ')
        before = self.files()
        with self.assertRaisesRegex(ValueError, 'hash'):
            load_store(self.root / 'graph')
        self.assertEqual(self.files(), before)

    def test_projection_reads_one_committed_registry_snapshot_during_a_save(self):
        import knot.notes as notes

        note = create_note(self.root, 'A source.', entities=[SEED])
        original = notes._history
        changed = False

        def interleaved(root, note_id, registry):
            nonlocal changed
            if not changed:
                changed = True
                save_note(
                    root, note_id, note['body'], expected=note['revision'], entities=[CONCEPT]
                )
            return original(root, note_id, registry)

        with patch('knot.notes._history', side_effect=interleaved):
            store = load_store(self.root / 'graph')
        self.assertEqual(self.entities(store, note['note']), {SEED})
        self.assertEqual(
            one(store, note['note'], VOCAB + 'currentRevision', CURRENT).value, note['revision']
        )
        self.assertEqual(self.entities(load_store(self.root / 'graph'), note['note']), {CONCEPT})

    def test_concurrent_association_edits_preserve_expected_head_protection(self):
        note = create_note(self.root, 'A source.', entities=[SEED])
        barrier = Barrier(2)

        def update(entities):
            barrier.wait(timeout=5)
            try:
                return save_note(
                    self.root,
                    note['note'],
                    note['body'],
                    expected=note['revision'],
                    entities=entities,
                )
            except ValueError as error:
                return str(error)

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(update, [[CONCEPT], []]))
        self.assertEqual(sum(isinstance(r, dict) for r in results), 1)
        self.assertTrue(any(isinstance(r, str) and 'head changed' in r for r in results))
        history = note_history(self.root, note['note'])
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0]['entities'], [SEED])
        self.assertEqual(
            self.entities(load_store(self.root / 'graph'), note['note']),
            set(history[-1]['entities']),
        )

    def test_v1_manifests_remain_immutable_and_upgrade_only_after_a_real_change(self):
        body = b'Legacy source.\r\n'
        sha = digest(body)
        note_id = 'urn:knot:note:12345678-1234-4234-8234-123456789abc'
        manifest = {
            'schema_version': 1,
            'note': note_id,
            'parent': None,
            'body_sha256': sha,
            'body_path': f'sources/revisions/{sha}/note.txt',
            'format': 'markdown',
            'created_at': '2026-11-04T12:00:00.000000Z',
            'modified_at': '2026-11-04T12:00:00.000000Z',
            'title': None,
            'author': None,
            'agent': None,
            'reason': None,
        }
        raw = (
            json.dumps(manifest, sort_keys=True, ensure_ascii=False, separators=(',', ':')) + '\n'
        ).encode()
        key = digest(raw)
        revision = 'urn:knot:note-revision:' + key
        snapshot = self.root / manifest['body_path']
        snapshot.parent.mkdir(parents=True)
        snapshot.write_bytes(body)
        path = self.root / 'notes/revisions' / (key + '.json')
        path.parent.mkdir(parents=True)
        path.write_bytes(raw)
        (self.root / 'notes/registry.json').write_text(
            json.dumps({'schema_version': 1, 'notes': {note_id: revision}})
        )
        legacy = read_note(self.root, note_id)
        self.assertEqual(legacy['entities'], [])
        self.assertIsNone(legacy['kind'])
        self.assertEqual(
            save_note(self.root, note_id, body, expected=revision)['revision'], revision
        )
        updated = save_note(
            self.root, note_id, body, expected=revision, entities=[SEED], kind='Observation'
        )
        self.assertEqual(updated['schema_version'], 2)
        self.assertEqual(updated['parent'], revision)
        self.assertEqual(path.read_bytes(), raw)
        self.assertEqual(snapshot.read_bytes(), body)
        self.assertEqual(len(note_history(self.root, note_id)), 2)
        self.assertEqual(self.entities(load_store(self.root / 'graph'), note_id), {SEED})

    def test_factual_retrieval_scopes_and_review_history_remain_unchanged(self):
        policy = Policy(max_chars=30000)
        question = 'What Orion dependencies remain unresolved?'
        before = {}
        base = load_store(self.root / 'graph')
        pins = {}
        for aid in (CLAIM, ROUTE):
            for evidence in values(base, aid, DERIVED):
                revision = one(base, evidence.value, VOCAB + 'revision').value
                pins[revision] = one(base, revision, VOCAB + 'sha256').value
        restricted = AccessScope(revisions=tuple(sorted(pins.items())))
        for scope in (None, AccessScope.all(), restricted):
            for mode in ('graph', 'text', 'hybrid'):
                before[scope, mode] = serialise(
                    retrieve(self.root, SEED, policy, question=question, mode=mode, scope=scope)
                )
        aliases = lookup(self.root, 'Orion')
        store = load_store(self.root / 'graph')
        signature = fingerprint(store, CLAIM)
        note = create_note(
            self.root,
            'Secret Orion dependencies. No factual assertion.',
            entities=[SEED],
            kind='Thought',
        )
        self.assertEqual(fingerprint(load_store(self.root / 'graph'), CLAIM), signature)
        for scope, mode in before:
            after = retrieve(self.root, SEED, policy, question=question, mode=mode, scope=scope)
            if scope == restricted or mode == 'graph':
                self.assertEqual(before[scope, mode], serialise(after))
            else:
                self.assertTrue(any('native_note' in s for s in after['sources'].values()))
        self.assertEqual(lookup(self.root, 'Orion'), aliases)
        self.assertFalse(lookup(self.root, 'Secret', scope=AccessScope())['candidates'])
        # A note outside a source-pinned grant cannot affect its retrieval/review.
        (self.root / note['body_path']).write_text('Corrupt note')
        self.assertEqual(
            before[restricted, 'hybrid'],
            serialise(
                retrieve(
                    self.root, SEED, policy, question=question, mode='hybrid', scope=restricted
                )
            ),
        )
        decide(
            self.root,
            ROUTE,
            'reject',
            reviewer='Test',
            reason='Explicit review remains independent',
        )
        historical = load_store(self.root / 'graph', history=True, include_notes=False)
        self.assertEqual(one(historical, ROUTE, VOCAB + 'reviewStatus').value, VOCAB + 'Rejected')
        self.assertFalse(
            list(
                load_store(self.root / 'graph', include_notes=False).quads_for_pattern(
                    None, None, None, NamedNode(ROUTE)
                )
            )
        )
        (self.root / note['body_path']).write_bytes(note['body'].encode())
        projected = load_store(self.root / 'graph')
        self.assertEqual(self.entities(projected, note['note']), {SEED})
        self.assertFalse(list(projected.quads_for_pattern(None, None, None, NamedNode(ROUTE))))
