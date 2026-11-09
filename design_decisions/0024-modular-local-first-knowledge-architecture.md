# ADR 0024: Evolve KNOT as a modular, local-first knowledge system

- Status: Proposed
- Date: 2026-11-05
- Implementation: Partial; bounded refactors separately accepted in ADRs 0036 and 0037
- Documentation reviewed: 2026-11-07
- Extends: ADRs 0002, 0014 and 0019–0023
- Preserves: ADRs 0003, 0007–0013 and 0016–0018
- Supersedes: None

## Context

KNOT is a local Python application with native writing, reviewed assertions, source
provenance and bounded retrieval. Its original modules contained working dependency
cycles and repeated preparation/verification work. File size alone does not justify
services or a new storage system; ownership and measured costs are the useful boundaries.

This record proposes a broader architecture. ADRs 0036 and 0037 separately authorise
and implement a narrower refactor. Their feature packages are the current structure;
the ports, specialised indexes and publication protocol below remain proposals.

## Proposed decision

Retain a modular monolith: one local application with cohesive responsibilities and
one authoritative dataset per selected store. Keep free-form notes useful without
classification or extraction. AI assistants consume scoped evidence through adapters;
they are optional and do not own the knowledge.

Use ports and adapters only at concrete I/O boundaries where replacement or testing
needs justify a contract. Ordinary functions and data records are sufficient until
another implementation is needed. Do not add a repository hierarchy or framework
merely to impose a diagram on the application.

### Proposed responsibilities

| Boundary | Owns | Excludes |
| --- | --- | --- |
| Knowledge rules | Identity, review/lifecycle, provenance and revision semantics | Transport, provider calls and ranking |
| Persistence | Exact bytes, manifests, registries, RDF encoding and safe publication | Relevance scoring and implicit acceptance |
| Retrieval | Scoped traversal, candidate ranking, evidence verification, budgets and omissions | Authoritative writes and autonomous follow-up |
| Discovery | Explainable subject suggestions and caller-selected investigation | Persistent inferred relationships without review |
| Application coordination | Use-case ordering and shared request budgets | Duplicate domain policy or backend query implementations |
| Interfaces | CLI/configuration, SDK framing and rendering | Direct authoritative mutations or grant widening |

Keep shared hashing, vocabulary, tokenisation and response encoding independent of
orchestrators. Discovery may reuse retrieval engines, but retrieval must not depend
on discovery orchestration. Separate review replay from review mutation. Preserve
existing external entry points while new internal code uses canonical packages.

### Authority and publication

Retain source bytes, manifests, committed registry membership, assertion graphs,
reviews, identity decisions, ledgers and cited extracted text. File suffixes and
generation methods do not determine disposability. The query store is a projection;
native RDF navigation is rebuilt from committed revisions. Use the
[dataset retention rules](../docs/datasets.md#files-and-ownership).

Current per-file atomic replacement does not make a multi-file rebuild transactional.
A future generation manifest or recovery journal could prevent partial publication,
but must define crash recovery, concurrent writes, hash guards, compatibility and
backup semantics before adoption. Never infer registry membership from orphan files.

### Read models and performance

Measure preparation, evidence I/O, ranking and package selection separately before
introducing caches. A persistent Oxigraph view, SQLite full-text index or vector index
would be disposable derived state, never a new authority. Any cache must be keyed by
dataset identity, source/review generation, relevant configuration and access scope.
Fail closed on incompatible or stale state; retain a tested rebuild path.

An index must not leak denied source text, metadata, counts or ranking signals.
Do not hide a backend's semantics behind a universal query language. Keep SPARQL
where useful and test each replacement against current citation/review contracts.
Larger histories and multiple writers are anticipated pressures, not demonstrated
evidence that a database migration is already necessary.

## Alternatives

- Keep all current coupling: lowest immediate effort, but changes continue to cross ownership boundaries.
- Introduce microservices: independent deployment adds operational and consistency costs without a demonstrated need.
- Adopt a broad framework or new database now: more uniform abstractions, but a larger migration surface and weaker evidence of benefit.
- Refactor existing boundaries incrementally: fits current deployment and retains behavioural comparisons.

## Consequences and invariants

More explicit boundaries can reduce coupling but add coordination and compatibility
code. Keep cohesive lifecycles together and avoid a class per concept. Any increment
must preserve stable IDs, exact source bytes, review replay, current/granted revision
semantics, access filtering, deterministic output and bounded evidence packages.

Use synthetic fixtures, exact response comparisons, import-boundary checks and
measured scenarios. Private developer-assessed experiments inform questions but do
not establish independent relevance validation or production-scale performance.

## Implementation and remaining decisions

The shared helpers, retrieval engine boundaries and review separation in ADR 0036,
and feature-package layout in ADR 0037, are implemented. This proposal as a whole
is not accepted merely because those increments were delivered.

Separate decisions remain necessary for persistent indexes, a publication journal,
schema migration, external editing, multi-writer coordination or remote hosting.
The [current architecture](../docs/architecture.md) describes delivered behaviour;
the [release guide](../docs/release.md) records tool/data separation work.
