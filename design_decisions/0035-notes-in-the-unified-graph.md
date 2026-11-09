# ADR 0035: Show notes as nodes in the unified graph

- Status: Accepted
- Date: 2026-11-07
- Implementation: Implemented
- Documentation reviewed: 2026-11-07
- Extends: ADRs 0022, 0026 and 0032

The note identities and navigation/filtering contracts also apply to
[ADR 0047](0047-unified-knowledge-library-and-graph-exploration.md). Specific visual
roles and controls below describe the legacy viewer; the default Graph/Library
interface uses note boxes, entity circles and bounded focused exploration.

## Context

The CLI saves note links in RDF, but the viewer only drew assertions. Native notes
appeared only as curated text in entity inspectors. The owner expected saved notes
and their connections to be visible in the same graph, without creating duplicate
entities or asserting claims merely to make a connection appear.

## Decision

Render current native notes as nodes using their existing logical identifiers.
Include ordinary, curated and unlinked notes. Reuse the verified retrieval adapter
for source bodies, canonical associations and derivation evidence. Show saved
note links and their reasons, plus note–entity associations, as labelled connections.
The graph is one view; edge meaning and provenance remain explicit.

Do not convert navigation into substantive assertions, infer transitive claims,
merge a note with its subject, or change review states. A note linked to a note
about an entity supplies a traversable path, not an invented direct relationship.
Keep claim filters for review/origin. Apply theme/kind filters to note connections;
accepted-only and framework-only exports exclude note navigation. Provide a live
notes-and-links toggle. Isolated notes remain visible in the ordinary view.

Selecting a note reads its body. Selecting a connection shows its saved reason and
revision, with buttons to explore either endpoint. Entity inspectors include their
associated notes. Render text literally and keep assets offline. Counts distinguish
claims from note connections. Filtered exports include immediate linked context.

## Tradeoffs and verification

This reuses existing identities and storage with no migration or new graph backend.
More nodes and bodies increase snapshot size and layout work; existing node filters,
focus, paused layout and the notes toggle bound exploration. Snapshots still require
regeneration; browser filtering is not access control or redaction.

Synthetic Python and JavaScript tests cover note-only datasets, unlinked notes,
canonical associations, incoming links, review separation, filtering and unchanged
source evidence. Browser tests follow a reflection through its linked foundations
note to the associated entity, exercise literal hostile text and narrow layouts.

## Incremental exploration

Focus begins at one relationship hop. A **+1 hop** control expands the current
neighbourhood one layer at a time across both note connections and claims, in either
direction. Build the eligible relationship graph after applying the existing filters;
excluded nodes or edges cannot act as invisible bridges. Theme hubs and literal
attributes never expand reach. Attributes of reached subjects remain inspectable.

Keep the seed and hop depth in view state, so filter changes recompute the reachable
neighbourhood consistently. **−1 hop** decreases depth by one, with a one-hop minimum.
Reset hops returns to one; changing focus starts again;
clear focus restores the full filtered view. Disable expansion when no further
eligible edges touch the visible neighbourhood. Fit the enlarged view without
repositioning nodes or altering stored knowledge. This avoids automatic whole-graph
expansion, while allowing deliberate exploration beyond immediate neighbours.

## Visual note roles

Notes that are endpoints of exported claims (including literal attributes) use
purple ovals. Other associated or standalone notes use blue boxes. A note with
both roles keeps one identity and uses the claim-endpoint appearance. Determine
the role from the exported graph before adding navigation, so toggling associations
does not change shapes. These are presentation roles, not stored classifications
or evidence resources. Evidence remains in the inspector.

The Associated notes toggle controls note navigation and standalone notes. It does
not hide claim endpoints; claim filters control those. This preserves relationship
exploration while distinguishing the notes that remain when associations are hidden.
