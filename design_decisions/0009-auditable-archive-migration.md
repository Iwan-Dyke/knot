# ADR 0009: Track migration coverage separately from claim review

- Status: Accepted
- Date: 2026-11-03
- Implementation: Implemented
- Documentation reviewed: 2026-11-07
- Extends: ADR 0004 (the user now requests migration of the full archives)

## Context

The archives overlap, contain revisions of the same notes and mix document formats.
A successful file copy does not demonstrate successful text extraction or semantic
conversion. The user needs to know exactly what has and has not migrated.

## Decision

The clarified target is the RDF knowledge base. Preserve all source text and add
source-checked semantic candidates in the same migration, with selective semantic
coverage and human review tracked separately.

Inventory every archive member and retain archive and content hashes. Preserve every
distinct source revision once while retaining all archive occurrences. Never count
duplicate copies as independent evidence. Record explicit errors or exclusions;
do not silently omit unsupported formats or documents without obvious claims.

Keep separate progress stages for verified source preservation, text extraction,
output conversion and semantic coverage. Human acceptance is separate from migration
completion: accurately migrated assertions may still be unreviewed.

Use a machine-readable ledger under `data/migration/`. Link each output to its input
revision and transformation version. Reruns verify existing snapshots and reuse
stable identities. A stage is complete only after its outputs pass the applicable
checks. Never infer semantic completeness from a file count or from copied text.

## Alternatives and consequences

- A checklist of filenames is easy to read but cannot detect changed content,
  revision collisions or incomplete transformations.
- Hash-based accounting makes repeat runs verifiable and supports an explicit
  coverage report. It cannot prove that an AI found every meaningful relationship;
  semantic review must remain visible as a separate task.
