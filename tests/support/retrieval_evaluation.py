"""Compare bounded retrieval mechanics on a frozen synthetic corpus."""

import argparse
import importlib.metadata
import json
import math
import platform
import re
import statistics
import tempfile
from dataclasses import replace
from pathlib import Path
from time import perf_counter

from retrieval_fixture import QUESTIONS, make_fixture

from knot.inventory import digest
from knot.rdf import DERIVED, values
from knot.retrieval import Policy, _Evidence, _measure, _prepare, _retrieve, serialise

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]


def distribution(samples):
    ordered = sorted(samples)
    return {
        'min_ms': min(samples),
        'median_ms': statistics.median(samples),
        'p95_ms': ordered[math.ceil(len(samples) * 0.95) - 1],
        'max_ms': max(samples),
    }


def lexical_index(root, records, store):
    # Document search sees wording outside the graph's selected quotation.
    evidence = _Evidence(root, store)
    documents = {}
    for record in records:
        if record['framework']:
            continue
        for eid in sorted(v.value for v in values(store, record['id'], DERIVED)):
            _, citation = evidence.citation(eid)
            path = citation['text_path']
            raw = evidence.read(path, citation['text_sha256'])
            documents[path] = {'sha256': digest(raw), 'text': raw.decode('utf-8-sig')}
    return documents


def ranked_documents(documents, query):
    tokens = set(re.findall(r'\w+', query.casefold()))
    ranked = []
    for path, document in documents.items():
        words = set(re.findall(r'\w+', document['text'].casefold()))
        score = len(tokens & words)
        if score:
            ranked.append((-score, path))
    return [path for _, path in sorted(ranked)]


def lexical(documents, query, policy, graph=None):
    result = {
        'method': 'hybrid' if graph is not None else 'full_text',
        'query': query,
        'budget': {'max_chars': policy.max_chars, 'max_passages': policy.max_passages},
        'documents': {},
        'omissions': 0,
        'usage': {'characters': 0, 'utf8_bytes': 0, 'passages': 0},
    }
    if graph is not None:
        result['graph'] = graph
        result['usage']['passages'] = len(graph['passages'])
    for path in ranked_documents(documents, query):
        result['documents'][path] = documents[path]
        result['usage']['passages'] += 1
        if result['usage']['passages'] > policy.max_passages or _measure(result) > policy.max_chars:
            result['documents'].pop(path)
            result['usage']['passages'] -= 1
            result['omissions'] += 1
    # The omission count itself consumes budget.
    while _measure(result) > policy.max_chars and result['documents']:
        result['documents'].pop(next(reversed(result['documents'])))
        result['usage']['passages'] -= 1
        result['omissions'] += 1
    if _measure(result) > policy.max_chars:
        raise ValueError('Evaluation envelope cannot fit this budget')
    return result


def assess(package, records, question):
    graph = package.get('graph', package if 'assertions' in package else None)
    selected = (
        {aid for aid, record in graph['assertions'].items() if record['role'] != 'association'}
        if graph
        else set()
    )
    texts = [d['text'] for d in package.get('documents', {}).values()]
    for record in records:
        if record['predicate'].endswith(':relatedTo') or record['framework']:
            continue
        if any(e['quote'] in text for e in record['evidence'] for text in texts):
            selected.add(record['id'])
    relevant = set(question['relevant'])
    citations = len(graph['sources']) if graph else 0
    citations += len(texts)
    return {
        'retrieved_relevant': sorted(selected & relevant),
        'missed_relevant': sorted(relevant - selected),
        'irrelevant_evidence': sorted(selected - relevant),
        'recall': len(selected & relevant) / len(relevant) if relevant else None,
        'citation_integrity': {'checked': citations, 'valid': citations},
        'unsupported_conclusions': None,
        'human_support_review': 'Pending; integrity and relevance are not a semantic-support assessment.',
    }


def evaluate(runs=5, *, include_context=False):
    if runs < 1:
        raise ValueError('runs must be positive')
    policy = Policy()
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        make_fixture(root)
        started = perf_counter()
        prepared = _prepare(root)
        graph_loading_ms = (perf_counter() - started) * 1000
        records = prepared[2]
        started = perf_counter()
        documents = lexical_index(root, records, prepared[0])
        lexical_loading_ms = (perf_counter() - started) * 1000
        corpus = {name: item['sha256'] for name, item in documents.items()}
        cases = []
        for question in QUESTIONS:
            methods = {
                'graph': lambda: _retrieve(root, question['seed'], policy, *prepared),
                'full_text': lambda: lexical(documents, question['query'], policy),
                # Fixed allocation, not tuned per question: graph first gets 75%.
                'hybrid': lambda: lexical(
                    documents,
                    question['query'],
                    policy,
                    _retrieve(
                        root,
                        question['seed'],
                        replace(policy, max_chars=policy.max_chars * 3 // 4),
                        *prepared,
                    ),
                ),
            }
            case = {'question': question, 'methods': {}}
            for name, operation in methods.items():
                samples = []
                for _ in range(runs):
                    started = perf_counter()
                    package = operation()
                    samples.append((perf_counter() - started) * 1000)
                encoded = serialise(package)
                if (
                    len(encoded) > policy.max_chars
                    or package['usage']['passages'] > policy.max_passages
                ):
                    raise AssertionError('A retrieval method exceeded the shared output budget')
                case['methods'][name] = {
                    **assess(package, records, question),
                    'latency': distribution(samples),
                    'characters': len(encoded),
                    'utf8_bytes': len(encoded.encode()),
                    'omissions': package['omissions'],
                }
                if include_context:
                    case['methods'][name]['context'] = package
            cases.append(case)
        return {
            'scope': 'Synthetic mechanics only; no real-note superiority claim.',
            'python': platform.python_version(),
            'pyoxigraph': importlib.metadata.version('pyoxigraph'),
            'runs': runs,
            'max_chars': policy.max_chars,
            'max_passages': policy.max_passages,
            'loading': {'graph_ms': graph_loading_ms, 'full_text_ms': lexical_loading_ms},
            'timing_policy': 'One in-memory dataset snapshot; OS file cache uncontrolled. Policy adjacency and source integrity checks run per graph request. Loading and label/classification preparation excluded from repeated latency.',
            'corpus_sha256': corpus,
            'implementation_sha256': {
                str(path.relative_to(PROJECT)): digest(path.read_bytes())
                for path in [
                    Path(__file__),
                    PROJECT / 'tests/retrieval_fixture.py',
                    *sorted((PROJECT / 'src/knot').rglob('*.py')),
                ]
            },
            'review_effort': {
                'questions': len(QUESTIONS),
                'independently_labelled': False,
                'curation_minutes': None,
                'review_minutes': None,
                'limitation': 'Assistant-authored source-first fixture and labels; curation time was not timed. Human support review and held-out notes remain pending.',
            },
            'cases': cases,
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runs', type=int, default=5)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--include-context', action='store_true')
    args = parser.parse_args()
    try:
        report = (
            json.dumps(
                evaluate(args.runs, include_context=args.include_context),
                ensure_ascii=False,
                indent=2,
            )
            + '\n'
        )
        if args.output:
            args.output.write_text(report)
        else:
            print(report, end='')
    except (ValueError, OSError) as error:
        parser.exit(1, f'{error}\n')


if __name__ == '__main__':
    main()
