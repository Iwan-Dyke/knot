# Capture and connect notes

Run commands from the repository root after [setup](../README.md#installation).
Examples use the selected dataset; see
[dataset selection](datasets.md#select-a-dataset) for external folders. Replace
uppercase identifiers with values returned by your own dataset.
Here `data/` in a storage path denotes that selected dataset, not a folder required
inside the application checkout.

## Guided capture

Run `./knot add` or `just notes add` from the repository root. Install a launcher
for use from any Linux/WSL terminal directory:

```sh
./install.sh
knot add
```

The installer writes `~/bin/knot`, reuses the existing project environment and
refuses to overwrite an unrelated command. Re-running it is safe. Ensure `~/bin` is on your shell PATH; open a new terminal after changing it. An alternative destination is
supported with `./install.sh --bin-dir /path/to/bin`.
The launcher points to this checkout: keep it in place. No dependencies are
installed and no shell configuration is edited. Windows PowerShell/CMD needs a
separate Windows launcher; use a WSL terminal for this command.

The launcher uses this checkout's `.venv` and your selected dataset. It preserves
the caller's working directory, so relative input and dataset paths resolve there.
Use `knot dataset init PATH`, `use PATH` or `clone URL [PATH]` for setup.
Override the selection for one command with `knot --data-root /path/to/data add`.

Title, author and knowledge kind are separate optional fields. Content is one
continuous entry area. Guidance is displayed once: consider the context, your
interpretation, why it matters, connections, uncertainty and possible next steps.
You do not answer these as separate questions. KNOT adds no headings to the body.

At the visible `note>` prompt, type or paste your note. Enter continues writing;
blank lines preserve paragraph breaks. Type `/done` on its own line to finish, or
`/cancel` to cancel. At least some content is needed. The final entered line is
stored with a newline. The commands themselves are not included in the note.

The useful question is: **What would a future reader need to understand why I
think this, rather than merely know that I think it?** Questions and doubts are
useful notes. Distinguish a quotation from your interpretation and preserve
uncertainty.

After writing, choose **organise manually now**, **save for a CLI agent later**,
or a menu. Manual mode walks through themes, related notes, entities and relationships.
The menu lets you repeat steps, review, edit writing, remove selections, save, or
prepare an agent handoff.

- **Themes:** select multiple existing catalogue themes by number. Membership is
  stored in the note revision and projected into RDF. Enter keeps your current
  selection; use **Remove a selection** to clear a theme.
- **Note links:** search note titles and bodies, select a target and explain the
  connection. These navigation links have discoverable backlinks.
- **Entities:** search existing names and aliases, then explicitly reuse a result
  or name a distinct new referent. Choose its type and an exact passage from your
  note supporting the declaration. KNOT generates its identifier and RDF metadata.
- **Relationships:** choose a subject, the meaning of the edge and its target.
  Endpoints can be this note, linked notes, selected entities or new declarations.
  Select exact supporting text, distinguish Explicit from Inferred, and explain
  the rationale. Repeated quotations require selecting the correct occurrence.
  Kind and themes default to the note's selections and can be overridden.
- **Review and save:** inspect the complete draft before confirming. New substantive
  relationships remain Unreviewed. Note links and themes do not accept claims.

Skipping the initial organisation choice opens the menu. Review shows your prose,
theme labels, linked note titles and reasons, and any relationship candidates.
Save receipts remain JSON for use with scripts and CLI agents.

The graph is an exported HTML snapshot. Adding or editing a note does not update
an already exported file. After saving, regenerate it and open the current graph:

```sh
knot view
```

Successful saves also print this command with the saved note's dataset path to
stderr, leaving the JSON receipt on stdout. Reload an existing browser tab after
regenerating. Every saved note is available in Library and search. Graph initially
waits for a selection; selecting a standalone note shows it without requiring an
entity or relationship. **Associated notes** and relationship filters can hide
other note nodes. See [graph exploration](viewer.md#focused-and-live-graph-exploration).

Once content entry finishes, a draft is saved under `data/drafts/`. Each
completed menu step is retained. EOF or Ctrl-C retains that draft; content entry interrupted
before the first draft save is not recoverable. Run `knot resume` to choose a draft
by number from a list of titles, newest first. Press Enter to cancel. Saved notes
remain listed for resuming publication. You can also supply a draft path directly:

```sh
knot resume
knot resume /absolute/path/to/data/drafts/UUID.json
knot list --theme learning-and-development
knot list --linked-to NOTE_IRI
knot show NOTE_IRI
```

`list --linked-to` returns incoming links; `show` includes outgoing links and their
explanations in `navigation`. Notes, declarations and links are visible through
native retrieval. Note navigation does not grant access to linked notes.

Drafts pin their dataset and reserve note/assertion IDs. Publication saves the note
first, then publishes relationships through the normal curation API and rebuilds
organisation when a catalogue is present. If a later step fails, resume the same
draft: completed records are reused. The draft reports its saved revision, and
later changes to the note stop resume rather than overwrite it. Work on a draft in
one CLI session at a time. Drafts are local working files ignored by Git; published
notes and assertions remain in their normal authoritative stores.

For quick prose-only capture use `knot add --writing-only`. For an existing note,
`save --navigation FILE --expected REVISION_IRI` updates navigation through the same
revision API. The JSON object has `themes` (`id`, `label`), `links` (`note`, `reason`)
and `declarations` (`id`, `label`, `type`, `quote`, `offset`) lists. An empty list
clears that category; omitted `--navigation` retains it. Declaration quotes must
still match the body. Original revision manifests are never rewritten.

To write a separate interpretation of saved sources, use `knot curate`. It guides
source and passage selection before returning to this entity and relationship
workflow. See [manual curation](curation.md#guided-manual-curation). A related-note
link is navigation; it does not replace a pinned source citation.

## Organise with a CLI agent after capture

Choose **save for a CLI agent later** to save the note and create an `.agent.txt`
task beside the draft. The receipt and terminal output identify its path. Open your
preferred CLI agent in this repository and ask it to carry out that task file.
KNOT does not start an agent, call a model endpoint or require a local model.

The handoff identifies the dataset, logical note, immutable revision and body hash.
It asks the agent to search existing knowledge, preserve your source writing, and
create useful source-backed relationships through the existing APIs. New substantive
claims remain Unreviewed; ambiguous connections stay as questions. It does not
authorise acceptance, access changes or historical cleanup.

You can generate a handoff for any saved note later:

```sh
knot agent-task NOTE_IRI > /tmp/knot-agent-task.txt
knot agent-task NOTE_IRI --revision REVISION_IRI > /tmp/knot-agent-task.txt
```

Replace the identifiers with those from your receipt. The default pins the current
revision at task generation time. This command only prints the task; invoking your
CLI agent is a separate action.

## File and stdin capture

[ADR 0022](../design_decisions/0022-native-free-text-knowledge-and-entity-notes.md)
provides native note storage and a rebuildable RDF navigation view.

Use `just notes` to capture UTF-8 text without invoking Python or activating the
virtual environment yourself:

```sh
just notes add /tmp/my-note.md --title 'A reflection' --author 'Your name'
just notes add /tmp/my-note.org --kind Thought --agent Codex
just notes add - --title 'From stdin' < /tmp/my-note.md
just notes list
just notes show NOTE_IRI
just notes history NOTE_IRI
just notes show NOTE_IRI --body-only > /tmp/draft.md
just notes save NOTE_IRI /tmp/draft.md --expected REVISION_IRI
```

Replace `NOTE_IRI` and `REVISION_IRI` with the IDs returned by `add` or `show`.
Keep the revision observed before editing: a stale `--expected` fails without
overwriting a newer save. `show --revision REVISION_IRI` reads an exact historical
version. `--body-only` outputs the original bytes with no added newline.

`add` always creates a new logical note; identical text does not imply the same
note. Check `list` and `show` before retrying an uncertain capture. File input and
explicit `-` stdin preserve exact UTF-8 bytes, including BOMs and line endings.
New `.org` files default to Org; other files and stdin default to Markdown.
Use `--format markdown` or `--format org` to override. `save` retains the previous
format, title, author, kind and associations unless explicitly changed. Agent and
reason describe the new commit and remain unset when omitted.

For ordinary capture, title, author, saving agent, reason, kind and entity associations are optional.
Use `--author`, `--agent`, `--reason`, `--kind` and repeat `--entity EXISTING_IRI`
as needed; resolve entity identities with `just retrieval lookup` first. For saves,
`--entity` replaces the association set. `--clear-title`, `--clear-author`,
`--clear-kind` and `--clear-entities` explicitly remove optional metadata.
Unknown authors/agents remain unset. Capture does not extract or accept assertions.

Commands return JSON: capture receipts, listings and history contain IDs, hashes
and metadata; `show` also includes the body. Listing and history verify committed
evidence, so corrupt ancestors fail explicitly. Put `--data-root PATH` before the
subcommand for a separate dataset. Run `just notes --help` or
`just notes add --help` for arguments. The existing project environment must still
be installed; `just` selects its Python automatically.

The [CLI design](../design_decisions/0025-owner-local-note-cli.md) records the tradeoffs.

## Themes, links and declarations

The versioned `navigation` object is described above under guided capture. For the
revision model and programmatic operations, see the [Python API](reference/python-api.md).
For derived notes and claims, see [curation](curation.md).
