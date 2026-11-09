# ADR 0027: Preserve sources and curate readable knowledge

- Status: Proposed
- Date: 2026-11-05
- Implementation: Partial; provenance and curation APIs delivered, broader standard remains proposed
- Documentation reviewed: 2026-11-07
- Extends: ADRs 0003, 0010, 0011, 0016, 0019, 0021, 0022 and 0025
- Supersedes: None

## Context

Exact evidence and explicit reviews are necessary but do not make a collection of
headings and conversational captures a readable knowledge system. The whole-graph
audit found ambiguous entity granularity, names that describe claims rather than
referents, and instructions used as the main readable representation of knowledge.
Changing stored assertion labels can invalidate review fingerprints. Rewriting
source notes destroys the distinction between what was said and our interpretation.

## Proposed standard

### Entities identify referents

An entity represents a distinguishable referent useful for identification,
connection or retrieval: a person, project, organisation, book, tool, concept,
event, activity, decision or outcome. A noun phrase, heading, instruction or
sentence is not sufficient reason to create one. Use a note for an idea that does
not need a separate identity. Navigation notes and source documents are not
automatically substantive domain entities.

An IRI is stable identity; a preferred label is presentation. Use concise,
descriptive names with enough context to distinguish similar things. Prefer
“Data engineer candidate selection” to “Suitable candidate selected”. Preserve
old spellings as search aliases. An alias is not an identity decision. The same
name can legitimately identify different people, events or framework concepts.

Reuse an existing entity only when evidence establishes the referent. Search labels,
aliases, types and surrounding evidence before proposing a new one. Normalised
spelling and overlapping labels produce review candidates, never automatic merges.
Accepted identity bindings remain the only projection of confirmed equivalence.

Choose the narrowest supported existing type, without guessing from grammar.
Separate a continuing project from an activity within it, a decision from its
implementation, and an outcome concept from the claim that it occurred. A concept
is a reusable subject; a statement about it belongs in a note or assertion. Use
singular identities for individuals and a Group for a genuinely collective referent;
do not merge named people into an anonymous team or split a group without evidence.
Keep unresolved mentions distinct or unassociated. Do not infer ownership from
involvement, nor completion from a completed-task heading containing future work.

### Notes express coherent, reusable knowledge

Permanent knowledge notes have one coherent idea, a descriptive title, understandable
prose, explicit qualifications and a verifiable source. Closely related context can
remain together; sentence-by-sentence splitting is not a goal. Remove conversational
instructions from the curated prose, correct spelling and explain necessary context.
Do not silently supply an event date, person identity, causal explanation or result.

Use existing kinds: Statement for attributed claims; Observation for reports;
Thought for reflections; Idea for proposals; Hypothesis for uncertain explanations;
Question for unresolved enquiries; Assessment for judgements; Definition for terms.
Kinds do not imply verification. Source capture, permanent knowledge, fleeting
capture and navigation are useful workflow roles, not a second mandatory taxonomy.
Free-form notes may have no title, kind, entity association or assertion.

### Three layers retain different responsibilities

1. **Immutable source:** exact original bytes, source author where known, revisions,
   hashes and locators. User instructions can be preserved here as evidence of intent.
   A transcription is evidence text derived from an image, not a verbatim guarantee
   about the handwriting. Preserve both pins. Archive occurrences and revisions
   sharing one account do not independently corroborate it.
2. **Curated knowledge:** a separate native note with its own stable identity,
   actual author (including Codex/Kiro when AI-written), method, qualification and
   pinned input quotations. The original note's head stays unchanged. Describe
   faithful restatement versus synthesis explicitly. Exact quotations remain exact;
   paraphrases belong in the curated body, never in the original-quotation field.
3. **Structured graph:** source-backed candidate relationships. Curation does not
   accept an assertion or establish identity. New claims start Unreviewed; existing
   accepted claims require the append-only correction/review workflow.

Source and curated note associations are navigation, not factual assertions. A
reading note can link to a book without asserting that its reader applied a concept.
Keep useful notes without associations when identity is uncertain.

### Relationships express only supported meaning

