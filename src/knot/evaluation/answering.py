"""Deterministic routing and artifact selection for the supported question contracts."""

from __future__ import annotations

import json
import re
from pathlib import Path

from pyoxigraph import NamedNode

from knot.evaluation import explanations, questions
from knot.evaluation.access import ScopedSnapshot
from knot.evaluation.revalidation import revalidation_report
from knot.evaluation.snapshot import canonical_hash
from knot.graph.rdf import LABEL, META, VOCAB
from knot.interfaces.access import AccessScope
from knot.retrieval_engine.context import _labels
from knot.retrieval_engine.discovery_score import terms
from knot.writing.notes import _revision_hash

CONTRACT = 'checked-answer/1'
MAX_CANDIDATES = 100
MAX_WORDING_CANDIDATES = 1000
MAX_ALTERNATIVES = 5
MAX_ALTERNATIVE_CHECKS = 5
QUESTION_WORDS = {
    'we',
    'choose',
    'chosen',
    'choice',
    'decision',
    'reason',
    'rationale',
    'preferred',
    'prefer',
    'preferable',
    'option',
    'made',
    'make',
    'pick',
    'picked',
    'selected',
    'selection',
    'select',
    'explain',
    'tell',
    'use',
}


def _envelope(question, selection, *, status, route=None, request=None, steps=None, **fields):
    result = {
        'answer_contract': CONTRACT,
        'question': question,
        'explanation_revision': selection,
        'status': status,
        'route': route,
        'request': request,
        'steps': steps or [],
        **fields,
    }
    result['answer_sha256'] = canonical_hash(result)
    return result


def budget_abstention(result):
    return _envelope(
        result['question'],
        result['explanation_revision'],
        status='unknown',
        route=result['route'],
        request=result['request'],
        reasons=['output_budget'],
    )


def _track_sources(snapshot, result):
    for path, expected in result['manifest']['verified_files'].items():
        if snapshot.sources.setdefault(path, expected) != expected:
            raise ValueError('Inconsistent source pins during selection')


def _alternatives(snapshot, question, candidates):
    """Lexical navigation never supplies an interpretation or answer to the question."""
    query = terms(question) - QUESTION_WORDS
    ranked = []
    for request, title, events in candidates:
        if not events or events[-1]['action'] != 'approve':
            continue
        for wording in events[-1].get('wordings', []):
            words = terms(wording) - QUESTION_WORDS
            overlap = query & words
            if overlap and len(overlap) * 4 >= len(query):
                score = len(overlap) / len(query | words)
                ranked.append(
                    (-score, wording, request['decision'], request['revision'], request, title)
                )
    ranked.sort(key=lambda row: row[:4])
    checked, options, truncated = {}, [], False
    for index, (_, wording, decision, revision, request, title) in enumerate(ranked):
        key = (decision, revision)
        if key not in checked:
            if len(checked) >= MAX_ALTERNATIVE_CHECKS:
                truncated = True
                break
            result = explanations.answer(snapshot.root, request, scope=snapshot.scope)
            checked[key] = result
            if result['status'] == 'approved':
                _track_sources(snapshot, result)
        result = checked[key]
        if result['status'] != 'approved':
            continue
        options.append(
            {
                'question': wording,
                'explanation_revision': revision,
                'decision': decision,
                'title': title,
                'review_event_sha256': result['review']['event_sha256'],
            }
        )
        if len(options) >= MAX_ALTERNATIVES:
            truncated = index + 1 < len(ranked)
            break
    fields = {'alternatives': options, 'alternatives_truncated': truncated}
    if options:
        fields['alternatives_guidance'] = (
            'Your question remains unsupported. These are related reviewed questions, '
            'not verified paraphrases. Choose one explicitly only if its full wording '
            'matches your intended scope; do not drop conditions from the original question.'
        )
    return fields


def answer(root, question, *, explanation_revision=None, scope=None):
    """No ranked fallback, generated query, automatic review or unselected ambiguity."""
    if not isinstance(question, str) or not 1 <= len(question) <= 2000:
        raise ValueError('Supply a question of 1–2000 characters')
    if explanation_revision is not None:
        _revision_hash(explanation_revision)
    if scope is not None and not isinstance(scope, AccessScope):
        raise TypeError('Supply an AccessScope')
    match = re.fullmatch(questions.DECISION_PATTERN, question.strip(), re.I)
    if match:
        try:
            decision = json.loads(match['decision'])
        except ValueError:
            decision = None
        if decision and decision.strip():
            return _explanation(Path(root), question, decision, explanation_revision, scope)
    if questions._parse(question) is not None:
        if explanation_revision is not None:
            raise ValueError('An explanation revision cannot qualify a coverage question')
        result = questions.answer_question(root, question, scope=scope)
        status = result['status']
        if status == 'evaluated':
            status = (
                'unknown'
                if result['evaluation']['criteria'][0]['outcome'] == 'unknown'
                else 'answered'
            )
        return _envelope(
            question,
            None,
            status=status,
            route='framework_coverage',
            request=result['request'],
            result=result,
            answer=result['answer'],
            steps=[
                {'check': 'question_contract', 'result': 'framework_coverage'},
                {'check': 'coverage_execution', 'result': status},
            ],
        )
    return _explanation(Path(root), question, None, explanation_revision, scope)


