# ADR 0032: Guide Zettelkasten notes, entities and relationships together

- Status: Accepted
- Date: 2026-11-06
- Implementation: Implemented
- Documentation reviewed: 2026-11-07
- Extends: ADRs 0022, 0027, 0030 and 0031

## Context

The owner wants a complete Zettelkasten capture workflow, including real note
themes, links, entity creation and guided relationships. The initial wizard only
captures prose and basic metadata. Native notes currently support entity
associations but lack theme membership and explicit note-to-note navigation.
The organisation catalogue assigns themes to assertions, not native notes.

## Decision

Keep one guided authoring flow over the existing note and candidate APIs:

1. Capture a title, author, knowledge kind and personal writing. Content is entered
   continuously with optional guidance shown once; uncertainty and source attribution
   stay explicit.
2. Select overlapping themes from the existing catalogue. Persist memberships as
   native revision metadata, with proper listing/filtering and RDF navigation.
3. Find related notes and record why each connection is useful. Persist explicit
   note links with stable targets and link explanations. Make incoming links
   discoverable without rewriting the target note.
4. Search existing entity names and aliases. Reuse an explicitly selected identity,
   or define a distinguishable new referent with a name, supported type and context.
   Generate stable identifiers and RDF through an owning API. Similar labels
   prompt comparison, not automatic identity merging.
5. Optionally compose substantive relationships: select subject, predicate and
   object, explain the connection and identify exact supporting text. Show the
   complete relationship as a sentence, its direction and its qualifications.
6. Review the note, navigation choices, new referents, relationship candidates and
   warnings. Allow corrections before publishing. Preserve a recoverable draft
   with stable identifiers so retries cannot create duplicate notes or assertions.
7. Save through the existing owner APIs, report every resulting record and any
   incomplete publication, then verify retrieval and integrity.

Notes and assertions share meaningful metadata: authorship/attribution, kind,
themes, source context and immutable history. Their roles remain distinguishable.
A note is a source of writing; a relationship has explicit endpoints and predicate,
origin, rationale, exact evidence and its own review lifecycle. Navigation between
notes does not automatically assert causation, agreement or factual support.

Theme selection for notes is an explicit organisational choice. It does not accept
claims. New substantive relationships use the existing candidate publisher and
start Unreviewed. Entity declarations require provenance and do not imply accepted
identity bindings. No additional model is required to generate RDF from explicit
guided choices.

## Storage and implementation boundaries

Extend immutable native manifests compatibly for note themes and links. Older
revisions remain readable and unchanged. Preserve omitted metadata on save, allow
explicit clearing and include real metadata changes in revision identity. Use
the existing theme vocabulary and catalogue rather than a parallel tag system.

Expose note organisation and links in local reads, listings, RDF navigation and
permitted retrieval. Scoped retrieval must not expose a linked note's private
title or body merely because its identifier appears in an accessible note.

New entities and claims must have a defined owning workflow, validated provenance
and stable retry identifiers. Reuse candidate publication for claims. Do not append
handwritten triples or introduce unreviewed mutable side files as hidden authority.
Saving a note and publishing assertions are currently separate transactions;
draft recovery must make partial completion visible and safely resumable.

## Deferred CLI-agent interaction

The owner clarified that a local model is not available and requested manual
organisation or CLI-agent organisation after capture. Remove the local model and
inline command adapters. The wizard now saves the note first and optionally writes
a bounded agent task containing its exact revision/body hash and authorised curation
scope. `agent-task` can generate this handoff again for any saved revision.

The user invokes their chosen CLI agent separately. KNOT runs no model or agent
process during capture. The task directs the agent to search existing identities,
preserve source writing, publish only supported Unreviewed candidates through the
existing workflow, and leave ambiguity visible. Review/acceptance and access changes
remain separate. This replaces the earlier inline AI-suggestion implementation.

## Implementation and limits

Schema-v4 note manifests contain optional navigation and optional derivation together.
Themes store catalogue IDs and labels at selection time. Links store target note IDs
and reasons. Entity declarations store a generated UUID, label, type and a quote/offset
into the note body; their RDF is rebuilt from committed source revisions. These remain
unreviewed declarations, not accepted identity merges. Existing schema versions remain
unchanged. The native adapter projects only declarations from eligible revisions.

Relationship drafts use the current note as evidence. Explicit classification can
carry note kinds/themes into the candidate, with optional per-edge overrides; normal
organisation rebuilding turns these into separately Unreviewed classifications.
The CLI creates named-endpoint relationships; typed literal claims still use the
existing candidate API. It uses existing catalogue themes; theme definition editing
remains in the catalogue workflow. Note themes/backlinks are exposed through the CLI,
RDF and native retrieval. [ADR 0035](0035-notes-in-the-unified-graph.md) subsequently
adds these notes and connections to the unified viewer.

The draft is saved after prose capture and after menu steps, with final preservation
on exceptions. Publication uses stable note/assertion IDs and records the note revision
before publishing edges. Resuming reuses completed records and rejects conflicting
note content. Drafts bind to an explicit dataset. This is resumable publication, not
a cross-file transaction. Draft editing assumes one interactive writer; publication
has a per-draft lock. Cancellation during initial prose entry does not retain a draft.

## Verification

Use synthetic datasets to cover old/new manifests, metadata retention and clearing,
theme filtering, links and backlinks, entity reuse versus creation, exact source
pins, relationship direction and qualifiers, cancellation, partial publication and
idempotent resume. Exercise retrieval and scoped non-disclosure alongside existing
note, curation, identity and review regressions. Do not test against personal data.

The end-to-end UX review found that Enter-to-skip cleared existing themes and
unexpectedly started guided organisation. Skipping now preserves selections and
opens the menu respectively; explicit removal remains a separate action. Draft
review uses readable prose and link titles/reasons, while machine receipts remain
JSON. An installed-launcher regression covers capture, linking, draft selection,
publication, backlinks, push and refresh against a disposable Git remote.
