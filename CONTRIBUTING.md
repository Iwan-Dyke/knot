# Contributing to KNOT

Work from a source checkout using the
[README setup](README.md#installation). Keep changes small enough to review and
preserve existing functionality unless the change explicitly revises it.

## Development workflow

1. Read the relevant guide, [architecture](docs/architecture.md), tests and ADRs.
2. Explain the intended design and tradeoff for a non-trivial change.
3. Use a failing synthetic test where practical, then make the smallest correct change.
4. Run the relevant checks and update the affected usage documentation.

```sh
just test
just lint
just format-check
just check
```

Use `just format` to apply the configured Python formatter. No Docker workflow is
provided. `just test` includes the Node.js model/filter checks when Node is available.
It also isolates dataset selection in temporary configuration, removed on exit.
Tests that exercise configuration must still provide their own temporary
`KNOT_CONFIG` and `KNOT_DATA_ROOT` for direct unittest runs.
Rich markup integration tests require Pandoc; the ordinary storage tests use a
synthetic renderer. Install the `dev` extra to run viewer and MCP tests.

An external Playwright installation and its browser runtimes enable optional
browser checks. Set `NODE_PATH` and `PLAYWRIGHT_BROWSERS_PATH` to that installation
if they are not already discoverable; Linux also needs the browsers' system libraries:

```sh
# Current Graph/Library interface; requires Pandoc and the viewer extra.
node scripts/test_library_browser.cjs chromium
node scripts/test_library_browser.cjs firefox
# Optional local Library editing; synthetic datasets only.
just test-library-authoring chromium
just test-library-authoring firefox
# Supported legacy graph viewer.
node scripts/test_viewer_browser.cjs
```

These scripts generate temporary synthetic fixtures and report their artifact
directories. The Graph/Library checks share `data-examples/` and cover reading,
history, graph filters, spacing, focused/live motion and dense neighbourhoods.
The authoring checks cover saves, conflicts, retries, previews and refresh failures
through the real local server in Chromium and Firefox.
The legacy script also accepts a supplied export; personal HTML makes its screenshots
and results private material too. Performance scripts, profiles and measured limits
are documented in [Library performance](docs/library-performance.md).

### Code-only checks

The behaviour suite runs without `data/` or private experiment outputs. Shared
synthetic evaluation helpers live in `tests/support/`. Retired experiment outcomes
and rejected alternatives are summarised in
[ADR 0042](design_decisions/0042-retire-experiments-and-export-tool-only.md).

Ruff explicitly treats `knot` as a first-party package, including its legacy import
aliases. This avoids cache-dependent import classification. For a release check,
run `ruff check --no-cache src tests scripts` as well as `just check`.
Report environment failures and existing failures separately from new regressions.

Use `just export-code /absolute/path/to/new-directory` to prepare a code-only
checkout for independent checks. See [release preparation](docs/release.md).

## Code and data boundaries

Follow existing feature ownership under `src/knot/`. Prefer ordinary functions and
cohesive modules to new frameworks or interfaces without a second use case. Keep
compatibility imports for existing callers; new internal imports use canonical
package paths. Tests should use temporary synthetic datasets and local test remotes.

Never put personal notes, source documents, quotations, credentials, real grants or
private exports into public examples, issues, screenshots or test fixtures. A graph
filter only changes visibility; an exported HTML file still contains its embedded
data. Preserve exact source bytes and use the note, curation and review APIs for
authorised knowledge changes. See [AGENTS.md](AGENTS.md) for agent workflows.

## Documentation and decisions

Keep the README focused on installation and a small working example. Put workflows
in `docs/`, schema/API detail in `docs/reference/`, and rationale in
`design_decisions/`. Update links and use invented examples with explicit placeholders.
Describe implemented behaviour accurately; put pending work in the release guide
or a Proposed ADR.

Write an ADR for a significant decision or coherent theme, using the
[template](design_decisions/TEMPLATE.md). A module does not automatically need an
ADR. Separate decision status from implementation progress, preserve identifiers,
and link superseding decisions. See the [ADR index](design_decisions/README.md).

## Licence and submissions

Original tool contributions are intended to be distributed under [MIT](LICENSE).
Contribute only material you have the right to submit, preserve third-party
attribution, and disclose new dependencies and their licences. Personal datasets
and private research material remain excluded under [LICENSE_SCOPE.txt](LICENSE_SCOPE.txt).

Describe the problem, resulting behaviour, relevant checks and any remaining limits
in a proposed change. A clean test run does not establish licence clearance or
permission to publish private data. Publication is a separate release step.
