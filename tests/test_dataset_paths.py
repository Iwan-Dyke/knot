"""Managed dataset paths cannot redirect operations into another directory."""

import io
import os
import shutil
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from html import escape
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile

from pyoxigraph import Store
from retrieval_fixture import ROUTE, make_fixture

from knot.curating.entity_labels import apply_entity_labels
from knot.curating.evidence_accounts import annotate_accounts
from knot.graph.knowledge import rebuild
from knot.graph.query import load_store
from knot.ingestion.inventory import build_inventory, verify_sources
from knot.interfaces.access import AccessScope
from knot.presentation.library import main as library_main
from knot.presentation.library_snapshot import input_signature
from knot.presentation.visualise import main as legacy_main
from knot.retrieval_engine.context import lookup
from knot.retrieval_engine.evidence import _Evidence
from knot.reviewing.state import read_events
from knot.reviewing.writer import decide
from knot.shared.storage import atomic_json, digest
from knot.writing.authoring import choose_draft, new_draft, publish_draft, run_workflow
from knot.writing.datasets import clone, initialise, select
from knot.writing.notes import create_note
from knot.writing.sync import refresh
from knot.writing.themes import add_themes


class DatasetPathTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.root = self.base / 'dataset'
        self.outside = self.base / 'outside'
        self.outside.mkdir()
        settings = patch.dict(
            os.environ,
            {'KNOT_CONFIG': str(self.base / 'config.json'), 'KNOT_DATA_ROOT': str(self.root)},
        )
        settings.start()
        self.addCleanup(settings.stop)

    def redirect(self, relative):
        path = self.root / relative
        target = self.outside / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        path.rename(target)
        path.symlink_to(target, target_is_directory=target.is_dir())
        return target

    def test_graph_directory_and_individual_file_cannot_disclose_external_labels(self):
        for relative in ('graph', 'graph/claims.trig'):
            with self.subTest(relative=relative):
                make_fixture(self.root)
                self.redirect(relative)
                with self.assertRaisesRegex(ValueError, 'Unsafe'):
                    lookup(self.root, 'Orion', scope=AccessScope.all())
                shutil.rmtree(self.root)
                shutil.rmtree(self.outside)
                self.outside.mkdir()

    def test_chosen_root_may_be_an_alias_but_internal_aliases_are_rejected(self):
        initialise(self.root)
        alias = self.base / 'chosen-root'
        alias.symlink_to(self.root, target_is_directory=True)
        self.assertEqual(initialise(alias), self.root)
        self.assertTrue(load_store(alias / 'graph'))
        (self.root / 'graph/alias.trig').symlink_to(self.root / 'graph/ontology.trig')
        with self.assertRaisesRegex(ValueError, 'Unsafe'):
            load_store(alias / 'graph')

    def test_existing_dataset_admission_rejects_nested_and_dangling_symlinks(self):
        initialise(self.root)
        nested = self.root / 'sources/revisions'
        nested.mkdir(parents=True)
        link = nested / 'unexpected.txt'
        link.symlink_to(self.outside / 'missing.txt')
        for operation in (initialise, select):
            with self.subTest(operation=operation.__name__):
                with self.assertRaisesRegex(ValueError, 'Unsafe'):
                    operation(self.root)

    def test_clone_rejects_a_committed_external_graph_symlink(self):
        self.root.mkdir()
        (self.root / 'knot.json').write_text('{"schema_version":1}')
        (self.root / 'graph').symlink_to(self.outside, target_is_directory=True)
        for args in (
            ['init', '--quiet', str(self.root)],
            ['-C', str(self.root), 'add', '.'],
            [
                '-C',
                str(self.root),
                '-c',
                'user.name=Test',
                '-c',
                'user.email=test@example.invalid',
                'commit',
                '--quiet',
                '-m',
                'Synthetic symlink fixture',
            ],
        ):
            subprocess.run(['git', *args], check=True, capture_output=True)
        destination = self.base / 'clone'
        with self.assertRaisesRegex(ValueError, 'Unsafe'):
            clone(str(self.root), destination)
        self.assertFalse(destination.exists())
        self.assertEqual(list(self.outside.iterdir()), [])

    def test_refresh_validates_links_introduced_by_incoming_commit(self):
        initialise(self.root)

        def git(*args, **kwargs):
            if args[0] == 'pull':
                self.redirect('graph')
            return ''

        with patch(
            'knot.writing.sync._repository',
            return_value=(git, 'origin', 'refs/heads/main', '', True),
        ):
            with self.assertRaisesRegex(ValueError, 'Unsafe'):
                refresh(self.root)
        with self.assertRaisesRegex(ValueError, 'Unsafe'):
            load_store(self.root / 'graph')

    def test_rebuild_checks_output_and_catalogue_links_before_writing(self):
        for relative in (
            'graph',
            'organisation',
            'organisation/catalogue.json',
            'organisation/generated.json',
        ):
            with self.subTest(relative=relative):
                initialise(self.root)
                self.redirect(relative)
                before = {
                    p.relative_to(self.outside): p.read_bytes()
                    for p in self.outside.rglob('*')
                    if p.is_file()
                }
                with self.assertRaisesRegex(ValueError, 'Unsafe'):
                    rebuild(self.root)
                self.assertEqual(
                    before,
                    {
                        p.relative_to(self.outside): p.read_bytes()
                        for p in self.outside.rglob('*')
                        if p.is_file()
                    },
                )
                shutil.rmtree(self.root)
                shutil.rmtree(self.outside)
                self.outside.mkdir()

    def test_theme_write_cannot_follow_an_organisation_directory_link(self):
        initialise(self.root)
        self.redirect('organisation')
        catalogue = self.outside / 'organisation/catalogue.json'
        before = catalogue.read_bytes()
        with self.assertRaisesRegex(ValueError, 'Unsafe'):
            add_themes(self.root, [{'id': 'sample', 'label': 'Sample', 'keywords': []}])
        self.assertEqual(catalogue.read_bytes(), before)

    def test_review_reads_and_writes_reject_linked_event_directory(self):
        make_fixture(self.root)
        (self.root / 'reviews/events').mkdir(parents=True)
        self.redirect('reviews')
        with self.assertRaisesRegex(ValueError, 'Unsafe'):
            read_events(self.root)
        with self.assertRaisesRegex(ValueError, 'Unsafe'):
            decide(self.root, ROUTE, 'accept', reviewer='Test', reason='Synthetic review')
        self.assertEqual(list((self.outside / 'reviews/events').iterdir()), [])
        self.assertFalse((self.outside / 'reviews/.lock').exists())

    def test_review_reader_rejects_linked_event_file_before_parsing(self):
        (self.root / 'reviews/events').mkdir(parents=True)
        external = self.outside / 'event.trig'
        external.write_text('Not RDF')
        (self.root / 'reviews/events/event.trig').symlink_to(external)
        with self.assertRaisesRegex(ValueError, 'Unsafe'):
            read_events(self.root)

    def test_inventory_cannot_write_through_a_linked_snapshot_directory(self):
        (self.root / 'sources').mkdir(parents=True)
        with ZipFile(self.root / 'sources/sample.zip', 'w') as archive:
            archive.writestr('sample.md', 'Synthetic note')
        (self.root / 'sources/revisions').symlink_to(self.outside, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'Unsafe'):
            build_inventory(self.root)
        self.assertEqual(list(self.outside.iterdir()), [])

    def test_inventory_metadata_cannot_read_outside_root(self):
        self.root.mkdir()
        external = self.outside / 'sample.md'
        external.write_bytes(b'Synthetic note')
        for relative in ('../outside/sample.md', str(external)):
            inventory = {
                'archives': [],
                'entries': [
                    {
                        'status': 'verified',
                        'member': 'sample.md',
                        'snapshot': relative,
                        'sha256': digest(external.read_bytes()),
                    }
                ],
            }
            with self.subTest(relative=relative):
                with self.assertRaisesRegex(ValueError, 'Unsafe'):
                    verify_sources(self.root, inventory)

    def test_auxiliary_readers_reject_linked_files_before_parsing(self):
        cases = (
            ('migration/conversion.json', lambda: _Evidence(self.root, Store())),
            (
                'curation/entity-labels.json',
                lambda: apply_entity_labels(self.root, Store(), [], {}),
            ),
            ('curation/evidence-accounts.json', lambda: annotate_accounts(self.root, Store(), [])),
            ('sources/linked.txt', lambda: input_signature(self.root)),
        )
        for relative, operation in cases:
            with self.subTest(relative=relative):
                path = self.root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                external = self.outside / 'unreadable.json'
                external.write_text('Not JSON; must not be read')
                path.symlink_to(external)
                with self.assertRaisesRegex(ValueError, 'Unsafe'):
                    operation()
                path.unlink()

    def test_default_viewer_outputs_are_guarded_and_explicit_outputs_still_work(self):
        initialise(self.root)
        create_note(self.root, 'Synthetic viewer note.')
        (self.root / 'views').symlink_to(self.outside, target_is_directory=True)
        for main in (library_main, legacy_main):
            with self.subTest(main=main.__module__):
                errors = io.StringIO()
                with redirect_stderr(errors), self.assertRaises(SystemExit) as raised:
                    main(['--data-root', str(self.root), '--no-open'])
                self.assertEqual(raised.exception.code, 2)
                self.assertIn('Unsafe', errors.getvalue())
                self.assertEqual(list(self.outside.iterdir()), [])
                output = self.outside / 'chosen.html'
                with (
                    patch(
                        'knot.presentation.library_snapshot.render_markup',
                        side_effect=lambda body, format: '<pre>' + escape(body) + '</pre>',
                    ),
                    redirect_stdout(io.StringIO()),
                ):
                    main(['--data-root', str(self.root), '--no-open', '--output', str(output)])
                self.assertTrue(output.is_file())
                output.unlink()

    def test_draft_navigation_and_capture_reject_a_linked_directory(self):
        initialise(self.root)
        (self.root / 'drafts').symlink_to(self.outside, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'Unsafe'):
            choose_draft(self.root)
        with patch('knot.interfaces.note_cli._wizard', return_value='Synthetic capture'):
            with self.assertRaisesRegex(ValueError, 'Unsafe'):
                run_workflow(self.root, {})
        self.assertEqual(list(self.outside.iterdir()), [])

    def test_managed_and_external_drafts_reject_linked_sidecar_locks(self):
        initialise(self.root)
        for directory in (self.root / 'drafts', self.outside / 'drafts'):
            for existing in (False, True):
                with self.subTest(directory=directory.name, existing=existing):
                    draft = new_draft(
                        'Synthetic draft.',
                        {'navigation': {'themes': [], 'links': [], 'declarations': []}},
                        root=self.root,
                    )
                    path = directory / (str(existing) + '.json')
                    atomic_json(path, draft)
                    target = self.outside / (directory.parent.name + str(existing) + '.lock')
                    if existing:
                        target.write_bytes(b'Unchanged external file')
                    path.with_suffix('.lock').symlink_to(target)
                    with self.assertRaisesRegex(ValueError, 'Unsafe'):
                        publish_draft(self.root, path)
                    self.assertEqual(target.exists(), existing)
                    if existing:
                        self.assertEqual(target.read_bytes(), b'Unchanged external file')
                    self.assertFalse((self.root / 'notes/registry.json').exists())

    def test_managed_draft_json_cannot_redirect_but_explicit_external_drafts_work(self):
        initialise(self.root)
        draft = new_draft(
            'Synthetic draft.',
            {'navigation': {'themes': [], 'links': [], 'declarations': []}},
            root=self.root,
        )
        external = self.outside / 'chosen.json'
        atomic_json(external, draft)
        linked = self.root / 'drafts/linked.json'
        linked.parent.mkdir()
        linked.symlink_to(external)
        for operation in (
            lambda: publish_draft(self.root, linked),
            lambda: run_workflow(self.root, {}, draft_path=linked),
        ):
            with self.subTest(operation=operation):
                with self.assertRaisesRegex(ValueError, 'Unsafe'):
                    operation()
        self.assertFalse(external.with_suffix('.lock').exists())
        self.assertEqual(publish_draft(self.root, external)['note'], draft['note'])


if __name__ == '__main__':
    unittest.main()
