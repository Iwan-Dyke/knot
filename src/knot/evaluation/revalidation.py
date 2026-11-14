"""Recompute saved evaluation receipts under current rules and authorisation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from knot.evaluation.engine import evaluate
from knot.evaluation.questions import CONTRACT, answer_question
from knot.evaluation.request import CoverageRequest
from knot.evaluation.snapshot import canonical_hash
from knot.interfaces.access import AccessScope

MAX_RECEIPT_CHARS = 2_000_000


def _check_hash(value: dict[str, Any], field: str) -> None:
    if value.get(field) != canonical_hash(
        {key: item for key, item in value.items() if key != field}
    ):
        raise ValueError('Saved receipt hash does not match its contents')


def validate_receipt(saved: dict[str, Any]) -> CoverageRequest:
    """Validate an untrusted saved envelope, without reading any of its paths."""
    if (
        not isinstance(saved, dict)
        or len(json.dumps(saved, ensure_ascii=False)) > MAX_RECEIPT_CHARS
    ):
        raise ValueError('Supply a saved receipt of at most 2,000,000 characters')
    question = 'question_contract' in saved
    if question:
        _check_hash(saved, 'answer_sha256')
        if (
            saved['question_contract'] != CONTRACT
            or saved.get('status') != 'evaluated'
            or not isinstance(saved.get('question'), str)
            or not 1 <= len(saved['question']) <= 2000
            or not isinstance(saved.get('evaluation'), dict)
        ):
            raise ValueError('Unsupported saved question receipt')
    receipt = saved['evaluation'] if question else saved
    _check_hash(receipt, 'receipt_sha256')
    if type(receipt.get('schema_version')) is not int or receipt['schema_version'] != 1:
        raise ValueError('Unsupported saved evaluation schema')
    request = CoverageRequest.from_dict(receipt.get('request'))
    rows = receipt.get('criteria')
    if (
        receipt['request'] != request.to_dict()
        or not isinstance(rows, list)
        or any(not isinstance(row, dict) for row in rows)
        or [row.get('criterion') for row in rows] != list(request.criteria)
        or any(
            row.get('outcome') not in {'support_found', 'no_qualifying_support', 'unknown'}
            for row in rows
        )
        or type(receipt.get('complete')) is not bool
        or type(receipt.get('enumeration_complete')) is not bool
        or not isinstance(receipt.get('assertions'), dict)
    ):
        raise ValueError('Invalid saved evaluation receipt')
    if receipt.get('receipt_kind') == 'abstention':
        if (
            receipt['complete']
            or receipt['enumeration_complete']
            or receipt['assertions']
            or any(row['outcome'] != 'unknown' for row in rows)
        ):
            raise ValueError('Invalid saved abstention')
    elif (
        'receipt_kind' in receipt
        or not isinstance(receipt.get('manifest'), dict)
        or receipt['manifest'].get('request') != receipt['request']
    ):
        raise ValueError('Invalid saved evaluation manifest')
    if question and (
        saved.get('request') != receipt['request']
        or len(request.criteria) != 1
        or request
        != CoverageRequest(
            request.subject, request.framework, request.framework_revision, request.criteria
        )
    ):
        raise ValueError('Saved question and evaluation request disagree')
    return request


def revalidation_report(
    previous_sha256: str,
    current: dict[str, Any],
    *,
    status: str = 'not_comparable',
    reasons: list[str],
    interpretation_unchanged: bool | None = None,
    outcomes_unchanged: bool | None = None,
) -> dict[str, Any]:
    result = {
        'revalidation_version': 'current-receipt/1',
        'previous_sha256': previous_sha256,
        'status': status,
        'reasons': reasons,
        'interpretation_unchanged': interpretation_unchanged,
        'outcomes_unchanged': outcomes_unchanged,
        'current': current,
    }
    result['revalidation_sha256'] = canonical_hash(result)
    return result


def revalidate(
    root: Path, saved: dict[str, Any], *, scope: AccessScope | None = None
) -> dict[str, Any]:
    """Compare fresh computation, never restoring saved permissions, files or code."""
    request = validate_receipt(saved)
    question = 'question_contract' in saved
    digest_field = 'answer_sha256' if question else 'receipt_sha256'
    old = saved['evaluation'] if question else saved
    current = (
        answer_question(root, saved['question'], scope=scope)
        if question
        else evaluate(root, request, scope=scope)
    )
    fresh = current.get('evaluation') if question else current
    if fresh is None:
        return revalidation_report(saved[digest_field], current, reasons=['question_not_resolved'])
    if old.get('receipt_kind') == 'abstention':
        return revalidation_report(saved[digest_field], current, reasons=['saved_abstention'])
    same_request = old['request'] == fresh['request']
    same_outcomes = (
        (
            [(row['criterion'], row['outcome']) for row in old['criteria']]
            == [(row['criterion'], row['outcome']) for row in fresh['criteria']]
        )
        if same_request
        else None
    )
    reasons = []
    if not same_request:
        reasons.append('request_changed')
    if old['manifest'].get('implementation') != fresh['manifest'].get('implementation'):
        reasons.append('implementation_changed')
    if old['manifest'].get('access') != fresh['manifest'].get('access'):
        reasons.append('access_changed')
    if old['manifest'] != fresh['manifest']:
        reasons.append('dependencies_changed')
    if same_outcomes is False:
        reasons.append('outcomes_changed')
    unchanged = saved[digest_field] == current[digest_field]
    if not unchanged and not reasons:
        reasons.append('receipt_content_changed')
    return revalidation_report(
        saved[digest_field],
        current,
        status='unchanged' if unchanged else 'changed',
        reasons=reasons,
        interpretation_unchanged=same_request,
        outcomes_unchanged=same_outcomes,
    )
