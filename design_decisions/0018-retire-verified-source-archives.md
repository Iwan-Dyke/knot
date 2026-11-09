# ADR 0018: Retire verified source archives

- Status: Accepted
- Date: 2026-11-04
- Implementation: Implemented
- Documentation reviewed: 2026-11-07
- Refines: ADR 0009

## Context

The user requested removal of examples, completed reviews and successfully migrated
source files. The imported ZIPs duplicate preserved revision bytes, but rebuilding
previously required the ZIPs and reinventorying without them discarded occurrences.
Semantic extraction remains selective, so snapshots cannot be discarded.

## Decision

Permit removal of a ZIP after verifying every member against its preserved snapshot
and checking a complete rebuild in a temporary copy. Record `retired: true` on the
archive's inventory entry; retain its path, hash and every member occurrence.
Missing archives without that explicit record remain errors. Retained ZIPs and all
snapshots must still pass hash verification before migration writes any output.

Inventory retains and verifies retired occurrences while importing new archives.
Keep source snapshots, extracted text, curation inputs, conversion ledgers, RDF,
review decisions and referenced audits. Remove redundant completed report summaries
and the obsolete first-graph example; keep pending work in the relevant ADR or queue.

## Alternatives and consequences

Keeping ZIPs indefinitely duplicates source storage. Removing snapshots would break
citations, rebuilding and future extraction, and lose PDF/Word layout information.
An explicit retirement flag fits the existing inventory without introducing another
store or changing assertion identifiers and review fingerprints. The inventory is
now required to preserve retired archive provenance and must travel with the data.
