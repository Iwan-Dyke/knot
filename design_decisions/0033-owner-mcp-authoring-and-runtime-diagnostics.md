# ADR 0033: Expose owner authoring through MCP and diagnose blocked runtimes

- Status: Accepted
- Date: 2026-11-06
- Implementation: Implemented
- Documentation reviewed: 2026-11-07
- Extends: ADRs 0021, 0022, 0027, 0030 and 0032
- Supersedes: The read-only-only transport restriction in ADRs 0021 and 0030;
  preserves their scoped retrieval contract

## Context

The owner requested that MCP support the note and relationship authoring workflows
available locally and that the stalled protocol tests be investigated.

A minimal asyncio thread test reproduced denied writes to the event loop's internal
socket pair (`PermissionError: Operation not permitted`) inside the execution sandbox.
SDK synchronous tools use worker threads, whose completion wakes that loop. Blocking
the wake-up path caused apparent hangs until other events or timers ran. The original
full suite, including 14 MCP tests, passed all 389 tests outside the sandbox in about
12 seconds. This was an environment restriction, not a retrieval deadlock or a reason
to replace the SDK or bypass its thread handling.

## Decision

Keep read-only lookup/retrieval as the default, including all existing revision-pin
and whole-dataset read modes. Add explicit `--allow-write`, requiring `--allow-all`,
for owner authoring. Do not register owner tools for scoped readers. A separate
`--allow-review`, requiring write mode, registers assertion decisions. Flags are
fixed at startup; tool arguments cannot change the dataset, permissions or grants.
Do not edit client configuration or existing grants automatically.

Add a thin adapter over existing note, provenance, candidate, review, organisation
and quality APIs. Expose vocabulary/themes, actual IDs/time, note listing/history,
exact paged reads, paged navigation, backlinks, create/update, source-pin construction,
candidate check/publish, assertion browsing/inspection, integrity diagnostics and
organisation rebuild. Entity declarations and note themes/links use the existing
native navigation API. Curated notes use the existing derivation metadata.

Creation requires a reserved note ID and returns the original creation receipt on
an identical retry, including after later revisions. Conflicting creation inputs fail.
Updates require the observed head. Candidate retries retain the original ID, time and
pins and use the publisher's idempotency guarantees. Review requires the observed
global event token; corrections create Unreviewed replacements and cannot implicitly
accept them. The caller supplies actual attribution; tool availability is not a
substitute for task-specific user authorisation.

Tool descriptions and annotations distinguish reads, append-only publication and
revisions/review. Outputs fit the configured serialized response ceiling. Listing
pages shrink by whole records; note text is paged explicitly with revision, offset,
total length and next offset. No silent source clipping occurs. Mutation receipts
contain compact stable IDs/hashes so oversized metadata cannot conceal a successful
save. Detailed warnings remain available in candidate checking.

Theme definitions, imported-identity reviews, archive migration and grants remain
operator-managed workflows. Expose no arbitrary filesystem, shell, raw RDF or import
tool just to approximate those operations. Whole-dataset authoring can see existing
owner data; supporting writes under revision-only grants would need a separate
capability design and cannot safely reuse the owner APIs as-is.

Before stdio startup and protocol tests, probe the local wake-up socket. If denied,
fail promptly with instructions to use a runtime allowing asyncio socket pairs.
Do not skip tests or alter event-loop internals. Normal stdio needs no network
listener. `sources` inspection remains usable without the socket probe.

## Verification and tradeoffs

Use the pinned SDK without dependency changes. Exercise both in-process and actual
stdio clients with synthetic datasets. Cover default denial, startup permissions,
creation replay/conflicts, stale revisions, source integrity, curated provenance,
entity declaration reuse, paged Unicode/escaped text within wire budgets, publication
replay, separately enabled acceptance/correction and preservation of Unreviewed
replacement status. Retain all scoped read and legacy-client regressions.

The transport adds schemas and permission gates while the existing APIs remain
authoritative. Owner-mode reads expose more operational detail than the sanitised
scoped reader, intentionally within a whole-dataset grant. The socket check makes
environment failures clear; it cannot guarantee that every later operation is
permitted by every sandbox. Run complete protocol checks in a compatible runtime.
