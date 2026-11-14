"""Read-only access to deterministic question routing and artifact selection."""

from typing import Annotated, Any

from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import Field

from knot.evaluation.answering import answer, budget_abstention, revalidate
from knot.evaluation.revalidation import revalidation_report
from knot.interfaces.mcp_evaluation import Budget, _encode


def register_answer_tool(server, root, scope, ceiling):
    @server.tool(
        annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False),
        structured_output=False,
    )
    def knot_answer(
        question: Annotated[str, Field(min_length=1, max_length=2000)] | None = None,
        receipt: dict[str, Any] | None = None,
        explanation_revision: Annotated[str, Field(max_length=2048)] | None = None,
        max_chars: Budget = None,
    ) -> str:
        """Answer only a supported question using deterministic routing and selection.
        Templates: Does project "PROJECT" have reviewed support for criterion "CRITERION"?
        What reviewed support does project "PROJECT" have for criterion "CRITERION"?
        Why was decision "DECISION" chosen?
        Also accepts complete alternative questions explicitly reviewed with an
        explanation. Only surrounding whitespace is ignored; case, punctuation and
        every condition must match the reviewed wording. Unregistered paraphrases
        are unsupported. No fuzzy or model-generated translation is performed.
        An unsupported question may include related reviewed alternatives. These are
        lexical navigation choices, not verified paraphrases or answers to the original
        question. Present the complete alternatives and their guidance. The user must
        explicitly choose a question before you execute it; never automatically replace
        the original, drop its conditions or treat an alternative as its interpretation.
        Alternatives are bounded and checked for current approval and source eligibility.
        Names must resolve exactly in the visible view, or supply exact IRIs.
        Coverage allows the framework/revision suffix documented by knot_evaluate.
        Explanations require one eligible approved current revision, or explicit
        explanation_revision selection from returned choices. Never pick an ambiguous
        choice automatically. Preserve exact answer, qualification, authorship and review.
        Approval does not prove independent truth, applicability beyond the approved question,
        or successful delivery. Restricted currentness means latest granted revision only.
        Unknown and unsupported questions establish no absence outside the checked contract.
        Do not silently simplify extra conditions or turn retrieved prose into a checked answer.
        Supply receipt alone to recompute routing, wording approval and selection with
        current scope and reviews. A wording review can be withdrawn or replaced.
        Saved hashes are not signatures or access grants. Output-budget abstentions contain
        no partial answer and are not comparable receipts. This tool cannot approve or write.
        """
        budget = ceiling if max_chars is None else max_chars
        if budget > ceiling:
            raise ToolError('Requested budget exceeds the server ceiling.')
        if (question is None) == (receipt is None) or (
            receipt is not None and explanation_revision is not None
        ):
            raise ToolError('Supply question with optional selection, or receipt alone.')
        try:
            result = (
                answer(root, question, explanation_revision=explanation_revision, scope=scope)
                if question is not None
                else revalidate(root, receipt, scope=scope)
            )
        except Exception:
            raise ToolError(
                'KNOT checked answer unavailable; check the local dataset, scope and arguments.'
            ) from None
        text, size = _encode(result)
        if size > budget:
            current = budget_abstention(result['current'] if receipt is not None else result)
            result = (
                revalidation_report(result['previous_sha256'], current, reasons=['output_budget'])
                if receipt is not None
                else current
            )
            text, size = _encode(result)
        if size > budget:
            raise ToolError('Checked abstention cannot fit; increase the permitted budget.')
        return text
