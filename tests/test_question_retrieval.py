import json
import subprocess
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from retrieval_fixture import CLAIM, ROUTE, SEED, make_fixture

from knot.inventory import digest
from knot.rdf import DERIVED, RDF_TYPE, VOCAB
from knot.retrieval import Policy, retrieve, serialise
from knot.review import decide
from knot.search import Limits


class QuestionRetrievalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.dataset = make_fixture(self.root)
        self.policy = Policy(max_chars=30000)

    def get(
        self, question='What unresolved dependencies threaten Orion?', mode='hybrid', **changes
    ):
        return retrieve(
            self.root, SEED, replace(self.policy, **changes), question=question, mode=mode
        )

    def source(self, name, text):
        (self.root / 'sources' / name).write_text(text)
        revision = 'urn:revision:' + digest(text.encode())
        self.dataset.add(revision, VOCAB + 'snapshotPath', 'sources/' + name, literal=True)
        self.dataset.add(revision, VOCAB + 'sha256', digest(text.encode()), literal=True)
        self.dataset.add('urn:document:' + name, RDF_TYPE, VOCAB + 'Document')
        self.dataset.add('urn:document:' + name, VOCAB + 'revision', revision)
        return revision

    def claim(self, aid, subject, predicate, obj, quote, *, status='Accepted'):
        revision = self.source(aid.rsplit(':', 1)[-1] + '.md', quote + '\n')
        self.dataset.add(subject, VOCAB + predicate, obj, graph=aid)
        self.dataset.add(aid, RDF_TYPE, VOCAB + 'Assertion')
        for key, value in [
            ('reviewStatus', status),
            ('origin', 'Explicit'),
            ('lifecycle', 'Active'),
        ]:
            self.dataset.add(aid, VOCAB + key, VOCAB + value)
        for key, value in [
            ('subjectLabel', subject),
            ('objectLabel', obj),
            ('rationale', 'Source account'),
        ]:
            self.dataset.add(aid, VOCAB + key, value, literal=True)
        self.dataset.add(aid, DERIVED, aid + ':evidence')
        self.dataset.add(aid + ':evidence', VOCAB + 'revision', revision)
        self.dataset.add(aid + ':evidence', VOCAB + 'quote', quote, literal=True)

    def save(self):
        (self.root / 'graph/claims.trig').write_text(self.dataset.text())

    def test_same_seed_selects_different_paths_before_degree_limit(self):
        self.claim(
            'urn:assertion:team-route',
            'urn:team:delivery',
            'relatedTo',
            SEED,
            'The team belongs to Orion.',
            status='Unreviewed',
        )
        self.claim(
            'urn:assertion:team-outcome',
            'urn:team:delivery',
            'reportedOutcome',
            'urn:outcome:autonomy',
            'Leadership outcomes: the team delivered independently while the lead was away.',
        )
        self.save()
        dependencies = self.get(mode='graph', max_degree=1, max_assertions=2)
        leadership = self.get(
            'What were my strongest Orion leadership outcomes?',
            mode='graph',
            max_degree=1,
            max_assertions=2,
        )
        self.assertIn(CLAIM, dependencies['assertions'])
        self.assertNotIn('urn:assertion:team-outcome', dependencies['assertions'])
        self.assertIn('urn:assertion:team-outcome', leadership['assertions'])
        self.assertNotIn(CLAIM, leadership['assertions'])
        match = leadership['matches'][0]
        self.assertGreater(match['ranking']['score'], 0)
        self.assertIn('leadership', match['ranking']['intents'])
        self.assertEqual(len(leadership['paths'][match['path']]), 2)

    def test_question_only_hybrid_preserves_focused_text_relevance(self):
        focused = self.source(
            'capacity.md',
            '# Nova capacity\nThe limit is three jobs. However, adoption is unmeasured.\n',
        )
        self.source(
            'background.md',
            '# General research\nNova capacity limit unknown is an example search query.\n'
            + 'Unrelated background about search systems and response formats. ' * 50,
        )
        self.save()
        for mode in ('text', 'hybrid'):
            with self.subTest(mode=mode):
                result = retrieve(
                    self.root,
                    question='Is the Nova capacity limit unknown?',
                    mode=mode,
                    policy=Policy(max_chars=12000, max_passages=1),
                )
                self.assertEqual({s['revision'] for s in result['sources'].values()}, {focused})
                self.assertIn('adoption is unmeasured', ' '.join(result['passages'].values()))

    def test_hybrid_recovers_source_with_no_assertion_and_keeps_qualification(self):
        text = '# Orion\n\n## Retry plan\nRetries are planned.\nThey have not been tested; no delivery outcome is established.\n'
        self.source('unlinked-plan.md', text)
        self.save()
        result = self.get('What is the Orion retry plan?')
        found = [
            result['sources'][eid]
            for eid in result['source_context']
            if result['sources'][eid]['snapshot'].endswith('unlinked-plan.md')
        ]
        self.assertEqual(len(found), 1)
        self.assertIn('They have not been tested', result['passages'][found[0]['passage']])
        self.assertEqual(result['assertions'].get('unlinked-plan'), None)
        self.assertTrue(all(r['claim_review'] is None for r in result['source_context'].values()))
        self.assertTrue(
            all(r['entity_link'] == 'LexicalOnly' for r in result['source_context'].values())
        )
        self.assertTrue(found[0]['locator']['heading_path'])
        graph = self.get('What is the Orion retry plan?', mode='graph')
        self.assertFalse(graph['source_context'])

    def test_accepted_only_cannot_promote_source_text_or_unreviewed_path(self):
        result = self.get(accepted_only=True)
        self.assertFalse(result['source_context'])
        self.assertFalse(result['assertions'])
        self.assertTrue(result['omissions']['source_only_excluded'])
        decide(self.root, ROUTE, 'accept', reviewer='Test', reason='Checked')
        result = self.get(accepted_only=True)
        self.assertIn(CLAIM, result['assertions'])
        self.assertEqual(result['assertions'][CLAIM]['kind'], 'Thought')
        self.assertFalse(result['source_context'])
        self.assertTrue(all(a['status'] == 'Accepted' for a in result['assertions'].values()))
        self.assertFalse(self.get(mode='text', accepted_only=True)['passages'])

    def test_text_does_not_restore_rejected_assertions_or_confirm_same_name(self):
        decide(self.root, ROUTE, 'reject', reviewer='Test', reason='Wrong association')
        result = self.get('What Orion budget constraints were recorded?', mode='text')
        self.assertFalse(result['assertions'])
        self.assertFalse(result['paths'])
        self.assertFalse(result['identities'])
        self.assertTrue(result['source_context'])
        self.assertTrue(
            all(v['entity_link'] == 'LexicalOnly' for v in result['source_context'].values())
        )

    def test_changed_source_is_excluded_and_unknown_seed_is_not_guessed(self):
        (self.root / 'sources/dependency.md').write_text('changed bytes')
        result = self.get(mode='text')
        self.assertGreater(result['omissions']['invalid_citations'], 0)
        self.assertFalse(
            any(s['snapshot'].endswith('dependency.md') for s in result['sources'].values())
        )
        with self.assertRaisesRegex(ValueError, 'canonical IRI'):
            retrieve(self.root, 'Orion', self.policy, question='Orion dependencies', mode='hybrid')

    def test_shared_budget_envelope_determinism_and_no_orphaned_records(self):
        for mode in ('graph', 'text', 'hybrid'):
            for budget in (2000, 4000, 12000):
                with self.subTest(mode=mode, budget=budget):
                    result = self.get(mode=mode, max_chars=budget, max_passages=2, max_assertions=2)
                    wire = serialise(result)
                    self.assertLessEqual(len(wire), budget)
                    self.assertEqual(len(wire), result['usage']['characters'])
                    self.assertEqual(len(wire.encode()), result['usage']['utf8_bytes'])
                    self.assertLessEqual(len(result['passages']), 2)
                    self.assertLessEqual(len(result['assertions']), 2)
                    self.assertEqual(
                        wire,
                        serialise(
                            self.get(mode=mode, max_chars=budget, max_passages=2, max_assertions=2)
                        ),
                    )
                    for path in result['paths']:
                        self.assertTrue(
                            all(step['assertion'] in result['assertions'] for step in path)
                        )
                    used = {s for a in result['assertions'].values() for s in a['sources']} | set(
                        result['source_context']
                    )
                    self.assertEqual(set(result['sources']), used)
        with self.assertRaisesRegex(ValueError, 'envelope'):
            self.get(max_chars=10)

    def test_source_scan_and_candidate_limits_are_finite_and_visible(self):
        result = retrieve(
            self.root,
            SEED,
            self.policy,
            question='What Orion retries remain untested?',
            mode='hybrid',
            limits=Limits(max_source_revisions=1, max_source_sections=1, max_candidates=1),
        )
        self.assertLessEqual(result['usage']['source_revisions'], 1)
        self.assertLessEqual(result['usage']['source_sections'], 1)
        self.assertLessEqual(result['usage']['candidates'], 1)
        self.assertTrue(result['omissions']['further_unknown'])
        with self.assertRaises(ValueError):
            Limits(max_candidates=0)

    def test_rejects_empty_question_and_text_without_question(self):
        for question in ('', '   '):
            with self.assertRaises(ValueError):
                self.get(question)
        with self.assertRaises(ValueError):
            retrieve(self.root, SEED, self.policy, mode='text')

    def test_document_context_connects_revisions_without_merging_entities(self):
        first = self.source('named.md', '# Orion\nThe main workstream.\n')
        second = self.source('unnamed.md', '# Dependencies\nA missing survey feed is a risk.\n')
        self.dataset.add('urn:document:shared', RDF_TYPE, VOCAB + 'Document')
        for revision in (first, second):
            self.dataset.add('urn:document:shared', VOCAB + 'revision', revision)
        self.save()
        result = self.get(mode='text')
        contexts = [
            eid
            for eid in result['source_context']
            if result['sources'][eid]['snapshot'].endswith('unnamed.md')
        ]
        self.assertEqual(len(contexts), 1)
        self.assertEqual(
            result['source_context'][contexts[0]]['seed_context'], 'LabelTermsInSameDocument'
        )
        self.assertEqual(result['sources'][contexts[0]]['independence'], 'Unknown')
        self.assertFalse(result['identities'])

    def test_incidental_body_mention_keeps_weaker_locality_than_entity_heading(self):
        self.source('incidental.md', '# Measurement research\nOrion is one possible application.\n')
        self.source('direct.md', '# Orion measurement\nThe experiment was completed.\n')
        self.save()
        result = self.get('What Orion measurement research was completed?', mode='text')
        localities = {
            result['sources'][match['source']]['snapshot'].rsplit('/', 1)[-1]: match['ranking'][
                'seed_locality'
            ]
            for match in result['matches']
        }
        self.assertEqual(localities['incidental.md'], 'Document')
        self.assertEqual(localities['direct.md'], 'Section')

    def test_oversized_section_is_omitted_intact_and_unicode_counts_are_exact(self):
        text = '# Orion\n## Retry plan\nRetry ' + 'λ' * 6000 + '\nThis is not delivered.\n'
        self.source('large.md', text)
        self.save()
        small = self.get('What is the Orion retry plan λ?', mode='text', max_chars=4000)
        self.assertFalse(any(s['snapshot'].endswith('large.md') for s in small['sources'].values()))
        large = self.get('What is the Orion retry plan λ?', mode='text')
        found = [s for s in large['sources'].values() if s['snapshot'].endswith('large.md')]
        self.assertEqual(len(found), 1)
        self.assertTrue(large['passages'][found[0]['passage']].endswith('This is not delivered.\n'))
        self.assertGreater(large['usage']['utf8_bytes'], large['usage']['characters'])

    def test_ranked_traversal_limits_and_invalid_routing_evidence(self):
        for change in ({'max_depth': 1}, {'max_expanded': 1}):
            with self.subTest(change=change):
                result = self.get(mode='graph', **change)
                self.assertNotIn(CLAIM, result['assertions'])
                self.assertTrue(result['omissions']['further_unknown'])
        (self.root / 'sources/association.md').unlink()
        result = self.get(mode='graph')
        self.assertNotIn(CLAIM, result['assertions'])
        self.assertEqual(result['omissions']['citation_errors'], {'MissingFile': 1})

    def test_source_framework_eligibility_is_explicit(self):
        aid = 'urn:assertion:extra-framework'
        self.claim(
            aid,
            'urn:competency:extra',
            'hasCriterion',
            'urn:criterion:extra',
            'Orion risk review definition.',
        )
        self.dataset.add(aid, VOCAB + 'recordKind', VOCAB + 'FrameworkDefinition')
        self.save()
        ordinary = self.get('What Orion risk review definition is recorded?', mode='text')
        included = self.get(
            'What Orion risk review definition is recorded?', mode='text', include_frameworks=True
        )
        self.assertFalse(
            any(s['snapshot'].endswith('extra-framework.md') for s in ordinary['sources'].values())
        )
        self.assertTrue(
            any(s['snapshot'].endswith('extra-framework.md') for s in included['sources'].values())
        )

    def test_empty_question_result_has_exact_envelope_boundary(self):
        result = self.get(accepted_only=True)
        budget = len(serialise(result))
        budget = len(serialise(self.get(accepted_only=True, max_chars=budget)))
        self.assertEqual(len(serialise(self.get(accepted_only=True, max_chars=budget))), budget)
        with self.assertRaisesRegex(ValueError, 'envelope'):
            self.get(accepted_only=True, max_chars=budget - 1)

    def test_word_forms_supply_lexical_context_without_identity_claims(self):
        self.dataset.add(
            SEED,
            'http://www.w3.org/2000/01/rdf-schema#label',
            'Deployment approval redesign',
            literal=True,
        )
        self.source(
            'approvals.md',
            '# Approvals\nRedesigned the pipeline: deployed with team approvers and ownership.\n',
        )
        self.save()
        result = self.get('What ownership followed the deployment approval redesign?', mode='text')
        self.assertTrue(
            any(s['snapshot'].endswith('approvals.md') for s in result['sources'].values())
        )
        self.assertFalse(result['identities'])

    def test_keyword_heavy_long_section_does_not_crowd_out_concise_evidence(self):
        self.source('ownership.md', '# Orion\n## Result\nTeam ownership is established.\n')
        self.source(
            'long-distractor.md',
            '# Orion\n## Other\nOther team ownership is mentioned.\n'
            + 'Unrelated background. ' * 500,
        )
        self.save()
        result = self.get('What ownership did other Orion teams gain?', mode='text', max_passages=1)
        self.assertEqual(len(result['sources']), 1)
        self.assertTrue(next(iter(result['sources'].values()))['snapshot'].endswith('ownership.md'))

    def test_leadership_intent_recovers_demonstrated_independence_before_retention(self):
        self.source(
            'outcome.md',
            '# Orion\n## Delivery\nThe team delivered independently while I was on leave.\n'
            'Correlation does not prove my process caused this outcome.\n',
        )
        self.source('reading.md', '# Orion\n## Leadership outcomes\nI read a leadership book.\n')
        self.save()
        result = retrieve(
            self.root,
            SEED,
            self.policy,
            question='What were my strongest Orion leadership outcomes?',
            mode='text',
            limits=Limits(max_candidates=1),
        )
        self.assertTrue(
            any(s['snapshot'].endswith('outcome.md') for s in result['sources'].values())
        )
        self.assertIn('Correlation does not prove', ' '.join(result['passages'].values()))

    def test_hybrid_prefers_qualifying_context_over_duplicate_graph_quotation(self):
        quote = 'All Orion reports are reconciled.'
        aid = 'urn:assertion:reports'
        self.claim(aid, SEED, 'reportedOutcome', 'urn:outcome:reports', quote)
        text = '# Orion reports\n' + quote + '\nCaveat: two reports still have missing data.\n'
        revision = self.source('qualified.md', text)
        # Both channels cite the same original revision and exact statement.
        from knot.rdf import META

        self.dataset.graphs[META.value] = {
            line
            for line in self.dataset.graphs[META.value]
            if not line.startswith(f'<{aid}:evidence> <{VOCAB}revision>')
        }
        self.dataset.add(aid + ':evidence', VOCAB + 'revision', revision)
        self.save()
        result = self.get('Were all Orion reports reconciled?', max_passages=1)
        self.assertIn('Caveat: two reports', ' '.join(result['passages'].values()))
        self.assertIn(aid, result['assertions'])
        parent = next(match for match in result['matches'] if match['channel'] == 'graph')
        self.assertTrue(parent['context_sources'])
        self.assertEqual(parent['context_reason'], 'SameSourceUnitQualificationCue')

    def test_long_evidence_body_retains_qualification_without_interview_repetition(self):
        from knot.search import _sections

        text = (
            '* Orion delivery\n:PROPERTIES:\n:ID: delivery\n:END:\n'
            '- The team delivered independently.\n'
            '- Caveat: this does not prove the process caused delivery.\n'
            '- Why this matters: ' + 'Leadership interpretation. ' * 90 + '\n'
            '- Interview lens (Leadership): ' + 'Repeated interpretation. ' * 90 + '\n'
        )
        units = list(_sections(text, 'source.org'))
        body = next((quote, loc) for quote, loc in units if 'The team delivered' in quote)
        self.assertIn('Caveat: this does not prove', body[0])
        self.assertNotIn('Interview lens', body[0])
        start = int(body[1]['characterOffset'])
        self.assertEqual(text[start : start + len(body[0])], body[0])
        self.assertFalse(body[1]['section_complete'])

    def test_multiple_citations_keep_each_identified_qualification_with_the_claim(self):
        from knot.rdf import META

        aid = 'urn:assertion:paired-reports'
        quote = 'Orion reports were completed.'
        self.claim(aid, SEED, 'reportedOutcome', 'urn:outcome:reports', quote)
        first = self.source(
            'first-qualified.md',
            '# Orion reports\n' + quote + '\nHowever, acceptance is pending.\n',
        )
        second = self.source(
            'second-qualified.md',
            '# Orion reports\n' + quote + '\nCaveat: reconciliation remains unverified.\n',
        )
        self.dataset.graphs[META.value] = {
            line
            for line in self.dataset.graphs[META.value]
            if not line.startswith(f'<{aid}:evidence> <{VOCAB}revision>')
        }
        self.dataset.add(aid + ':evidence', VOCAB + 'revision', first)
        self.dataset.add(aid, DERIVED, aid + ':second')
        self.dataset.add(aid + ':second', VOCAB + 'revision', second)
        self.dataset.add(aid + ':second', VOCAB + 'quote', quote, literal=True)
        self.save()
        result = self.get('What Orion report outcomes are recorded?', max_passages=2)
        self.assertIn(aid, result['assertions'])
        parent = next(
            m
            for m in result['matches']
            if m['channel'] == 'graph'
            and aid in {s['assertion'] for s in result['paths'][m['path']]}
        )
        self.assertEqual(len(parent['context_sources']), 2)

    def test_high_degree_project_seed_can_expand_more_than_four_relevant_routes(self):
        for i in range(7):
            work = f'urn:work:team:{i}'
            self.claim(
                f'urn:assertion:route-{i}', work, 'relatedTo', SEED, f'Team {i} belongs to Orion.'
            )
            self.claim(
                f'urn:assertion:outcome-{i}',
                work,
                'reportedOutcome',
                f'urn:outcome:{i}',
                f'Team {i} delivered independently with leadership support.',
            )
        self.save()
        result = self.get(
            'What Orion leadership outcomes demonstrate independence?',
            mode='graph',
            hub_degree=5,
            max_chars=100000,
            max_passages=30,
            max_assertions=30,
        )
        self.assertGreater(len(result['paths']), 4)
        self.assertLessEqual(result['usage']['expanded'], self.policy.max_expanded)

    def test_multihop_lookahead_prioritises_deep_evidence_without_generic_shortcuts(self):
        self.claim(
            'urn:assertion:deep-route',
            'urn:work:outer',
            'relatedTo',
            SEED,
            'Outer work belongs to Orion.',
        )
        self.claim(
            'urn:assertion:deep-link',
            'urn:work:outer',
            'relatedTo',
            'urn:work:inner',
            'Inner work is related to outer work.',
        )
        self.claim(
            'urn:assertion:deep-dependency',
            'urn:work:inner',
            'dependsOn',
            'urn:dependency:retry',
            'The retry dependency remains outstanding.',
        )
        self.save()
        result = self.get(
            'What Orion retry dependency remains outstanding?',
            mode='graph',
            max_depth=3,
            max_degree=1,
        )
        self.assertIn('urn:assertion:deep-dependency', result['assertions'])
        self.assertEqual(len(result['paths'][0]), 3)
        self.dataset.add('urn:work:inner', RDF_TYPE, VOCAB + 'Person')
        self.save()
        result = self.get(
            'What Orion retry dependency remains outstanding?',
            mode='graph',
            max_depth=3,
            max_degree=1,
        )
        self.assertNotIn('urn:assertion:deep-dependency', result['assertions'])

    def test_qualification_in_interpretation_tail_keeps_whole_section(self):
        from knot.search import _sections

        text = (
            '* Orion outcome\n- Delivered.\n- Why this matters: '
            + 'Background. ' * 180
            + '\n- Caveat: this is not yet verified.\n'
        )
        units = list(_sections(text, 'source.org'))
        self.assertEqual(len(units), 1)
        self.assertEqual(units[0][0], text)
        self.assertTrue(units[0][1]['section_complete'])

    def test_invalid_assertion_citation_cannot_supply_seed_context_to_unnamed_source(self):
        from knot.rdf import META

        aid = 'urn:assertion:bad-anchor'
        self.claim(aid, SEED, 'dependsOn', 'urn:feed:secret', 'The secret feed remains missing.')
        self.dataset.graphs[META.value] = {
            line
            for line in self.dataset.graphs[META.value]
            if not line.startswith(f'<{aid}:evidence> <{VOCAB}quote>')
        }
        self.dataset.add(aid + ':evidence', VOCAB + 'quote', 'Absent quotation', literal=True)
        self.save()
        result = self.get('What Orion secret feed remains missing?', mode='text')
        self.assertFalse(
            any(s['snapshot'].endswith('bad-anchor.md') for s in result['sources'].values())
        )
        self.assertGreater(result['omissions']['invalid_citations'], 0)

    def test_question_cli_preserves_arguments_and_wire_budget(self):
        question = 'What unresolved dependencies threaten Orion?'
        run = subprocess.run(
            [
                'just',
                'retrieval',
                'get',
                SEED,
                '--data-root',
                str(self.root),
                '--question',
                question,
                '--mode',
                'hybrid',
                '--max-chars',
                '12000',
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertEqual(run.stdout, serialise(self.get(question, max_chars=12000)))
        self.assertEqual(json.loads(run.stdout)['question'], question)


if __name__ == '__main__':
    unittest.main()
