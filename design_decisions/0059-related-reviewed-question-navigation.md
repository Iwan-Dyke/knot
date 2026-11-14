# ADR 0059: Offer reviewed questions without interpreting unsupported wording

- Status: Accepted for read-only question navigation
- Date: 2026-11-14
- Implementation: Checked-answer CLI/MCP alternatives and current revalidation
- Extends: [0057](0057-checked-routing-and-artifact-selection.md), [0058](0058-reviewed-alternative-question-wordings.md)

## Context

A frozen twelve-question development exercise returned the two registered control
answers and rejected ten unregistered questions. Several questions concerned the
same decisions but used different wording. The unsupported response offered no
way to discover a permitted question. Automatically treating lexical similarity
as equivalent meaning would bypass the reviewed interpretation boundary.

## Decision

When no reviewed wording matches, retain `unsupported_question`, the original
question, null route/request and no answer. Optionally include up to five related
reviewed questions as `alternatives`, with explicit navigation guidance. Each
contains complete wording, explanation revision, decision, title and review-event
hash. These are choices, not an interpretation or answer to the original question.
Clients must obtain an explicit user selection before submitting a different
question; one suggestion is not permission to silently replace the request.

Reuse the existing lexical token normalisation for navigation, filtering generic
question words. Candidates must share at least one remaining term and cover at
least one quarter of the query's remaining terms. Rank by shared terms divided
by union size, with stable textual/request tie-breaks. This is a relevance heuristic,
not a semantic-equivalence test; it can miss useful choices or suggest questions
with a different scope. No generated queries or new review events are involved.

Search only the already bounded, current, visible curated candidates and their
accessible review histories. Only active approvals with registered wordings can
be suggested. Verify each shortlisted artifact with the existing explanation
contract; stale or ineligible artifacts are not offered. Corrupt evidence fails
explicitly. Check at most five distinct requests and return at most five choices.
`alternatives_truncated` means further candidates may remain unchecked; it does
not assert that omitted candidates would be eligible.

Track verified source hashes in the enclosing snapshot and recheck all observed
review histories before returning, including nonmatching histories. This prevents
detected source/review changes from leaving stale navigation results. All source
grants and hidden-data isolation rules remain in force. Revalidation recomputes
navigation, removing withdrawn or inaccessible choices without echoing old content.

The existing complete-output budget applies. An oversized response becomes an
output-budget abstention without partial alternatives or guidance. No fallback
answer is emitted. Built-in templates and exact reviewed wordings retain their
existing execution behavior.

## Tradeoffs and verification

This improves discoverability without expanding what KNOT claims to understand.
It adds bounded source verification work to some unsupported requests. A related
decision rationale does not answer a question about delivery, timing or success;
guidance must preserve that distinction. Clients can still misuse suggestions,
so the server exposes the original unsupported status and supplies explicit client
instructions rather than claiming to enforce user intent outside the tool.

Existing test modules cover unchanged original questions, explicit selection,
extra conditions, unrelated topics, stale/withdrawn artifacts, hidden and missing
grants, result/work budgets, source corruption, concurrent changes, revalidation,
read-only CLI use and MCP framing/stdio behavior. Development measurements report
answer coverage separately from the presence of navigation choices. No personal
question is registered or approved to make the comparison pass.
