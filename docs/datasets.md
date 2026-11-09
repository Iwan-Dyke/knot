# Manage a personal dataset

A KNOT dataset is a directory containing notes, immutable source revisions,
structured assertions, reviews and organisation inputs. Keep it together when
backing up or moving it. The [software licence](../LICENSE_SCOPE.txt) does not
license its content.

## Select a dataset

KNOT always reads and writes a local dataset folder. That folder can optionally be
its own Git repository, synchronised with GitHub or another Git host. No network
connection is needed for ordinary note capture, retrieval or review.

From a source checkout use `./knot`; after installing the launcher or package use
`knot`. Equivalent setup commands are available through `just dataset`.

```sh
knot dataset init /path/to/new-dataset
knot dataset use /path/to/existing-dataset
knot dataset clone git@github.com:YOUR_ACCOUNT/knot-data.git /path/to/clone
knot dataset show
```

`init` creates an empty dataset, organisation catalogue, generated ontology/view
inputs, `knot.json` version marker, Git ignore rules and byte-preserving attributes.
It does not create a Git repository or a dummy note. Repeating it on a recognised
dataset leaves its files unchanged. A nonempty unrelated directory is rejected;
these commands do not import loose Markdown files or source archives.

`use` selects an existing dataset without modifying it. Existing note registries
and graph datasets are recognised without requiring a new marker. An existing
local Git checkout uses its configured remote. Selection is not a full integrity
audit; use `just quality` when checking an existing dataset.

`clone` accepts HTTPS, SSH (including `git@host:path`), Git protocol, file URLs and
local repository paths. It uses the installed Git executable and your existing SSH
agent/credential helper. Embedded HTTP credentials and command transports are
rejected. It never recursively clones submodules. The destination must not exist;
a failed clone or unrelated repository is removed without changing the selection.
Empty repositories, including those with only README/licence/Git metadata files,
are initialised automatically. The remote repository must already exist: KNOT does
not create GitHub repositories or change their visibility.

Omit the clone destination to use `$XDG_DATA_HOME/knot/datasets/REPOSITORY`, falling
back to `~/.local/share/knot/datasets/REPOSITORY`. An existing destination is never
replaced. Clone/setup selects the dataset only after success; no commit or push is
performed. A failed configuration write leaves the successfully created folder
available for `use` after repairing configuration.

KNOT resolves the folder you select, so the selected root may itself be a symbolic
link. Files and directories managed inside that dataset must not be symbolic links
or use parent traversal. Setup and refresh check these paths, and reads and writes
check them again before use. This prevents a cloned or subsequently changed dataset
from redirecting graph, source, review or catalogue operations outside its root.
Default viewer outputs and authoring drafts follow the same rule; an explicit
`--output` can still select an external export destination.

If refresh reports an unsafe path, the Git update has already occurred. Inspect
and repair the offending link before using the dataset; KNOT leaves the checkout
available for that repair and rejects subsequent operations through the link.

### Configuration and precedence

All CLI entry points, including MCP, use this order:

