# ADR 0007: Preserve Org heading identity across revisions

- Status: Accepted
- Date: 2026-11-03
- Implementation: Implemented
- Documentation reviewed: 2026-11-07
- Related: [ADR 0003](0003-assertions-and-provenance.md)

## Context

Existing Org notes contain heading IDs and links. Replacing those IDs during
conversion would lose useful continuity and make future Emacs integration harder.
A heading can retain its identity while its text changes, so identity alone is
insufficient for a verifiable citation.

## Decision

Reuse existing Org heading IDs to recognise the same heading across edits. Preserve
the source ID in RDF and maintain a stable mapping to its RDF identifier. A heading
ID identifies the source section; it does not automatically identify every person,
project or assertion mentioned there.

Record a separate content hash for the document revision. Anchor each cited passage
to that revision and its location, retaining the quoted text. A changed heading
keeps its logical identity while citations to earlier text retain their original
revision reference.

Detect conflicting reuse of an Org ID rather than silently merging unrelated
headings. Exact copies of the same source in multiple archives are duplicate
occurrences, not independent evidence.

For headings without source IDs, assign KNOT identifiers and persist their mappings
in KNOT's own metadata alongside the RDF. Apply the same approach to Markdown
headings. Leave source notes untouched during Phase 1. Repeated ingestion of the
same revision must reuse the recorded identifiers.

Across changed revisions, reuse a heading's identity only when the match is
unambiguous. Flag uncertain matches for review rather than silently merging them
or inventing continuity. A heading's title or line number alone is not a stable
identifier. The matching algorithm remains an implementation decision to test
against renamed, moved and repeated headings.

Phase 2 may offer an explicit Emacs operation to add permanent Org IDs to source
notes. That is a future option, not a requirement or permission to edit notes now.

## Alternatives and consequences

- Generating new identities on every conversion loses continuity across edits.
- Using only content hashes identifies exact content but cannot by itself connect
  successive revisions of the same heading.
- Reusing source IDs supports existing Org links and future Emacs navigation, but
  requires explicit handling of missing or conflicting IDs.
- Keeping generated IDs outside source files works across formats and preserves
  the existing writing workflow. Matching heavily edited headings may require
  human review, and the mappings must travel with the RDF dataset.
