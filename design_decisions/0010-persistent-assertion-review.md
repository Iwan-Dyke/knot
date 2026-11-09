# ADR 0010: Preserve review decisions independently of extraction

- Status: Accepted
- Date: 2026-11-03
- Implementation: Implemented
- Documentation reviewed: 2026-11-07
- Extends: ADR 0003

## Context

Extraction regenerates candidate assertions. Human review must survive that process,
and ordinary queries must not see conflicting current review statuses.

## Decision

Store immutable RDF review events under `data/reviews/events/`. Record the target
assertion, its content fingerprint, reviewer, time, reason, action and preceding
decision. Use an exclusive file lock while validating and writing a decision; write
each complete event atomically. This is a single-machine workflow, not distributed
concurrency control.

Build the current query projection by replaying events after loading source RDF.
Replace effective status in that disposable store only. Keep the original assertions
and review events unchanged on disk. Reject unknown targets, changed content and
forked decision histories explicitly rather than applying stale approval.

Corrections create new assertions with explicit supersession links. Preserve the old
assertion and evidence in the historical view; remove its domain triple from the
ordinary active view. Rejected triples are also excluded from that view. A correction
does not accept its replacement unless explicitly requested. Initial corrections
retain the original source evidence; new evidence ingestion is a separate operation.

Identity proposals do not rewrite assertion endpoints unless explicitly accepted.
Retain source-scoped identities otherwise. Existing proposal applications are removed
by regenerating imports. Full identity review and splitting commands remain deferred.

## Alternatives and consequences

- Editing generated RDF directly is simpler initially, but blocks regeneration and
  mixes extraction with human decisions.
- Loading review files as a simple RDF union would leave contradictory statuses.
  An effective projection gives CLI, SPARQL and the viewer one consistent policy.
- Event fingerprints prevent silent approval of changed assertions. Changed or
  removed extraction records require explicit reconciliation before queries resume.
- The CLI supports inspect, accept, reject and correct without a web application or
  additional dependency. Historical access remains explicit and includes uncertainty.
