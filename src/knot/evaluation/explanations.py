"""Explicit review and exact reuse of source-backed decision explanations."""

from __future__ import annotations

import fcntl
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from pyoxigraph import NamedNode

from knot.evaluation import questions
from knot.evaluation.access import ScopedSnapshot
from knot.evaluation.revalidation import revalidation_report
from knot.evaluation.snapshot import Evidence, canonical_hash
from knot.graph.rdf import VOCAB, values
from knot.interfaces.access import AccessScope
from knot.shared.storage import atomic_json, managed_path
from knot.writing.notes import _revision_hash

CONTRACT = 'decision-explanation/1'
HASH = re.compile('[0-9a-f]{64}')


class Unavailable(ValueError):
    """The permitted current view cannot supply an eligible explanation."""


def _request(request):
    if not isinstance(request, dict) or set(request) != {'decision', 'revision', 'question'}:
        raise ValueError('Supply exactly decision, revision and question')
    if any(not isinstance(v, str) or not 1 <= len(v) <= 2048 for v in request.values()):
        raise ValueError('Request values must be nonempty strings of at most 2048 characters')
    NamedNode(request['decision'])
    _revision_hash(request['revision'])
    return dict(request)


def _supported(request):
    return (
        request['question']
        == f'Why was decision {json.dumps(request["decision"], ensure_ascii=False)} chosen?'
    )


def _wordings(wordings):
    if not isinstance(wordings, list) or len(wordings) > 20:
        raise ValueError('Supply a list of at most 20 complete alternative questions')
    result = []
    for wording in wordings:
        if not isinstance(wording, str) or not 1 <= len(wording.strip()) <= 2000:
            raise ValueError('Each alternative question needs 1–2000 characters')
        wording = wording.strip()
        if (
            wording in result
            or questions._parse(wording) is not None
            or re.fullmatch(questions.DECISION_PATTERN, wording, re.I)
        ):
            raise ValueError('Alternative questions must be unique and cannot replace templates')
        result.append(wording)
    return result


def _seal(result, field='receipt_sha256'):
    return {**result, field: canonical_hash(result)}


def _check_hash(result, field):
    if not isinstance(result, dict) or len(json.dumps(result, ensure_ascii=False)) > 2_000_000:
        raise ValueError('Supply a JSON envelope of at most 2,000,000 characters')
    if result.get(field) != canonical_hash({k: v for k, v in result.items() if k != field}):
        raise ValueError('Saved content hash does not match')


def _directory(root, request):
    return managed_path(
        root, 'reviews/explanations/' + canonical_hash({'contract': CONTRACT, 'request': request})
    )


def _events(root, request):
    """Replay only this artifact's chain; no global review heads leak into receipts."""
    directory = _directory(root, request)
    by_previous = {}
    for path in sorted(directory.glob('*.json')):
        value = json.loads(managed_path(root, path.relative_to(Path(root).resolve())).read_bytes())
        if not isinstance(value, dict) or set(value) - {'wordings'} != {
            'contract',
            'request',
            'previous',
            'action',
            'content_sha256',
            'reviewer',
            'reason',
            'time',
            'event_sha256',
        }:
            raise ValueError('Invalid explanation review event')
        _check_hash(value, 'event_sha256')
        if 'wordings' in value and _wordings(value['wordings']) != value['wordings']:
            raise ValueError('Noncanonical alternative question wording')
        if (
            value['contract'] != CONTRACT
            or value['request'] != request
            or path.stem != value['event_sha256']
            or value['action'] not in ('approve', 'withdraw')
            or any(
                not isinstance(value[k], str) or not value[k].strip()
                for k in ('reviewer', 'reason', 'time')
            )
            or not isinstance(value['content_sha256'], str)
            or not HASH.fullmatch(value['content_sha256'])
            or (
                value['previous'] is not None
                and (
                    not isinstance(value['previous'], str) or not HASH.fullmatch(value['previous'])
                )
            )
            or value['previous'] in by_previous
        ):
            raise ValueError('Invalid or branched explanation review history')
        if datetime.fromisoformat(value['time']).utcoffset() is None:
            raise ValueError('Explanation review time requires a timezone')
        by_previous[value['previous']] = value
    result, previous = [], None
    while previous in by_previous:
        event = by_previous.pop(previous)
        if event['action'] == 'withdraw' and (
            not result
            or result[-1]['action'] != 'approve'
            or event['content_sha256'] != result[-1]['content_sha256']
            or event.get('wordings', []) != result[-1].get('wordings', [])
        ):
            raise ValueError('Invalid explanation withdrawal')
        result.append(event)
        previous = event['event_sha256']
    if by_previous:
        raise ValueError('Incomplete explanation review history')
    return result


