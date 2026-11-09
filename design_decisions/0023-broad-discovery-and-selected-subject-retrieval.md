# ADR 0023: Discover subjects before retrieving their evidence

- Status: Accepted
- Date: 2026-11-04
- Implementation: Implemented; independent broad-relevance evaluation pending
- Documentation reviewed: 2026-11-07
- Extends: ADRs 0019, 0020, 0021 and 0022
- Relates to: ADR 0015, whose persistent inferred-relationship proposal stays proposed

## Context

Question-only retrieval currently skips graph traversal. Label lookup cannot find
subjects from broad natural-language questions. Text retrieval chooses revisions
by IRI before scoring, so a relevant source after the revision cutoff is never
considered. A bounded evidence response is also an expensive discovery catalogue:
whole passages and provenance crowd out other subjects.

The user authorised a small broad-retrieval increment. Preserve the graph, sources,
review history, canonical identities, scoped view and evidence selector. Do not
create inferred relationships, an autonomous agent, a database or an extraction path.

## Decision

Provide two explicitly separate stages, both stateless and deterministic:

1. `discover(question)` returns compact candidate entity/note/revision IRIs, labels,
   verified source locators, relevance reasons, supporting assertion review/origin,
   source coverage and omissions. Labels never resolve identity by similarity.
2. `gather(subjects, question)` collects complete packages from the existing graph,
   text and hybrid retriever, deduplicates them, then uses the existing selector
   once under a shared response budget. The caller chooses subjects after inspection.

The discovery plan offers three complementary, domain-independent objectives:
recorded relationships, original source context, and explicitly signalled
qualifications/changed accounts. The same question can be examined through any
subset. These are evidence perspectives, not a leadership template or semantic
contradiction detector. Multiple selected subjects share a finite work allowance;
no retry loop or automatic follow-up is introduced.

Stable assertion/source-unit handles allow callers to exclude previously examined
matches. Exclusion applies after qualification dependencies are assembled: it
cannot remove context required by a returned claim. Shared provenance remains exact.

Discovery references contain source hashes and exact locator/quotation hashes,
rather than incomplete quotations presented as evidence. Stage B returns complete
evidence units. Candidate review states describe supporting assertions only;
source-only text and native navigation have no claim acceptance. The candidate's
rank does not establish a fact, causation, chronology or independent corroboration.

Original source revisions without entity assertions remain selectable source seeds.
Discovery returns an exact complete source-unit selector (revision, character offset,
length and full quotation hash), so follow-up questions need not rediscover that
passage lexically. Forged partial units cannot clip qualifying context.
Native note seeds retain existing current/granted/historical semantics; a raw
historical native revision must not bypass the explicit historical-read interface.

## Source selection and resource bounds

Select from the already eligible revision catalogue. Rank cheap assertion metadata,
native titles, source names and bounded text samples before loading complete
evidence. Samples are unverified routing hints, never returned as quotations or
claims. A selected source must pass the existing complete snapshot/text/manifest
verification before supplying any discovery reference or evidence.

Bound the number of sampled revisions, bytes per sample, complete revision loads,
sections, candidate records, subjects and output characters. Use deterministic
sampling/ranking/ties and report uninspected revisions and incomplete sample coverage.
Explicitly selected source/note reads avoid scanning unrelated sources. Sampling
cannot guarantee discovery in very large files or a catalogue beyond its bound.

## MCP and compatibility

Extend `knot_lookup` with an explicit discovery mode. Extend `knot_retrieve` with
selected subject IRIs, an objective and exclusion handles. Keep the same two tools,
operator-selected root/grants, generic errors, strict limits and complete-package
framing. Ordinary label lookup and single-seed retrieval remain supported.

All indexing, samples, frequencies, graph candidates, labels and omissions use the
eligible view. Denied sources or native revisions must not affect visible results.
Discovery and evidence collection write nothing and cannot broaden grants.

