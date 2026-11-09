# KNOT

KNOT (Knowledge Network of Observations and Traces) is a local knowledge tool for
notes, source documents and evidence-backed relationships. Use it to capture ideas,
connect them to existing knowledge and give AI assistants traceable context.

Notes remain useful without entities or claims. KNOT preserves source revisions,
distinguishes recorded statements from inferences, and keeps claim review explicit.
The core workflows run locally without an LLM or hosted service.

## Project status

KNOT v0.1.1 is an early MIT-licensed release. Keep your
dataset outside the application checkout and select it using the commands below.
The [clean code export](docs/release.md#prepare-a-clean-code-checkout) command can
prepare application files for a new repository without datasets or Git history.
Release verification and packaging guidance are in the [release guide](docs/release.md).

The current supported workflow runs from a source checkout on Linux or WSL with
Python 3.12+. Use a local dataset folder or clone a Git repository. CLI commands and
MCP share the selected dataset; Git synchronisation is optional and supports a
standalone data repository. See [dataset selection](docs/datasets.md#select-a-dataset).

## What you can do

- Write Markdown or Org notes with immutable revisions and optional connections.
- Curate separate, readable notes with exact source provenance.
- Publish source-backed claims and explicitly accept, reject or correct them.
- Retrieve bounded graph, text or hybrid evidence with citations and omissions.
- Browse an offline Knowledge Library and explore a focused graph over the same records.
- Connect an MCP client with explicit read, authoring and review permissions.

## Installation

From your source checkout, install [uv](https://docs.astral.sh/uv/) and
[just](https://just.systems/), then run:

```sh
uv venv .venv
uv pip install --python .venv/bin/python -r pyproject.toml --extra dev
```

The `dev` extra includes the viewer, MCP SDK and Ruff. Omit it for core commands,
or select `--extra visualisation` or `--extra mcp` for those capabilities.
Pandoc is needed for rich Library snapshots and DOCX conversion. It is a separately
installed command-line dependency; opening a generated snapshot needs only a browser.
Node.js enables additional viewer tests;
Playwright is optional. No Docker workflow is currently provided.

## Choose your dataset

Choose one setup option from the source checkout:

```sh
# Create a new local dataset; Git is not required.
./knot dataset init ../knot-data

# Or select an existing KNOT dataset, including an existing Git checkout.
./knot dataset use /path/to/knot-data

# Or clone a repository and select it. Existing Git authentication is used.
./knot dataset clone git@github.com:YOUR_ACCOUNT/knot-data.git ../knot-data
```

An empty remote is initialised automatically. Omit the clone destination to use
`~/.local/share/knot/datasets/REPOSITORY`. These commands save the selection outside
the code repository and never commit or push. Existing dataset bytes are preserved.
They do not import arbitrary documents from a nonempty folder.

Run `./knot dataset show` to inspect the selection, then `./knot add` to write a
note. `./knot push` prompts for a commit message and pushes a Git-backed dataset;
`./knot refresh` pulls with fast-forward only. For a local-only folder, all note
workflows work without a remote. Install the checkout launcher with `./install.sh`
to use `knot` from other directories; package installations also expose `knot`.

Use `knot curate` to select saved sources and exact passages, write a separate
curated note, then organise its entities and connections. KNOT records the evidence
metadata and preserves the originals. `knot resume` continues an interrupted draft.
See [guided manual curation](docs/curation.md#guided-manual-curation).

## Browse your knowledge

```sh
./knot view
```

`knot view` and `just visualise` generate and open the same offline interface in
one browser tab, with **Graph** and **Library** buttons. It starts in Graph View.
Search for a note or entity to explore
its immediate connections, then expand or collapse branches. Select **Library** to
read the same record with its notes, backlinks, sources and revision history.
Within Graph, choose **Focused** for a local neighbourhood or **Live network** for
the moving full network. In Focused mode, **Live layout** lets the visible nodes
spread out; **Pause layout** keeps their new positions. **Node spacing** works in
both modes, whether moving or paused. Both modes share filters, selection and the
Library in the same tab.
Uncheck **Associated notes** to hide note-only navigation; notes used in claim
relationships remain governed by the relationship filters. All notes remain in Library.
Themes provide overlapping navigation paths without duplicating notes. Recently
viewed items last only for the current page session.

The page is a snapshot. After saving changes, rerun `knot view`.
Use `--data-root /path/to/dataset`, `--output /path/to/library.html` or
`--visual-theme paper` to override the selected defaults. The existing full-network
viewer remains available through `knot view --legacy`. Use `--no-open` to export
without launching a browser; `knot browse` also remains an export-only entry point.
See the [viewer guide](docs/viewer.md).

Choose **Idle**, then **Start**, to let KNOT travel through existing connections
and reveal excerpts from your notes. It observes each node, presents its knowledge,
then slowly follows a connection while the surrounding map unfolds. Adjust focus,
reading and travel times, choose one or two hops,
or open it in another window for a second monitor. **Full screen** hides browser
chrome; **Exit Idle** restores your previous reading or graph context. Idle works
offline and never generates or changes knowledge. See [Idle Mode](docs/viewer.md#idle-mode).

Try the same public synthetic examples used by the browser tests:

```sh
./knot view example
```

This generates a disposable example dataset in the system temporary directory and
opens the same Graph/Library interface. It never changes your selected dataset.
The demo starts on a connected garden project, with notes, dependencies and decisions
to explore; **+ Hop** reveals further relationships. It also includes a deliberately
isolated note. Follow the [example tour](data-examples/README.md#explore-the-connected-example).
The source examples and explanation live in [data-examples/](data-examples/README.md).

## Customise themes

Choose Matrix (green terminal), Paper (light), or Midnight (dark blue):

```sh
./knot theme list
./knot theme use midnight
./knot view --open
```

The command remembers your choice for future exports. Matrix is the initial default.
Create a custom CSS palette with `./knot theme create ocean --from midnight`, edit
the generated file, then run `./knot theme use ocean`. You can also drop a CSS or
JSON palette into `~/.config/knot/themes/`; `knot theme list` reports the actual
folder when configuration is customised. See the
[visual theme guide](docs/viewer.md#visual-themes) for variables and examples.

Knowledge themes are topic categories in your dataset:

```sh
./knot themes add concepts --label Concepts --description 'Ideas and mental models.' --keyword concept
./knot themes list
just organise
```

New categories are immediately available when writing a note. Rebuild with
`just organise` to apply keyword suggestions and update graph filters. See
[knowledge themes](docs/organisation.md#add-your-own-knowledge-themes) for importing
definitions and keeping topic review separate from claim review.

## Try a note in a separate folder

These commands create a disposable dataset outside the checkout. They do not need
an existing dataset or an organisation catalogue. Keep the same shell
open so `knot_demo` remains available.

```sh
knot_demo="$(mktemp -d)"
printf '%s\n' 'A small test note about learning.' > "$knot_demo/note.md"
just notes --data-root "$knot_demo/store" add "$knot_demo/note.md" --title 'First note'
just notes --data-root "$knot_demo/store" list
just retrieval get --data-root "$knot_demo/store" --question 'learning' --mode text
```

The capture receipt includes the note ID and immutable revision ID. Use those values
with `just notes --data-root "$knot_demo/store" show NOTE_IRI` and `history NOTE_IRI`.
Saving an edit requires the last observed revision as `--expected`.

With Pandoc and the viewer extra installed, open the same dataset in Graph/Library:

```sh
./knot view --data-root "$knot_demo/store" --output "$knot_demo/library.html"
```

Choose **Library** to read the note, or select it in Graph to explore it. Add
`--no-open` to export without launching a browser. The HTML embeds the exported
content; visual filters do not remove that content from the file.

## Documentation

Start with the [documentation index](docs/README.md).

| Task | Guide |
| --- | --- |
| Capture, edit and connect notes | [Notes](docs/notes.md) |
| Curate writing and publish claims | [Curation](docs/curation.md) |
| Search and retrieve evidence | [Retrieval](docs/retrieval.md) |
| Connect an AI client | [MCP](docs/mcp.md) |
| Browse the Library and explore the graph | [Viewer](docs/viewer.md) |
| Review claims and identities | [Reviews](docs/reviews.md) |
| Choose a dataset, back up or import sources | [Datasets](docs/datasets.md) |
| Adjust themes and types | [Organisation](docs/organisation.md) |
| Understand the code | [Architecture](docs/architecture.md) |

## Development

```sh
just test         # Behaviour tests using temporary datasets
just lint         # Python lint checks
just format-check
just check        # Lint, formatting and tests
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for the development workflow and known check
limitations. Record architectural rationale in [design_decisions/](design_decisions/README.md).
Repository-aware assistants should also read [AGENTS.md](AGENTS.md).

## Licence

KNOT's original tool code is licensed under the [MIT License](LICENSE), copyright
(c) 2026 KNOT authors. MIT permits commercial use, modification and redistribution,
including closed-source modifications, with retention of its copyright and
permission notice. The software is supplied without warranty.

[Licence scope](LICENSE_SCOPE.txt) excludes personal datasets, work-related knowledge
and private research material. Using KNOT does not license your notes under MIT.
Dependencies retain their own [licences and notices](THIRD_PARTY_NOTICES.txt).

## Reference links

These entry points retain links from earlier documentation.

### Curated knowledge notes

See [curated knowledge notes](docs/curation.md#curated-knowledge-notes).

### Source-backed assertion candidates

See [source-backed assertion candidates](docs/curation.md#source-backed-assertion-candidates).

### Review assertions

See [review claims and identities](docs/reviews.md).

### Native notes and graph navigation

See [capture and connect notes](docs/notes.md).
