# ADR 0008: Keep personal data in this repository initially

- Status: Superseded
- Date: 2026-11-03
- Implementation: Replaced by external datasets; legacy mixed-repository sync remains supported
- Documentation reviewed: 2026-11-08
- Superseded by: [ADR 0038](0038-open-source-tool-and-private-datasets.md)
- Partially supersedes: ADRs 0002, 0003, 0004 and 0006 (dataset location only)

The following records the original private-checkout decision. The dataset is now
separate from the application. ADR 0038 establishes that distribution boundary;
[ADR 0043](0043-local-datasets-and-optional-git.md) implements external dataset
selection and standalone Git synchronisation. This record is not current setup guidance.

## Context

The user intends to use this KNOT repository as a private repository containing
both the application and personal knowledge. Separating the data into another
repository is deferred until there is a reason to do so.

## Decision

Keep personal source snapshots, generated identity mappings and authoritative RDF
under `data/` in this repository. Use `data/sources/` for unchanged source revisions
and `data/graph/` for RDF, including identity and provenance metadata. Resolve source
locators relative to the dataset root so the directory can be moved as a unit later.

Keep application code, synthetic examples and automated test fixtures outside
`data/`. Tests should not depend on private documents. Retain the file-first storage
and rebuildable query-store decisions; do not treat a database cache as authoritative.

This replaces earlier requirements to keep personal data outside this repository.
It does not change the user-directed assistant access policy or authorise automatic
commits, pushes or changes to GitHub visibility.

## Alternatives and consequences

- A separate private data repository provides an immediate separation from code,
  but adds management overhead before it is needed.
- Keeping code and data together simplifies the initial workflow. The dataset
  directory can be separated later, but moving files does not remove data from
  existing Git history. Any future public release must account for that history.
- The repository is intended to remain private while it contains personal data;
  remote visibility must be verified before publishing that data.
