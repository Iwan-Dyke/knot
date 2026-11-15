import copy
import tempfile
import unittest
from pathlib import Path

from retrieval_fixture import make_fixture

from knot.curating.provenance import source_pin
from knot.diagnostics.benchmark import _assess
from knot.diagnostics.coverage_benchmark import _evidence_package
from knot.interfaces.access import AccessScope
from knot.notes import create_note
from knot.retrieval_engine.context import _prepare
from knot.retrieval_engine.evidence import _Evidence
from knot.retrieval_engine.policy import Policy
from knot.retrieval_engine.service import retrieve


class ProvenanceAccountingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        make_fixture(self.root)
        self.quote = 'The trial reduced latency, but only for the sampled inputs.'
        body = 'Δ Earlier account:\n' + self.quote + '\nLater account:\n' + self.quote + '\n'
        self.original = create_note(self.root, body, author='Original author')
        self.offset = body.rindex(self.quote)
        self.pin = source_pin(self.root, self.original['revision'], self.quote, self.offset)
        self.curated = create_note(
            self.root,
            'A limited trial reported better response times.\n',
            title='Latency trial and its scope',
            author='Synthetic curator',
            agent='Test',
            derivation={
                'method': 'synthesis',
                'qualification': 'One attributed trial, not universal.',
                'sources': [self.pin],
            },
        )
        self.store = _prepare(self.root)[0]
        self.result = retrieve(self.root, self.curated['note'], Policy(max_chars=64000))
        self.question = {
            'judgements': [
                {
                    'path': self.original['body_path'],
                    'sha256': self.original['body_sha256'],
                    'quote': self.quote,
                    'character_offset': self.offset,
                    'start_line': self.pin['start_line'],
                    'judgement': 'Relevant',
                    'qualification': True,
                }
            ]
        }

    def assess(self, result=None, question=None, store=None):
        return _assess(
            self.root,
            self.store if store is None else store,
            self.result if result is None else result,
            self.question if question is None else question,
        )

    def test_embedded_exact_original_is_counted_without_treating_curator_as_original_author(self):
        before = copy.deepcopy(self.result)
        score = self.assess()
        self.assertEqual(score['labelled_recall'], 1)
        self.assertEqual(score['qualification_recall'], 1)
        self.assertEqual(
            score['evidence_accounting']['by_representation']['curated_provenance'], [0]
        )
        self.assertEqual(score['citation_integrity']['checked'], 2)
        self.assertEqual(self.result, before)

    def test_direct_assertion_and_embedded_delivery_count_the_same_label_once(self):
        _, source = _Evidence(self.root, self.store).revision(self.original['revision'])
        for assertion in (False, True):
            result = copy.deepcopy(self.result)
            result['passages']['direct'] = self.quote
            result['sources']['direct'] = {
                **source,
                'passage': 'direct',
                'locator': {'characterOffset': str(self.offset)},
            }
            if assertion:
                result['assertions']['claim'] = {'sources': ['direct']}
            score = self.assess(result)
            self.assertEqual(score['relevant_retrieved'], [0])
            self.assertEqual(score['labelled_recall'], 1)
            channel = 'assertion_evidence' if assertion else 'source_passage'
            self.assertEqual(score['evidence_accounting']['by_representation'][channel], [0])
            self.assertEqual(score['evidence_accounting']['unique_spans'], 2)

    def test_duplicate_labels_do_not_inflate_denominators(self):
        question = copy.deepcopy(self.question)
        question['judgements'].append(copy.deepcopy(question['judgements'][0]))
        self.assertEqual(self.assess(question=question)['relevant_retrieved'], [0])

    def test_partial_quotation_does_not_cover_a_qualified_label(self):
        partial = create_note(
            self.root,
            'A trial was reported.',
            title='Trial report',
            author='Synthetic curator',
            agent='Test',
            derivation={
                'method': 'faithful_restatement',
                'qualification': 'Partial context for an accounting test.',
                'sources': [
                    source_pin(
                        self.root,
                        self.original['revision'],
                        'The trial reduced latency',
                        self.offset,
                    )
                ],
            },
        )
        result = retrieve(self.root, partial['note'], Policy(max_chars=64000))
        score = self.assess(result, store=_prepare(self.root)[0])
        self.assertEqual(score['labelled_recall'], 0)
        self.assertEqual(score['qualification_recall'], 0)

    def test_conflicting_labels_are_rejected(self):
        question = copy.deepcopy(self.question)
        question['judgements'].append({**question['judgements'][0], 'judgement': 'Irrelevant'})
        with self.assertRaisesRegex(ValueError, 'Conflicting judgements'):
            self.assess(question=question)

    def test_paraphrase_and_unserialized_ancestors_do_not_receive_original_span_credit(self):
        result = copy.deepcopy(self.result)
        for source in result['sources'].values():
            source['native_note'].pop('derivation')
        self.assertEqual(self.assess(result)['labelled_recall'], 0)
        # Even exact original words in a different note are not the original source location.
        copied = create_note(self.root, self.quote, title='Copied sentence')
        result = retrieve(self.root, copied['note'], Policy(max_chars=64000))
        self.assertEqual(self.assess(result, store=_prepare(self.root)[0])['labelled_recall'], 0)

    def test_tampered_embedded_provenance_is_rejected(self):
        for field, value in [
            ('sha256', '0' * 64),
            ('text_sha256', '0' * 64),
            ('quote', 'An unsupported claim.'),
            ('character_offset', 0),
            ('start_line', 1),
            ('revision', 'urn:revision:invented'),
        ]:
            with self.subTest(field=field):
                result = copy.deepcopy(self.result)
                next(iter(result['sources'].values()))['native_note']['derivation']['sources'][0][
                    field
                ] = value
                with self.assertRaises(ValueError):
                    self.assess(result)

    def test_alternative_valid_occurrence_cannot_be_injected_into_provenance(self):
        result = copy.deepcopy(self.result)
        pin = next(iter(result['sources'].values()))['native_note']['derivation']['sources'][0]
        pin.update(character_offset=self.original['body'].index(self.quote), start_line=2)
        with self.assertRaises(ValueError):
            self.assess(result)

    def test_paths_hashes_and_line_locators_are_verified_for_top_level_sources(self):
        for field in ('snapshot', 'text_path', 'sha256', 'text_sha256'):
            result = copy.deepcopy(self.result)
            next(iter(result['sources'].values()))[field] = 'incorrect'
            with self.assertRaises(ValueError):
                self.assess(result)
        result = copy.deepcopy(self.result)
        next(iter(result['sources'].values()))['locator']['startLine'] = '99'
        with self.assertRaises(ValueError):
            self.assess(result)

    def test_missing_source_grant_prevents_curated_evidence_delivery(self):
        scope = AccessScope(revisions=((self.curated['revision'], self.curated['body_sha256']),))
        with self.assertRaisesRegex(ValueError, 'active canonical IRI'):
            retrieve(self.root, self.curated['note'], Policy(max_chars=64000), scope=scope)
        with self.assertRaises(ValueError):
            self.assess(store=_prepare(self.root, scope=scope)[0])

    def test_transitive_verification_does_not_credit_unreturned_original_quotation(self):
        nested = create_note(
            self.root,
            'A second interpretation.',
            title='Interpretation of a trial summary',
            author='Synthetic curator',
            agent='Test',
            derivation={
                'method': 'faithful_restatement',
                'qualification': 'A derivative account.',
                'sources': [
                    source_pin(self.root, self.curated['revision'], self.curated['body'], 0)
                ],
            },
        )
        result = retrieve(self.root, nested['note'], Policy(max_chars=64000))
        self.assertEqual(self.assess(result, store=_prepare(self.root)[0])['labelled_recall'], 0)

    def test_receipt_normalisation_cannot_invent_undelivered_derivation(self):
        receipt = {
            'assertions': {
                'claim': {
                    'sources': [],
                    'evidence_account_sources': [
                        {
                            'revision': self.curated['revision'],
                            'sha256': self.curated['body_sha256'],
                            'text_sha256': self.curated['body_sha256'],
                            'quote': self.curated['body'],
                            'start': 0,
                            'end': len(self.curated['body']),
                        }
                    ],
                }
            },
        }
        package = _evidence_package(self.root, self.store, receipt)
        self.assertEqual(self.assess(package)['labelled_recall'], 0)
        source = copy.deepcopy(next(iter(self.result['sources'].values())))
        source['quote'] = self.result['passages'][source['passage']]
        package = _evidence_package(self.root, self.store, {'sources': [source]})
        self.assertEqual(self.assess(package)['labelled_recall'], 1)
