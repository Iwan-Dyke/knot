# ADR 0020: Rank question-aware graph paths and source context together

- Status: Accepted
- Date: 2026-11-04
- Implementation: Implemented; independent relevance evaluation pending
- Documentation reviewed: 2026-11-07
- Extends: ADR 0019
- Preserves: ADRs 0003, 0010, 0011, 0016 and 0017

## Context

Deterministic neighbourhood traversal preserves provenance but can spend a small
response budget on evidence unrelated to the caller's question. Useful source text
may also have no extracted assertion. Graph-only retrieval is therefore insufficient
for questions spanning notes, decisions and qualifications.

## Decision

Provide graph, text and hybrid retrieval over the same eligible dataset. Keep
no-question graph traversal deterministic. A question enables lexical/intent ranking
of graph routes and verified source units. No model provider or embedding index is
required. Ranking signals indicate relevance, never truth or independent support.

Graph retrieval follows review-aware assertion paths, preserving original and
projected endpoints and evidence for every hop. Text retrieval can return source
sections without assertions. Text context retains `claim_review: null`; it does not
restore a rejected assertion or manufacture an entity relationship. Accepted-only
retrieval excludes source-only context and requires every graph hop to be Accepted.

### Source units and qualifications

Use complete sections, preserving ancestor headings, exact Unicode/line locators,
revision hashes and recognised qualifications. Explicit interpretation boundaries
may separate an evidence body from commentary when caveats remain intact. Unknown
cross-section or cross-note qualifications are not automatically resolved.

Seed context requires meaningful label terms, a verified assertion anchor or
eligible same-document context. Same-name matches remain lexical relevance, not
identity acceptance. Unassociated notes remain eligible for question-only search.

### Ranking and selection

Rank within finite revision, section, candidate, degree and frontier limits. Hybrid
reserves candidate capacity for graph exploration, then uses the remainder for text.
Both channels share one response budget, including provenance and omission metadata.

The initial implementation interleaved ranked channels. Subsequent refinements
select bounded combinations of complete evidence packages using relevance, question
coverage, repeated content, qualification cues and measured serialised cost. Stable
ties and bounded trials retain reproducibility. Higher-ranked individual candidates
can lose to a more useful feasible combination; the selector is not a global optimum.

Required qualifying source context stays with its claim during trimming. Overlapping
quotations may share one containing passage; exact citation ranges remain available.
Do not clip source quotations or count shared source bytes as corroboration.
Actual omission metadata may release room for one additional complete package.
Verify the final response at its exact wire size and report excluded evidence.

### Compatibility and resource bounds

Keep existing Python and CLI entry points and reload current sources/reviews per
public call. Optional access scopes filter eligibility before ranking. Shared budgets
apply to traversal, text candidates, final response and MCP framing. The current
defaults and API fields are documented in [retrieval](../docs/retrieval.md).

This decision adds no persistent cache, new authority, automatic acceptance,
contradiction engine or answer generator. ADR 0023 subsequently adds caller-selected
discovery and gathering over these same retrieval components.

## Alternatives

- Graph-only traversal misses assertion-free knowledge and question relevance.
- Text-only search remains a useful baseline but cannot explain stored relationship paths.
- Fixed interleaving is simple but can waste budget on redundant or expensive packages.
- Learned ranking may improve paraphrase recall but introduces dependencies and evaluation
  requirements; investigate measured failures before adopting it.

## Consequences

Complete evidence and qualifications cost space. A small budget can return omissions
instead of useful context, and lexical ranking can miss synonyms or favour verbosity.
Bounded selection improves allocation but adds computation and cannot establish
completeness. Scope checks and provenance remain mandatory regardless of score.

## Validation and implementation

Implemented in `retrieval_engine/`. Synthetic tests cover question-sensitive ranking,
graph/text mixing, source-only results, review and identity negatives, citation ranges,
qualification retention, deterministic selection and exact output limits.

Evaluate graph, text and hybrid modes on equal budgets with source-first labels,
held-out questions, recorded authorship and explicit unjudged results. Separate
preparation, ranking and selection time. Private development benchmarks informed
refinements but do not constitute independent relevance or support validation.

## Question-only selection refinement, 2026-11-07

Question-only retrieval has no graph traversal. Applying cross-channel fusion to
its sole text channel discarded parts of the existing relevance score, allowing
keyword-rich background to outrank more focused evidence. Preserve the text score
and ordering for these requests, including when the requested mode is hybrid.

For question-only requests, retain the highest-ranked complete package that fits,
then use the existing marginal density selector for complementary context. Report
this as `selection.strategy = relevance_first`. An oversized package remains
omitted intact; neither its quotation nor its provenance is clipped to make room.
Keep the existing density selection and graph/text fusion for explicit seeds and
selected-subject gathering.

This deliberately trades some aggregate snippet coverage for a stable primary
account. A lexical top result can still be wrong; retaining it is not an answer
correctness guarantee. Merely replacing the scorer or using pure rank selection
introduced other losses in the bounded comparison. No special project names,
known answer strings, recency-as-truth rules or increased limits are introduced.

Synthetic tests cover keyword-rich background versus focused evidence, complete
primary context, oversized-package fallback and complementary evidence. The
private frozen-question comparison improves smaller-budget expected-record
coverage but retains a larger-budget record substitution and substantial broad
misses. Historical withheld source spans remain recovered; independent answer
evaluation is still pending. This is an incremental selection improvement, not a
solution to early source-routing misses or cross-note contradiction handling.

## Indexed routing experiment (2026-11-07)

A subsequent bounded comparison evaluated body-only BM25, existing metadata as
index context, rank-fused routing and existing note-link expansion. The indexes
were disposable, built from an already scoped view, and did not replace source
verification. Index construction was charged separately from warm query work.

The experiment does not justify replacing the current default. More relevant
sources can reach verification without surviving candidate ranking and selection.
Contextual BM25 ranking improved some development answers but displaced a relevant
reading account on a withheld question. MCP transport pruning also removed a
necessary clarification, offsetting the smaller-budget development gains.

Keep alternative routes experimental until improvements survive the complete
delivery path. The next comparison should test complementary evidence selection
against the actual transport budget and bounded follow-up retrieval for explicit
evidence gaps. Existing discovery/gather interfaces supply that mechanism without
a new ontology or agent framework. A production index additionally needs explicit
scope isolation, invalidation and bounded build work; fresh citation verification
alone does not establish a safe cache lifecycle. No automatic route selector or
new production storage model is adopted by this experiment.