## Alternatives and evaluation

A single larger context does not solve subject discovery or pre-ranking exclusion.
An LLM planner, persisted links or vector database add infrastructure and uncertainty
without a measured need. First evaluate lexical discovery with existing graph
semantics and a local shared-concept routing prototype. An implicit conceptual link
without recorded support remains uncertain; do not manufacture it to satisfy a test.

Freeze source-first broad questions before implementation, with development and
held-out splits. Compare discovery coverage, evidence recall, source diversity,
qualifications, negative matches, citations, total context and work/latency against
single-pass and label-lookup workflows. Charge both stages to one response budget
in evaluation. Labels are developer-assessed, with previously exposed underlying
passages; no independent validation claim follows. Report regressions and missing
domains rather than repeatedly tuning existing ranking weights.

## Acceptance and limits

The increment requires reproducible baseline failures, useful discovery without an
entity seed, bounded selected-subject gathering, relevance-first revision selection,
scope/identity/review/provenance tests, a real MCP replay, and separate validation
results. Full semantic search, automatic contradiction resolution, arbitrary history
enumeration, authoring and automatic assertion acceptance remain outside scope.

This does not implement or supersede ADR 0015's persistent discovery candidates or
their dependency/review lifecycle. All results here are ephemeral retrieval hints.

## Implementation and measured consequences

Stage A uses corpus-normalised lexical cosine similarity, visible aliases and note
titles, with one verified existing `relatedTo` hop. Generic person/theme/grade hubs
are excluded from routing. Accepted identity bindings only break equal-score ties;
they do not upgrade the truth of supporting claims. The old evidence ranking weights
are unchanged. Each card keeps its strongest supporting context and compact routing
assertion receipts; Stage B supplies complete evidence paths. Distinct source contexts
are offered before additional cards supported by the same revision.

Discovery defaults to 64 full revision reads, 256 previews of at most 8,192 bytes,
1,024 sections, 128 candidates per channel and eight returned cards. Selected subjects (at most
four) share one source-reader cap and divided candidate/section/expansion allowances.
Native historical reads continue through ADR 0022's explicit revision interface.

The completed experiment recorded
both useful discovery and a material regression when a simplistic caller chooses
the first three cards automatically. This interface is an opt-in exploration step,
not a demonstrated replacement for single-pass retrieval. A local LSA prototype
showed no target-recall gain under matched resource limits and remains outside production. False lexical
suggestions, budget-dependent selection and incomplete conceptual coverage remain.
The experiment artifacts and old Git history were removed; the outcome summary is
retained in [ADR 0042](0042-retire-experiments-and-export-tool-only.md).

## Normal-use client guidance

Added 2026-11-08. The completed agentic-investigation experiment recovered useful
justification through existing tools in three compliant cases. It also produced an
unsupported leadership-change interpretation after missing a continuation saying
the coaching method was already established, and exposed a client counter that
counted expansion calls rather than selected sources. More retrieval alone did not
ensure better reasoning; independent answer-quality validation remains outstanding.

Maintain concise investigation guidance in the existing MCP server initialization
instructions. Direct factual retrieval remains the fast path; complex questions use
AI-chosen follow-ups with explicit missing-evidence needs, cumulative client limits,
source-unit accounting and early stopping. Personal motivations and reasoning need
explicit support. Change claims require chronology, corrections and continuity,
including omitted context; unavailable evidence requires withholding the claim.

Initialization reaches read-only and owner clients without repository instructions
or another tool. Keep the executable instruction text in one place; AGENTS.md and
the MCP guide point to it. Avoid a separate prompt catalogue, duplicated policy or
an agent loop inside KNOT. The trade-off is that hosts/models must apply the guidance:
the stateless server still enforces only individual-call bounds and access controls.
Protocol and synthetic continuity tests verify delivery and intact evidence, not
model compliance. No new tool, retrieval algorithm, data change or review action.
