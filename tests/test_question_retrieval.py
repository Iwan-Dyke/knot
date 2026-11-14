import json
import subprocess
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from retrieval_fixture import CLAIM, ROUTE, SEED, make_fixture

from knot.inventory import digest
from knot.rdf import DERIVED, META, RDF_TYPE, VOCAB
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

    def test_question_only_hybrid_finds_existing_mappings_without_selecting_a_seed(self):
        aids = ['urn:assertion:release-checks', 'urn:assertion:release-approvals']
        for aid, subject, quote in (
            (aids[0], 'urn:project:falcon', 'Falcon release engineering uses automated checks.'),
            (aids[1], 'urn:project:harbor', 'Harbor release engineering retains team approvals.'),
        ):
            self.claim(aid, subject, 'supports', 'urn:criterion:release-engineering', quote)
        self.source(
            'guide.md',
            '# Release engineering skills\nGeneral skills support release engineering skills.',
        )
        self.save()
        before = {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        for accepted_only in (False, True):
            result = retrieve(
                self.root,
                question='What evidence supports my release engineering skills?',
                mode='hybrid',
                policy=Policy(max_chars=24000, accepted_only=accepted_only),
            )
            self.assertLessEqual(set(aids), result['assertions'].keys())
            self.assertIsNone(result['seed'])
            self.assertTrue(all(len(path) == 1 for path in result['paths']))
            self.assertEqual(result['matches'][0]['channel'], 'graph')
        text = retrieve(self.root, question='release engineering', mode='text', policy=self.policy)
        self.assertFalse(text['assertions'])
        self.assertEqual(before, {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()})

    def test_question_only_comparison_retains_evidence_against_the_premise(self):
        quote = (
            '# Quartz pipeline jobs\nRuntime and cost increased. '
            'This was reported for one workload only, not every service.\n'
        )
        expected = self.source('runtime.md', quote)
        self.source('cleanup.md', '# Quartz pipeline jobs\nNow include a cleanup command.\n')
        self.save()
        for mode in ('text', 'hybrid'):
            with self.subTest(mode=mode):
                result = retrieve(
                    self.root,
                    question='Did Quartz pipeline jobs become faster and cheaper?',
                    mode=mode,
                    policy=Policy(max_chars=12000, max_passages=1),
                )
                self.assertEqual({s['revision'] for s in result['sources'].values()}, {expected})
                self.assertIn(quote, result['passages'].values())
                self.assertFalse(result['assertions'])

    def test_question_only_conflicting_measurements_retain_both_qualified_accounts(self):
        quotes = (
            '# Lumen rollout — first measurement\n'
            'On 3 April, the Lumen rollout report measured a 20% latency reduction. '
            'This is a team report, not independently verified.\n',
            '# Lumen rollout — later measurement\n'
            'On 8 April, the Lumen rollout report measured a 15% latency increase. '
            'The workloads differed, so these measurements cannot establish a trend '
            'or explain the discrepancy.\n',
        )
        expected = {self.source(f'measurement-{i}.md', quote) for i, quote in enumerate(quotes)}
        self.save()
        result = retrieve(
            self.root,
            question='What conflicting latency measurements were reported for the Lumen rollout?',
            mode='hybrid',
            policy=Policy(max_chars=24000),
        )
        self.assertEqual({s['revision'] for s in result['sources'].values()}, expected)
        self.assertEqual(set(result['passages'].values()), set(quotes))
        self.assertTrue(all(c['claim_review'] is None for c in result['source_context'].values()))
        self.assertFalse(result['assertions'])

    def test_question_only_named_claim_keeps_review_kind_and_qualification(self):
        aid = 'urn:assertion:falcon-plan'
        quote = 'Falcon release engineering was proposed; it is not yet implemented.'
        self.claim(
            aid,
            'urn:project:falcon',
            'supports',
            'urn:criterion:release-engineering',
            quote,
            status='Unreviewed',
        )
        self.source(
            'research.md', '# Release metrics\nFalcon is mentioned in general metrics research.'
        )
        self.save()
        question = 'What does Falcon demonstrate about release engineering?'
        result = retrieve(self.root, question=question, mode='hybrid', policy=self.policy)
        self.assertIn(aid, result['assertions'])
        self.assertEqual(result['assertions'][aid]['status'], 'Unreviewed')
        self.assertIn('not yet implemented', ' '.join(result['passages'].values()))
        accepted = retrieve(
            self.root,
            question=question,
            mode='hybrid',
            policy=replace(self.policy, accepted_only=True),
        )
        self.assertNotIn(aid, accepted['assertions'])

    def test_explicit_unknown_subject_does_not_return_generic_delivery_evidence(self):
        self.claim(
            'urn:assertion:other-delivery',
            'urn:project:delivery',
            'reportedOutcome',
            'urn:outcome:successful-delivery',
            'The delivery team reported successful delivery, not independently verified.',
        )
        self.source('delivery.md', '# Delivery evidence\nThe team delivered the release.\n')
        self.save()
        for subject in ('MISSING-731', 'project Nimbus', 'project "Blue Ember"'):
            for mode in ('text', 'hybrid'):
                with self.subTest(subject=subject, mode=mode):
                    result = retrieve(
                        self.root,
                        question=f'What evidence supports successful delivery of {subject}?',
                        mode=mode,
                        policy=self.policy,
                    )
                    self.assertFalse(result['matches'])
                    self.assertFalse(result['sources'])
                    self.assertFalse(result['assertions'])
                    self.assertIn('subject_constraint', result)
                    self.assertTrue(result['subject_constraint']['absence_not_established'])
        broad = retrieve(
            self.root,
            question='What evidence supports successful delivery?',
            mode='hybrid',
            policy=self.policy,
        )
        self.assertTrue(broad['matches'])
        self.assertNotIn('subject_constraint', broad)

    def test_explicit_subject_matches_complete_source_only_units_before_candidate_cap(self):
        expected = self.source(
            'target.md',
            '# MISSING-731\nA delivery was proposed; it is not yet implemented.\n',
        )
        self.source(
            'other.md',
            '# MISSING-7310 successful delivery evidence\nSuccessful delivery was reported.\n',
        )
        self.save()
        for mode in ('text', 'hybrid'):
            with self.subTest(mode=mode):
                result = retrieve(
                    self.root,
                    question='What evidence supports successful delivery of MISSING-731?',
                    mode=mode,
                    policy=self.policy,
                    limits=Limits(max_candidates=1),
                )
                self.assertEqual({s['revision'] for s in result['sources'].values()}, {expected})
                self.assertIn('not yet implemented', ' '.join(result['passages'].values()))
                self.assertFalse(result['assertions'])

    def test_explicit_project_name_uses_visible_alias_and_keeps_required_context(self):
        from knot.rdf import LABEL

        aid, subject = 'urn:assertion:falcon-delivery', 'urn:project:falcon'
        quote = 'The team reported successful delivery.'
        self.claim(aid, subject, 'reportedOutcome', 'urn:outcome:delivery', quote)
        self.dataset.add(subject, LABEL, 'Silverwing', literal=True)
        # The subject is in metadata only: its contextual caveat must still travel
        # with the matching claim even though that context lacks the query's name.
        full = '# Delivery account\n' + quote + '\nHowever, independent verification is pending.\n'
        revision = self.source('qualified.md', full)
        self.dataset.add(aid + ':evidence', VOCAB + 'revision', revision)
        # Replace the original citation revision rather than creating two targets.
        old = 'urn:revision:' + digest((quote + '\n').encode())
        self.dataset.graphs[META.value] = {
            line
            for line in self.dataset.graphs[META.value]
            if old not in line or aid + ':evidence' not in line
        }
        self.save()
        result = retrieve(
            self.root,
            question='What evidence supports successful delivery of project Silverwing?',
            mode='hybrid',
            policy=self.policy,
        )
        self.assertIn(aid, result['assertions'])
        self.assertIn('independent verification is pending', ' '.join(result['passages'].values()))

    def test_explicit_subject_cannot_reveal_denied_sources_or_bypass_verification(self):
        from knot.access import AccessScope

        visible = self.source('visible.md', '# Delivery\nA different project delivered.\n')
        self.save()
        raw = (self.root / 'sources/visible.md').read_bytes()
        scope = AccessScope(revisions=((visible, digest(raw)),))
        question = 'What supports delivery of HIDDEN-42?'

        def request(scope):
            return retrieve(
                self.root, question=question, mode='hybrid', policy=self.policy, scope=scope
            )

        before = request(scope)
        self.source(
            'hidden.md', '# HIDDEN-42\nThe project delivered, but verification is pending.\n'
        )
        self.save()
        self.assertEqual(serialise(before), serialise(request(scope)))
        self.assertFalse(before['sources'])
        allowed = request(AccessScope.all())
        self.assertTrue(allowed['sources'])
        (self.root / 'sources/hidden.md').write_text('Changed bytes')
        corrupt = request(AccessScope.all())
        self.assertFalse(corrupt['sources'])
        self.assertGreater(corrupt['omissions']['invalid_citations'], 0)

    def test_explicit_multiple_projects_can_return_evidence_for_either_without_guessing_identity(
        self,
    ):
        expected = {
            self.source('north.md', '# North Star\nDelivery was reported, not verified.\n'),
            self.source('south.md', '# South Star\nDelivery was proposed, not completed.\n'),
        }
        self.source('other.md', '# Delivery\nThe unrelated team delivered successfully.\n')
        self.save()
        result = retrieve(
            self.root,
            question='Compare delivery of project "North Star" and project "South Star".',
            mode='hybrid',
            policy=self.policy,
        )
        self.assertEqual({s['revision'] for s in result['sources'].values()}, expected)
        self.assertFalse(result['identities'])
        self.assertFalse(result['assertions'])

    def test_reviewed_definition_pin_does_not_require_the_entire_framework_as_claim_context(self):
        aid, criterion = 'urn:assertion:release-assessment', 'urn:criterion:release-engineering'
        self.claim(
            aid,
            'urn:project:falcon',
            'supports',
            criterion,
            'Release engineering: a reported exercise, not proof of a grade.',
        )
        definition = 'Release engineering includes designing a component delivery process.'
        revision = self.source(
            'framework.txt',
            'General framework introduction. ' * 1000
            + '\n'
            + definition
            + '\nHowever, the unrelated mentoring section has further guidance.\n',
        )
        self.dataset.add(aid, DERIVED, aid + ':definition')
        self.dataset.add(aid + ':definition', VOCAB + 'revision', revision)
        self.dataset.add(aid + ':definition', VOCAB + 'quote', definition, literal=True)
        did = 'urn:assertion:release-definition'
        self.dataset.add(
            criterion,
            'http://www.w3.org/2004/02/skos/core#definition',
            definition,
            literal=True,
            graph=did,
        )
        self.dataset.add(did, RDF_TYPE, VOCAB + 'Assertion')
        for key, value in [
            ('reviewStatus', 'Accepted'),
            ('lifecycle', 'Active'),
            ('origin', 'Explicit'),
            ('recordKind', 'FrameworkDefinition'),
        ]:
            self.dataset.add(did, VOCAB + key, VOCAB + value)
        for key, value in [
            ('subjectLabel', 'Release engineering'),
            ('objectLabel', definition),
            ('rationale', 'The framework definition, not performance evidence.'),
        ]:
            self.dataset.add(did, VOCAB + key, value, literal=True)
        self.dataset.add(did, DERIVED, aid + ':definition')
        self.save()
        result = retrieve(
            self.root,
            question='What supports release engineering?',
            mode='hybrid',
            policy=Policy(max_chars=12000),
        )
        self.assertIn(aid, result['assertions'])
        self.assertEqual(len(result['assertions'][aid]['sources']), 2)
        self.assertIn(definition, ' '.join(result['passages'].values()))
        self.assertIn('not proof of a grade', ' '.join(result['passages'].values()))
        # Without a reviewed definition, do not infer that the extra context is irrelevant.
        self.dataset.graphs[META.value] = {
            line
            for line in self.dataset.graphs[META.value]
            if not line.startswith(f'<{did}> <{VOCAB}reviewStatus>')
        }
        self.dataset.add(did, VOCAB + 'reviewStatus', VOCAB + 'Unreviewed')
        self.save()
        unreviewed = retrieve(
            self.root,
            question='What supports release engineering?',
            mode='hybrid',
            policy=Policy(max_chars=12000),
        )
        self.assertNotIn(aid, unreviewed['assertions'])

    def test_question_only_claim_search_is_unchanged_by_denied_matching_claims(self):
        from knot.access import AccessScope

        aid = 'urn:assertion:visible-release'
        quote = 'Falcon release engineering retains approvals.'
        self.claim(
            aid, 'urn:project:falcon', 'supports', 'urn:criterion:release-engineering', quote
        )
        self.save()
        sha = digest((quote + '\n').encode())
        scope = AccessScope(revisions=(('urn:revision:' + sha, sha),))

        def request():
            return retrieve(
                self.root,
                question='What supports release engineering?',
                mode='hybrid',
                policy=self.policy,
                scope=scope,
            )

        before = request()
        self.assertIn(aid, before['assertions'])
        self.claim(
            'urn:assertion:hidden-release',
            'urn:project:private-falcon',
            'supports',
            'urn:criterion:release-engineering',
            'Secret release engineering skills demonstrate private facts.',
        )
        self.save()
        self.assertEqual(serialise(before), serialise(request()))
        self.assertFalse(
            retrieve(
                self.root,
                question='What supports release engineering?',
                mode='hybrid',
                policy=self.policy,
                scope=AccessScope(),
            )['assertions']
        )

    def test_question_only_support_priority_precedes_candidate_cap(self):
        aid = 'urn:assertion:requested-support'
        self.claim(
            aid,
            'urn:project:falcon',
            'supports',
            'urn:criterion:release-engineering',
            'A release engineering exercise was reported.',
        )
        self.claim(
            'urn:assertion:incidental-use',
            'urn:project:falcon',
            'used',
            'urn:tool:release-engineering',
            'Falcon support skills demonstrate release engineering research tools.',
        )
        self.save()
        result = retrieve(
            self.root,
            question='What supports Falcon release engineering skills?',
            mode='hybrid',
            policy=self.policy,
            limits=Limits(max_candidates=1),
        )
        self.assertEqual(set(result['assertions']), {aid})
        self.assertLessEqual(result['usage']['candidates'], 1)

    def test_question_only_requires_every_citation_and_keeps_complete_packages(self):
        from knot.access import AccessScope

        aid, quote = 'urn:assertion:qualified-release', 'Falcon release engineering was reported.'
        self.claim(
            aid, 'urn:project:falcon', 'supports', 'urn:criterion:release-engineering', quote
        )
        qualification = 'However, this report is not independently verified.'
        revision = self.source('qualification.md', qualification)
        self.dataset.add(aid, DERIVED, aid + ':qualification')
        self.dataset.add(aid + ':qualification', VOCAB + 'revision', revision)
        self.dataset.add(aid + ':qualification', VOCAB + 'quote', qualification, literal=True)
        self.save()
        sha = digest((quote + '\n').encode())
        partial = AccessScope(revisions=(('urn:revision:' + sha, sha),))
        question = 'What supports release engineering?'
        denied = retrieve(
            self.root, question=question, mode='hybrid', policy=self.policy, scope=partial
        )
        self.assertNotIn(aid, denied['assertions'])
        self.assertNotIn(qualification, serialise(denied))
        for budget in (2000, 6000, 12000):
            result = retrieve(
                self.root, question=question, mode='hybrid', policy=Policy(max_chars=budget)
            )
            self.assertLessEqual(len(serialise(result)), budget)
            if aid in result['assertions']:
                self.assertEqual(len(result['assertions'][aid]['sources']), 2)
                self.assertIn(qualification, ' '.join(result['passages'].values()))
        (self.root / 'sources/qualification.md').write_text('Changed bytes.')
        corrupt = retrieve(self.root, question=question, mode='hybrid', policy=self.policy)
        self.assertNotIn(aid, corrupt['assertions'])
        self.assertGreater(corrupt['omissions']['invalid_citations'], 0)

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
