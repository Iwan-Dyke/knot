# ADR 0019: Bounded Knowledge Retrieval for AI Context

- Status: Accepted
- Date: 2026-11-04
- Implementation: Implemented; independent relevance evaluation pending
- Documentation reviewed: 2026-11-07
- Implements: [ADR 0014](0014-one-logical-personal-knowledge-graph.md)
- Relates to: [ADR 0015](0015-bounded-cross-domain-discovery.md), still Proposed
- Preserves: ADRs 0002, 0003, 0010, 0011, 0013, 0016 and 0017

## Context

Accepted on 2026-11-04 following the user's instruction to implement this increment.
The design below records the agreed contract. Independent source-support review
and held-out real-note evaluation remain quality gates, not completed validation.

KNOT holds one personal knowledge graph. AI assistants need relevant evidence for
the current question without receiving the whole dataset in their context windows.
Accepted decisions already establish unified storage, provenance, review-aware
visibility and canonical identity projection. This decision defines how a bounded
retrieval interface puts those decisions into practice. It does not accept ADR 0015's
discovery rule or candidate-dependency workflow.

The normal loader reads local TriG into Oxigraph, replays immutable review events,
excludes rejected/superseded domain triples, then projects accepted identities.
Existing SPARQL can retrieve arbitrary relationships; the viewer's focus option
matches text, rather than expanding a graph neighbourhood. At proposal time there
was no reusable seed-resolution, bounded traversal or AI-context response contract.

Source-backed traversal can connect passages that omit an entity name. That
connectivity does not establish retrieval superiority: a text search may find the
same document, and repeated accounts are not independent corroboration.

## Decision

**KNOT holds the complete knowledge. The retrieval layer selects a relevant,
bounded and traceable subset. The AI reasons over that subset without requiring
the entire knowledge graph in its context window.**

Implement a local, deterministic, read-only retrieval API over the existing query
projection. The local store may load the complete dataset; the bounded boundary is
what the caller receives and what traversal is allowed to expand. Keep model
providers optional. An MCP server may later adapt the same API, after access
scopes and retrieval semantics are tested; MCP is not a prerequisite.

### Resolve seeds explicitly

Find candidates by canonical IRI, exact label and confirmed aliases, with a small
deterministic lexical fallback over labels. Return ambiguous candidates for caller
selection; do not collapse similar names or silently choose a high-degree match.
The first traversal increment accepts a selected canonical IRI. It does not need a
natural-language parser or an LLM to choose a seed.

Reuse accepted identity projection under ADR 0011. Return canonical endpoints and
the original source identities, plus the mapping identifiers needed to explain
their resolution. Preserve the mapping's recorded status and available attribution;
report unavailable identity-review details as missing rather than inventing them.
Identity mappings explain resolution and are not additional evidence-bearing hops.

### Traverse classified relationships

Keep these roles explicit:

| Relationship role | Retrieval treatment |
| --- | --- |
| Substantive semantic assertion, such as a decision, dependency or reported outcome | Traverse only eligible assertion graphs; preserve its predicate and evidence. |
| Project or other associative `k:relatedTo` link | May route retrieval, with its own origin, status and rationale; does not imply containment, causation or equivalence. |
| Accepted identity mapping | Apply through the existing projection; expose the resolution receipt without rewriting authoritative assertions. |
| Theme membership and entity/theme navigation | Optional separate navigation context; never a factual path step or claim acceptance, including accepted memberships. |
| Ontology, framework structure and generic type metadata | Do not treat arbitrary shared metadata as personal-evidence relationships. Framework definitions remain eligible when explicitly relevant to the request. |

Each hop is one stored assertion, including project associations. Return traversal
direction separately from the original triple: following an incoming association
does not create its inverse assertion. Literal values can be returned as endpoints
but cannot be expanded as entities. Keep professional and framework knowledge in
one dataset, with explicit eligibility policies rather than separate stores.

Default to conservative predicate and direction policies. Generic high-degree
nodes, including a shared author, must not become automatic shortcuts
between unrelated work. Allow explicit selection of such a seed with stricter
expansion caps and clear omissions. Check eligibility before expansion and bound
the frontier as well as final output; limiting the returned rows alone is insufficient.

Use a stable breadth-first order with explicit predicate/direction ordering and IRI
tie-breaks initially. This makes results reproducible, not necessarily relevantly
ranked. Evaluate deterministic lexical ranking before adding more complex methods.

### Preserve evidence and effective state along the whole path

Load through `query.load_store`; do not construct a raw union as a substitute for
review replay. Default results may contain active Accepted and Unreviewed claims,
clearly identified. Rejected or superseded records require a separate explicit
historical operation and cannot route an ordinary active path.

