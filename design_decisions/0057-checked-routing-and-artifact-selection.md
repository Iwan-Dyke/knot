# ADR 0057: Route checked questions and select approved artifacts deterministically

- Status: Accepted for the existing coverage and decision-explanation contracts
- Date: 2026-11-13
- Implementation: Implemented; broader question contracts remain outside scope
- Related: [0052](0052-bounded-deterministic-evaluation.md), [0054](0054-checked-coverage-question-answers.md), [0056](0056-reviewed-decision-explanations.md)

## Context

Deterministic tools alone left the client choosing the tool and explanation
revision. That choice could apply approved wording to the wrong question or hide
several applicable accounts. The existing quality audit also omitted the new
explanation review chains. Neither gap requires a general planner or new database.

## Decision

Add the read-only `checked-answer/1` dispatcher in `knot.evaluation.answering`,
available through `knot answer` and `knot_answer`. Match the entire finite question
template before selecting an existing evaluator. Resolve names only from visible
metadata, including native declarations. Explicit IRIs identify requests without
establishing their existence, type or truth.

For decision explanations, enumerate current visible curated revisions with an
exact immutable association to that decision. Check their revision-specific
approval and existing provenance/freshness contract. Return exact text only for
one eligible artifact. Several require explicit revision selection; if none is
eligible, return unknown. More than 100 candidates produces unknown before
examining approvals.
Do not use recency, rank or automatic semantic similarity to break ambiguity.

Capture every candidate's review history before execution and compare it again
before returning, including initially unapproved candidates. Verify the scoped
view and every source file checked during execution. A concurrent approval may
create ambiguity; a withdrawal or changed source may invalidate an answer. Fail
on detected changes. These checks do not provide a transaction against arbitrary
concurrent filesystem writers. Hidden candidates and review histories are not read.

Keep full evidence receipts inside the answer envelope. Withhold the entire
answer when transport budgets cannot carry it. Revalidation repeats routing and
selection using current grants; it neither trusts saved text nor restores old
state. Approval remains an explicit owner workflow, separate from answering.

Extend the existing whole-dataset quality audit to check explanation review
chains and request-directory placement. Reuse the owning validator rather than
duplicating event semantics. Integrity checks do not establish semantic truth.

[ADR 0058](0058-reviewed-alternative-question-wordings.md) extends routing to exact
reviewed alternative questions, with a separate enumeration bound of 1,000 visible
revision/entity pairs.
[ADR 0059](0059-related-reviewed-question-navigation.md) adds related-question
suggestions for unsupported wording. Ranking those navigation choices does not
select an answer or resolve artifact ambiguity; the user must choose a question
before it is executed.

## Tradeoffs

Exact templates sacrifice conversational flexibility for a reviewable boundary
with no generated plan or executable code. This fits the existing finite evaluator
and approval lifecycle. Existing exploratory retrieval remains useful for unsupported
questions, with no checked-answer guarantee. Multiple applicable accounts remain
visible as choices rather than being merged into a newly authored explanation.

The implementation adopts a bounded architectural pattern; it is not a universal
STRIDE engine. See the [status and acceptance matrix](../docs/stride-status.md).
