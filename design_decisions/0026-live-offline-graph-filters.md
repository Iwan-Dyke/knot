# ADR 0026: Filter the offline graph interactively

- Status: Accepted
- Date: 2026-11-05
- Implementation: Implemented
- Documentation reviewed: 2026-11-07
- Extends: ADRs 0016 and 0017

This describes the viewer now launched with `knot view --legacy`.
[ADR 0047](0047-unified-knowledge-library-and-graph-exploration.md) adds the default
Graph/Library interface and shares its filtering semantics. Control labels and
layout behaviour differ; see the [current viewer guide](../docs/viewer.md).

## Context

The static export already contains claim evidence, review states and overlapping
themes, but exploring another subset requires a new CLI export. The user requested
live entity and theme switches and useful navigation improvements.

## Decision

Keep the existing PyVis/vis-network export and inline its local controls, styles and
JavaScript. The browser works on an immutable copy of the exported records; applying
filters changes visibility without rewriting identifiers, sources or reviews. A small
pure filtering function is shared by the browser and dependency-free Node tests.
No server, frontend framework, network request or new runtime dependency is required.

Combine choices within a group with OR and groups with AND. An entity is eligible
when enabled and at least one of its types is selected. Claims require both endpoints,
a selected review status/origin, the optional kind and a selected theme membership.
Unthemed claims have an explicit choice; selecting no choices shows no matches.
Same-label entities retain separate IDs and controls.

Themes filter individual claims, not all edges of incident entities. Theme navigation
requires a currently visible supporting claim and remains separately reviewed. Hide
theme hubs in accepted-only views, independently of whether a theme is used to filter
claims. Theme membership and claim acceptance must not acquire each other's authority.

Provide entity search, one-hop focus, visible counts, fit/reset controls and optional
edge labels/theme hubs. Search can enable matches or isolate them with **Hide
non-matches**; isolation replaces entity visibility without changing other facets.
Use static curves and pause physics after initial arrangement;
filters preserve positions by default. A spacing slider adjusts the existing
[spring and repulsion controls](https://visjs.github.io/vis-network/docs/network/physics.html),
with a roomier initial setting and overlap avoidance. Explicit rearrangement or a
spacing change animates visible frames for up to four seconds while keeping the camera
still. Opt-in live layout keeps physics enabled across filtering and dragging; Pause
disables it immediately. Hidden nodes and edges remain outside the simulation.
This keeps steady reading as the default while allowing interactive untangling,
at the cost of additional rendering work when live layout is enabled.
A persistent inspector shows
literal source text and provenance; entity and connection buttons offer a keyboard
route to evidence without requiring canvas or hover interaction.

The original inspector-only note presentation below is superseded by
[ADR 0035](0035-notes-in-the-unified-graph.md): all current notes now also appear as
nodes, with saved note links and entity associations in the unified graph.

Show current curated native notes above an entity's connections, using ADR 0027's
derivation metadata and the existing adapter's canonical navigation associations.
Do not infer associations from labels or co-occurrence in a source. Verify each
curated revision and its source pins through the retrieval evidence reader before
exporting. Embed each linked note once in a separate inert JSON payload; notes add
no graph nodes, edges or physics work. Exclude unassociated notes and notes whose
entities are outside the export.

Open the first note by default, show its author and knowledge kind, and keep source
quotations, qualifications and revision identifiers expandable. Render note bodies
as literal text with preserved line breaks, avoiding executable HTML or a new markup
dependency. Preserve expanded sections when filters change. Notes are readable
context independent of claim filters and acceptance; connection evidence retains its
exact source text. This adds snapshot size in exchange for offline reading and
verification without additional browser requests.

Reuse entity controls and precomputed search text across filter changes. Avoid setting
physics options again when already paused: vis-network redraws even for a redundant
pause. Keep the exported data and the existing renderer instead of adding a new graph
library or worker protocol.

Use level-of-detail rendering only for theme navigation. Below 0.25 zoom, replace its
short dots with solid lines at the original colour, opacity and width; above 0.35,
restore the original dots. The gap prevents repeated style updates near the boundary.
Check scale on drawing so wheel zoom, fit and focus all work, and batch changes on
the next animation frame. Preserve inferred-claim dashes, node glow, labels, curves,
positions and evidence at every scale. The tradeoff is a small overview texture change
for substantially less raster work; close views retain the original styling.

## Tradeoffs and limits

An offline snapshot fits existing tooling and is easy to reopen, but must be regenerated
after data changes. CLI export filters bound the available dataset; resetting live
filters cannot restore excluded claims. Hidden records remain embedded in the file,
so filtering is neither redaction nor an access boundary. This increment adds no
editing, review actions, server synchronisation or saved filter preferences.

ADR 0028 extends this presentation with preferred-name aliases in search and literal
assertions as subject attributes. Attributes share claim filters and evidence review,
but add no value nodes or physics edges. Complete definitions remain inspectable.

## Verification

Synthetic checks cover overlapping/absent themes, duplicate labels, filter intersections,
empty selections, focus, separate theme review and unchanged source records. Optional
Playwright checks exercise real controls, stable paused coordinates, increasing node
separation without a zoom change, live filtering, immediate pause, keyboard navigation,
literal handling of hostile source text, offline loading and narrow screens. Keep
browser screenshots and exported personal evidence outside tracked source files.
Browser checks also cover reusable entity controls, theme detail across programmatic
camera changes, threshold hysteresis and unchanged claim styling/evidence.
Curated-note checks cover current-head selection, shared notes, canonical associations,
same-label non-association, excluded/unlinked notes, source-integrity failure and
literal rendering of hostile text. Browser checks exercise canvas/list selection,
expandable sources, preserved open sections across filtering and narrow-screen reading.

On 2026-11-05, three alternating before/after runs of `scripts/benchmark_viewer.cjs`
used the same 627-node, 2,927-edge snapshot (1,929 theme links), Chromium 141 with
SwiftShader under WSL2, a Ryzen 9 5950X and a 1440×1000 viewport. Median results:

| Measurement | Before | After |
| --- | ---: | ---: |
| Scripted pan/zoom frames per second | 10.4 | 30.4 |
| Theme-filter handler | 103.4 ms | 66.0 ms |
| Theme-filter response through two animation frames | 316.4 ms | 133.5 ms |
| Entity-search handler | 7.5 ms | 4.0 ms |
| Initial load and layout | 2,818 ms | 2,845 ms |

These are comparative software-rendering measurements, not desktop FPS guarantees;
initial loading did not materially improve. A representative close view was
pixel-identical after fixing coordinates and camera, and claim records were unchanged.
The overview retains all links with the small texture difference described above.