def _head(events):
    return events[-1]['event_sha256'] if events else None


def history(root, request):
    """Owner inspection remains available when a source is stale or corrupt."""
    return _events(Path(root).resolve(), _request(request))


def _material(snapshot, request):
    store = snapshot.view.store
    revision = request['revision']
    metadata = values(store, revision, VOCAB + 'noteMetadata')
    if not metadata:
        raise Unavailable('No eligible explanation in the permitted current view')
    native = json.loads(metadata[0].value)
    if (
        native['currentness'] not in ('CurrentCommittedRevision', 'LatestGrantedRevision')
        or not native.get('derivation')
        or request['decision'] not in native['entities']
    ):
        raise Unavailable(
            'A current curated revision associated with the exact decision is required'
        )
    reader = Evidence(snapshot, store, 100)
    _, citation = reader.revision(revision)
    # Preserve the approved UTF-8 text, including BOM and original line endings.
    body = reader.read(citation['snapshot'], citation['sha256']).decode('utf-8')
    if not body.strip():
        raise Unavailable('An explanation cannot be empty')
    sources = []
    for pin in native['derivation']['sources']:
        _, source = reader.revision(pin['revision'])
        sources.append(
            {
                **source,
                'quote': pin['quote'],
                'locator': {
                    'characterOffset': str(pin['character_offset']),
                    'startLine': str(pin['start_line']),
                },
            }
        )
    dependencies = []
    for rid, (_, source) in sorted(reader.cache.items()):
        note = source.get('native_note')
        if note and note['currentness'] not in (
            'CurrentCommittedRevision',
            'LatestGrantedRevision',
        ):
            raise Unavailable(
                'A native dependency has a newer visible revision; curate and review again'
            )
        dependencies.append({k: source[k] for k in ('revision', 'sha256', 'text_sha256')})
    content = {
        'contract': CONTRACT,
        'request': request,
        'answer': body,
        'author': native['author'],
        'title': native['title'],
        'format': native['format'],
        'qualification': native['derivation']['qualification'],
        'dependencies': dependencies,
    }
    return {
        **content,
        'content_sha256': canonical_hash(content),
        'sources': sources,
        'freshness': 'current_native_revisions; imported_sources_pinned'
        if snapshot.scope.whole_dataset
        else 'latest_granted_revisions; global_currentness_unknown',
        'limitation': 'Review approves this wording for this question. It does not establish independent truth, successful delivery or absence of contrary evidence.',
    }


def prepare(root, request, *, wordings=None):
    """Read-only owner preview; a curated note is not automatically approved prose."""
    root, request = Path(root).resolve(), _request(request)
    if not _supported(request):
        raise ValueError('Unsupported decision-explanation question')
    snapshot = ScopedSnapshot(root, AccessScope.all())
    events = _events(root, request)
    if wordings is None:
        wordings = events[-1].get('wordings', []) if events else []
    wordings = _wordings(wordings)
    material = _material(snapshot, request)
    snapshot.verify()
    if events != _events(root, request):
        raise ValueError('Explanation reviews changed during preparation')
    return _seal(
        {**material, 'status': 'candidate', 'expected_review': _head(events), 'wordings': wordings},
        'preview_sha256',
    )


def _append(root, request, action, content_sha256, events, reviewer, reason, wordings):
    if any(not isinstance(v, str) or not v.strip() for v in (reviewer, reason)):
        raise ValueError('Actual reviewer and review reason are required')
    event = _seal(
        {
            'contract': CONTRACT,
            'request': request,
            'previous': _head(events),
            'action': action,
            'content_sha256': content_sha256,
            'reviewer': reviewer,
            'reason': reason,
            'wordings': wordings,
            'time': datetime.now(timezone.utc).isoformat(timespec='microseconds'),
        },
        'event_sha256',
    )
    directory = _directory(root, request)
    directory.mkdir(parents=True, exist_ok=True)
    atomic_json(
        managed_path(root, (directory / (event['event_sha256'] + '.json')).relative_to(root)), event
    )
    return event


