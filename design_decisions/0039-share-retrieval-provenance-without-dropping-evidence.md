# ADR 0039: Share retrieval provenance without dropping evidence

- Status: Accepted
- Date: 2026-11-07
- Implementation: Implemented; optional wire representation only
- Documentation reviewed: 2026-11-07
- Extends: ADRs 0019, 0020, 0021 and 0027
- Supersedes: None

## Context

Several citations can repeat the same revision metadata or derivation source pin.
Those bytes consume context without adding evidence. Removing input quotations or
qualifications would weaken the complete-provenance contract. Larger, semantically
complete curated notes can also exceed small budgets; wire duplication is only one
part of that problem.

## Decision

Offer an optional `shared-provenance-v1` response after ordinary scoped retrieval
and selection. Share identical source metadata in `source_metadata`, leaving each
citation's locator, passage and optional passage span in `sources`. Within native
metadata, share identical complete derivation pins in `derivation_sources`.

Compare complete metadata, not just revision IDs: currentness and other scope-aware
fields can legitimately differ for the same revision. Preserve all other fields,
including qualifications, authorship, review state, source independence and exact
input quotations. Expansion reconstructs the full response without another read or
network request. Recalculate exact Unicode character and UTF-8 byte counters.
Return the ordinary full response when sharing would be larger.

The Python helpers are `knot.retrieval_engine.wire.compact` and `expand`. CLI `get`
and `gather` accept `--compact`; MCP `knot_retrieve` accepts `compact=true`. Existing
clients and default wire hashes remain unchanged. The format requires consumers to
resolve references before interpreting evidence; it is not a summary or inferred
answer. No new database, vocabulary, grants or server permissions are introduced.

Keep selection costs and limits unchanged. MCP checks its complete transport
framing after optional compaction, pruning whole packages from the original full
payload when required. Compaction itself reads no files, expands no access scope
and cannot introduce denied metadata.

## Consequences and alternatives

This change saves bytes only where repeated provenance exists. It does not promise
more relevant evidence, better reasoning or lower end-to-end latency. Factoring
before selection could change the chosen evidence and requires a separate relevance
evaluation. Removing quotations in favour of remote references would create a
follow-up dependency and is deliberately deferred. Generic string compression is
less readable and unnecessary for this bounded representation.

Curation may instead narrow an oversized pin to a complete, relevant source span,
provided its reasoning and qualifications remain supported. Such a change belongs
to an immutable curated-note revision, never a silent response-time truncation.

## Validation

Round-trip tests preserve all fields, quotations and uncertainty, distinguish
currentness for the same revision, reject missing references, check non-ASCII byte
counts and retain the full format when smaller. MCP tests cover the opt-in format,
transport ceilings and denied scopes. Existing frozen default responses remain a
compatibility check. Private corpus experiments compare identical questions and
budgets, report regressions, and separate measured characters from estimated tokens;
they do not establish general answer-quality superiority.
