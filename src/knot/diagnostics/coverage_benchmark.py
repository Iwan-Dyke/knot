"""Compare retrieval and deterministic coverage using a frozen, owner-local question set."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from time import perf_counter

from knot.diagnostics.benchmark import _assess, _distribution, _validate_labels
from knot.evaluation import CoverageRequest, answer_question, evaluate
from knot.evaluation.snapshot import Snapshot, canonical_hash
from knot.interfaces.access import AccessScope
from knot.retrieval_engine.context import _prepare
from knot.retrieval_engine.evidence import _Evidence
from knot.retrieval_engine.policy import Policy
from knot.retrieval_engine.service import retrieve
from knot.shared.datasets import cli_data_root

OUTCOMES = {'support_found', 'no_qualifying_support', 'unknown'}


def _validate(root, manifest):
    if (
        manifest.get('version') != 1
        or not isinstance(manifest.get('label_author'), str)
        or not manifest['label_author'].strip()
        or type(manifest.get('independently_reviewed')) is not bool
        or not isinstance(manifest.get('selection'), str)
        or not manifest['selection'].strip()
        or not isinstance(manifest.get('questions'), list)
        or not 1 <= len(manifest['questions']) <= 50
    ):
        raise ValueError(
            'Supply version 1, label authorship, review state, selection and 1–50 cases'
        )
    for question in manifest['questions']:
        if not question['id'] or not question['category']:
            raise ValueError('Each case needs an id and category')
        expected = question['expected']
        status = expected['question_status']
        if status not in {'evaluated', 'needs_selection', 'unsupported_question'}:
            raise ValueError('Invalid expected question status')
        if not expected['rationale'].strip():
            raise ValueError('Explain the expected result independently of the benchmark output')
        if expected['request'] is None:
            if status == 'evaluated' or expected['outcomes'] is not None:
                raise ValueError('An evaluated question needs an expected request and outcomes')
        else:
            request = CoverageRequest.from_dict(expected['request'])
            outcomes = expected['outcomes']
            if (
                not isinstance(outcomes, list)
                or len(outcomes) != len(request.criteria)
                or any(outcome not in OUTCOMES for outcome in outcomes)
            ):
                raise ValueError('Supply an expected outcome for each selected criterion')
    _validate_labels(root, manifest)


def _evidence_package(root, store, receipt):
    # Reuse the retrieval benchmark's independent source/locator checks for both routes.
    package = {'passages': {}, 'sources': {}}
    reader = _Evidence(root, store)
    for assertion in receipt.get('assertions', {}).values():
        sources = list(assertion['sources'])
        for span in assertion.get('evidence_account_sources', []):
            text, source = reader.revision(span['revision'])
            if (
                span['sha256'] != source['sha256']
                or span['text_sha256'] != source['text_sha256']
                or text[span['start'] : span['end']] != span['quote']
            ):
                raise ValueError('Invalid evidence-account citation')
            sources.append(
                {
                    **source,
                    'quote': span['quote'],
                    'locator': {'characterOffset': str(span['start'])},
                }
            )
        for source in sources:
            key = str(len(package['sources']))
            package['passages'][key] = source['quote']
            package['sources'][key] = {**source, 'passage': key}
    return package


def _score(root, store, question, method, result, max_chars):
    size = len(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(',', ':')))
    receipt = result.get('evaluation', {}) if method == 'checked_question' else result
    status = (
        'evidence_only'
        if method == 'hybrid'
        else result['status']
        if method == 'checked_question'
        else 'evaluated'
    )
    fits = size <= max_chars
    evidence = result if method == 'hybrid' else _evidence_package(root, store, receipt)
    if not fits:
        evidence = {'sources': {}, 'passages': {}}
        status = 'output_budget'
    metrics = _assess(root, store, evidence, question)
    outcomes = [row['outcome'] for row in receipt.get('criteria', [])] if fits else []
    expected = question['expected']
    interpretation = outcome_match = contract = None
    if fits and method != 'hybrid':
        contract = status == (
            expected['question_status'] if method == 'checked_question' else 'evaluated'
        )
        if status == 'evaluated':
            wanted = expected['request']
            interpretation = (
                wanted is not None
                and receipt['request'] == CoverageRequest.from_dict(wanted).to_dict()
            )
            outcome_match = interpretation and outcomes == expected['outcomes']
            contract = contract and interpretation and outcome_match
    return {
        **metrics,
        'status': status,
        'outcomes': outcomes if method != 'hybrid' else None,
        'interpretation_match': interpretation,
        'outcomes_match': outcome_match,
        'contract_match': contract,
        'conclusive_answer': status == 'evaluated' and bool(outcomes) and 'unknown' not in outcomes,
        'characters': size,
        'within_budget': fits,
        'omissions': result.get('omissions'),
        'reasons': receipt.get('reasons', []),
    }


def _summarise(cases):
    summary = {}
    for name in ('hybrid', 'checked_question', 'structured_request'):
        rows = [case['methods'][name] for case in cases if name in case['methods']]
        relevant = sum(len(row['relevant_retrieved']) + len(row['relevant_missed']) for row in rows)
        hits = sum(len(row['relevant_retrieved']) for row in rows)
        summary[name] = {
            'cases': len(rows),
            'conclusive_answers': sum(row['conclusive_answer'] for row in rows),
            'correct_conclusive_answers': sum(
                row['conclusive_answer'] and row['contract_match'] is True for row in rows
            ),
            'contract_checks': sum(row['contract_match'] is not None for row in rows),
            'contract_failures': sum(row['contract_match'] is False for row in rows),
            'interpretation_checks': sum(row['interpretation_match'] is not None for row in rows),
            'interpretation_failures': sum(row['interpretation_match'] is False for row in rows),
            'unknown_answers': sum(
                row['status'] == 'evaluated' and 'unknown' in row['outcomes'] for row in rows
            ),
            'unsupported_questions': sum(row['status'] == 'unsupported_question' for row in rows),
            'unresolved_questions': sum(row['status'] == 'needs_selection' for row in rows),
            'over_budget': sum(not row['within_budget'] for row in rows),
            'relevant_spans': relevant,
            'relevant_retrieved': hits,
            'labelled_recall': hits / relevant if relevant else None,
            'citations_verified': sum(row['citation_integrity']['checked'] for row in rows),
            'repeat_identical': (
                all(row['repeat_identical'] for row in rows)
                if rows and all(row['repeat_identical'] is not None for row in rows)
                else None
            ),
        }
    return summary


def compare(root, manifest, *, runs=2, max_chars=24000, include_context=False):
    """Owner-only diagnostics; expected outcomes are supplied, never inferred from results."""
    if type(runs) is not int or not 1 <= runs <= 5:
        raise ValueError('runs must be between 1 and 5')
    if type(max_chars) is not int or not 2048 <= max_chars <= 131072:
        raise ValueError('max_chars must be between 2048 and 131072')
    root = Path(root)
    manifest = json.loads(json.dumps(manifest))
    snapshot = Snapshot(root)
    _validate(root, manifest)
    store = _prepare(root)[0]
    policy = Policy(max_chars=max_chars)
    scope = AccessScope.all()
    cases = []
    for question in manifest['questions']:
        methods = {
            'hybrid': lambda: retrieve(
                root, question=question['question'], mode='hybrid', policy=policy, scope=scope
            ),
            'checked_question': lambda: answer_question(root, question['question'], scope=scope),
        }
        if question['expected']['request'] is not None:
            request = CoverageRequest.from_dict(question['expected']['request'])
            methods['structured_request'] = lambda: evaluate(root, request, scope=scope)
        case = {
            'id': question['id'],
            'category': question['category'],
            'question': question['question'],
            'expected': question['expected'],
            'methods': {},
        }
        for method, operation in methods.items():
            samples, hashes = [], []
            for _ in range(runs):
                started = perf_counter()
                result = operation()
                samples.append((perf_counter() - started) * 1000)
                hashes.append(canonical_hash(result))
                if hashes[-1] != hashes[0]:
                    raise ValueError(f'Non-identical repeat: {question["id"]}/{method}')
                metrics = _score(root, store, question, method, result, max_chars)
            case['methods'][method] = {
                **metrics,
                'latency': _distribution(samples),
                'response_sha256': hashes[0],
                'repeat_identical': True if runs > 1 else None,
            }
            if include_context and metrics['within_budget']:
                case['methods'][method]['context'] = result
        cases.append(case)
    _validate_labels(root, manifest)
    snapshot.verify()
    return {
        'benchmark_version': 1,
        'scope': 'Owner-local development comparison; partial source-first labels, no independent truth or general-language guarantee.',
        'manifest_sha256': canonical_hash(manifest),
        'label_author': manifest['label_author'],
        'independently_reviewed': manifest['independently_reviewed'],
        'selection': manifest['selection'],
        'curation_minutes': manifest.get('curation_minutes'),
        'independent_review_minutes': manifest.get('independent_review_minutes'),
        'runs': runs,
        'max_chars': max_chars,
        'policy': policy.__dict__,
        'budget_policy': 'Compact JSON character ceiling, excluding transport. Oversized complete receipts are unavailable, never scored as answers. This is not an MCP transport benchmark.',
        'timing_policy': 'Fresh public API calls including loading; OS cache uncontrolled. Label checks and scoring excluded. Structured requests are supplied by the label author, not translated from prose.',
        'implementation': snapshot.implementation,
        'input_files': snapshot.files,
        'cases': cases,
        'summary': _summarise(cases),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--questions', type=Path, required=True)
    parser.add_argument('--data-root', type=Path)
    parser.add_argument('--runs', type=int, default=2)
    parser.add_argument('--max-chars', type=int, default=24000)
    parser.add_argument('--include-context', action='store_true')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args(argv)
    root = cli_data_root(parser, args.data_root)
    try:
        if args.output and (
            args.output.resolve().is_relative_to(root.resolve())
            or args.output.resolve() == args.questions.resolve()
        ):
            raise ValueError('Save the report outside the dataset and question manifest')
        manifest = json.loads(args.questions.read_bytes())
        report = compare(
            root,
            manifest,
            runs=args.runs,
            max_chars=args.max_chars,
            include_context=args.include_context,
        )
        rendered = json.dumps(report, ensure_ascii=False, indent=2) + '\n'
        if args.output:
            args.output.write_text(rendered)
        else:
            print(rendered, end='')
    except (ValueError, OSError, KeyError, TypeError) as error:
        parser.exit(1, f'Benchmark failed: {error}\n')


if __name__ == '__main__':
    main()
