# ADR 0022: Preserve native free-text knowledge and entity notes

- Status: Accepted
- Date: 2026-11-04
- Implementation: Partial; native lifecycle and interfaces delivered, general external editing deferred
- Documentation reviewed: 2026-11-07
- Extends: ADRs 0002, 0003, 0007, 0009, 0014, 0016, 0019, 0020 and 0021
- Retains: ADRs 0010 and 0011 for assertion review and canonical identities
- Supersedes: None

## Context

KNOT needs unrestricted native writing alongside imported documents and structured
assertions. A note can be useful before its meaning, entities or classification are
settled. Requiring graph extraction during capture would constrain writing and lose
context. Source preservation alone does not supply an editable note lifecycle.

## Decision

Store Markdown/Org bodies as exact UTF-8 source snapshots, with immutable revision
manifests and a small committed-note registry. Project navigation/history into RDF
when loading. This adds a native source lifecycle to the existing file-first dataset;
it does not create another authoritative database or replace writing with triples.

### Identity and publication

- Give each note a stable `urn:knot:note:<uuid>` identifier independent of its title,
  body, path and associated entities.
- Identify revisions by a deterministic manifest hash. The revision hash differs
  from the body hash and binds metadata as well as text.
- Preserve exact body bytes, parent revision, original author where known, saving
  agent, timestamps and optional title, classification, associations and derivation.
- Keep note creation/save times separate from events described in the writing.
- Require the last observed revision for an update. Reject stale writes rather
  than overwriting a concurrent save. An unchanged save creates no revision.
- Publish committed heads and ordered revision membership atomically in the registry.
  Unreferenced files from an interrupted save are not automatically published notes.

Body deduplication does not merge notes, metadata or source grants. A metadata-only
change can reuse body bytes; reverting text creates a new manifest with its own
parent. Keep earlier revisions readable and immutable. Do not silently reconstruct
a missing registry by scanning manifests.

### Notes, entities and claims

Ordinary capture requires no title, classification, entity or assertion. Associations
reuse resolved identities; accepted identity projection can affect current navigation
without rewriting stored manifests. Similar names do not merge referents.

Explained note links, themes and source-backed entity declarations use versioned
navigation metadata. They are not accepted substantive claims. Structured relationships
use the separate candidate/review workflows and always begin Unreviewed.
Derived notes have separate identities/authors and verified input pins under ADR 0027.

### Storage and read projections

| Record | Location relative to the dataset root |
| --- | --- |
| Committed heads and membership | `notes/registry.json` |
| Immutable metadata manifests | `notes/revisions/<manifest-hash>.json` |
| Exact body bytes | `sources/revisions/<body-hash>/note.txt` |
| Current RDF navigation | In-memory `urn:knot:notes` projection |
| Historical metadata | In-memory `urn:knot:note-history` projection |

Registry schema version 2 records committed history membership. Native manifest
versions 1–4 remain readable; later versions add optional classification, derivation
and navigation. A real save can update the mutable index format without rewriting
immutable historical evidence. See the [Python API](../docs/reference/python-api.md).

### Retrieval and access

Native sources participate in existing bounded text/hybrid retrieval, including
unassociated notes. A note seed selects that note; an explicit revision selects its
committed history. Return complete notes or relevant complete sections, with omissions
when they exceed the budget. Source text has no assertion acceptance status.

Citations identify the note, author, revision, body/manifest hashes and exact locators.
Native verification proves consistency with preserved text, not factual truth.
Recognised qualifications remain intact; arbitrary contradictions are not inferred.

Scoped access binds each revision IRI to its body hash. Granting an older revision
does not reveal a newer head, another note with shared bytes or linked notes.
Select the latest permitted revision without exposing global currentness. Derived
notes also require all transitive source grants. Scope filtering precedes source reads.

## Alternatives

- Bodies in RDF literals simplify one representation but make long prose and diffs awkward.
- Mutable Markdown with RDF-only metadata needs coordination to preserve verifiable history.
- A separate notes database adds an authority and synchronisation boundary.
- Versioned bodies and manifests preserve natural writing and existing provenance contracts,
  at the cost of more files and explicit publication/index management.

## Consequences

History verification has a cost proportional to retained records. Files must travel
together during backup and relocation. Note revisions do not correct old assertions;
the review workflow preserves their evidence independently. Missing or corrupt
committed evidence fails explicitly rather than yielding a partial silent recovery.

## Implementation and remaining scope

Persistence, navigation, retrieval, scoped access, a CLI and guided draft workflows
are implemented. ADRs 0025, 0031–0033 and 0035 define the later interfaces and viewer.
General external-editor working copies, deletion/tombstone policy and a complete
multi-editor workflow remain outside this delivered scope. No automatic extraction,
temporal reasoning engine or bulk migration of existing writing is implied.

Synthetic tests cover exact bytes, immutable ancestry, stale saves, idempotency,
navigation, corruption, source grants, retrieval budgets and protocol behaviour.
