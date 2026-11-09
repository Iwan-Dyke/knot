# ADR 0036: Separate retrieval coordination from reusable engines

- Status: Accepted
- Date: 2026-11-07
- Implementation: Implemented
- Documentation reviewed: 2026-11-07
- Extends: ADR 0024's modular monolith direction
- Preserves: Existing commands, Python entry points, storage and evidence contracts

## Context

The repository contains a single local application with useful functional modules.
Repository count and file size alone do not justify separate services. The review
found three concrete maintenance problems in the dependency graph:

1. **Retrieval coordination and reusable implementation depend on each other.**
   Previously `retrieval.py` dispatched to `search.py`, which imported graph assembly,
   source verification and response helpers back from retrieval. Selection imported
   retrieval's wire codec; source selection imported search's tokenisation while
   search called source selection. Discovery scoring also depended on search.
   These cycles made independent changes and testing harder, although deferred
   imports kept execution working.
2. **Shared rules and storage helpers are owned by higher-level workflows.**
   Hashing and atomic JSON publication lived in archive inventory. Note kind/type
   validation and lexical scoring imported the knowledge organisation workflow for
   constants and IRI names. These dependencies unnecessarily pulled unrelated
   workflows into consumers.
3. **Query loading depends on the review writer.** Query loading imported replay
   from `review.py`, while review authoring imported query loading. Replay needs
   immutable event reading and fingerprint checks, not authoring or CLI handling.

The existing tests cover note revision publication, source preservation, review
replay, identity handling, scoped access, retrieval budgets, MCP and presentation.
No replacement persistence framework or new deployment boundary is needed to
address these findings.

## Decision

Keep a **modular monolith**: one process and one authoritative dataset. Extract
cohesive functions without changing their algorithms, signatures or data formats.
Use a **compatibility facade** for historical imports, with explicit re-exports
pointing to the same objects rather than copied implementations.

| Module | Responsibility |
| --- | --- |
| `retrieval.py` | Public retrieval dispatch and historical Python imports |
| `retrieval_engine/cli.py` | Retrieval argument parsing and terminal output |
| `retrieval_engine/context.py` | Eligible graph/source preparation and label lookup |
| `retrieval_engine/graph.py` | Bounded graph traversal and assertion package assembly |
| `retrieval_engine/search.py`, `retrieval_engine/selection.py`, `retrieval_engine/source_selection.py` | Ranked candidates, package selection and source routing |
| `retrieval_engine/evidence.py` | Verified source reading, exact citations and request source budgets |
| `retrieval_engine/response.py` | Wire encoding, exact size accounting, quotation sharing and pruning |
| `retrieval_engine/policy.py` | Traversal policy values and predicate validation |
| `retrieval_engine/ranking.py` | Pure lexical scoring shared by search and discovery |
| `reviewing/state.py` | Immutable review event reading, inspection and replay |
| `shared/storage.py` | Shared hashing and atomic JSON publication |
| `shared/vocabulary.py` | Knowledge kinds, entity types and IRI local names |

Discovery calls retrieval components; engines do not import discovery or interfaces.
Response formatting and policy values have no application dependencies. Scoring
depends only on vocabulary. Query loading calls review replay; the writer continues
to coordinate validation, loading and publication. Existing importers and authoring
workflows use storage helpers directly.

The existing `just` commands remain valid. `python -m knot.retrieval` delegates to
the CLI adapter. Imports including `knot.retrieval.Policy`, `retrieve`, `lookup`
and `serialise` remain available. Historical private helpers used by experiments
are also re-exported. New implementation code imports helpers from their owner.
Tests that patch a function's globals must patch its owning module: the response
codec call-count test now patches `knot.retrieval_engine.response.serialise`.

Implementation folders are `retrieval_engine/`, `reviewing/` and `shared/`, each
with an import-safe `__init__.py`. The root retains public entry points and
compatibility facades such as `search.py`, `discovery.py` and `review.py`.
These moved legacy modules alias their implementation module, preserving imported
attributes and module-level instrumentation used by the frozen benchmark runners.
Internal imports target the implementation packages directly. Existing
`python -m knot.review` and `python -m knot.retrieval` commands remain unchanged.
Architecture checks scan these folders recursively.

## Tradeoffs and retained boundaries

More files make ownership explicit, at the cost of extra imports and compatibility
aliases. Each extraction has an independent responsibility or breaks a demonstrated
dependency cycle. A generic repository interface, dependency injection framework,
service deployment or package hierarchy would add ceremony without an alternative
implementation to support.

This is not a claim that the entire application now has an acyclic import graph.
Native note persistence, projection, navigation and transitive provenance still
cooperate through deferred imports. Keep their tested lifecycle together rather
than changing publication or verification while reorganising retrieval. Oxigraph
remains the concrete graph adapter; no backend-neutral query abstraction is added.
The broader read-model and persistence proposals in ADR 0024 remain proposals.

Preparation still loads original and projected graph views. This change makes no
latency, memory, retrieval relevance or crash-recovery improvement claim. Those
require their own measurements and, for publication changes, failure experiments.

## Verification and rollback

The pre-change `just check` baseline passed 416 tests outside the restrictive
sandbox. The sandbox-only attempt failed because MCP's asyncio wake-up sockets
were denied; it was not an application failure.

Before extraction, ten exact wire-response SHA-256 values were frozen using the
synthetic retrieval fixture. They cover graph/text/hybrid at two budgets, unranked
graph, accepted-only retrieval, discovery and gathering. These supplement the
existing semantic and access tests; they are compatibility checks, not relevance
benchmarks. Architecture tests enforce shared-leaf and engine dependency direction
and verify that compatibility exports are the original objects.

The final `just check` passed lint, formatting and all 421 tests, including MCP.
An AST comparison also confirmed that the 26 extracted functions/classes retain
their executable bodies apart from import routing. Tracked `data/` files are
unchanged, and no new untracked data files were created.

Run `just check` for lint, formatting and the full suite. No data migration,
dependency installation, lockfile change or personal-data edit is part of this
refactor. Rollback restores source and test files only; no data rollback is needed.