Return assertion IDs, original and projected endpoints, predicate, traversal
direction, origin, effective review status, lifecycle, knowledge kind, rationale,
source quotations and revision-specific locators/hashes for **every** path edge.
Keep classification/theme review separate from claim review. An accepted Thought
remains a Thought; a reported outcome remains an attributed account.

An accepted-only path requires every evidence-bearing hop to be Accepted. In the
default mode expose which steps are unreviewed and which are inferred; never promote
either because other steps are accepted. Do not replace mixed states with a single
accepted label. A path containing an Unreviewed association must remain absent from accepted-only
results until that association is explicitly accepted.

Check evidence availability and integrity before describing citations as verified.
The existing loader checks reviewed RDF fingerprints, not every source file's
current bytes. Missing or changed snapshots/transcriptions must be surfaced as
invalid citations; they must not silently support an accepted result. Visual
transcription checks establish consistency with the stored transcription, not
independent verification of the image's content or the underlying event.

Deduplicate presentation and quote repetition while retaining assertion IDs,
revision IDs, review states and all source occurrences. Group exact hashes,
multiple archive occurrences, revisions of one logical document and overlapping
images appropriately. Shared authors or repeated accounts do not establish source
independence. Do not equate different revisions or discard conflicting claims;
report independence as unknown where the available provenance cannot establish it.

### Enforce a complete response budget

Investigate configurable maximum depth, expanded entities, per-node degree,
assertions, evidence passages and serialised context size. Start the first
experiment with ADR 0015's provisional limits: two hops, ten assertion IDs **including
association steps**, four passages and 4,000 Unicode characters in the complete JSON
response. These are experiment defaults, not universal product limits or token
counts. Also set explicit finite expansion/degree caps and test their boundaries.

Count the response envelope, identifiers, evidence, path explanations and omission
metadata in the size budget. Do not return a substantive assertion without the
association/path records needed to interpret it. Prefer fewer complete paths over
orphaned edges. Initially omit a passage/path that cannot fit rather than silently
cutting away source qualifications. Reject budgets too small for a valid envelope.

The response contains the selected seed, applied policy, entities,
assertions, ordered paths with per-edge states, evidence/source groups, budget usage
and omissions. Indicate limits reached, evidence too large, skipped hubs, unavailable
citations and known omitted counts. If expansion stops before the whole neighbourhood
is inspected, say that further omissions are unknown; do not report false completeness.
Keep JSON ordering stable. Return no source documents or unrelated metadata merely
because the backend has loaded them.

## Alternatives

| Alternative | Tradeoff |
| --- | --- |
| Send the whole graph or all documents to an assistant | Simple calling interface, but defeats selective context, exposes unrelated material and gives no bounded evidence contract. |
| Caller-managed raw SPARQL | Already useful for local investigation; every caller would have to implement state, direction, provenance, deduplication and budgeting policy consistently. |
| Keyword/full-text retrieval alone | Cheap and reproducible, and may recover the same source documents. Retain it as a serious baseline; it may miss indirect relationships or return excessive context. |
| Graph traversal alone | Explains recorded paths but depends on curation, direction and incomplete relationships; unrelated hubs can overwhelm results. |
| Hybrid lexical and graph retrieval | May cover omissions in either method; adds ranking and budget allocation choices that need evaluation. Start with a fixed deterministic union in the evaluation harness. |
| Embeddings or an LLM retrieval planner | Could improve semantic matching, but introduces new dependencies, variability and evaluation questions before basic retrieval semantics are established. Defer. |
| MCP-first implementation | Provides a transport before the core contract and access policy are proven. Defer to a thin adapter over tested local functions. |

## Consequences and risks

A local retrieval function can give the CLI, evaluation harness and later adapters
one interpretation of review and provenance. It adds selection policy that must be
visible and tested. The graph remains useful without an AI model, and retrieval
does not write assertions or implement discovery.

Main risks are incomplete extraction, mistaken identities, weak associations,
unreviewed routing steps, high-degree hubs, stale evidence, duplicate-source inflation,
over-truncated context and ranking bias. Boundaries and negative cases must address
these explicitly. A short context package may omit useful contradictions; report
limits rather than implying consensus. Source acceptance is not objective truth.

The current graph contains hand-curated routing information. Evaluation must record
that curation and identity-review effort, as well as future retrieval review effort.
Synthetic fixtures can validate mechanics but cannot demonstrate general superiority.
Do not reuse a single worked example as the only benchmark or infer accuracy from
the 304 connected edges. Changes in identities, evidence or reviews require fresh
retrieval; a later cache would need input/policy fingerprints and invalidation.

