"""Read-only MCP coverage evaluation with indivisible evidence receipts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Any, Literal

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import CallToolResult, TextContent, ToolAnnotations
from pydantic import BaseModel, ConfigDict, Field

from knot.evaluation import CoverageRequest, answer_question, evaluate, revalidate
from knot.evaluation.questions import evaluation_answer
from knot.evaluation.revalidation import revalidation_report, validate_receipt
from knot.evaluation.snapshot import canonical_hash
from knot.interfaces.access import AccessScope

IRI = Annotated[str, Field(min_length=1, max_length=2048, strict=True)]
Budget = Annotated[int | None, Field(ge=2048, le=131072, strict=True)]


class EvaluationInput(BaseModel):
    """MCP input limits; the core CoverageRequest validates the rule contract."""

    model_config = ConfigDict(extra='forbid', strict=True)
    subject: IRI
    framework: IRI
    framework_revision: IRI
    criteria: Annotated[list[IRI], Field(min_length=1, max_length=20)]
    rule: Literal['framework-coverage'] = 'framework-coverage'
    version: Literal['1'] = '1'
    max_assertions: Annotated[int, Field(ge=1, le=1000)] = 1000
    max_sources: Annotated[int, Field(ge=1, le=100)] = 100
    as_of: Annotated[str | None, Field(min_length=1, max_length=128)] = None


def _encode(payload: dict[str, Any]) -> tuple[str, int]:
    from knot.interfaces.mcp_server import result_size

    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':')) + '\n'
    return text, result_size(CallToolResult(content=[TextContent(type='text', text=text)]))


def _budget_abstention(payload: dict[str, Any]) -> dict[str, Any]:
    # Never prune a premise while retaining a positive or negative conclusion.
    # The fallback certifies only abstention, not a truncated evidence package.
    abstention = {
        'schema_version': 1,
        'receipt_kind': 'abstention',
        'request': payload['request'],
        'scope': payload['scope'],
        'complete': False,
        'enumeration_complete': False,
        'reasons': ['output_budget'],
        'criteria': [
            {'criterion': criterion, 'outcome': 'unknown', 'reasons': ['output_budget']}
            for criterion in payload['request']['criteria']
        ],
        'assertions': {},
    }
    abstention['receipt_sha256'] = canonical_hash(abstention)
    return abstention


def _bounded_evaluation(payload: dict[str, Any], budget: int) -> str:
    text, size = _encode(payload)
    if size <= budget:
        return text
    text, size = _encode(_budget_abstention(payload))
    if size > budget:
        raise ToolError(
            'Budget too small for the evaluation request; select fewer criteria or increase the budget.'
        )
    return text


def _bounded_question(payload: dict[str, Any], budget: int) -> str:
    text, size = _encode(payload)
    if size > budget and 'evaluation' in payload:
        # Derive wording from the abstention, never from the now-withheld conclusion.
        payload = evaluation_answer(payload['question'], _budget_abstention(payload['evaluation']))
        text, size = _encode(payload)
    if size > budget:
        raise ToolError(
            'Question response cannot fit; shorten the question or increase the budget.'
        )
    return text


def _bounded_revalidation(payload: dict[str, Any], budget: int) -> str:
    text, size = _encode(payload)
    if size <= budget:
        return text
    current = payload['current']
    if 'question_contract' in current:
        if 'evaluation' not in current:
            raise ToolError('Revalidation choices cannot fit; increase the budget.')
        current = evaluation_answer(current['question'], _budget_abstention(current['evaluation']))
    else:
        current = _budget_abstention(current)
    payload = revalidation_report(payload['previous_sha256'], current, reasons=['output_budget'])
    text, size = _encode(payload)
    if size > budget:
        raise ToolError('Revalidation abstention cannot fit; increase the budget.')
    return text


def register_evaluation_tool(
    server: MCPServer, root: Path, scope: AccessScope, ceiling: int
) -> None:
    @server.tool(
        annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False),
        structured_output=False,
    )
    def knot_evaluate(
        request: EvaluationInput | None = None,
        max_chars: Budget = None,
        question: Annotated[str | None, Field(min_length=1, max_length=2000, strict=True)] = None,
        receipt: dict[str, Any] | None = None,
    ) -> str:
        """Evaluate reviewed direct supports mappings for explicitly selected criterion IRIs.
        request must name subject, framework, framework_revision and 1–20 criteria.
        The only rule/version is framework-coverage/1. Source grants are fixed by the
        operator; they cannot be supplied or widened by this tool. With pinned access,
        missing mappings are unknown, never evidence of global absence. Support found
        retains its attributed Assessment meaning; it does not certify capability.
        as_of requests are recognised but return unknown: temporal rules are unsupported.
        The response displays the exact interpreted request and all required evidence.
        If that receipt cannot fit max_chars, return an all-unknown output_budget
        abstention; select fewer criteria or request a larger operator-permitted budget.
        This tool does not publish, accept claims, replay historical code or execute queries.
        Alternatively supply question alone: Does project "PROJECT" have reviewed support for
        criterion "CRITERION"? Exact visible labels or explicit IRIs are required. Optional suffix:
        in framework "FRAMEWORK_IRI" at revision "REVISION_IRI". A unique visible definition may
        supply those two selections; ambiguity returns choices without evaluation. Extra conditions
        are unsupported, not ignored. The response includes the exact request, a fixed answer
        derived from the returned receipt, and its complete evidence. No general prose interpretation.
        Alternatively supply receipt alone with a saved evaluation or evaluated question envelope
        (maximum 2,000,000 JSON characters). Revalidation recomputes with current access and rules;
        saved hashes are not signatures or grants. It returns unchanged, changed or not_comparable,
        separately compares outcome categories, and returns only current evidence. Saved questions
        repeat name resolution. Output-budget abstention cannot certify an unchanged result.
        """
        budget = ceiling if max_chars is None else max_chars
        if budget > ceiling:
            raise ToolError('Requested budget exceeds the server ceiling.')
        if sum(value is not None for value in (request, question, receipt)) != 1:
            raise ToolError('Supply exactly one of request, question or receipt.')
        try:
            if receipt is not None:
                # A saved owner-local request must not bypass the current MCP execution limits.
                EvaluationInput.model_validate(validate_receipt(receipt).to_dict())
                result = revalidate(root, receipt, scope=scope)
            elif question is not None:
                result = answer_question(root, question, scope=scope)
            else:
                typed = CoverageRequest.from_dict(request.model_dump())
                result = evaluate(root, typed, scope=scope)
        except Exception:
            raise ToolError(
                'KNOT evaluation unavailable; check the local dataset, scope and arguments.'
            ) from None
        if receipt is not None:
            return _bounded_revalidation(result, budget)
        return (
            _bounded_question(result, budget)
            if question is not None
            else _bounded_evaluation(result, budget)
        )
