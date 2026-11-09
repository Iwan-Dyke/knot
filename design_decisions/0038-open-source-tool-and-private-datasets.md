# ADR 0038: Publish the tool separately from personal datasets

- Status: Accepted
- Date: 2026-11-07
- Implementation: Implemented for v0.1.0; licensing, documentation, data separation and dataset selection/sync delivered
- Documentation reviewed: 2026-11-08
- Supersedes: [ADR 0008](0008-keep-personal-data-in-knot-repository.md) for the target distribution boundary
- Related: [ADR 0002](0002-portable-rdf-storage.md), [ADR 0034](0034-knowledge-commit-and-push.md), [ADR 0037](0037-feature-packages-for-the-whole-application.md)

Configuration, local setup and standalone Git sync are now implemented by
[ADR 0043](0043-local-datasets-and-optional-git.md). The decision below records
the original distribution direction and its then-pending implementation. The dataset
has been separated, and [ADR 0042](0042-retire-experiments-and-export-tool-only.md)
records the later decision to discard the old local Git metadata instead of retaining
it here. Publication and the final dependency-notice audit remain release work.

## Context

The owner has chosen to prepare KNOT for open-source distribution under MIT while
keeping personal knowledge separately controlled. The existing private checkout
contains both code and data, including historical records and research material.
A new user should be able to understand and run the tool without that dataset.

## Decision

License the original tool under MIT, with explicit exclusions for personal data,
private research and third-party material. Keep the licence declaration and scope
in source and package metadata. Dependency licences remain separately applicable.

Separate the public tool from user-controlled datasets. Preserve the existing
file-first format, relative source locators, stable identifiers and review history.
Core filesystem access should work with local folders; a separate private Git
repository may supply optional versioning. Detailed configuration, initialisation
and sync changes require implementation; they are not delivered by this ADR.

Keep installation and a small working example in the README; put task guides in
`docs/`, API/schema details in `docs/reference/`, and rationale in
`design_decisions/`. Use generic examples and retain ADR identifiers and decision
history. Decision acceptance and implementation progress are separate metadata.

Review the selected tool files and release artifacts before creating a clean
public repository. Retain existing private history separately: deleting `data/`
from a later commit does not remove earlier private content.

## Alternatives

- Publish the existing repository after deleting data: leaves private history and
  material elsewhere in the tree, so it does not meet the intended boundary.
- Keep a mandatory private submodule in the public tool: ties users to repository
  bookkeeping when filesystem access alone is sufficient.
- Keep KNOT private: avoids release preparation but does not meet the owner's chosen direction.

## Consequences

Tool releases and personal knowledge history can evolve independently. Configuration,
packaging, synthetic fixtures and dependency notices need further work. Dataset
relocation must preserve all authoritative records, not just notes or RDF files.
The current Git wrappers remain tied to `<git-root>/data` until explicitly changed.

## Validation and remaining work

Use the [release checklist](../docs/release.md). Verify a fresh install and synthetic
quick start, code-only checks, package contents, documentation links, and a relocated
dataset's hashes, history and review behaviour. This direction does not authorise
publishing the existing private repository or granting broader access to its data.
