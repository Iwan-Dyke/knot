# ADR 0046: Guide source-backed curation through the existing note workflow

- Status: Accepted
- Date: 2026-11-08
- Implementation: Implemented
- Extends: ADRs 0027, 0030 and 0032 within this manual authoring scope

## Context

Guided capture already supports entities, note links and relationship candidates.
Curated notes can retain exact input provenance, but their CLI requires users to
prepare a body file and provenance JSON. Linking a related note does not supply
that provenance. A manual user needs to select evidence and write an interpretation
without calculating hashes or editing structured metadata.

## Decision

Add `knot curate` over the existing authoring draft, source verifier and note APIs.
The user selects current native notes or registered imported source revisions,
reads their evidence text, and chooses exact passages or inclusive line ranges.
Repeated text requires an explicit occurrence. `source_pin` computes and validates
the existing revision, snapshot hash, text hash, quotation and Unicode locator.

Require a restatement/synthesis method, explicit qualification, descriptive title
and actual author. Record the CLI as the saving agent by default. The separate
curated note then uses the existing themes, links, entity declaration, relationship,
review and publication workflow. An entity declaration is supported by the curated
text; its derivation preserves the original sources. Relationships cite the curated
revision and retain transitive provenance, starting Unreviewed as before.

Reuse the resumable draft rather than introduce another persistence system.
Reserve the note ID before source selection and retain each completed selection or
metadata step. Incomplete drafts may contain unfinished derivation fields, but must
pass the full existing validation before publication. Completed writing is retained
after `/done`, matching the ordinary capture boundary. Review displays evidence and
qualifications, and the menu can revise them before saving.

Source revisions stay pinned across resume, even if their current heads advance.
Final validation rereads evidence and rejects corrupt snapshots or altered pins.
Existing retry and partial-publication semantics prevent duplicate records. No
source heads, accepted claims, grants or existing identities are changed implicitly.

## Alternatives and tradeoffs

A second wizard with its own publisher would duplicate entity and relationship
validation. Extending the existing draft is smaller and shares its tested retry
behaviour. Requiring JSON preserves a smaller UI but leaves a central manual task
too technical. Searching native titles and registered source metadata avoids adding
another search engine; source bodies are displayed after selection.

This command selects already preserved evidence. New document importers, URL
fetching, automatic extraction, browser editing and interactive editing of published
notes remain separate work. Existing file capture and `knot save` remain available.
The broader proposed standards in ADRs 0027 and 0030 are not accepted by this change.

## Validation

Synthetic CLI tests cover new/reused entities, multiple sources, duplicate and
repeated quotations, Unicode offsets, CRLF line ranges, imported transcriptions,
source preservation, edited source heads, interrupted/resumed drafts, changed pins,
declined saves and Unreviewed relationships with transitive evidence. Existing
note, provenance, retrieval, scope and authoring regressions remain applicable.
