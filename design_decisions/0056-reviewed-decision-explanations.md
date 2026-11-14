# ADR 0056: Review exact decision explanations before reuse

- Status: Accepted for the first bounded explanation contract
- Date: 2026-11-13
- Implementation: Owner-local preview/review CLI, scoped read-only MCP and receipt revalidation
- Extends: ADR 0027, ADR 0052 and ADR 0055
- Supersedes: None

## Context

The frozen-question comparison found a recurring gap around decision explanations.
Curated notes already preserve readable wording, authorship and exact derivation,
but provenance validation does not approve that wording for a question. Reusing
text safely needs explicit applicability, revision-specific review and withdrawal.

## Decision

Add `decision-explanation/1`. An explicit request selects a decision IRI, a curated
native-note revision and exactly `Why was decision "DECISION_IRI" chosen?`. Require
the note's immutable entity associations to include that exact IRI. Association
is navigation, not proof of applicability: the reviewer must check the referent,
question, answer meaning, source qualifications and unsupported implications.
Do not resolve aliases, broaden questions or accept extra conditions in this pilot.

Keep the explanation in an ordinary curated note. Its revision pins authorship,
body and immutable derivation. The owner prepares a read-only preview containing
exact text, source citations, qualification, dependency hashes and current review
head. Explicit approval re-prepares and compares the complete preview before
writing an event. It records the actual reviewer, rationale and actual time;
it neither impersonates the note's author nor accepts graph assertions.

Use the existing append-only review pattern and review-writer lock, with a separate
JSON event chain per request under `reviews/explanations/<request-hash>/`.
Each immutable event hashes its contents and names its predecessor. Replay rejects
malformed, branched and incomplete chains. Approval and withdrawal are separate
owner-local actions. Withdrawal requires the observed head and remains possible
when old evidence is corrupt. A stale preview fails; inspect current history before
retrying an uncertain write. Existing assertion reviews and native sources remain
unchanged. Hashes and local reviewer labels are not signatures or identity authentication.

Answer execution requires a current approval and matching content fingerprint.
Return the approved UTF-8 wording unchanged, preserving line endings, with original
author, separate reviewer, exact direct source pins and transitive dependencies.
No synthesis or free-text interpretation occurs during answering. Imported source
revisions remain pinned; this does not establish absence of newer or contrary accounts.

Filter grants before body reads and review disclosure. All transitive inputs require
their own grants. Every native dependency must be the current committed revision
for whole-dataset access, or the latest granted revision for pinned access. A newer
visible revision makes the old explanation ineligible; new explanation revisions
have no inherited approval. Hidden successors must not affect scoped responses.
Pinned responses explicitly state that global currentness is unknown. An explicit
withdrawal stops reuse within every scope that can see the artifact.

Approval binds semantic contract version, exact request, content and immutable
dependencies. Runtime implementation hashes belong to execution receipts, not
the human content approval: a deployment need not revoke identical reviewed wording.
Changing interpretation semantics requires a new contract version and review.

Recheck the visible snapshot, source hashes and request-local review chain before
returning. Receipt revalidation recomputes under current grants and approvals and
never echoes old evidence after revocation. If a complete MCP package cannot fit,
return unknown without the answer; an oversized revalidation is `not_comparable`.
MCP exposes reading and revalidation only, even in owner-authoring mode.

## Reviewed question wording extension

[ADR 0058](0058-reviewed-alternative-question-wordings.md) adds explicit alternative
question wordings to the approval preview and event. The canonical request and
content fingerprint remain unchanged; the event hash binds the reviewed wordings.
Legacy events without that field mean an empty list. `knot_answer` matches complete
reviewed questions and retains the applicable review event in its receipt.

## Alternatives and tradeoffs

Reusing assertion acceptance would conflate approval of a triple with approval of
an entire explanation. Treating curated provenance as approval would skip semantic
review. A separate prose database would duplicate the existing note lifecycle.
The small per-request event chain reuses existing files, locks, hashing, source
verification and scopes without a new dependency or migration.

This first contract requires exact identifiers and manual artifact selection.
It is less convenient than general conversation. It supports no arbitrary question
matching, conflict adjudication, historical replay or truth verification. Native
source edits conservatively require recuration and review; imported sources have
no inferred logical-head mapping. Stable-read checks are not a transactional
snapshot or protection against an owner rewriting history and its hashes.

## Validation

Synthetic tests cover exact text and authorship, approval and withdrawal, stale or
forged previews, new note and input revisions, transitive grants, hidden successors,
malformed event chains, changed sources, concurrent withdrawal, CLI routing, real
MCP transport, budget abstention and revalidation without access restoration.
Live read-only checks must not approve knowledge merely to demonstrate a positive
answer. Real explanation approval remains a distinct owner review task.
