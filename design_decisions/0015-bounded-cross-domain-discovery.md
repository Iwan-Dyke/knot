# ADR 0015: Start discovery with a bounded shared-concept experiment

- Status: Proposed
- Date: 2026-11-03
- Implementation: Not implemented; persistent inference proposal remains open
- Documentation reviewed: 2026-11-07
- Implements: ADR 0014; proposed after the basic organisation in ADR 0016
- Extends: ADRs 0003, 0005, 0009, 0010 and 0011

## Context

Subsequently, ADR 0019 accepted and implemented the initial bounded retrieval
operation separately. The shared-concept discovery rule, candidate dependencies
and later roadmap below remain proposed.

At proposal time, KNOT stored source-backed assertions, projected confirmed
identities and supported review, but lacked bounded retrieval and discovery.
ADRs 0019–0023 later delivered retrieval and ephemeral subject discovery; the
persistent candidate-dependency proposal here remains unimplemented. A broad discovery engine would introduce
complexity before there is evidence that its suggestions are useful.

## Proposed decision

Use synthetic reading, work and personal-reflection sources connected through
one explicitly confirmed canonical concept. Include unrelated sources, a duplicate
account and a similarly named concept with a different meaning as negative cases.
Keep all material in the same logical dataset and use existing tooling.

Add optional assertion knowledge kind, claimant and recorded time. Start with
Statement, Observation and Thought. Missing classification remains unspecified.
Represent a speculative proposition as the content of a thought or hypothesis,
not a bare causal edge about the world. Review acceptance never changes its kind.

Use `k:supportedByAssertion` for discovery premises and `k:discoveryMethod` for
the rule. Keep passage evidence distinct from premise assertions: current review
readers expect document evidence under `prov:wasDerivedFrom`.

Run a deterministic, explicitly seeded shared-concept rule. Propose at most three
`k:relatedTo` candidates between distinct records referring to the same eligible
canonical concept. Exclude generic author/date/type matches, existing direct
connections, duplicate pairs and unchanged rejected suggestions. This proposes
possible relevance, not causation or a validated analogy.

Persist candidates as Inferred and Unreviewed with premise IDs, pinned content
fingerprints, relevant identity decisions, method version, rationale and source
references. Dependency changes must be detected before use or acceptance. A stale
candidate cannot establish an accepted path; keep its historical record and require
explicit reconciliation. Existing premise acceptance does not accept a candidate.

Provide a local seed-entity retrieval operation returning structured JSON. Proposed
experiment bounds are two hops, ten assertions, four source passages and 4,000
serialised characters. Return uncertainty, origin, kind, review state, premise IDs,
evidence and explicit omission information. Reserve space for a valid response
envelope; reject budgets too small to represent it. Do not equate characters with
tokens or implement the conceptual natural-language context API yet.

Default retrieval may expose candidates with clear status under ADR 0003.
Accepted-only traversal excludes paths that require candidates. Reuse the same
policy in retrieval, discovery and any later interface.

## Acceptance criteria

1. RDF round trips preserve knowledge kinds, sources and confirmed concept identity;
   same-name distractors and unreviewed identity matches do not connect records.
2. The expected candidate has exact supporting citations and a reproducible
   explanation. Repeated generation is idempotent; rejection suppresses the
   unchanged candidate.
3. Review decisions survive rebuilding. Changed, rejected or superseded premises
   invalidate dependent candidates, and accepting a Thought preserves its kind.
4. Bounded context contains the expected cross-domain evidence and no unrelated
   passages; limits and accepted-only policy are enforced with explicit omissions.
5. A predefined keyword comparison reports evidence recall, wrong connections,
   citation accuracy, unsupported conclusions and review effort. Existing tests
   remain green, with no private sources required by the new tests.

## Alternatives and consequences

Graph traversal alone can reveal a connection but does not exercise candidate
persistence and review. Embeddings or an LLM might suggest more diverse links,
but add variability and dependencies before basic discovery quality is established.
A seeded rule is reproducible, explainable and small enough for the current CLI.

A curated synthetic fixture demonstrates mechanics and can favour graph retrieval.
Record that limitation and the cost of explicit concept mapping; validate with
held-out real notes before claiming general retrieval or discovery improvement.

## Boundaries

Do not implement the whole identity register, temporal belief model, automatic
contradiction detection, incremental extraction engine, vector search, autonomous
agents, MCP server or web application in this increment. Agree this proposal before
implementation.

## Later roadmap

These proposals remain pending after the shared-concept experiment:

| Increment | Outcome and gate |
| --- | --- |
| Identity review and a real sample | Add identity review and split operations; finish relevant identity and framework mappings; evaluate selected real notes. |
| Knowledge evolution | Model one belief revision or tested hypothesis with context and time; verify current and historical retrieval. |
| Incremental ingestion | Process changed revisions and extraction scopes; invalidate dependent results without re-extracting everything. Stage and validate complete batches before promotion. |
| Better discovery and evaluation | Compare methods where measured failures justify them; measure useful suggestions and review effort. |
| Scoped AI integration | Expose tested retrieval through an authorised MCP adapter, filtering eligible records before traversal and budgeting results afterwards. Keep providers optional. |

The Emacs/Org authoring goal in ADR 0004 can use the same assertion and review
operations once the workflow is agreed; it does not require MCP or another store.
