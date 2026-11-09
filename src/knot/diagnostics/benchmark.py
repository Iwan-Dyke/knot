"""Compare retrieval modes against revision-specific source judgements."""

import argparse
import importlib.metadata
import json
import math
import platform
import statistics
from pathlib import Path
from time import perf_counter

from knot.retrieval_engine.context import _prepare
from knot.retrieval_engine.evidence import _Evidence
from knot.retrieval_engine.graph import _retrieve
from knot.retrieval_engine.policy import Policy
from knot.retrieval_engine.response import _quotation, serialise
from knot.retrieval_engine.search import Limits, _retrieve_ranked
from knot.shared.datasets import cli_data_root
from knot.shared.storage import digest


def _distribution(samples):
    ordered = sorted(samples)
    return {
        'min_ms': min(samples),
        'median_ms': statistics.median(samples),
        'p95_ms': ordered[math.ceil(len(samples) * 0.95) - 1],
        'max_ms': max(samples),
    }


def _validate_labels(root, manifest):
    # Validate labels directly against source bytes, independently of graph paths.
    reader = _Evidence(root, None)
    ids = [q['id'] for q in manifest['questions']]
    if len(ids) != len(set(ids)) or not ids:
        raise ValueError('Question identifiers must be nonempty and unique')
    for question in manifest['questions']:
        if not question['question'].strip():
            raise ValueError('Question text cannot be empty')
        for label in question['judgements']:
            text = reader.read(label['path'], label['sha256']).decode('utf-8-sig')
            start = label['character_offset']
            if (
                label['judgement'] not in ('Relevant', 'Irrelevant')
                or not label['quote']
                or start < 0
                or text[start : start + len(label['quote'])] != label['quote']
                or text[:start].count('\n') + 1 != label['start_line']
            ):
                raise ValueError(f'Invalid source judgement: {question["id"]}')


def _assess(root, store, result, question):
    reader = _Evidence(root, store)
    covered, judged_passages = set(), set()
    for source in result['sources'].values():
        text, recorded = reader.revision(source['revision'])
        quote = _quotation(result, source)
        if (
            any(
                recorded[key] != source[key]
                for key in ('sha256', 'text_sha256', 'text_path', 'snapshot')
            )
            or quote not in text
        ):
            raise ValueError('Returned citation failed the benchmark integrity check')
        offset = source.get('locator', {}).get('characterOffset')
        offset = (
            int(offset)
            if offset is not None
            else text.index(quote)
            if text.count(quote) == 1
            else None
        )
        if offset is not None and (offset < 0 or text[offset : offset + len(quote)] != quote):
            raise ValueError('Returned citation has an invalid character locator')
        for index, label in enumerate(question['judgements']):
            start = label['character_offset']
            if (
                label['path'] == source['text_path']
                and label['sha256'] == source['text_sha256']
                and offset is not None
                and offset <= start
                and start + len(label['quote']) <= offset + len(quote)
            ):
                covered.add(index)
                judged_passages.add(source['passage'])
    relevant = {i for i, j in enumerate(question['judgements']) if j['judgement'] == 'Relevant'}
    irrelevant = set(range(len(question['judgements']))) - relevant
    qualified = {i for i in relevant if question['judgements'][i].get('qualification')}
    hits, wrong = covered & relevant, covered & irrelevant
    return {
        'relevant_retrieved': sorted(hits),
        'relevant_missed': sorted(relevant - covered),
        'irrelevant_retrieved': sorted(wrong),
        'labelled_recall': len(hits) / len(relevant) if relevant else None,
        'judged_precision': len(hits) / len(hits | wrong) if hits | wrong else None,
        'qualification_recall': len(covered & qualified) / len(qualified) if qualified else None,
        'unjudged_passages': len(set(result['passages']) - judged_passages),
        'citation_integrity': {'checked': len(result['sources']), 'valid': len(result['sources'])},
        'unsupported_conclusions': None,
        'independent_support_review': 'Pending',
    }


