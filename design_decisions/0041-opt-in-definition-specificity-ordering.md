# ADR 0041: Offer bounded definition specificity ordering

- Status: Proposed
- Date: 2026-11-08
- Implementation: Opt-in MCP/Python option; default unchanged
- Extends: ADRs 0020, 0021, 0027 and 0028
- Supersedes: None

## Context

The evidence-sufficiency audit identified ten recoverable complete-set misses at
12,000 characters. Six concern selecting the requested framework scope or criterion
level. A generic overview or another level can match incidental question words and
outrank a more specific definition. The candidate's source-backed title provides a
bounded disambiguation signal without a model or new assertion.

The benchmark itself also needed correction: an engine account's explicit
implementation-not-proof qualification suffices for a narrow cutover question.
This changes the provisional default baseline from 34/55 to 35/55 and its achievable
ceiling from 44/55 to 45/55. Those are evaluation changes, not retrieval gains.

## Decision

Expose `definition_order=true` through question-only MCP/Python retrieval, disabled
by default. Before the existing relevance-first selector, refine only the positions
occupied by verified native Definition packages with faithful-restatement provenance.
Group by the exact set of original source revision identifiers. A title matching a
strict superset of query terms precedes a less specific title in that group. Stable
topological ordering uses original rank to break ties among eligible candidates.

Reuse the existing tokenizer. Introduce no weights, domain-specific names, benchmark
identifiers, model, database or new retrieval path. Keep candidate generation,
numeric relevance scores, complete provenance and selection costs unchanged.
Never remove packages. Kind and title are ranking metadata, not factual acceptance
or identity resolution. Access filtering and fresh source checks precede this step.

The pure ordering function is bounded to 128 candidates. Seeded retrieval, exact
historical notes and selected-subject gathering are outside this option's scope and
reject the option. The complete MCP response remains subject to the existing strict
character limit. The original `relevance_first` selector still chooses the final
set; per-match scores describe unchanged lexical relevance, not title precedence.

## Evidence and promotion boundary

One frozen implementation cycle, 55 existing questions plus four new same-author
held-out questions, across 4k/8k/12k/24k characters. At 12k, complete questions improve
from 35/55 to 36/55. At 8k, 27/55 becomes 28/55 and another case gains partial support.
At 4k and 24k complete counts are unchanged. No previously delivered annotated support,
qualification or correction is lost. Held-out results remain unchanged.

Retain the narrow opt-in integration; do not replace the general default. Gains are
small and concentrated. Source-backed labels remain provisional; generated-answer
quality was not measured with a controlled model backend. This is evidence for a
limited deterministic option, not proof of general semantic understanding.

## Consequences and alternatives

The ordering cannot reliably bind several skill/level/framework facets in a question.
It can promote a different topical definition without answering the question. It
does not resolve a wrong non-definition primary result, later corrections, ambiguous
source claims or complete evidence that cannot fit. No additional heuristic tuning
was undertaken after the benchmark. Default promotion would require broader evidence
of usefulness; independent review can focus on disputed cases rather than every note.

Tests cover deterministic ordering, unchanged scores/packages, source-group boundaries,
incomparable titles, scope denial, source mutation and real MCP budgets. Production
integration is checked against the frozen experimental responses. Research artifacts
retain historical labels and explicit evaluation uncertainty.
