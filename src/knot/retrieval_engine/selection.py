"""Bounded selection of already verified, complete evidence packages."""

import copy
import hashlib
import heapq
import math
import re

from knot.retrieval_engine.response import _coalesce, _measure, _quotation, _resize, serialise

QUALIFICATION = re.compile(
    r'\b(?:caveat|however|not yet|not independently|does not|uncertain|unverified|'
    r'outstanding|pending|planned|proposed|rejected|superseded|correlation)\b',
    re.I,
)


def merge(base, packages):
    # Records are read-only during selection. Copy the containers and the source
    # records that coalescing rewrites; detach the public result once at the end.
    result = dict(base)
    for key in ('entities', 'assertions', 'identities', 'source_context', 'passages', 'usage'):
        result[key] = dict(base[key])
    result['sources'] = {eid: dict(source) for eid, source in base['sources'].items()}
    result['paths'] = list(base['paths'])
    result['matches'] = list(base['matches'])
    result['omissions'] = {**base['omissions'], 'limits': dict(base['omissions']['limits'])}
    if 'selection' in base:
        result['selection'] = dict(base['selection'])
    for package in packages:
        envelope = package['envelope']
        for key in ('entities', 'assertions', 'identities', 'source_context'):
            result[key].update(envelope[key])
        for eid, source in envelope['sources'].items():
            if eid in result['sources']:
                continue
            quote = _quotation(envelope, source)
            pid = next((pid for pid, value in result['passages'].items() if value == quote), None)
            if pid is None:
                pid = 'p' + str(len(result['passages']) + 1)
                result['passages'][pid] = quote
            result['sources'][eid] = {**source, 'passage': pid}
            result['sources'][eid].pop('passage_span', None)
        for match in envelope['matches']:
            match = dict(match)
            if match['channel'] == 'graph':
                path = envelope['paths'][match['path']]
                if path not in result['paths']:
                    result['paths'].append(path)
                match['path'] = result['paths'].index(path)
            if match not in result['matches']:
                result['matches'].append(match)
    _coalesce(result)
    result['usage']['assertions'] = len(result['assertions'])
    result['usage']['passages'] = len(result['passages'])
    return result


def _features(package, weights):
    envelope, relevance = package['envelope'], package['relevance']
    shingles, heap, qualifications = set(), [], set()
    for text in envelope['passages'].values():
        words = re.findall(r'\w+', text.casefold())
        if not words:
            continue
        for i in range(max(1, len(words) - 4)):
            fingerprint = int.from_bytes(
                hashlib.blake2b(' '.join(words[i : i + 5]).encode(), digest_size=8).digest(), 'big'
            )
            if fingerprint in shingles:
                continue
            if len(shingles) < 512:
                shingles.add(fingerprint)
                heapq.heappush(heap, -fingerprint)
            elif fingerprint < -heap[0]:
                shingles.remove(-heapq.heapreplace(heap, -fingerprint))
                shingles.add(fingerprint)
        for match in QUALIFICATION.finditer(text):
            qualifications.add(text[max(0, match.start() - 40) : match.end() + 80].casefold())
            if len(qualifications) >= 64:
                break
    shingles = sorted(shingles)
    # Bottom-k fingerprints are stable under small edits, with bounded retained
    # memory. They score duplication only; quotations are never sampled or clipped.
    features = {('text', value): relevance / max(1, len(shingles)) for value in shingles}
    total = math.fsum(weights[term] for term in sorted(weights)) or 1
    features.update(
        {
            ('term', term): 1.5 * relevance * weights.get(term, 1) / total
            for term in package['terms']
        }
    )
    features.update(
        {
            ('qualification', value): 0.3 * relevance / len(qualifications)
            for value in sorted(qualifications)
        }
    )
    for assertion in envelope['assertions'].values():
        if assertion.get('role') == 'substantive':
            features[
                (
                    'claim',
                    assertion['subject'],
                    assertion['predicate'],
                    assertion['object'],
                    bool(assertion.get('object_literal')),
                    assertion.get('object_datatype') or '',
                    assertion.get('object_language') or '',
                )
            ] = 0.15 * relevance
    return dict(sorted(features.items()))


def _failure(result, policy, *, characters=None):
    if len(result['assertions']) > policy.max_assertions:
        return 'assertions'
    if len(result['passages']) > policy.max_passages:
        return 'passages'
    if (characters if characters is not None else _measure(result)) > policy.max_chars:
        return 'characters'
    return None


def _cost(current, candidate, policy, rule):
    costs = (
        (candidate['usage']['characters'] - current['usage']['characters']) / policy.max_chars,
        (len(candidate['passages']) - len(current['passages'])) / policy.max_passages,
        (len(candidate['assertions']) - len(current['assertions'])) / policy.max_assertions,
    )
    # Charge the limiting resource; a passage need not pay twice when its text fits.
    return max(1 / policy.max_chars, sum(costs) if rule == 'sum_density' else max(costs))