def evaluate(root, manifest, *, runs=3, policy=None, include_context=False):
    if type(runs) is not int or runs < 1:
        raise ValueError('runs must be a positive integer')
    root, policy = Path(root), policy or Policy(max_chars=12000)
    _validate_labels(root, manifest)
    started = perf_counter()
    prepared = _prepare(root)
    preparation_ms = (perf_counter() - started) * 1000
    labels = prepared[3]
    cases = []
    for question in manifest['questions']:
        if question.get('seed') is not None:
            candidates = [question['seed']] if question['seed'] in labels else []
        else:
            candidates = [
                eid
                for eid, names in labels.items()
                if question.get('seed_label', '').casefold() in {n.casefold() for n in names}
            ]
        if len(candidates) != 1:
            raise ValueError(
                f'Choose one explicit seed for {question["id"]}; found {len(candidates)}'
            )
        seed = candidates[0]
        methods = {'legacy_graph': lambda: _retrieve(root, seed, policy, *prepared)}
        for mode in ('graph', 'text', 'hybrid'):
            methods[mode] = lambda mode=mode: _retrieve_ranked(
                root, seed, question['question'], policy, mode, Limits(), prepared
            )
        case = {'id': question['id'], 'question': question['question'], 'seed': seed, 'methods': {}}
        for method, operation in methods.items():
            samples, previous = [], None
            for _ in range(runs):
                started = perf_counter()
                result = operation()
                samples.append((perf_counter() - started) * 1000)
                wire = serialise(result)
                if previous is not None and previous != wire:
                    raise ValueError('Identical benchmark inputs produced different responses')
                previous = wire
                if (
                    len(wire) > policy.max_chars
                    or len(result['passages']) > policy.max_passages
                    or len(result['assertions']) > policy.max_assertions
                ):
                    raise ValueError('A method exceeded the shared output budget')
            metrics = _assess(root, prepared[0], result, question)
            case['methods'][method] = {
                **metrics,
                'latency': _distribution(samples),
                'characters': len(wire),
                'utf8_bytes': len(wire.encode()),
                'omissions': result['omissions'],
                'usage': result['usage'],
            }
            if include_context:
                case['methods'][method]['context'] = result
        cases.append(case)
    inputs = [
        *sorted((root / 'graph').glob('*.trig')),
        *sorted((root / 'reviews/events').glob('*.trig')),
    ]
    if (root / 'migration/conversion.json').exists():
        inputs.append(root / 'migration/conversion.json')
    return {
        'scope': 'Development comparison on partial source-first labels; not independent or held-out validation.',
        'label_author': manifest['label_author'],
        'independently_reviewed': manifest['independently_reviewed'],
        'label_manifest_sha256': digest(
            json.dumps(manifest, sort_keys=True, ensure_ascii=False).encode()
        ),
        'curation_minutes': manifest.get('curation_minutes'),
        'independent_review_minutes': manifest.get('independent_review_minutes'),
        'python': platform.python_version(),
        'pyoxigraph': importlib.metadata.version('pyoxigraph'),
        'runs': runs,
        'max_chars': policy.max_chars,
        'max_passages': policy.max_passages,
        'preparation_ms': preparation_ms,
        'timing_policy': 'RDF/review replay, classifications and labels prepared once. Ranking, source verification and candidate selection rerun per request; OS cache uncontrolled. Integrity/relevance assessment excluded from retrieval latency.',
        'input_files_sha256': {
            p.relative_to(root).as_posix(): digest(p.read_bytes()) for p in inputs
        },
        'implementation_sha256': {
            p.relative_to(Path(__file__).parents[1]).as_posix(): digest(p.read_bytes())
            for p in sorted(Path(__file__).parents[1].rglob('*.py'))
        },
        'cases': cases,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--questions',
        type=Path,
        required=True,
        help='Source-pinned question manifest for the selected dataset',
    )
    parser.add_argument('--data-root', type=Path)
    parser.add_argument('--runs', type=int, default=3)
    parser.add_argument('--max-chars', type=int, default=12000)
    parser.add_argument('--include-context', action='store_true')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    args.data_root = cli_data_root(parser, args.data_root)
    try:
        manifest = json.loads(args.questions.read_text())
        report = evaluate(
            args.data_root,
            manifest,
            runs=args.runs,
            policy=Policy(max_chars=args.max_chars),
            include_context=args.include_context,
        )
        rendered = json.dumps(report, ensure_ascii=False, indent=2) + '\n'
        if args.output:
            args.output.write_text(rendered)
        else:
            print(rendered, end='')
    except (ValueError, OSError, KeyError) as error:
        parser.exit(1, f'{error}\n')


if __name__ == '__main__':
    main()
