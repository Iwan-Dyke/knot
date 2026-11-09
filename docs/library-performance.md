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
