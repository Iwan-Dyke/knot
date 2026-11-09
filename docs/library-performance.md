# Library performance validation

The new interface is an offline file. Lazy DOM rendering and bounded graph layout
reduce interactive work, but the full embedded payload still loads. These measurements
describe synthetic browser fixtures, not export-generation speed or private datasets.

## Reproduce

Run the normal Python/JavaScript checks, then the optional browser checks using an
external Playwright installation and its downloaded browsers:

```sh
just check
node scripts/test_library.cjs
node scripts/test_library_browser.cjs chromium
node scripts/test_library_browser.cjs firefox
node scripts/benchmark_library.cjs chromium
node scripts/benchmark_library.cjs firefox
```

Set `NODE_PATH` and `PLAYWRIGHT_BROWSERS_PATH` to that installation when necessary;
Linux systems also need the browser's system libraries. No npm dependency or browser
runtime is included in KNOT's application package. The scripts report temporary
artifact directories containing HTML, screenshots or raw JSON measurements.
The Library benchmark blocks HTTP(S) requests in every cold and warm context,
records attempted URLs in `blocked_requests` and fails if any are observed.

The legacy PyVis benchmark requires an explicit exported HTML input:

```sh
node scripts/benchmark_viewer.cjs /path/to/legacy-graph.html
# Optionally choose a local artifact directory and repetition count.
node scripts/benchmark_viewer.cjs /path/to/legacy-graph.html /tmp/knot-legacy-benchmark 3
```

Its default output is a new private temporary directory, printed before measurement.
It does not select a dataset or assume a `data/` folder in the checkout. Benchmark
pages and screenshots contain the input's evidence; keep personal exports and their
artifacts outside the public tool. A supplied output directory is reused.

`tests/library_scale_fixture.py` uses seed 20261108 and two profiles:

| Profile | Notes | Entities | Claims | Note links | Export bytes in measured run |
| --- | ---: | ---: | ---: | ---: | ---: |
| M | 1,000 | 3,000 | 10,000 | 3,000 | 14,938,129 |
| L | 5,000 | 10,000 | 50,000 | 15,000 | 71,364,699 |

Bodies are approximately 2 KiB, with occasional 100 KiB bodies. Fixtures include
overlapping themes, duplicate labels, isolated notes, directed cycles and a
high-degree hub. They are presentation test records, explicitly labelled synthetic;
they are not a replacement for the verified exporter tests. The smaller
`data-examples/` fixture exercises real note creation, revisions, curation, claims,
review corrections and provenance through existing APIs.

## Observed results — 2026-11-08

Reference environment: AMD Ryzen 9 5950X, approximately 32 GiB exposed RAM,
Linux/WSL2, headless Chromium 141.0.7390.37 and Firefox 142.0.1, 1500 × 1000 viewport,
no CPU throttling. Each profile uses 20 fresh browser contexts and 50 warm actions.
The operating-system file cache is **not** cleared between opens.

| Operation, p95 milliseconds | Chromium M | Chromium L | Firefox M | Firefox L |
| --- | ---: | ---: | ---: | ---: |
| Initial search screen ready | 532 | 3,532 | 491 | 1,637 |
| Metadata search computation | 3.4 | 12.7 | 4 | 13 |
| Body search computation | 2.7 | 11.1 | 4 | 9 |
| Open note and paint | 30.7 | 31.6 | 31 | 36 |
| Focus graph and paint | 40.9 | 50.3 | 59 | 73 |
| Switch back to Library and paint | 33.7 | 33.7 | 33 | 45 |

No graph instance starts on an unselected initial page or a direct Library route.
The subsequently added **Live network** and Focused mode's optional **Live layout**
start only on explicit selection and are outside these measurements.
Local graphs stay within 100 records and 300 connections. Result/connection pages
mount at most 100 rows each. These runs used the default static Focused layout;
they do not measure animation settling time. They meet the provisional
reference-machine targets in [ADR 0047](../design_decisions/0047-unified-knowledge-library-and-graph-exploration.md).

