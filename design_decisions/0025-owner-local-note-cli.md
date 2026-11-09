# ADR 0025: Add an owner-local note CLI over the existing API

- Status: Accepted
- Date: 2026-11-05
- Implementation: Implemented
- Documentation reviewed: 2026-11-07
- Extends: ADR 0022
- Supersedes: None

## Context

Native notes already have exact-byte preservation, immutable revisions, optional
associations and optimistic concurrency. Capturing text currently requires a Python
snippet and an explicit virtual-environment interpreter. The user requested a
convenient `just notes` interface, with design before implementation.

The repository already exposes its local commands through `just` and standard-library
argument parsing. Its environment and authoritative storage need no changes.

## Decision

Add a thin **CLI adapter** in `knot.note_cli`, invoked by `just notes`. It translates
arguments into the existing `create_note`, `read_note`, `save_note` and `note_history`
calls. A small `list_notes` API reads current notes from one registry snapshot,
verifying each complete committed history in stable note-ID order.

Support `add FILE`, `list`, `show NOTE`, `save NOTE FILE --expected REVISION` and
`history NOTE`. Explicit `-` reads stdin; file and stdin input use bytes, preserving
UTF-8 BOMs, whitespace and line endings. New `.org` files default to Org; other
inputs default to Markdown. Save retains the recorded format unless overridden.

Optional arguments expose title, author, saving agent, reason, kind and repeatable
entity IRIs. Unknown attribution stays unset. Omitted save metadata retains API
semantics; mutually exclusive clearing flags explicitly remove optional values.
The API continues to validate associations and serialize writes with its lock.
`--expected` is mandatory, so a caller cannot unknowingly overwrite an intervening
revision. Unchanged saves remain idempotent; `add` always creates a distinct note.

Use JSON for metadata and capture receipts, including IDs and hashes needed for
later edits. Omit bodies from receipts, listings and history; `show` includes the
body and supports exact raw output with `--body-only`. Historical reads use an
explicit revision. Report validation/I/O errors with a nonzero exit and concise
message. Forward recipe arguments through `"$@"` to preserve literal shell characters.

This adapter is an owner operation. It neither changes scoped MCP access nor adds
MCP writes, assertion extraction, review decisions or a new persistence path.
Tests use temporary synthetic datasets; implementation requires no personal-data
migration, dependency installation or lockfile change.

## Alternatives and consequences

- Keeping only Python snippets is smaller but leaves the requested convenience
  problem unsolved.
- A standalone installed executable adds packaging/setup work. The existing `just`
  convention already selects the project environment and fits this increment.
- An editor launcher or tracked working-copy system could simplify interactive
  revision later, but needs draft/identity/recovery policy beyond file capture.

The CLI adds argument handling and tests while reusing storage and integrity rules.
Users still install the existing project environment once. Listing verifies all
note histories and reads their bodies; this favours current integrity guarantees
over a separate index. Revisit that cost with measurements if the collection grows.
The CLI manages neither editor drafts nor duplicate detection. README documents
current commands, and AGENTS.md points capture workflows at the adapter.

## Verification

Subprocess tests cover file/stdin capture, empty notes, Unicode/BOM/mixed line endings,
metadata and association clearing, exact/historical reads, stale and unchanged saves,
verified listings/history, invalid input and literal argument forwarding through
`just`. Existing note, graph, retrieval and access tests remain the underlying API
regression checks; `just check` runs the repository's lint, formatting and tests.
