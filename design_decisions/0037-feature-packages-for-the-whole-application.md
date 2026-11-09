# ADR 0037: Organise the whole application into feature packages

- Status: Accepted
- Date: 2026-11-07
- Implementation: Implemented
- Documentation reviewed: 2026-11-07
- Extends: ADR 0036
- Supersedes: ADR 0036's top-level implementation and compatibility-file layout

## Context

Extracting retrieval components clarified dependencies but left most of `src/knot/`
as a flat directory. The owner requested organisation of the entire directory,
including existing implementations and assets, rather than another partial split.
Existing imports, module commands, benchmark instrumentation, source paths inside
the dataset and optional MCP loading must continue to work.

## Decision

Group every implementation by responsibility. The package root contains only its
initialiser; Python's generated `__pycache__/` is not application source.

| Folder | Owns |
| --- | --- |
| `writing/` | Native note persistence, guided authoring, navigation, source projection and Git sync |
| `graph/` | RDF helpers, query loading, organisation, themes and ontology |
| `curating/` | Candidate publication, relationship rules, provenance, display labels and evidence accounts |
| `ingestion/` | Archive inventory, migration and framework import |
| `retrieval_engine/` | Retrieval service, graph/text search, discovery, ranking, evidence and response contracts |
| `reviewing/` | Review authoring and immutable event replay |
| `interfaces/` | Note CLI, MCP server/authoring adapter and access scopes |
| `presentation/` | Viewer export and its HTML, JavaScript and CSS assets |
| `diagnostics/` | Quality checks and retrieval benchmarks |
| `shared/` | Atomic storage helpers, vocabulary values and text extraction/segmentation |
| `_compat/` | Historical module aliases and command entry points only |

Feature packages import each other directly. The retrieval service is now
`knot.retrieval_engine.service`; note persistence is `knot.writing.notes`, for
example. Keep cohesive existing workflows together rather than creating more
layers or introducing new class hierarchies during a directory move.

### Compatibility without a cluttered root

The root initialiser adds its own `_compat/` directory to the package search path.
Python therefore still finds `knot.notes`, `knot.review` and the other old names.
Each shim aliases its implementation module in `sys.modules`, preserving module
identity and monkeypatches used by tests and experiment instrumentation. Executing
a legacy module with `-m` calls the original main function and retains its exit
handling, including the quality command's nonzero error status.

This is a local package-path extension, not a global import hook. Imports stay
lazy: importing KNOT does not import MCP, load a dataset or eagerly initialise all
features. New internal imports must not depend on the compatibility layer. The
launcher and `just` recipes use the canonical feature paths; their command names
and arguments are unchanged.

The tradeoff is maintaining a small alias per historical module and a package-path
extension. This preserves callers without leaving dozens of shim files at the
root. Removing those aliases would be a separate API-breaking decision.

### Resources and diagnostics

The ontology moves byte-for-byte into `graph/`; its resource path is shared by
organisation, guided authoring and MCP. Viewer assets move byte-for-byte beside
the viewer implementation. Package-data declarations include these assets, and
the JavaScript test harness uses the new viewer path.

Benchmark implementation fingerprints now scan Python files recursively and use
relative paths, so they include the actual engines instead of only a facade or
the diagnostics directory. The synthetic evaluation and historical reproduction
scripts use the same recursive discovery. Existing recorded results and frozen
hash manifests remain historical artifacts and are not rewritten.

## Verification and scope

Architecture tests reject files at the root other than `__init__.py`, check that
implementations never import legacy modules, verify every compatibility module's
identity, and launch all twelve legacy module commands with `--help`. Existing
tests cover note capture, scoped MCP, review replay, generated views, launcher
installation, source integrity and exact retrieval responses.

The completed reorganisation passes `just check`: lint, formatting and 425 tests.
All four moved ontology/viewer assets are byte-identical. An AST comparison of
the newly moved implementations found 138 unchanged functions/classes apart from
import routing; four functions change only resource lookup or fingerprint file
discovery. Tracked data and untracked data membership remain unchanged.

Use `just check` for the full suite. No knowledge data, identifiers, evidence,
grants, schemas or dependency versions change. The package-data configuration
describes existing assets; it does not install dependencies. Revert code, tooling
and documentation together to roll back; there is no data migration.