Search computation timings exclude the UI's 120 ms debounce and result painting.
Reader/graph/switch timings include two animation frames. Warm graph measurements
mix the first construction with later changes of focus; they are not 50 cold graph
constructions. Chromium's p95 sampled JS heap was approximately 42 MB / 123 MB for
M/L; Firefox exposes no equivalent through this harness. These samples are neither
peak memory nor total browser resident memory.

Browser checks cover offline operation, shared selection, history, citations, Org
rendering, accepted-only/associated-note filtering, isolated roots, session recents
and a 360 px viewport. Later regression checks also cover spacing, separate motion
settings for each graph mode, reduced motion and a dense synthetic neighbourhood.
Those checks do not replace the recorded scale benchmarks. Manual screen-reader
review and broader device testing remain necessary
before claiming WCAG conformance or universal performance guarantees. There is no
mobile performance promise, and full-network layout is outside the bounded target.

Record new runs when the model, renderer or reference environment changes. Keep raw
results outside the dataset. If payload/startup costs become unacceptable, revisit
optional local serving rather than adding another authoritative store.

## Idle validation

Idle renders at most 20 records/40 connections at rest and a 40/80 union during
travel. Coordinates persist for all discovered records, bounded by the snapshot's
record count, and are released on Exit. The measurements above predate Idle and do
not establish animation or long-session performance.

The model checks exercise 10,000 synthetic selections, long chains/cycles, content-free
bridges, provenance selection and retained geography after more than 200 discoveries.
Another 6,000 steps across 12 reproducible generated graphs verify filtered adjacency,
parallel edges, self-links, repeated labels, missing endpoints, chain termination and
input immutability. Content checks retain evidence qualifications, skip missing source
records and exclude summaries outside the chosen content filters.

The phase clock checks pause/resume progress and remaining reading time, duplicate
starts, cancelled arrivals, rendering errors, delayed frames, reduced-motion completion
and drawing time within phase timing. These fast checks run through `just check`
when Node.js is available; a missing Node.js executable is reported as a skipped test.

The browser suite checks actual vis-network camera coordinates along an existing
edge, unchanged world coordinates, fixed zoom, progressive node/edge opacity and
screenshots at focus, reading, mid-travel and arrival. It exercises several connected
steps, a missing-excerpt bridge, a cycle, a disconnected region and a dense hub.
It also retains accelerated repeated-visit, visibility, reduced-motion, empty/singleton,
full-screen, separate-window and manual-context restoration checks. Outbound HTTP is
blocked and reported, and the embedded model is compared before and after traversal.

For Idle changes, run `just check`, `just test-idle chromium` and `just test-idle firefox`.
The browser recipes require the optional external Playwright installation described
above and run `node scripts/test_library_browser.cjs BROWSER --idle-only`.
`scripts/test_idle_browser.cjs` supplies the cinematic canvas checks; it is loaded by
that runner. These synthetic fixtures are browser projections, never authoritative
knowledge records. Screenshots are written to the runner's temporary artifact folder.

The lifecycle cases cover depth changes during a region fade, filtering all records
out during travel and recovering, hidden-window suspension mid-journey, reduced motion
while paused, keyboard source inspection, Space/Escape and full-screen denial. Exit,
browser Back and explicit view switching restore manual coordinates and selection
without allowing cancelled phases to overwrite them. Repeated entry reuses one canvas
and renderer. An eight-hour accelerated run in reduced-motion mode checks that actual
displayed notes continue changing while DOM elements, history, recents and coordinate
caches remain bounded; this is a functional endurance check, not a heap benchmark.

On 2026-11-09, `just check` passed all 528 tests. The expanded Idle browser suite
passed in Chromium and Firefox, including canvas movement, progressive label pixels,
stable world coordinates, interrupted transitions and eight accelerated hours in each
browser. The full Chromium Library suite also passed before this test expansion.
These are functional results, not frame-rate or memory benchmarks.

The real-time eight-hour soak, reference-machine frame/heap budgets and physical
second-monitor/screen-reader assessment in ADR 0048 remain outstanding. Accelerated
checks do not establish leak freedom, sustained animated frame rate or those performance targets.