def _explanation(root, question, decision, selection, scope):
    snapshot = ScopedSnapshot(root, scope if scope is not None else AccessScope.all())
    view = snapshot.view
    wording = decision is None
    route = None if wording else 'decision_explanation'
    steps = [{'check': 'question_contract', 'result': 'reviewed_wording' if wording else route}]
    histories = []

    def finish(status, **fields):
        snapshot.verify()
        for request, observed in histories:
            if explanations.history(root, request) != observed:
                raise ValueError('Explanation reviews changed during selection; retry')
        return _envelope(question, selection, status=status, route=route, steps=steps, **fields)

    if not wording:
        labels = _labels(view.store, view.records)
        # Native declarations can name a decision without a substantive assertion.
        # Only projected labels are visible; global labels are not scope grants.
        for quad in view.store.quads_for_pattern(None, NamedNode(LABEL), None, None):
            labels.setdefault(quad.subject.value, set()).add(quad.object.value)
        selected = questions._matches(decision, labels)
        steps.append(
            {
                'check': 'decision_selection',
                'result': 'unique' if len(selected) == 1 else 'needs_selection',
            }
        )
        if len(selected) != 1:
            return finish(
                'needs_selection', choices=selected[:10], choices_truncated=len(selected) > 10
            )
        decision = selected[0]
    candidates = []
    for quad in view.store.quads_for_pattern(None, NamedNode(VOCAB + 'noteMetadata'), None, META):
        native = json.loads(quad.object.value)
        revision = quad.subject.value
        if (
            native.get('derivation')
            and (wording or decision in native['entities'])
            and native['currentness'] in ('CurrentCommittedRevision', 'LatestGrantedRevision')
            and (selection is None or selection == revision)
        ):
            for target in native['entities'] if wording else [decision]:
                request = {
                    'decision': target,
                    'revision': revision,
                    'question': f'Why was decision {json.dumps(target, ensure_ascii=False)} chosen?',
                }
                candidates.append((request, native['title']))
                if len(candidates) > (MAX_WORDING_CANDIDATES if wording else MAX_CANDIDATES):
                    steps.append(
                        {'check': 'approved_artifact_selection', 'result': 'candidate_budget'}
                    )
                    return finish('unknown', reasons=['candidate_budget'])
    candidates.sort(key=lambda item: (item[0]['revision'], item[0]['decision']))
    # Capture every eligible candidate's review head before executing any. A new
    # approval during selection can introduce ambiguity just as a new note can.
    for request, _ in candidates:
        histories.append((request, explanations.history(root, request)))
    eligible = [
        (request, title, events)
        for (request, title), (_, events) in zip(candidates, histories, strict=True)
    ]
    if wording:
        candidates_for_navigation = eligible
        eligible = [
            (request, title, events)
            for request, title, events in eligible
            if events and question.strip() in events[-1].get('wordings', [])
        ]
        steps.append({'check': 'wording_selection', 'result': 'matched' if eligible else 'none'})
        if not eligible:
            return finish(
                'unsupported_question',
                reasons=['unsupported_question'],
                **_alternatives(snapshot, question, candidates_for_navigation),
            )
        route = 'decision_explanation'
        active = [
            (request, title)
            for request, title, events in eligible
            if events[-1]['action'] == 'approve'
        ]
        # Distinct reviewed meanings are ambiguous before checking which answer
        # remains usable. Stale evidence must not silently pick another meaning.
        if len({request['decision'] for request, _ in active}) > 1:
            return finish(
                'needs_selection',
                choices=[{'request': request, 'title': title} for request, title in active[:10]],
                choices_truncated=len(active) > 10,
            )
    approved = []
    for request, title, events in eligible:
        if not events or events[-1]['action'] != 'approve':
            continue
        result = explanations.answer(root, request, scope=scope)
        if result['status'] == 'approved':
            _track_sources(snapshot, result)
            approved.append((result, title))
    steps.append(
        {
            'check': 'approved_artifact_selection',
            'result': 'unique'
            if len(approved) == 1
            else 'none'
            if not approved
            else 'needs_selection',
        }
    )
    if not approved:
        return finish('unknown', reasons=['no_eligible_approved_explanation'])
    if len(approved) != 1:
        return finish(
            'needs_selection',
            choices=[{'request': r['request'], 'title': title} for r, title in approved[:10]],
            choices_truncated=len(approved) > 10,
        )
    result = approved[0][0]
    steps.append({'check': 'artifact_execution', 'result': 'approved'})
    extra = (
        {
            'wording_review': {
                'wording': question.strip(),
                'event_sha256': result['review']['event_sha256'],
            }
        }
        if wording
        else {}
    )
    return finish(
        'answered', request=result['request'], answer=result['answer'], result=result, **extra
    )


def _outcomes(result):
    if result.get('route') == 'framework_coverage':
        return [
            (row['criterion'], row['outcome'])
            for row in result.get('result', {}).get('evaluation', {}).get('criteria', [])
        ]
    return result['status']


def revalidate(root, saved, *, scope=None):
    explanations._check_hash(saved, 'answer_sha256')
    if saved.get('answer_contract') != CONTRACT:
        raise ValueError('Unsupported checked-answer receipt')
    current = answer(
        root, saved['question'], explanation_revision=saved['explanation_revision'], scope=scope
    )
    if saved.get('reasons') == ['output_budget']:
        return revalidation_report(saved['answer_sha256'], current, reasons=['saved_abstention'])
    same_request = (
        saved.get('request') == current['request']
        if saved.get('request') and current['request']
        else None
    )
    same = current == saved
    return revalidation_report(
        saved['answer_sha256'],
        current,
        status='unchanged' if same else 'changed',
        reasons=[] if same else ['answer_changed'],
        interpretation_unchanged=same_request,
        outcomes_unchanged=_outcomes(saved) == _outcomes(current) if same_request else None,
    )