def approve(root, preview, *, reviewer, reason):
    """Owner write requiring explicit review of this exact preview; never used by read tools."""
    root = Path(root).resolve()
    _check_hash(preview, 'preview_sha256')
    request = _request(preview['request'])
    directory = managed_path(root, 'reviews')
    directory.mkdir(parents=True, exist_ok=True)
    with managed_path(root, 'reviews/.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        current = prepare(root, request, wordings=preview.get('wordings'))
        if current != preview:
            raise ValueError('Explanation or review state changed; inspect a fresh preview')
        return _append(
            root,
            request,
            'approve',
            current['content_sha256'],
            _events(root, request),
            reviewer,
            reason,
            current['wordings'],
        )


def withdraw(root, request, *, expected, reviewer, reason):
    """Withdraw without requiring the old body to remain readable or valid."""
    root, request = Path(root).resolve(), _request(request)
    managed_path(root, 'reviews').mkdir(parents=True, exist_ok=True)
    with managed_path(root, 'reviews/.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        events = _events(root, request)
        if not events or _head(events) != expected or events[-1]['action'] != 'approve':
            raise ValueError('No matching current approval; inspect review state')
        return _append(
            root,
            request,
            'withdraw',
            events[-1]['content_sha256'],
            events,
            reviewer,
            reason,
            events[-1].get('wordings', []),
        )


def abstention(request, reason, *, status='unknown'):
    return _seal({'contract': CONTRACT, 'request': request, 'status': status, 'reasons': [reason]})


def answer(root, request, *, scope=None):
    root, request = Path(root).resolve(), _request(request)
    if not _supported(request):
        return abstention(request, 'unsupported_question', status='unsupported_question')
    if scope is not None and not isinstance(scope, AccessScope):
        raise TypeError('Supply an AccessScope')
    snapshot = ScopedSnapshot(root, scope if scope is not None else AccessScope.all())
    # Check visibility before inspecting approval metadata or reading source bodies.
    if not values(snapshot.view.store, request['revision'], VOCAB + 'noteMetadata'):
        snapshot.verify()
        return abstention(request, 'not_available')
    events = _events(root, request)
    if not events or events[-1]['action'] != 'approve':
        result = abstention(request, 'not_approved')
    else:
        try:
            material = _material(snapshot, request)
            if material['content_sha256'] != events[-1]['content_sha256']:
                raise Unavailable('Approved content no longer matches')
            result = _seal(
                {
                    **material,
                    'status': 'approved',
                    'review': events[-1],
                    'manifest': {**snapshot.manifest(), 'implementation': snapshot.implementation},
                }
            )
        except Unavailable:
            result = abstention(request, 'not_current_or_applicable')
    snapshot.verify()
    if events != _events(root, request):
        raise ValueError('Explanation reviews changed during execution; retry')
    return result


def revalidate(root, saved, *, scope=None):
    if not isinstance(saved, dict) or len(json.dumps(saved, ensure_ascii=False)) > 2_000_000:
        raise ValueError('Supply an explanation receipt of at most 2,000,000 characters')
    _check_hash(saved, 'receipt_sha256')
    if saved.get('contract') != CONTRACT or saved.get('status') not in (
        'approved',
        'unknown',
        'unsupported_question',
    ):
        raise ValueError('Unsupported explanation receipt')
    current = answer(root, saved['request'], scope=scope)
    if saved.get('reasons') == ['output_budget']:
        return revalidation_report(saved['receipt_sha256'], current, reasons=['saved_abstention'])
    same = current == saved
    return revalidation_report(
        saved['receipt_sha256'],
        current,
        status='unchanged' if same else 'changed',
        reasons=[] if same else ['explanation_changed'],
        interpretation_unchanged=True,
        outcomes_unchanged=current['status'] == saved['status'],
    )
