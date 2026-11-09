# ADR 0049: Make workflow and presentation boundaries explicit

- Status: Accepted
- Date: 2026-11-09
- Implementation: Implemented
- Extends: ADRs 0036, 0037 and 0048

## Context

The feature packages already provide useful ownership boundaries, but several
functions still combine independent responsibilities. Terminal prompts live beside
draft publication, the note CLI dispatches through a long command chain, and the
browser shell coordinates both DOM rendering and navigation history. Graph styling
branches repeatedly between manual and Idle modes. Quality auditing and text
retrieval contain long sequences whose ordering matters to evidence integrity.

The owner requested a source review and authorised these six refactors. The goal
is to make existing behaviour easier to follow and test, while retaining the
current storage, access, provenance and presentation contracts.

## Decision

Use small functions and explicit owners within the existing packages:

1. Move terminal prompts to `interfaces/console.py` and interactive authoring and
   curation to `interfaces/authoring_cli.py` and `interfaces/curation_cli.py`.
   Keep draft validation, warnings, publication, source choices and provenance
   review text in `writing/`. Retain thin lazy delegates for the historical
   interactive entry points. Existing module aliases keep their identity.
2. Dispatch note commands through a function table, with argparse selecting the
   handler. Delegate specialised commands through a separate table with explicit
   dataset-prefix support and lazy imports. Use a small editor table in guided
   authoring; keep confirmation, publication and recovery in the coordinator.
3. Give `library_navigation.js` ownership of selection, route transitions, browser
   history and Idle entry/exit. A pure transition function decides the route;
   the controller applies lifecycle effects. The shell supplies DOM rendering
   and state capture/restore callbacks. Automatic Idle visits still bypass manual
   history and recents.
4. Use a functional **Strategy** for manual and Idle graph styles in
   `library_graph_style.js`. Both return complete render properties so switching
   modes resets fixed positions, selection styling and opacity. The existing
   graph adapter continues to own one network instance and camera movement.
5. Split `quality.audit()` into ordered graph, note, evidence, semantic,
   association and naming passes. Private dataclasses name shared results. The
   coordinator owns finding accumulation, final counts and diagnostics; a finding
   in an earlier pass does not suppress independent later checks.
6. Split text candidate retrieval into revision selection, verified source
   loading, section extraction and scoring. A private request dataclass carries
   shared references. Keep access checks, verification, scorer fitting, ranking,
   omission accounting and budgets in their existing order.

The function tables are a lightweight form of the **Command** pattern. The audit
and retrieval stages form explicit pipelines with direct calls, not configurable
registries. Dataclasses freeze field bindings, not the mutable stores or counters
they reference. No class hierarchy, plugin protocol or UI framework is needed.

## Alternatives

- **Keep the existing branches and long functions.** Small conditionals remain
  appropriate for validation and local decisions, but the identified dispatch and
  workflow blocks hide ownership and make unrelated changes collide.
- **Introduce command classes and a general state-machine framework.** These
  would add indirection without a present need for interchangeable implementations
  or persisted state. Plain functions express the current transitions and actions.
- **Split every pass into a separate module.** The audit and text stages still
  share substantial context and ordering constraints. Keep each pipeline together
  until independent reuse justifies another boundary.

## Consequences

Terminal interaction can evolve independently of draft publication. Navigation
effects have one owner, and graph style changes no longer mix with network updates.
Audit and retrieval coordinators expose their execution order directly.

There are more named functions and several small modules to navigate. Compatibility
delegates are deliberate exceptions to the authoring dependency boundary; removing
them requires a separate API decision. This does not make every application import
acyclic or move every historical CLI out of its feature package.

Valid command forms, persisted drafts, audit finding IDs/order and retrieval wire
responses remain compatible. Unsupported dataset-prefix combinations receive an
argument-parser error instead of falling through to an unrelated handler.
Knowledge files, grants, schemas, dependencies and public retrieval APIs do not
change. This is not a performance optimisation or a new storage transaction model.

## Validation and rollback

- Exercise delegated commands with their supported dataset-prefix forms, existing
  capture/curation workflows, cancellation and resumed publication.
- Enforce the authoring boundary with an architecture test, allowing only the
  named compatibility delegates. Retain legacy import and command checks.
- Compare complete audit reports before and after extraction on six synthetic
  datasets: empty, healthy, semantic warnings, damaged evidence, curated notes and
  reviewed assertions. Retain an error-recovery case covering later warnings.
- Run existing frozen retrieval response, ranking, evidence, access and budget
  tests without regenerating their expected outputs.
- Test pure route decisions and complete style resets. Run the actual offline
  viewer in Chromium and Firefox, including history, pinned evidence, camera
  movement, stable geography, fades, interrupted transitions and accelerated Idle
  endurance. Accelerated playback does not establish real-time memory stability.
- Run `just check` for lint, formatting and the complete repository suite.

Roll back code, tests and documentation together. No dataset migration is needed.