def _select(base, packages, policy, weights, *, strategy='density'):
    if strategy not in ('rank', 'value', 'sum_density', 'density', 'best', 'relevance_first'):
        raise ValueError('Unknown evidence selection strategy')
    base = copy.deepcopy(base)
    steps = min(len(packages), policy.max_assertions + policy.max_passages)
    trial_limit = max(1, len(packages) * (2 * steps + 4))
    base['selection'] = {
        'method': 'marginal-packages-v1',
        'strategy': strategy,
        'packages': len(packages),
        'trial_limit': trial_limit,
        'trials': trial_limit,
        'selected_packages': len(packages),
        'redundant_packages': len(packages),
    }
    if not packages:
        base['selection'].update(trials=0, selected_packages=0, redundant_packages=0)
        if _measure(base) > policy.max_chars:
            raise ValueError('Budget too small for a valid selection envelope')
        return base
    initial_limits = dict(base['omissions']['limits'])
    for name in ('characters', 'assertions', 'passages'):
        base['omissions']['limits'][name] = initial_limits.get(name, 0) + len(packages)
    if _measure(base) > policy.max_chars:
        raise ValueError('Budget too small for a valid selection envelope')
    features = [_features(package, weights) for package in packages]
    trials = 0

    def coverage(indices):
        covered = {}
        for index in indices:
            for feature, weight in features[index].items():
                covered[feature] = max(covered.get(feature, 0), weight)
        return covered

    def gain(index, covered):
        return round(
            math.fsum(
                max(0, weight - covered.get(feature, 0))
                for feature, weight in features[index].items()
            ),
            12,
        )

    def trial(result, index):
        nonlocal trials
        if trials >= trial_limit:
            return None
        trials += 1
        result = merge(result, [packages[index]])
        return result if _failure(result, policy) is None else None

    singletons = [trial(base, i) for i in range(len(packages))]

    def greedy(rule):
        indices, result, covered = [], merge(base, []), {}
        # Shared containing context can make an initially unfit package feasible.
        pending = list(range(len(packages)))
        for _ in range(steps):
            best = None
            if not indices:
                _measure(result)
            for index in pending:
                additional = gain(index, covered)
                if additional <= 0:
                    continue
                candidate = singletons[index] if not indices else trial(result, index)
                if candidate is None:
                    continue
                score = (
                    -index
                    if rule == 'rank' or (rule == 'relevance_first' and not indices)
                    else additional / _cost(result, candidate, policy, rule)
                    if rule in ('density', 'sum_density', 'relevance_first')
                    else additional
                )
                key = (score, additional, -index)
                if best is None or key > best[0]:
                    best = (key, index, candidate)
            if best is None:
                break
            _, index, result = best
            indices.append(index)
            pending.remove(index)
            for feature, weight in features[index].items():
                covered[feature] = max(covered.get(feature, 0), weight)
        return indices, result

    alternatives = [
        greedy(rule) for rule in (('value', 'density') if strategy == 'best' else (strategy,))
    ]
    # Relevance-first keeps its strongest fitting package. Comparing it against
    # unrelated singleton alternatives could silently discard that primary context.
    if strategy in ('best', 'density', 'sum_density'):
        alternatives.extend(
            ([index], result) for index, result in enumerate(singletons) if result is not None
        )
    indices, _ = max(
        alternatives,
        key=lambda choice: (
            round(math.fsum(coverage(choice[0]).values()), 12),
            -_measure(choice[1]),
            tuple(-i for i in choice[0]),
        ),
    )

    def finish(indices):
        nonlocal trials
        result = merge(base, [packages[i] for i in indices])
        result['omissions']['limits'] = dict(initial_limits)
        covered = coverage(indices)
        remaining = [i for i in range(len(packages)) if i not in indices]
        trials += len(remaining)
        result['selection'].update(
            selected_packages=len(indices),
            trials=trials,
            redundant_packages=sum(gain(i, covered) <= 0 for i in remaining),
        )
        candidates = [merge(result, [packages[i]]) for i in remaining]
        for candidate in candidates:
            _measure(candidate)
        omission_size = len(serialise(result['omissions']))
        # Counts only grow as omission metadata makes the envelope larger.
        for _ in range(len(packages) + 2):
            updated_size = len(serialise(result['omissions']))
            delta = updated_size - omission_size
            limits = dict(initial_limits)
            for candidate in candidates:
                candidate['omissions'] = result['omissions']
                usage = candidate['usage']
                # Only counts/booleans changed: their JSON is entirely ASCII.
                characters = _resize(
                    candidate, (usage['characters'] + delta, usage['utf8_bytes'] + delta)
                )
                reason = _failure(candidate, policy, characters=characters)
                if reason:
                    limits[reason] = limits.get(reason, 0) + 1
            if limits == result['omissions']['limits']:
                break
            result['omissions']['limits'] = limits
            result['omissions']['further_unknown'] = True
            omission_size = updated_size
        else:
            raise ValueError('Could not account for final omission metadata')
        _measure(result)
        return result, dict(zip(remaining, candidates))

    # Preserve the existing combination. Relaxing every intermediate cost changed
    # choices and lost development evidence. Instead use the actual diagnostics to
    # try one additional complete package in the small released metadata space.
    result, candidates = finish(indices)
    if len(indices) < steps:
        covered = coverage(indices)
        repairs = []
        for index, candidate in candidates.items():
            additional = gain(index, covered)
            if additional <= 0 or _failure(
                candidate, policy, characters=candidate['usage']['characters']
            ):
                continue
            repairs.append(
                (additional / _cost(result, candidate, policy, strategy), additional, -index, index)
            )
        if repairs:
            repaired, _ = finish([*indices, max(repairs)[-1]])
            if _failure(repaired, policy) is None:
                result = repaired
            else:
                result, _ = finish(indices)
    if _failure(result, policy):
        raise ValueError('Budget too small for final selection envelope')
    return copy.deepcopy(result)