| Predicate | Required meaning and limit |
| --- | --- |
| `relatedTo` | Contextual association; no identity, causation or ownership. Explain the association. |
| `workedOn` / `contributedTo` | Reported involvement or contribution, not exclusive responsibility. |
| `madeDecision` / `selected` | An attributed choice; do not substitute a project for an unknown decision-maker. |
| `implemented` / `developed` / `produced` | Source reports the corresponding action or artefact; a plan is insufficient. |
| `reportedOutcome` | An attributed result, with context and uncertainty; not independent corroboration. |
| `supports` / `demonstrates` | Explicit assessment linking evidence to a claim/capability; retain the assessor. |
| `resultedIn` / `enabled` | Source-supported causal/enabling claim; preserve attribution and competing explanations. |
| `dependsOn` | A stated dependency, not merely adjacent work. |
| `documentedIn` | Navigation to a document; no evidence of application or success. |

The existing vocabulary is sufficient for this pilot. Do not add stronger predicates
to make a picture look connected. Questionable relationships, compound identities
and changes affecting Accepted assertions enter a review queue.

A bounded implementation and dataset-specific pilot were authorised separately.
Their completion does not silently accept this proposed architectural standard.
Private audit records remain with the dataset.

## Bounded implementation

Extend native manifests with optional schema-v3 derivation metadata. Existing v1/v2
manifests and ordinary capture remain unchanged. Pin each input revision, original
snapshot hash, evidence-text hash, exact quotation, Unicode offset and start line.
Validate these before publication through the existing API and CLI; record method
and qualification with the revision. A new curated note is not a revision of its
original source. Subsequent curated edits retain optimistic concurrency and history.

Scoped retrieval admits a derived note only when its own revision and the complete
transitive input closure have matching explicit grants. Check grants before reading
denied inputs. A grant never propagates to an original, successor or derivative.
Retrieval identifies curated authorship and derivation separately from exact source
text and assertion acceptance. Prefer a verified curated representation when useful,
while retaining the source path and reporting a shared account, not corroboration.
Retain complete provenance in responses rather than clipping qualifications or input
quotations. Complete curated provenance can exceed the old 4,000-character default.
Use a 12,000-character default, matching the
existing MCP ceiling; explicit smaller budgets remain strict and report omissions.
Transitive inputs share the evidence reader's revision budget and cache. Bound
derivation chains to 32 input edges and report overlap using leaf source hashes.
Graph preparation and preferred-label validation are separate catalogue overhead;
the source-revision budget measures traversal/evidence work, not all filesystem I/O.

Preferred entity names live in a provenance-backed presentation overlay. Apply it
after access filtering and after organisation/review fingerprints are computed.
Keep historical labels and aliases available. Neither IRIs nor factual assertion
metadata are rewritten for presentation. The overlay is an owner-managed input,
not generated RDF or a second identity registry.

A read-only quality command checks referential/citation integrity and emits warnings
for subjective quality: generic names, collisions, unsupported associations,
conversational permanent-note candidates, missing derivation and suspicious predicate
usage. Integrity errors are distinct from warnings. Warnings never reject legitimate
free writing or decide identities, facts, themes or reviews.

## Migration and verification

Capture a baseline of file hashes, note heads/history, assertion fingerprints and
review events before changes. Record every affected ID, old representation, problem,
proposed/applied change, exact support and review implications in a curation ledger.
Start with a bounded sample spanning projects, reading, instructions, decisions
and unresolved sources; validate before expanding the batch.
Use API-owned note writes and normal organisation rebuilding. An explicit source
registration repair must first prove that no reviewed assertion fingerprint changes.

Check source byte identity, history, quotations, review replay, scopes, retrieval,
entity resolution and negative cases. Freeze representative questions before applying
data changes. Report unresolved counts and retrieval regressions as well as gains;
the development pilot is not independent evidence of general answer quality.

## Alternatives and consequences

Editing original captures is smaller but corrupts provenance. Putting cleaned prose
only in titles or assertion rationales does not provide reusable notes. A mutable
external derivation index separates provenance from the revision it explains. Optional
immutable metadata adds validation and access-closure work but fits the existing note
owner and needs no new database, ingestion system, mandatory taxonomy or dependency.

Presentation overlays avoid invalidating reviewed assertions, at the cost of another
small version-controlled authoring input. Quality heuristics inevitably have false
positives; the review queue preserves that uncertainty. Human review remains necessary
for ambiguous identities, disputed interpretations and changes to accepted claims.
