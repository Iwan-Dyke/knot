# ADR 0001: Start with an evidence retrieval proof of concept

- Status: Superseded
- Date: 2026-11-03
- Implementation: Not implemented; replaced before delivery
- Documentation reviewed: 2026-11-07
- Superseded by: [ADR 0004](0004-local-semantic-store-and-assistant-workflow.md)

This proposal was replaced during design discussion. Phase 1 now prioritises storing
existing documents and extracted semantics in RDF. The retrieval experiment below
remains a possible later evaluation, not an agreed implementation scope.

## Context

KNOT starts as a local-first personal knowledge graph intended for use by AI
assistants. The question is whether explicit relationships improve retrieval of
evidence scattered across documents while preserving source context and uncertainty.

Loading RDF and running SPARQL proves technical feasibility, but does not establish
retrieval value. Adding AI extraction at the same time would make it difficult to
separate modelling problems from extraction errors.

## Proposed decision

Build one small Python CLI increment using hand-authored synthetic knowledge.
Use four short source documents covering a project, decision, outcome and capability
assessment. Include another project with an incomplete evidence chain, an unreviewed
inference and a conflicting claim.

Provide two commands:

```text
knot validate <dataset>
knot evidence <dataset> --capability <iri>
```

Validation checks RDF syntax and the required assertion and passage metadata.
Retrieval uses a fixed SPARQL query and returns JSON containing evidence paths,
assertion identifiers, review status and revision-specific source passages.
Unresolved or conflicting evidence must remain distinguishable from accepted paths.
No missing relationship may be invented to complete an answer.

Use `pyoxigraph` as the runtime dependency, standard-library `argparse` for the CLI,
and `pytest` and Ruff for development. Expose test, lint and format commands through
a justfile. Start with `src/knot/`, synthetic fixtures under `tests/fixtures/`, and
tests for storage and retrieval. Keep modules small; do not introduce provider or
database interfaces before a second implementation requires them.

Define evaluation questions and expected supporting passages before implementation.
Compare graph retrieval with a documented keyword-search baseline over the same
sources. Report expected-passage recall and unsupported connections for each question;
record the baseline's matching and ranking rules so the comparison can be repeated.

## Acceptance criteria

1. Creating, persisting and reloading the synthetic dataset preserves equivalent
   RDF quads and retrieval results.
2. The capability query returns the expected cross-document evidence chain, with
   revision-specific passages supporting every relationship used in the answer.
3. Unreviewed and rejected claims cannot establish accepted evidence paths;
   conflicting claims remain inspectable.
4. Removing a required connection produces an incomplete result without inventing
   a connection, and the result distinguishes missing evidence from a negative claim.
5. A reproducible comparison reports passage recall and unsupported connections
   against the predefined expected results for graph retrieval and keyword search.

## Alternatives and consequences

- A persistence-only demo is smaller, but does not address the central question.
- Beginning with an LLM would exercise more of the eventual workflow, but introduces
  provider, privacy and extraction variability before the model is tested.
- A hand-authored fixture isolates retrieval behaviour, but can favour graph queries.
  Results establish feasibility on this fixture, not superiority on real collections.

## Boundaries and follow-up

Do not implement ingestion, external LLM calls, natural-language query translation,
MCP, APIs or cloud infrastructure in this increment. Agree the next phase separately.
Later evaluation must include held-out questions, realistic collections, extraction
errors and an AI assistant consuming the returned evidence. JSON output alone does
not demonstrate improved AI answers.
