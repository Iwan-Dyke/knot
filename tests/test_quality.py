import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from knot.inventory import digest
from knot.notes import create_note, save_note
from knot.provenance import source_pin
from knot.quality import audit, main
from knot.rdf import ATTRIBUTED, DERIVED, LABEL, RDF_TYPE, VOCAB, Dataset
from knot.review import decide


class QualityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def files(self):
        return {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()}

    def claim(
        self,
        *,
        native=None,
        register=True,
        quote='A chose B.',
        subject_label='A',
        object_label='B',
        literal=None,
        predicate=None,
        subject_type='Person',
        object_type='Decision',
    ):
        data = Dataset()
        if native:
            revision, path, sha = (native['revision'], native['body_path'], native['body_sha256'])
        else:
            self.root.joinpath('sources').mkdir(exist_ok=True)
            self.root.joinpath('sources/account.md').write_text('A chose B.\n')
            sha = digest(b'A chose B.\n')
            revision, path = 'urn:revision:' + sha, 'sources/account.md'
        data.add(
            'urn:a',
            VOCAB + (predicate or ('madeDecision' if literal is None else 'eventCount')),
            'urn:b' if literal is None else literal,
            literal=literal is not None,
            graph='urn:claim',
        )
        data.add('urn:claim', RDF_TYPE, VOCAB + 'Assertion')
        for key, value in (
            ('reviewStatus', 'Unreviewed'),
            ('origin', 'Explicit'),
            ('lifecycle', 'Active'),
        ):
            data.add('urn:claim', VOCAB + key, VOCAB + value)
        for key, value in (
            ('subjectLabel', subject_label),
            ('objectLabel', object_label),
            ('rationale', 'Reported choice.'),
            ('generatedAt', '2026-11-05T12:00:00Z'),
        ):
            data.add('urn:claim', VOCAB + key, value, literal=True)
        data.add('urn:claim', ATTRIBUTED, 'urn:agent:test')
        data.add('urn:claim', DERIVED, 'urn:evidence')
        data.add('urn:evidence', VOCAB + 'revision', revision)
        data.add('urn:evidence', VOCAB + 'quote', quote, literal=True)
        data.add('urn:evidence', VOCAB + 'characterOffset', 0, literal=True)
        data.add('urn:evidence', VOCAB + 'startLine', 1, literal=True)
        data.add('urn:evidence', VOCAB + 'locatorKind', 'source_line', literal=True)
        if register:
            data.add(revision, VOCAB + 'snapshotPath', path, literal=True)
            data.add(revision, VOCAB + 'sha256', sha, literal=True)
        data.add('urn:a', RDF_TYPE, VOCAB + subject_type)
        data.add('urn:a', LABEL, subject_label, literal=True)
        if literal is None:
            data.add('urn:b', RDF_TYPE, VOCAB + object_type)
            data.add('urn:b', LABEL, object_label, literal=True)
        self.write_graph(data)
        return revision

    def write_graph(self, data, name='claims.trig'):
        self.root.joinpath('graph').mkdir(exist_ok=True)
        self.root.joinpath('graph', name).write_text(data.text())

    def codes(self, result, severity='errors'):
        return {finding['code'] for finding in result[severity]}

    def test_audit_keeps_independent_errors_and_later_warnings(self):
        self.claim(quote='Wrong quotation', subject_type='Project', subject_label='Meeting')
        self.root.joinpath('graph/broken.trig').write_text('not valid RDF {')
        create_note(self.root, 'A separate observation.', author='Codex')
        before = self.files()
        report = audit(self.root)
        self.assertLessEqual({'invalid_graph', 'invalid_citation'}, self.codes(report))
        self.assertLessEqual(
            {'missing_derivation', 'decision_subject_needs_review', 'generic_entity_name'},
            self.codes(report, 'warnings'),
        )
        self.assertEqual(report['counts']['native_notes'], 1)
        self.assertEqual(report['counts']['assertions'], 1)
        self.assertEqual(self.files(), before)

    def test_audit_preserves_accepted_reviews_and_all_files(self):
        self.claim()
        decide(self.root, 'urn:claim', 'accept', reviewer='Owner', reason='Checked original.')
        before = self.files()
        result = audit(self.root)
        self.assertEqual(result['errors'], [])
        self.assertEqual(result['counts']['assertions'], 1)
        self.assertEqual(result['counts']['statuses'], {'Accepted': 1})
        self.assertEqual(self.files(), before)

    def test_same_label_distinct_entities_are_warned_never_merged(self):
        self.claim()
        data = Dataset()
        for entity, label in [('urn:other:1', 'Shared name'), ('urn:other:2', 'Shared-name')]:
            data.add(entity, LABEL, label, literal=True)
        self.write_graph(data, 'other.trig')
        before = self.files()
        result = audit(self.root)
        self.assertEqual(result['errors'], [])
        collision = next(w for w in result['warnings'] if w['code'] == 'label_collision')
        self.assertEqual(collision['entities'], ['urn:other:1', 'urn:other:2'])
        self.assertEqual(self.files(), before)

    def test_free_writing_and_missing_curated_provenance_are_warnings_only(self):
        create_note(self.root, 'can you add this idea; maybe it is wrong?', kind='Thought')
        create_note(self.root, 'A compiled interpretation.', title='Summary', author='Codex')
        before = self.files()
        result = audit(self.root)
        self.assertEqual(result['errors'], [])
        self.assertIn('conversational_note', self.codes(result, 'warnings'))
        self.assertIn('missing_derivation', self.codes(result, 'warnings'))
        self.assertEqual(self.files(), before)

    def test_broken_hash_quote_and_missing_source_are_errors(self):
        self.claim(quote='A chose C.')
        self.assertIn('invalid_citation', self.codes(audit(self.root)))
        self.claim()
        self.root.joinpath('sources/account.md').write_text('Changed bytes.')
        self.assertIn('invalid_citation', self.codes(audit(self.root)))
        self.claim(register=False)
        self.assertIn('invalid_citation', self.codes(audit(self.root)))

    def test_historical_native_registration_gap_is_visible_before_adapter(self):
        first = create_note(self.root, 'A chose B.')
        save_note(self.root, first['note'], 'A chose C.', expected=first['revision'])
        self.claim(native=first, register=False)
        result = audit(self.root)
        self.assertIn('missing_native_registration', self.codes(result))
        self.assertNotIn('invalid_citation', self.codes(result))
        self.assertEqual(result['counts']['verified_citations'], 1)
        self.assertEqual(result['counts']['native_revisions'], 2)

    def test_corrupt_native_ancestry_and_derivation_are_errors(self):
        original = create_note(self.root, 'Original account.')
        pin = source_pin(self.root, original['revision'], original['body'], 0)
        create_note(
            self.root,
            'Faithful account.',
            title='Curated account',
            author='Codex',
            agent='Codex',
            derivation={
                'method': 'faithful_restatement',
                'qualification': 'Reported.',
                'sources': [pin],
            },
        )
        self.root.joinpath(original['body_path']).write_text('Corrupt.')
        result = audit(self.root)
        self.assertIn('invalid_note_history', self.codes(result))
        self.assertIn('invalid_derivation', self.codes(result))

    def test_profiles_and_unknown_associations_are_checked(self):
        self.claim()
        note = create_note(self.root, 'A chose B.', entities=['urn:a'])
        self.root.joinpath('graph/claims.trig').unlink()
        result = audit(self.root)
        self.assertIn('invalid_note_association', self.codes(result))
        self.claim()
        path = self.root / 'curation/entity-labels.json'
        path.parent.mkdir()
        path.write_text(
            json.dumps(
                {
                    'schema_version': 1,
                    'profiles': [
                        {
                            'entity': 'urn:a',
                            'preferred_label': 'A clearer name',
                            'aliases': [],
                            'agent': 'Codex',
                            'reason': 'Source-backed',
                            'sources': [
                                {
                                    **source_pin(self.root, note['revision'], note['body'], 0),
                                    'quote': 'Unfaithful paraphrase',
                                }
                            ],
                        }
                    ],
                }
            )
        )
        self.assertIn('invalid_entity_labels', self.codes(audit(self.root)))

    def test_cli_exit_status_uses_errors_not_warnings(self):
        create_note(self.root, 'can you add a reminder?')
        with patch('sys.argv', ['quality', '--data-root', str(self.root)]):
            with contextlib.redirect_stdout(io.StringIO()) as stdout:
                self.assertEqual(main(), 0)
        self.assertTrue(json.loads(stdout.getvalue())['warnings'])
        self.claim(quote='Wrong quote')
        with patch('sys.argv', ['quality', '--data-root', str(self.root)]):
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(), 1)

    def test_invalid_metadata_domain_shape_and_review_fingerprint_are_errors(self):
        self.claim()
        data = Dataset()
        data.add('urn:a', VOCAB + 'relatedTo', 'urn:c', graph='urn:claim')
        data.add('urn:claim', VOCAB + 'origin', VOCAB + 'Certain')
        self.write_graph(data, 'bad.trig')
        result = audit(self.root)
        self.assertIn('invalid_assertion_metadata', self.codes(result))
        self.assertIn('invalid_domain_triple', self.codes(result))
        self.root.joinpath('graph/bad.trig').unlink()
        decide(self.root, 'urn:claim', 'accept', reviewer='Owner', reason='Checked.')
        path = self.root / 'graph/claims.trig'
        path.write_text(path.read_text().replace('Reported choice.', 'Changed rationale.'))
        self.assertIn('invalid_reviews', self.codes(audit(self.root)))

    def test_duplicate_binding_and_shared_body_warnings_preserve_distinct_notes(self):
        self.claim()
        data = Dataset()
        for mapping in ('urn:mapping:one', 'urn:mapping:two'):
            data.add(mapping, VOCAB + 'sourceEntity', 'urn:source:person')
            data.add(mapping, VOCAB + 'entity', 'urn:a')
            data.add(mapping, VOCAB + 'reviewStatus', VOCAB + 'Accepted')
        self.write_graph(data, 'mappings.trig')
        first = create_note(self.root, 'Identical writing.')
        second = create_note(self.root, 'Identical writing.')
        result = audit(self.root)
        self.assertEqual(result['errors'], [])
        self.assertIn('duplicate_identity_bindings', self.codes(result, 'warnings'))
        self.assertIn('shared_source_bytes', self.codes(result, 'warnings'))
        self.assertNotEqual(first['note'], second['note'])
        self.assertEqual(result['counts']['native_notes'], 2)

    def test_curated_associations_warn_when_known_identity_has_no_source_trace(self):
        revision = self.claim()
        original = create_note(self.root, 'Original account.', entities=['urn:a'])

        def curated(pin, entities):
            return create_note(
                self.root,
                'Faithful account.',
                title='Curated account',
                author='Codex',
                agent='Codex',
                entities=entities,
                derivation={
                    'method': 'faithful_restatement',
                    'qualification': 'Source account, not independent confirmation.',
                    'sources': [pin],
                },
            )

        native_pin = source_pin(self.root, original['revision'], original['body'], 0)
        unsupported = curated(native_pin, ['urn:a', 'urn:b'])
        # Navigation through a source association and through an assertion are both traces.
        curated(source_pin(self.root, revision, 'chose', 2), ['urn:a', 'urn:b'])
        curated(native_pin, [])
        before = self.files()
        result = audit(self.root)
        self.assertEqual(result['errors'], [])
        warnings = [w for w in result['warnings'] if w['code'] == 'unsupported_curated_association']
        self.assertEqual(len(warnings), 1)
        self.assertEqual(warnings[0]['record'], unsupported['revision'])
        self.assertEqual(warnings[0]['entity'], 'urn:b')
        self.assertEqual(self.files(), before)

    def test_resource_counts_distinguish_labels_from_domain_endpoints(self):
        self.claim()
        data = Dataset()
        data.add('urn:source:document', LABEL, 'A source document', literal=True)
        data.add('urn:source:document', RDF_TYPE, VOCAB + 'Document')
        self.write_graph(data, 'documents.trig')
        counts = audit(self.root)['counts']
        self.assertEqual(counts['labelled_resources'], 3)
        self.assertEqual(counts['domain_endpoints'], 2)
        self.assertNotIn('entities', counts)

    def test_numeric_referents_and_numeric_literals_have_separate_warning_semantics(self):
        self.claim(subject_label='1984', object_label='18', literal=18)
        # A numeric title may be legitimate. It needs review, never rejection.
        before = self.files()
        result = audit(self.root)
        self.assertEqual(result['errors'], [])
        numeric = [w for w in result['warnings'] if w['code'] == 'numeric_entity_name']
        self.assertEqual([w['record'] for w in numeric], ['urn:a'])
        self.assertEqual(result['counts']['literal_occurrences'], 1)
        self.assertEqual(result['counts']['numeric_literal_occurrences'], 1)
        self.assertEqual(result['counts']['current_numeric_name_nodes'], 1)
        self.assertTrue(all(not w['record'].startswith('literal:') for w in numeric))
        self.assertEqual(self.files(), before)

    def test_literal_under_entity_relationship_is_a_warning_not_a_numeric_name_error(self):
        self.claim(object_label='18', literal=18)
        path = self.root / 'graph/claims.trig'
        path.write_text(path.read_text().replace(VOCAB + 'eventCount', VOCAB + 'hasCompetency'))
        result = audit(self.root)
        self.assertEqual(result['errors'], [])
        self.assertNotIn('numeric_entity_name', self.codes(result, 'warnings'))
        warning = next(w for w in result['warnings'] if w['code'] == 'literal_entity_relation')
        self.assertEqual(warning['record'], 'urn:claim')
        self.assertEqual(warning['value'], '18')

    def test_preferred_names_clear_current_warnings_without_erasing_historical_aliases(self):
        revision = self.claim(subject_label='Meeting', object_label='Meeting')
        before = audit(self.root)
        self.assertEqual(before['counts']['current_generic_name_nodes'], 2)
        self.assertEqual(before['counts']['current_name_duplicate_groups'], 1)
        path = self.root / 'curation/entity-labels.json'
        path.parent.mkdir()
        path.write_text(
            json.dumps(
                {
                    'schema_version': 1,
                    'profiles': [
                        {
                            'entity': 'urn:a',
                            'preferred_label': "A's recorded choice",
                            'aliases': ['Meeting'],
                            'agent': 'Codex',
                            'reason': 'Make the subject context explicit.',
                            'sources': [source_pin(self.root, revision, 'A chose B.', 0)],
                        }
                    ],
                }
            )
        )
        saved = self.files()
        after = audit(self.root)
        generic = [w for w in after['warnings'] if w['code'] == 'generic_entity_name']
        self.assertEqual([w['record'] for w in generic], ['urn:b'])
        self.assertEqual(after['counts']['current_generic_name_nodes'], 1)
        self.assertEqual(after['counts']['current_name_duplicate_groups'], 0)
        historical = [w for w in after['warnings'] if w['code'] == 'label_collision']
        self.assertTrue(any(w['record'] == 'meeting' for w in historical))
        self.assertEqual(self.files(), saved)

    def test_context_and_granularity_candidates_warn_without_rejecting_concepts(self):
        self.claim()
        data = Dataset()
        names = {
            'urn:outcome': 'Built and reviewed by the team',
            'urn:sentence': 'The team has delivered all reports and fixed every issue.',
            'urn:compound': 'Data platform; recruitment; mentoring',
            'urn:concept': 'Data Analysis & Synthesis',
        }
        for entity, label in names.items():
            data.add(entity, LABEL, label, literal=True)
            data.add(entity, RDF_TYPE, VOCAB + 'Concept')
        self.write_graph(data, 'names.trig')
        result = audit(self.root)
        self.assertEqual(result['errors'], [])
        by_code = {}
        for warning in result['warnings']:
            by_code.setdefault(warning['code'], set()).add(warning['record'])
        self.assertIn('urn:outcome', by_code['context_dependent_entity_name'])
        self.assertIn('urn:sentence', by_code['sentence_like_entity'])
        self.assertIn('urn:compound', by_code['compound_entity_candidate'])
        self.assertNotIn('urn:concept', set().union(*by_code.values()))

    def test_accepted_identity_removes_current_duplicate_candidate_without_merging_by_name(self):
        self.claim(subject_label='Shared name', object_label='Shared name')
        self.assertEqual(audit(self.root)['counts']['current_name_duplicate_groups'], 1)
        data = Dataset()
        data.add('urn:identity', VOCAB + 'sourceEntity', 'urn:a')
        data.add('urn:identity', VOCAB + 'entity', 'urn:b')
        data.add('urn:identity', VOCAB + 'reviewStatus', VOCAB + 'Accepted')
        self.write_graph(data, 'identity.trig')
        result = audit(self.root)
        self.assertEqual(result['errors'], [])
        self.assertEqual(result['counts']['current_name_duplicate_groups'], 0)

    def test_actor_predicates_warn_for_known_nonactors_without_guessing_unknown_types(self):
        for predicate in ('madeDecision', 'selected', 'proposed'):
            with self.subTest(predicate=predicate):
                self.claim(predicate=predicate, subject_type='Tool')
                result = audit(self.root)
                self.assertEqual(result['errors'], [])
                self.assertEqual(result['counts']['active_nonactor_claims'], 1)
                self.claim(predicate=predicate, subject_type='Entity')
                self.assertEqual(audit(self.root)['counts']['active_nonactor_claims'], 0)
                self.claim(predicate=predicate, subject_type='Group')
                self.assertEqual(audit(self.root)['counts']['active_nonactor_claims'], 0)

    def test_superseded_nonactor_claim_does_not_warn_about_current_decision_attribution(self):
        self.claim(subject_type='Project')
        decide(self.root, 'urn:claim', 'accept', reviewer='Owner', reason='Earlier review.')
        self.assertEqual(audit(self.root)['counts']['active_nonactor_claims'], 1)
        decide(
            self.root,
            'urn:claim',
            'correct',
            reviewer='Codex',
            reason='The project is the subject of the decision, not its actor.',
            replacement={
                'subject': 'urn:b',
                'predicate': VOCAB + 'decisionAbout',
                'object': 'urn:a',
                'subject_label': 'B',
                'object_label': 'A',
                'rationale': 'Recorded decision concerning the project; actor unknown.',
            },
        )
        before = self.files()
        result = audit(self.root)
        self.assertEqual(result['errors'], [])
        self.assertEqual(result['counts']['active_nonactor_claims'], 0)
        self.assertNotIn('decision_subject_needs_review', self.codes(result, 'warnings'))
        self.assertEqual(self.files(), before)

    def test_decision_about_checks_known_subject_type_without_inventing_a_decision(self):
        self.claim(predicate='decisionAbout', subject_type='Person', object_type='Project')
        result = audit(self.root)
        self.assertIn('decision_about_subject_needs_review', self.codes(result, 'warnings'))
        self.claim(predicate='decisionAbout', subject_type='Decision', object_type='Project')
        self.assertNotIn(
            'decision_about_subject_needs_review', self.codes(audit(self.root), 'warnings')
        )

    def test_proposals_warn_only_when_relationship_can_overstate_choice_or_completion(self):
        cases = [
            ('madeDecision', 'I proposed moving the apprentice.', 'Transfer proposal', True),
            ('proposed', 'I proposed moving the apprentice.', 'Transfer proposal', False),
            ('implemented', 'We planned to migrate the pipeline.', 'Pipeline migration', True),
            ('implemented', 'I proposed it, then implemented it.', 'Pipeline migration', False),
            ('produced', 'I produced an implementation plan.', 'Implementation plan', False),
            ('reportedOutcome', 'The stages are still undecided.', 'Undecided stages', True),
            (
                'reportedOutcome',
                'No Jira writes made; review remains pending.',
                'No Jira writes made',
                False,
            ),
        ]
        for predicate, body, label, expected in cases:
            with self.subTest(predicate=predicate, body=body):
                note = create_note(self.root, body)
                self.claim(native=note, quote=body, predicate=predicate, object_label=label)
                result = audit(self.root)
                self.assertEqual(result['errors'], [])
                self.assertEqual(bool(result['counts']['active_qualification_warnings']), expected)

    def test_projected_self_link_warns_without_changing_identity_or_source(self):
        self.claim(predicate='relatedTo')
        data = Dataset()
        data.add('urn:identity', VOCAB + 'sourceEntity', 'urn:a')
        data.add('urn:identity', VOCAB + 'entity', 'urn:b')
        data.add('urn:identity', VOCAB + 'reviewStatus', VOCAB + 'Accepted')
        self.write_graph(data, 'identity.trig')
        before = self.files()
        result = audit(self.root)
        self.assertEqual(result['counts']['active_projected_self_links'], 1)
        self.assertIn('self_relationship_needs_review', self.codes(result, 'warnings'))
        self.assertEqual(self.files(), before)

    def test_identical_spans_across_revisions_warn_without_confirming_same_account(self):
        quote = 'The team reported that all eighteen migration events were completed using the documented tooling and the existing onboarding guide.'
        first = create_note(self.root, quote + '\nFirst surrounding account.')
        second = create_note(self.root, quote + '\nDifferent surrounding account.')
        self.claim(native=first, quote=quote)
        path = self.root / 'graph/claims.trig'
        previous = (
            path.read_text()
            .replace('urn:claim', 'urn:first')
            .replace('urn:evidence', 'urn:first-evidence')
        )
        self.claim(native=second, quote=quote)
        self.root.joinpath('graph/first.trig').write_text(previous)
        before = self.files()
        result = audit(self.root)
        self.assertEqual(result['errors'], [])
        self.assertEqual(result['counts']['repeated_source_span_groups'], 1)
        warning = next(w for w in result['warnings'] if w['code'] == 'repeated_source_span')
        self.assertEqual(warning['assertions'], ['urn:claim', 'urn:first'])
        self.assertIn('do not establish', warning['detail'])
        self.assertEqual(self.files(), before)
        decide(self.root, 'urn:first', 'reject', reviewer='Codex', reason='Retain only in history.')
        self.assertEqual(audit(self.root)['counts']['repeated_source_span_groups'], 0)

    def test_account_catalogue_provenance_is_validated_without_changing_claims(self):
        revision = self.claim()
        catalogue = {
            'schema_version': 1,
            'groups': [
                {
                    'id': 'urn:account',
                    'relationship': 'OverlapUnresolved',
                    'qualification': 'Overlap is not established by this account alone.',
                    'reviewer': 'Codex',
                    'assertions': ['urn:claim'],
                    'sources': [source_pin(self.root, revision, 'A chose B.', 0)],
                }
            ],
        }
        path = self.root / 'curation/evidence-accounts.json'
        path.parent.mkdir()
        path.write_text(json.dumps(catalogue))
        before = self.files()
        result = audit(self.root)
        self.assertEqual(result['errors'], [])
        self.assertEqual(result['counts']['active_evidence_account_groups'], 1)
        self.assertEqual(result['counts']['active_evidence_account_members'], 1)
        self.assertEqual(self.files(), before)
        catalogue['groups'][0]['sources'][0]['quote'] = 'A different quotation.'
        path.write_text(json.dumps(catalogue))
        self.assertIn('invalid_evidence_accounts', self.codes(audit(self.root)))

    def curate(self, *sources):
        return create_note(
            self.root,
            'A self-contained account.',
            title='Curated account',
            author='Codex',
            agent='Codex',
            derivation={
                'method': 'faithful_restatement',
                'qualification': 'Reported by the source.',
                'sources': [source_pin(self.root, s['revision'], s['body'], 0) for s in sources],
            },
        )

    def test_curated_capture_is_counted_without_warning_until_source_body_changes(self):
        original = create_note(self.root, 'Can you add this observation?')
        self.curate(original)
        metadata_only = save_note(
            self.root,
            original['note'],
            original['body'],
            expected=original['revision'],
            title='Original observation',
        )
        before = self.files()
        result = audit(self.root)
        self.assertEqual(result['errors'], [])
        self.assertNotIn('conversational_note', self.codes(result, 'warnings'))
        self.assertEqual(result['counts']['conversational_source_captures'], 1)
        self.assertEqual(result['counts']['conversational_captures_with_curation'], 1)
        self.assertEqual(result['counts']['uncurated_conversational_captures'], 0)
        self.assertEqual(self.files(), before)
        save_note(
            self.root,
            original['note'],
            'Can you add this revised observation?',
            expected=metadata_only['revision'],
        )
        result = audit(self.root)
        self.assertEqual(result['errors'], [])
        self.assertIn('conversational_note', self.codes(result, 'warnings'))
        self.assertEqual(result['counts']['conversational_captures_with_curation'], 0)
        self.assertEqual(result['counts']['uncurated_conversational_captures'], 1)
        self.assertEqual(self.root.joinpath(original['body_path']).read_text(), original['body'])

    def test_only_current_curation_of_same_note_covers_a_capture(self):
        first = create_note(self.root, 'Can you add this account?')
        duplicate = create_note(self.root, first['body'])
        curated = self.curate(first)
        before = audit(self.root)
        warning = next(w for w in before['warnings'] if w['code'] == 'conversational_note')
        self.assertEqual(warning['record'], duplicate['note'])
        save_note(
            self.root,
            curated['note'],
            'An account of the other source.',
            expected=curated['revision'],
            agent='Codex',
            derivation={
                **curated['derivation'],
                'sources': [source_pin(self.root, duplicate['revision'], duplicate['body'], 0)],
            },
        )
        after = audit(self.root)
        warning = next(w for w in after['warnings'] if w['code'] == 'conversational_note')
        self.assertEqual(warning['record'], first['note'])
        self.assertEqual(after['counts']['conversational_source_captures'], 2)
        self.assertEqual(after['counts']['conversational_captures_with_curation'], 1)

    def test_invalid_current_derivation_does_not_suppress_source_warning(self):
        original = create_note(self.root, 'Can you add this observation?')
        other = create_note(self.root, 'Additional source context.')
        self.curate(original, other)
        self.root.joinpath(other['body_path']).write_text('Changed evidence.')
        result = audit(self.root)
        self.assertIn('invalid_derivation', self.codes(result))
        self.assertIn('conversational_note', self.codes(result, 'warnings'))
        self.assertEqual(result['counts']['conversational_captures_with_curation'], 0)


if __name__ == '__main__':
    unittest.main()
