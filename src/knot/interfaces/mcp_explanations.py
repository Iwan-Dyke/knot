"""Read-only explanation reuse; approval is an explicit owner-local operation."""

from typing import Annotated, Any

from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import BaseModel, ConfigDict, Field

from knot.evaluation.explanations import abstention, answer, revalidate
from knot.evaluation.revalidation import revalidation_report
from knot.interfaces.mcp_evaluation import Budget, _encode


class ExplanationInput(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    decision: Annotated[str, Field(min_length=1, max_length=2048)]
    revision: Annotated[str, Field(min_length=1, max_length=2048)]
    question: Annotated[str, Field(min_length=1, max_length=2048)]


def register_explanation_tool(server, root, scope, ceiling):
    @server.tool(
        annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False),
        structured_output=False,
    )
    def knot_explain(
        request: ExplanationInput | None = None,
        receipt: dict[str, Any] | None = None,
        max_chars: Budget = None,
    ) -> str:
        """Reuse exact wording from an explicitly reviewed curated-note revision.
        Supply request with decision IRI, native note revision IRI and exactly:
        Why was decision "DECISION_IRI" chosen? Extra conditions are unsupported.
        Approval binds that decision, question and immutable explanation revision.
        Review approves wording/applicability, not independent truth or successful delivery.
        A source-backed curated note alone has no answer approval. This tool cannot approve,
        withdraw, edit notes or widen grants. The operator's transitive source grants apply.
        Unknown means no eligible current approval in this scope, not no decision or evidence.
        Under pinned access, currentness is only latest granted revisions; global currentness
        is unknown. Imported inputs remain explicitly pinned, not checked for newer accounts.
        Preserve the complete answer, qualification, original author and separate reviewer.
        Alternatively supply receipt alone to recompute under current access and approval state.
        Saved hashes are not signatures or grants. Oversized output yields an unknown
        output_budget abstention; revalidation then reports not_comparable.
        """
        budget = ceiling if max_chars is None else max_chars
        if budget > ceiling:
            raise ToolError('Requested budget exceeds the server ceiling.')
        if (request is None) == (receipt is None):
            raise ToolError('Supply exactly one of request or receipt.')
        try:
            result = (
                answer(root, request.model_dump(), scope=scope)
                if request is not None
                else revalidate(root, receipt, scope=scope)
            )
        except Exception:
            raise ToolError(
                'KNOT explanation unavailable; check the local dataset, scope and arguments.'
            ) from None
        text, size = _encode(result)
        if size > budget:
            current = result['current'] if receipt is not None else result
            current = abstention(current['request'], 'output_budget')
            result = (
                revalidation_report(result['previous_sha256'], current, reasons=['output_budget'])
                if receipt is not None
                else current
            )
            text, size = _encode(result)
        if size > budget:
            raise ToolError('Explanation abstention cannot fit; increase the permitted budget.')
        return text
