"""Observe candidate retention and packing with synthetic source judgements."""

import hashlib
from pathlib import Path
from time import perf_counter

import knot.benchmark as benchmark
import knot.search as search
from knot.rdf import DERIVED, values
from knot.retrieval import Policy, _Evidence


def covered(store, candidate, reader, cache, labels):
    if candidate['channel'] == 'text':
        sources = [(candidate['quote'], candidate['citation'])]
    else:
        sources = []
        for step in candidate['path']:
            aid = step['assertion']
            if aid not in cache:
                cache[aid] = [reader.citation(e.value) for e in values(store, aid, DERIVED)]
            sources.extend(cache[aid])
    hits = set()
    for quote, source in sources:
        offset = source.get('locator', {}).get('characterOffset')
        if offset is None:
            text, _ = reader.revision(source['revision'])
            offset = text.index(quote) if text.count(quote) == 1 else None
        if offset is None:
            continue
        offset = int(offset)
        for i, label in enumerate(labels):
            if (
                source['text_path'] == label['path']
                and source['text_sha256'] == label['sha256']
                and offset <= label['character_offset']
                and label['character_offset'] + len(label['quote']) <= offset + len(quote)
            ):
                hits.add(i)
    return hits


def evaluate(root, manifest, *, runs=3, max_chars=12000):
    root = Path(root)
    original_keep, original_retrieve = search._keep, benchmark._retrieve_ranked
    diagnostics = {}
    timings = {}
    observed = []

    def observe(candidates, candidate, cap, result):
        observed.append((candidate, candidates))
        return original_keep(candidates, candidate, cap, result)

    def retrieve(root, seed, question, policy, mode, limits, prepared):
        observed.clear()
        started = perf_counter()
        result = original_retrieve(root, seed, question, policy, mode, limits, prepared)
        timings.setdefault((question, mode), []).append((perf_counter() - started) * 1000)
        store = prepared[0]
        reader, cache = _Evidence(root, store), {}
        labels = next(q['judgements'] for q in manifest['questions'] if q['question'] == question)
        channels = {}
        for channel in ('graph', 'text'):
            candidates = [(c, retained) for c, retained in observed if c['channel'] == channel]
            ranked = sorted((c for c, _ in candidates), key=search._candidate_order)
            rank = {id(c): i + 1 for i, c in enumerate(ranked)}
            positions = [{'generated': [], 'ranked': [], 'retained': []} for _ in labels]
            for index, (candidate, retained) in enumerate(candidates, 1):
                hits = covered(store, candidate, reader, cache, labels)
                retained_ids = {id(c): i + 1 for i, c in enumerate(retained)}
                for label in hits:
                    positions[label]['generated'].append(index)
                    positions[label]['ranked'].append(rank[id(candidate)])
                    if id(candidate) in retained_ids:
                        positions[label]['retained'].append(retained_ids[id(candidate)])
            channels[channel] = {'generated_candidates': len(candidates), 'labels': positions}
        diagnostics[(question, mode)] = channels
        return result

    search._keep, benchmark._retrieve_ranked = observe, retrieve
    try:
        report = benchmark.evaluate(root, manifest, runs=runs, policy=Policy(max_chars=max_chars))
    finally:
        search._keep, benchmark._retrieve_ranked = original_keep, original_retrieve
    for case in report['cases']:
        for mode, method in case['methods'].items():
            method['context_utilisation'] = method['characters'] / max_chars
            method['qualifications_missed'] = [
                i
                for i in method['relevant_missed']
                if next(q for q in manifest['questions'] if q['id'] == case['id'])['judgements'][
                    i
                ].get('qualification')
            ]
            if mode != 'legacy_graph':
                method['candidate_positions'] = diagnostics[(case['question'], mode)]
                method['latency_with_diagnostics'] = method['latency']
                method['latency'] = benchmark._distribution(timings[(case['question'], mode)])
                retained = {
                    i
                    for channel in method['candidate_positions'].values()
                    for i, positions in enumerate(channel['labels'])
                    if positions['retained']
                }
                method['retained_relevant_omitted'] = sorted(
                    retained.intersection(method['relevant_missed'])
                )
    report['diagnostic_policy'] = (
        'One-based generation order, score rank before retention, and retained rank per channel. '
        'Empty means absent within the bounded scan. Positions include routing quotations; '
        'they are diagnostics, not independent relevance judgements. Legacy has no ranked candidates. '
        'Latency excludes diagnostic source-span assessment; cheap candidate capture is included. '
        'retained_relevant_omitted identifies retained labels lost during bounded packing, '
        'not the number of all relevant passages in the corpus.'
    )
    report['source_files_sha256'] = {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted((root / 'sources').rglob('*'))
        if path.is_file()
    }
    report['runner_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    return report