The local API does not create an access-control boundary by itself. Before exposing
an adapter to an assistant, authorisation must constrain eligible records before
traversal, including hidden neighbours, IDs and source passages. Themes are not
security scopes. Result-size budgets do not provide privacy isolation.

## Evaluation before comparative claims

Freeze a small question set and independently assessed relevant evidence before
running the competing methods. Assessors should use source material, not select
questions merely because a known graph path answers them. Include held-out notes
and questions whose expected evidence has no existing relationship. Separate
synthetic correctness tests from evaluation on real material.

Compare keyword/full-text, semantic graph traversal and a deterministic lexical/graph
hybrid over the same authorised corpus, including the same visual transcriptions.
Define each method's searchable fields, case/token rules, ranking, direction policy,
deduplication and output budget. Full-text retrieval must be allowed to match
elsewhere in a document, not only inside the graph's quoted span. Reserve embeddings
as a later baseline rather than requiring them for this comparison.

Measure relevant evidence retrieved and missed against the labelled set, incorrect
or irrelevant connections, citation accuracy, unsupported conclusions, latency,
context size and human review effort. Record disagreements and uncertain relevance.
Assess unsupported conclusions through human review of what the evidence package
actually supports; the initial retriever need not generate an answer or invoke an LLM.

Report source loading/indexing separately from repeated retrieval timings, corpus
and dependency versions, cache state, budgets, and latency distributions. Measure
the complete serialised context in characters and UTF-8 bytes; report tokens only
with a stated tokenizer if one is introduced later. Record curation time and reviewer
corrections rather than treating the graph's extra annotations as free information.

Negative cases must include a same-name different entity, an unreviewed identity,
a rejected or superseded path step, an accepted claim reached only through an
unreviewed association, unrelated work sharing an author or a theme, repeated document revisions
revisions, overlapping images, an absent relationship despite relevant source text,
and plans or self-assessments that must not become completed outcomes or facts.
Include a lexical distractor where “constraints” does not identify Theory of Constraints.

## Smallest development increment and acceptance criteria

Implement one read-only local function taking an explicitly selected canonical IRI
and a policy/budget object, plus a thin CLI JSON wrapper using existing tooling.
Add only the small label/IRI candidate lookup needed for seed selection. Reuse the
loader and vocabulary; do not introduce another datastore or rewrite assertions.

Use TDD with a small synthetic fixture and source-first relevance labels. Include
one two-hop project path, a second source context and the negative cases below.
Use at least three predefined evaluation questions spanning a known connection,
relevant evidence missing a graph link, and an unrelated lexical/identity distractor.
Compare the graph output with a simple full-text baseline and fixed hybrid union
in an evaluation harness; keep quality claims limited to that fixture until held-out
real-note evaluation is complete.

1. Return stable canonical/source identities, assertion IDs, directions and evidence
   for the expected path after normal review replay. Unreviewed identities and
   same-name distractors cannot supply a shortcut.
2. An accepted substantive claim behind an unreviewed association remains a mixed
   path and is excluded by accepted-only retrieval. Rejection/correction changes
   eligibility; history remains available separately. A Thought retains its kind.
3. Enforce depth, frontier, degree, assertion, passage and complete serialised-size
   limits, including exact-boundary and too-small-envelope tests. No orphaned paths,
   silent clipping or unknown omissions presented as zero. Identical inputs yield
   byte-identical JSON.
4. Generic author/type/theme nodes cannot connect unrelated records by default.
   Framework and personal evidence remain available under explicit eligibility
   rules; associations and identity mappings remain distinguishable from claims.
5. Every returned quotation resolves to its recorded revision. Changed/missing
   evidence is reported. Duplicate archive occurrences, document revisions and overlapping
   images retain provenance without being counted as independent corroboration.
6. Record all three retrieval modes' relevance, omissions, wrong connections,
   citation accuracy, unsupported conclusions, timings, context size and review
   effort against frozen labels, including failures. Do not claim general superiority.
7. Existing tests pass; source/RDF data and review events remain unchanged. No MCP
   server, embeddings, model calls, new discovery assertions or autonomous process
   is required. Keep historical evaluation records separate from public synthetic fixtures.

## Implementation status

Bounded retrieval is implemented. Question-aware ranking and selection are refined
by ADR 0020; discovery by ADR 0023; scoped transport by ADR 0021. Current defaults
and response fields belong in the [retrieval guide](../docs/retrieval.md), rather
than being inferred from this original experiment's proposed budgets.

Synthetic tests protect traversal, review, provenance, limits and omission behaviour.
Independent source-support and relevance evaluation remain incomplete. Historical
private benchmarks do not establish general retrieval superiority.
