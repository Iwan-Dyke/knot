import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import test_quality

from knot.notes import create_note, save_note
from knot.quality import audit, compare_reports, main
from knot.review import decide


class QualityDiagnosticsTests(unittest.TestCase):
    setUp = test_quality.QualityTests.setUp
    claim = test_quality.QualityTests.claim
    write_graph = test_quality.QualityTests.write_graph
    files = test_quality.QualityTests.files
    curate = test_quality.QualityTests.curate

    def test_stable_ids_and_groups_do_not_change_authoritative_data(self):
        self.claim(subject_type='Project', subject_label='Meeting')
        before = self.files()
        report = audit(self.root)
        self.assertEqual(report['schema_version'], 1)
        self.assertEqual(report, audit(self.root))
        self.assertEqual(self.files(), before)
        warnings = {item['code']: item for item in report['warnings']}
        semantic = warnings['decision_subject_needs_review']
        self.assertEqual(semantic['category'], 'relationship_semantics')
        self.assertEqual(semantic['priority'], 'review')
        self.assertEqual(warnings['low_quality_entity_name']['priority'], 'informational')
        self.assertGreater(report['counts']['findings_by_priority']['review'], 0)
        self.assertTrue(all(item['id'] for item in report['warnings']))

    def test_legacy_baseline_ids_and_prose_do_not_create_false_new_findings(self):
        self.claim(subject_type='Project')
        report = audit(self.root)
        legacy = json.loads(json.dumps(report))
        legacy.pop('schema_version')
        for finding in legacy['warnings']:
            for field in ('id', 'category', 'priority'):
                finding.pop(field)
            finding['detail'] = 'Older explanation of the same finding.'
        comparison = compare_reports(report, legacy)
        self.assertEqual(comparison['counts']['new'], {'errors': 0, 'warnings': 0})
        self.assertEqual(comparison['counts']['resolved'], {'errors': 0, 'warnings': 0})
        self.assertEqual(comparison['counts']['persisting']['warnings'], len(report['warnings']))

    def test_delta_reports_new_and_resolved_without_suppressing_existing_errors(self):
        self.claim(quote='Invalid quotation', subject_type='Project')
        baseline = audit(self.root)
        self.claim(quote='Invalid quotation', subject_type='Person', subject_label='Meeting')
        current = audit(self.root)
        delta = compare_reports(current, baseline)
        self.assertGreater(delta['counts']['new']['warnings'], 0)
        self.assertGreater(delta['counts']['resolved']['warnings'], 0)
        self.assertGreater(delta['counts']['persisting']['errors'], 0)
        self.assertTrue(current['errors'])

    def test_invalid_or_unsupported_baseline_fails_explicitly(self):
        report = audit(self.root)
        for baseline in (
            {},
            {'errors': [], 'warnings': 'invalid'},
            {**report, 'schema_version': 99},
        ):
            with self.subTest(baseline=baseline), self.assertRaises(ValueError):
                compare_reports(report, baseline)

    def test_relationship_structure_rejects_unknown_vocabulary_but_type_mismatch_warns(self):
        self.claim(predicate='inventedRelationship')
        before = self.files()
        self.assertIn(
            'invalid_relationship_structure', {w['code'] for w in audit(self.root)['errors']}
        )
        self.assertEqual(self.files(), before)
        self.claim(object_type='Tool')
        result = audit(self.root)
        self.assertFalse(result['errors'])
        self.assertIn(
            'relationship_object_type_needs_review', {w['code'] for w in result['warnings']}
        )

    def test_separate_metadata_errors_on_same_record_have_distinct_ids(self):
        self.claim()
        path = self.root / 'graph/claims.trig'
        path.write_text(
            '\n'.join(
                line
                for line in path.read_text().splitlines()
                if 'subjectLabel' not in line and 'objectLabel' not in line
            )
        )
        errors = [
            w for w in audit(self.root)['errors'] if w['code'] == 'invalid_assertion_metadata'
        ]
        self.assertEqual(len(errors), 2)
        self.assertEqual(len({w['id'] for w in errors}), 2)

    def test_current_note_coverage_respects_logical_note_and_body(self):
        source = create_note(self.root, 'I may try a different approach.')
        create_note(self.root, source['body'])
        self.curate(source)
        counts = audit(self.root)['counts']
        self.assertEqual(counts['current_source_notes'], 2)
        self.assertEqual(counts['current_curated_notes'], 1)
        self.assertEqual(counts['current_valid_curated_notes'], 1)
        self.assertEqual(counts['current_source_notes_with_curation'], 1)
        metadata = save_note(
            self.root, source['note'], source['body'], expected=source['revision'], title='Thought'
        )
        self.assertEqual(audit(self.root)['counts']['current_source_notes_with_curation'], 1)
        save_note(self.root, source['note'], 'I changed my mind.', expected=metadata['revision'])
        self.assertEqual(audit(self.root)['counts']['current_source_notes_with_curation'], 0)

    def test_corrections_are_event_counts_not_a_quality_failure_score(self):
        self.claim()
        decide(
            self.root,
            'urn:claim',
            'correct',
            reviewer='Owner',
            reason='Clarify meaning.',
            replacement={
                'subject': 'urn:b',
                'predicate': 'urn:knot:vocab:decisionAbout',
                'object': 'urn:a',
                'subject_label': 'B',
                'object_label': 'A',
                'rationale': 'Recorded decision concerns A.',
            },
        )
        counts = audit(self.root)['counts']
        self.assertEqual(counts['correction_events'], 1)
        self.assertEqual(counts['active_correction_replacements'], 1)

    def test_cli_output_cannot_overwrite_dataset_even_through_symlink(self):
        self.claim()
        before = self.files()
        with tempfile.TemporaryDirectory() as directory:
            alias = Path(directory) / 'alias'
            alias.symlink_to(self.root, target_is_directory=True)
            for output in (self.root / 'graph/claims.trig', alias / 'report.json'):
                with (
                    self.subTest(output=output),
                    contextlib.redirect_stderr(io.StringIO()),
                    patch(
                        'sys.argv',
                        ['quality', '--data-root', str(self.root), '--output', str(output)],
                    ),
                ):
                    with self.assertRaises(SystemExit) as failure:
                        main()
                    self.assertEqual(failure.exception.code, 2)
        self.assertEqual(self.files(), before)

    def test_cli_baseline_is_read_only_and_errors_still_set_exit_status(self):
        self.claim(quote='Invalid quotation')
        report = audit(self.root)
        with tempfile.TemporaryDirectory() as directory:
            baseline = Path(directory) / 'baseline.json'
            baseline.write_text(json.dumps(report))
            output = Path(directory) / 'current.json'
            with patch(
                'sys.argv',
                [
                    'quality',
                    '--data-root',
                    str(self.root),
                    '--baseline',
                    str(baseline),
                    '--output',
                    str(output),
                ],
            ):
                self.assertEqual(main(), 1)
            current = json.loads(output.read_text())
            self.assertEqual(current['comparison']['counts']['new']['errors'], 0)
            self.assertGreater(current['comparison']['counts']['persisting']['errors'], 0)
            self.assertEqual(json.loads(baseline.read_text()), report)


if __name__ == '__main__':
    unittest.main()
