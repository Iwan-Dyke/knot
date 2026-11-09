# Prepare an open-source release

KNOT v0.1.0 separates the MIT-licensed tool from independently controlled personal
datasets. This checklist records release verification and checks to repeat for
future releases; it does not authorise publication of a dataset or working tree.

| Area | Current state | Remaining work |
| --- | --- | --- |
| Tool licence | MIT text, scope exclusions and package metadata are present | Check final artifacts and bundled/transitive dependency obligations |
| Documentation | README, task guides and ADR index describe the tool | Review examples and links again against the final release tree |
| Dataset selection | Shared configuration, local init/use and Git clone delivered | Validate supported installation environments |
| Data history | Dataset lives in a separate private checkout; v0.1.0 starts from reviewed tool files without the old application history | Keep datasets and generated private artifacts out of future commits |
| Git sync | Standalone dataset repositories and initial push supported; legacy layout retained | Validate real-host authentication in the release environment |
| Tests and experiments | Experiments removed; synthetic helpers live in `tests/support/` and shared examples in `data-examples/`; checks run without private data | Keep new fixtures synthetic and review final release contents |
| Distribution | Temporary builds checked package metadata/assets; an installed-wheel synthetic viewer smoke test passed | Repeat against final release artifacts and supported environments |
| Viewer notices | Both exporters embed the complete notices for the audited PyVis/vis-network assets and bundled components; asset/version drift stops export | Repeat the [asset audit](viewer-licences.md) when dependencies or embedded bytes change |

## Release boundary

Keep application source, generic schemas, synthetic examples, reusable test support
and technical documentation in the public tool. Keep notes, immutable source bytes,
assertions, reviews, data-specific catalogues, grants, exports and research results
in owner-controlled storage. Source documents retain their original rights.

The data boundary is a local folder, optionally versioned in a separate
private Git repository. Submodule support is not required for the core filesystem
interface. Shared path configuration, initialisation and standalone Git synchronisation are
implemented; relocating an existing dataset remains an explicit owner operation.

Moving files or adding `.gitignore` does not remove them from existing Git history.
Prepare the public tool in a clean repository after reviewing the selected files.
The old local repository metadata has been removed for a fresh start. Review documentation, fixtures,
package archives, screenshots and generated assets as well as `data/`.

## Prepare a clean code checkout

From the development checkout, choose a destination that does not exist:

```sh
just export-code ../knot-code
```

The export contains `src/knot/`, `tests/`, `scripts/`, `queries/`, `docs/`,
`design_decisions/`, `data-examples/` and the explicitly listed root configuration, licence and
launcher files. It excludes `data/`, `.git/`, environments, build output and caches.
Symlinks and existing destinations are rejected. It copies current working files,
including uncommitted edits; it does not initialise Git, commit, configure a remote
or push. Rerun into a new destination after further changes.

Install the development environment in the export using the README, then run
`just check` and the temporary-dataset quick start there. Keep the original dataset
in its private directory and select it using explicit absolute paths from the
[dataset guide](datasets.md#select-a-dataset). Do not copy it into the code export.
The exporter does not inspect prose for confidential content; review the selected
files before publication.

For a fresh repository, initialise Git in the reviewed export and connect the new
remote. The exporter does not copy `.git` metadata; `data/` and the runtime link are
ignored. Existing public clones already have their own history and need no reset.

Dataset selection and standalone Git synchronisation are now implemented. Use
`knot dataset init`, `use` or `clone` as described in [datasets](datasets.md).
The tool directory itself does not need Git to read or write an external dataset.

## Retired research

The 29 experiment directories and their private outputs have been removed from the
working tree. [ADR 0042](../design_decisions/0042-retire-experiments-and-export-tool-only.md)
records the outcomes, rejected alternatives and retained production changes. The
old local Git history was subsequently discarded at the owner's request. Detailed
experiment artifacts are no longer retained here. Dataset-owned curation records
and saved note revisions remain unchanged.

The supported benchmark accepts an explicit source-pinned question manifest:

```sh
just benchmark-retrieval --data-root /absolute/path/to/store \
  --questions /absolute/path/to/questions.json --output /tmp/knot-benchmark.json
```

Question manifests and reports can contain private evidence. Keep them with the
corresponding private dataset, outside the tool checkout.

## Personal-information checks

Use invented names, projects and scenarios in fixtures. Browser checks must select
synthetic records or inspect a supplied export generically, without embedding real
note IDs, quotations or private project names. Apply the same review to agent
instructions, ADRs, licence attribution, hidden files and generated caches. Preserve
third-party licence notices.

The original development checkout keeps its existing environment outside both
repositories, under `~/.local/share/knot/runtime/venv/`, with a relative `.venv`
link. This keeps local paths in environment metadata outside the application and
dataset. Runtime state is disposable and excluded from code exports. Fresh code
checkouts can create their own environment using the README installation steps.

Python bytecode and tool caches can retain local paths or old fixture strings.
Use `PYTHONDONTWRITEBYTECODE=1 RUFF_NO_CACHE=true just check` during a privacy audit,
and remove stale caches afterward. Ignoring a file does not remove its contents.
Git history and repository configuration require separate inspection; sanitising
current files does not sanitise earlier commits or remote URLs.

## Verification before publication

The v0.1.0 code export passed 528 tests, lint and formatting, 337 local documentation
links, Graph/Library checks in Chromium and Firefox, and legacy viewer browser
checks. Wheel and source archives excluded private data and runtime artifacts;
both installed exporters rendered synthetic examples with complete software
notices. Repeat the relevant checks when release files change.

- Run a fresh installation and the quick start without any personal dataset.
- Run behaviour, formatting and uncached lint checks with only public release files.
- Inspect wheel and source-distribution file lists and licence metadata.
- Verify a dataset copy preserves source hashes, note revisions, assertion IDs and reviews.
- Confirm command defaults and MCP grants cannot silently select a different dataset.
- Verify local documentation links and section anchors, command options and examples
  independently of private `data/` and `experiments/`.
- Exercise `knot view example --no-open` from an installed package as well as the
  source checkout; distinguish current Graph/Library and legacy viewer options.

Keep this document current as work is completed. The
[ADR index](../design_decisions/README.md) records decisions; this checklist records delivery.