1. Explicit `--data-root PATH` (or `--graph PATH` on commands that expose it, such
   as the legacy viewer; `--graph` names the dataset's `graph/` subdirectory).
2. `KNOT_DATA_ROOT` environment variable.
3. `data_root` in the user configuration.

The configuration is `$XDG_CONFIG_HOME/knot/config.json`, or
`~/.config/knot/config.json`. Set `KNOT_CONFIG` to select a different configuration
file, for example in an isolated integration. Setup saves an absolute path using
an atomic JSON replacement:

```json
{"schema_version": 1, "data_root": "/path/to/knot-data"}
```

The same file can store a `visual_theme` preference set by `knot theme use`.
Dataset setup preserves it. A theme can be selected before a dataset; data commands
still require an explicit or configured dataset path.

Environment overrides remain in effect after setup; `dataset show` reports the
effective selection. A missing selected folder or invalid configuration fails
explicitly. No command silently falls back to `data/` in the working directory.
An explicit path can still create a first note without running setup, as in the
README quick start. A moved dataset needs `dataset use` with its new location.

Relative paths are resolved from the caller's working directory. The installed
launcher keeps that directory; `just` runs recipes from its justfile directory.
Do not commit personal paths or authentication credentials in the tool repository.
MCP resolves the path at startup; restart it after changing the selection. Dataset
selection never changes source grants, write permissions or review permissions.

| Command | Explicit override |
| --- | --- |
| Notes | `just notes --data-root /path/to/store list` |
| Retrieval | `just retrieval get --data-root /path/to/store --question 'learning' --mode text` |
| Curation | `just curate --data-root /path/to/store check /tmp/candidate.json` |
| Reviews | `just review --data-root /path/to/store summary` |
| Knowledge | `just knowledge --data-root /path/to/store show` |
| Quality | `just quality --data-root /path/to/store` |
| MCP | `just mcp --data-root /path/to/store --scope /path/to/scope.json` |
| Graph and Library | `knot view --data-root /path/to/store` |
| Export without opening | `knot browse --data-root /path/to/store` |
| Legacy viewer | `knot view --legacy --data-root /path/to/store` |
| SPARQL | `PYTHONPATH=src .venv/bin/python -m knot.graph.query /tmp/query.rq --data-root /path/to/store` |

Organisation, inventory and migration recipes use the same selection. Their
module commands also accept `--data-root`. `knot view`, `knot browse` and
`just visualise` default to the selected dataset's `views/library.html`.
The legacy viewer uses `views/graph.html` (or `views/frameworks.html` with
`--frameworks`). `--output` overrides these paths. `knot view example` builds a
temporary synthetic dataset without selecting it; see the [viewer guide](viewer.md).

## Start with notes

After setup, use `knot add` or `just notes add`. Native note capture does not need
an imported archive. A freshly initialised dataset supports organisation immediately.
Older note-only datasets selected with `use` may need an organisation catalogue
before running `just organise`; `use` never rewrites their configuration.

## Files and ownership

All paths below are relative to the selected dataset root.

| Location | Purpose and owning workflow |
| --- | --- |
| `notes/registry.json` | Committed note heads and revision membership, maintained by the note API |
| `notes/revisions/` | Immutable metadata manifests, including authorship, navigation and derivation |
| `sources/` | Exact source snapshots, original documents and preserved transcription evidence |
| `graph/` | Persisted assertions, provenance, framework definitions and guarded projections |
| `curation/` | Imported extraction inputs, identity bindings, preferred labels and evidence qualifications |
| `reviews/events/` | Immutable assertion review events, maintained by the review writer |
| `reviews/` | Identity decisions and dataset-specific review records |
| `migration/` | Archive inventory, conversion ledgers, retained extracted text and coverage reports |
| `organisation/` | Theme/type catalogue, theme reviews and generated-output hashes |
| `drafts/` | Local resumable authoring drafts; not committed notes |
| `views/` | Disposable HTML exports that can be regenerated |

Generated does not mean disposable. Extracted text can be cited evidence; conversion
ledgers and output hashes protect rebuilds; supplementary graph files are not
recreated by the importer. The in-memory query store and HTML exports are disposable.

## Back up and relocate

Finish active writes before copying the dataset. Back up the registry, all committed
revision manifests, source bytes, RDF, catalogues, ledgers and reviews together.
Preserve byte contents and relative paths. Git users must prevent line-ending
conversion of content-addressed evidence. Dataset `init` and empty-repository
`clone` write `* -text` to the dataset's `.gitattributes`. `use` leaves existing
files untouched, so check byte-preserving rules when selecting an older repository.

After relocation, read representative notes and their history, compare hashes,
inspect reviewed claims and run quality checks. Source locators are dataset-relative,
but authoring drafts pin their original dataset path. Complete drafts before moving
or reconcile them explicitly; do not edit immutable manifests to make paths fit.
Update client paths while preserving existing access grants.

Use the owning API for changes. Do not scan orphaned manifests to reconstruct
registry membership, rewrite old source snapshots, or edit accepted assertion
content in place. A clean quality report establishes integrity, not semantic truth.

## Import and rebuild

Archive inventory and migration are for preserved source imports. They are not
required to capture, save or search native notes. Import requires the appropriate
curation inputs and source inventory; it is not a generic automatic importer for
an arbitrary document folder.

`just inventory` verifies source occurrences. `just migrate` rebuilds imported
assertions and conversion reports, then organisation. When invoking the migration
module directly, run the organisation module afterwards. Older datasets may keep
curation inputs in `migration/`; a partial split between that directory and
`curation/` is rejected. Historical path mappings belong to the dataset's
`curation/relocations.json`.

Rebuilds verify source and previous output hashes and preserve review events and
supplementary overlays. Reconcile modified generated output before rebuilding.
Each replacement is atomic; a complete multi-file migration is not one transaction.
PDF/Word extraction can lose layout, tables or image content. Preserve the originals
and inspect those limits rather than treating successful conversion as full coverage.

## Retire duplicate ZIP containers

Only retire a redundant container after verifying every member against its saved
snapshot and successfully rebuilding a temporary dataset copy. In that copy, mark
the verified archive's inventory entry `retired: true`, remove the container, and
rerun inventory, migration and organisation. Compare graph content, evidence and
reviews before applying the same change to the working dataset.

Keep inventory occurrences, source snapshots and extracted text. A missing archive
without a retirement record is an error; retained archives still need matching
hashes. This policy does not authorise deleting original notebook or image evidence.

## Git refresh and push

`knot push` and `knot refresh` operate on the selected dataset's own Git repository.
The legacy `<git-root>/data` layout also remains supported for existing users.
A local-only folder can be used normally; synchronisation requires Git and a remote.

For a cloned empty repository, the first `knot push` asks for a commit message,
commits dataset files, pushes to the configured branch and establishes tracking.
Git's configured author identity and authentication are required. KNOT does not
invent an author or change Git credentials. Refresh an empty remote only after its
first commit. For a manually created repository with just `origin`, the first push
uses the current branch; ambiguous remotes need explicit Git upstream configuration.

`knot refresh` requires a clean checkout and pulls with fast-forward only. It never
automatically stashes, merges or rebases. Conflicting/divergent changes require
explicit Git resolution. In a standalone data repository, it cannot update the
separate application repository. Legacy mixed repositories still pull their whole branch.

`knot push` displays changes and pending commits, asks for a commit message when
there are changes, and excludes drafts, views, local runtimes and locks. Staged
transient files cause it to stop. A standalone dataset repository should contain
only dataset material; all other committed files and pending commits on its branch
are pushed too. No operation silently accepts claims or resolves note conflicts.
A failed push retains local commits, and retry does not create duplicate commits.
Use a private remote for personal data. See
[ADR 0043](../design_decisions/0043-local-datasets-and-optional-git.md).
