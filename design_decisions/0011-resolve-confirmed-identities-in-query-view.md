# ADR 0011: Resolve confirmed identities in the query view

- Status: Accepted
- Date: 2026-11-03
- Implementation: Implemented
- Documentation reviewed: 2026-11-07
- Refines: ADR 0010

## Context

Explicit identity review can establish that mentions in different source documents
refer to the same person or project. Rewriting stored assertion endpoints to apply
those bindings would invalidate previously recorded review fingerprints.

## Decision

Keep imported assertion endpoints scoped to their source revision. Persist explicit
identity proposals and their review status in RDF, including the source entity and
canonical target. Apply accepted mappings to assertion endpoints in the disposable
query projection after validating and applying assertion reviews. CLI queries and
the viewer therefore share the same connected graph. Unreviewed and rejected
mappings have no effect; conflicting accepted mappings fail explicitly.

Historical inspection and review operations use original endpoints. Preserve the
identity confirmation, reviewer, former bindings and evidence in a separate local
review record. Withdrawing a mapping restores separate endpoints on the next
rebuild without modifying any assertion review event. Repeated accounts retain
separate assertion graphs and do not become independent corroboration.

## Alternatives and consequences

Rewriting assertions would require migrating their review history. Rendering-only
merges would leave SPARQL traversal disconnected. Resolving identities in the query
projection preserves review history and provides consistent traversal with little
additional code. Raw RDF consumers must apply the explicit mappings themselves;
this deliberately avoids assigning unrestricted OWL equivalence semantics.
