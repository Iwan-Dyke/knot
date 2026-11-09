# ADR 0031: Guide personal note capture through the existing CLI

- Status: Accepted
- Date: 2026-11-06
- Implementation: Implemented
- Documentation reviewed: 2026-11-07
- Extends: ADRs 0022, 0025 and 0030

## Context

The owner wants notes to express personal thinking, motivations and uncertainty,
alongside facts that could be found elsewhere. Existing curation guidance describes
safe representation, but file capture offers little support for developing a note.
The user requested a step-by-step `knot add` wizard.

## Decision

Extend the existing CLI adapter: `add` without a file runs guided capture; file
and explicit stdin capture retain their exact-byte behaviour. Reuse the note API,
immutable revisions and optional metadata. Introduce no dependencies or taxonomy.

Ask for optional title, authorship and kind, then context, thinking, personal
significance, connections, uncertainty and possible next steps. Keep answers under
Markdown headings without paraphrasing. Allow multiline prose and skipped sections.
Require some prose in the wizard, show a preview and save only on an affirmative
answer. EOF, interruption and cancellation before saving write no note. A source
author is not inferred from the terminal user, and the CLI is not assigned authorship.

Connections remain user-authored prose; explicit entity flags retain the existing
API validation. Capture creates no assertions, identity decisions or access grants.
Curated notes and Org capture continue through the existing file interface.

Provide a small repository-local `knot` launcher using the existing virtual
environment. Resolve the checkout and run from its root so the default dataset is
consistent when the launcher is invoked elsewhere. Document PATH use without
modifying the user's shell configuration. No packaging migration is required.

## Tradeoffs and verification

Guided questions can help expose reasoning but can also make a quick capture feel
like a form. Every prompt therefore permits skipping, and the file interface stays
available. Plain line input avoids a terminal UI dependency but reserves a line
containing only `.` as a terminator. Drafts stay in memory and are lost on cancellation
or interruption; persistent draft recovery and interactive editing are future work.

Subprocess tests use temporary datasets to check assembled prose, Unicode, paragraph
preservation, optional metadata, preview, cancellation, EOF and launcher behaviour.
Existing CLI tests protect exact file/stdin capture and revision semantics.

## Subsequent extension

ADR 0032 extends the default wizard with persisted drafts, organisation and AI-assisted
choices. The prose-only behaviour described here remains available with `--writing-only`.

## Content-entry correction

Live terminal testing reproduced an unclear wait after a paragraph: the old reader
printed an empty prompt while waiting for a period terminator. The owner requested
one content entry with guidance, keeping title and kind as separate fields. The
wizard now shows guidance once, accepts continuous prose with a visible `note>`
prompt, and uses explicit `/done` and `/cancel` commands. It no longer assembles
content from separate answers or inserts section headings. Paragraphs are retained.
