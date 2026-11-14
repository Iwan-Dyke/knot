# ADR 0055: Revalidate saved receipts against current authorised inputs

- Status: Accepted for the existing coverage and checked-question contracts
- Date: 2026-11-13
- Implementation: Implemented through the coverage CLI and MCP tool
- Extends: ADR 0052 and ADR 0054
- Supersedes: None

## Context

A saved receipt records an execution. Newly accepted mappings, withdrawn claims,
changed rules or revoked grants can make it unsuitable for a current answer.
Matching a previous witness alone cannot detect a newly eligible mapping that
invalidates an earlier absence result. Saved question names can become ambiguous.

## Decision

Add current revalidation by recomputing through the existing evaluator and current
operator scope. A saved evaluated question repeats its template parsing and name
resolution. Validate the saved envelope's hashes, supported contract, normalised
request and essential shape before execution. Hashes detect accidental alteration;
they are not signatures, grants or verification of the saved claims.

Return `current-receipt/1`, the opaque previous hash and the complete current result.
Never follow saved manifest paths, restore saved permissions, use saved outcomes
as current premises or republish old evidence. Unsupported versions and corrupt
current inputs fail explicitly without falling back to the saved result. MCP also
applies its current request limits to receipts created by an owner-local caller.

`unchanged` requires an identical recomputed receipt hash. `changed` separately
reports whether interpretation and outcome categories match: dependency changes
need not change the outcome. `not_comparable` covers a saved output-budget
abstention or a question that can no longer resolve. A changed interpretation
leaves outcome comparison unset. Current evidence and qualifications remain
necessary even when outcome categories match.

If the report cannot fit the MCP response budget, replace current evidence with an
all-unknown abstention and the comparison with `not_comparable`. If that cannot
fit, fail explicitly. Never retain an unchanged claim after withholding its proof
package. Only the current result is returned, apart from the previous opaque hash.

## Tradeoffs and limits

Fresh computation reuses the existing eligibility, access and source verification
boundaries and needs no cache invalidation machinery. Its cost is the same graph
loading and verification work as a new evaluation. The saved JSON is capped at
2,000,000 serialised characters; this is not a transport streaming or file-read cap.
The existing stable-input checks do not provide transactional snapshots.

This is current revalidation, not historical replay. It does not recover old
rules, sources or authorisations, certify authorship, establish semantic truth,
add evaluation rules or provide a continuous monitoring service. Persistent caching
and explicit historical replay remain deferred.

## Validation

Synthetic tests cover new and withdrawn mappings, implementation changes with
unchanged outcomes, corrupted receipts and sources, forged but rehashed claims,
malicious saved paths, revoked access, hidden-data noninterference, changed name
resolution, execution limits, CLI routing and MCP response-budget abstention.
Live verification uses saved receipts read-only and checks current evidence pins,
determinism and unchanged dataset metadata.
