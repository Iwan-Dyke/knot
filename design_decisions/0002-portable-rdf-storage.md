# ADR 0002: Keep RDF files authoritative and rebuild the query store

- Status: Accepted
- Date: 2026-11-03
- Implementation: Implemented
- Documentation reviewed: 2026-11-07
- Related: [ADR 0004](0004-local-semantic-store-and-assistant-workflow.md)

Dataset-location policy was temporarily changed by ADR 0008. The public tool and
private datasets are now separated under [ADR 0038](0038-open-source-tool-and-private-datasets.md).
Local folder selection and optional standalone Git repositories are implemented in
[ADR 0043](0043-local-datasets-and-optional-git.md); authoritative personal data lives
outside the application checkout.

## Context

Personal knowledge must remain inspectable, portable and independent of a database
or LLM provider. Source documents and their evidence must survive rebuilding or
replacing the query engine. Maintaining files and a database as equal authorities
would introduce synchronisation and recovery problems.

## Decision

Use TriG as the authoritative dataset format because it preserves named graphs.
Use Turtle for a standalone vocabulary if needed. Use `pyoxigraph` to load files
into a temporary local store and execute SPARQL. Rebuild that store from the files
for each invocation in the proof of concept; introduce an on-disk cache only when
measured rebuild costs justify it.

Knowledge changes must be persisted to the authoritative files. Query-store edits
alone are not durable knowledge changes. Treat file writes as replacements through
a temporary file in the same directory, preserving the existing file on failure.
Report parse and write failures explicitly; never silently load a partial dataset.

Use stable IRIs for entities, assertions and document revisions. Avoid generated
blank-node identifiers for records that require stable references or useful Git
diffs. Test semantic round trips as quad equivalence, independently of formatting.
Choose deterministic formatting before adding a general graph-editing command;
an arbitrary database dump is not assumed to produce reviewable diffs.

Keep application code and synthetic fixtures in the public project repository.
Keep personal datasets and private source snapshots in a separate user-controlled
directory or private repository. Store private source locators there, not in public
fixtures. Git is optional for personal data and is not a privacy boundary: its
history can retain removed content.

## Alternatives and consequences

- A database as authority simplifies updates and can scale better, but weakens the
  file-first portability and review workflow being tested.
- Turtle alone is simpler for a single graph, but does not retain named-graph
  boundaries needed by the proposed provenance model.
- Loading files for each query avoids cache invalidation and persistent database
  management, at the cost of startup time as datasets grow.
- RDFLib is a viable alternative. A second RDF library adds little to the initial
  load, save and SPARQL requirements; reconsider if interoperability tests require it.
- Concurrent writers, graph-file partitioning and automatic Git operations are
  outside the proof of concept. File replacement alone does not solve concurrency.

## References

- [Pyoxigraph store documentation](https://pyoxigraph.readthedocs.io/en/stable/store.html)
- [RDF 1.1 Primer: datasets and TriG](https://www.w3.org/TR/rdf11-primer/)
