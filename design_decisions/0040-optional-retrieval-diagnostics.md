# ADR 0040: Make retrieval diagnostics optional in AI responses

- Status: Proposed
- Date: 2026-11-07
- Implementation: Implemented as an opt-in view; default unchanged
- Extends: ADRs 0019, 0020, 0021 and 0039
- Supersedes: None

## Context

The retrieval envelope includes ranking explanations, selection statistics and
work counters. These help debugging, but a consuming AI often needs only the
selected evidence and the boundaries on its interpretation. The private
fixed-candidate packaging experiment measured a substantial administrative cost.
More elaborate shared-text tables and selection changes did not improve the
original 12k expected-record coverage without regressions.

## Decision

Implement an optional evidence view that omits only top-level ranking and selection
objects, per-match ranking/fusion scores and traversal/work usage counters. Keep
all selected quotations, original derivation pins, hashes, locators, authorship,
review and identity state, qualifications, source independence, relationships,
source context, full applied policy and omissions. Keep output-size and
assertion/passage usage counts. List the omitted categories explicitly.

The view is a pure copy of an already authorised result. It performs no reads,
discovery, reranking or permission changes. It composes with ADR 0039's existing
shared-provenance representation; no new reference format is introduced into
production. MCP measures the actual encoded view before pruning complete matches.
Default output, CLI behaviour and MCP diagnostic visibility remain unchanged.

This is an implemented experimental presentation choice, not adoption of a new
retrieval default. New shared-text tables, baseline-preserving refill, unanchored
marginal selection and progressive original-quote deferral remain private research
strategies. Their small-set results do not justify replacing the existing selector.

## Alternatives and consequences

Keeping every diagnostic preserves the current debugging experience and remains
the default. Hiding evidence, warnings, original quotations or applied access/view
policy would weaken interpretation and is excluded. Moving fields into hidden MCP
metadata could shift transport cost rather than remove it; this view does not
claim that uncharged bytes were compressed away.

Omitted diagnostics cannot be reconstructed from this response. Request a normal
response when inspecting ranking; a later request may observe changed data. Source
revision references and verification remain available in the original response.
Smaller context does not establish better answers or improved discovery. Because
selection is unchanged, a budget can still contain little useful evidence.

## Validation

Test exact semantic-field preservation, input immutability, deterministic encoding,
composition with shared provenance, denied scopes and actual MCP SDK delivery at
4k/8k/12k/24k character ceilings. Replay the frozen corpus through the production
formatter and separately compare representative live production-server calls.
Keep same-author evaluation limitations explicit. No authoring or dataset migration
is part of this change.
