# ADR 0052: Evaluate reviewed evidence with bounded deterministic rules

- Status: Proposed
- Date: 2026-11-12
- Implementation: Not started
- Related: [ADR 0029](0029-semantic-integrity-and-explicit-identity-resolution.md), [ADR 0030](0030-continuous-knowledge-curation.md), [ADR 0051](0051-reviewed-ontology-evolution.md)
- Supersedes: None

## Context

KNOT already preserves assertion provenance, review events, separate identity
decisions and immutable sources. Its [retrieval service](../docs/retrieval.md)
returns bounded evidence packages; omissions and relevance ranking prevent those
packages from establishing exhaustive absence. [Acceptance](../docs/reviews.md)
approves a claim's representation, not its independent truth. These boundaries
must survive any addition that computes conclusions from stored knowledge.

UnlikelyAI's STRIDE (Semantic TRanslation Into Deterministic Execution), described
in [Breaking Through AI's Trust Ceiling](https://williamtp.substack.com/p/breaking-through-ai-trust-ceiling),
proposes translating material into reusable semantic artifacts, validating them,
and executing consequential reasoning deterministically. This motivates a
bounded evaluation contract; it supplies neither KNOT's implementation nor proof
that extraction, sources or rules are correct.

AWS Context Ontology Accelerator provides related practical ideas. Its
[routing design](https://github.com/aws/context-ontology-accelerator/blob/d28c001cfcc0460cbd1ec1b356a63dcad272790e/packages/context-manager/docs/query-routing.md)
separates governed metric execution from generated queries and synthesis. Its
[SPARQL validator](https://github.com/aws/context-ontology-accelerator/blob/d28c001cfcc0460cbd1ec1b356a63dcad272790e/packages/context-manager/src/coa_serve/tier2/ontop/sparql_validator.py)
checks specified structural and semantic constraints; its
[planner](https://github.com/aws/context-ontology-accelerator/blob/d28c001cfcc0460cbd1ec1b356a63dcad272790e/packages/context-manager/src/coa_serve/tier3/agentic/planner.py)
still uses an LLM for tool proposals and sufficiency judgements. These are
inspirations for explicit boundaries, not equivalent guarantees or dependencies.

## Decision

Propose an optional, read-only evaluator for a small catalogue of versioned rules.
Retain authoritative RDF/TriG files, existing review workflows and Oxigraph.
Application code owns rule selection validation, execution and result assembly.
An AI client may propose a structured request or discuss its result; those acts
remain outside the execution guarantee. No arbitrary AI-authored query, code or
new rule runs in this route. Existing exploratory retrieval remains available.

### Exact requests and eligible inputs

A typed request identifies the rule and version, subject IRIs, framework or other
definition revisions, supported qualifiers and any explicit temporal scope.
Resolve ambiguous names before evaluation. Unsupported fields, unresolved
identities and unrepresented qualifications require abstention or disambiguation;
never silently drop them or substitute a broader question. Display the interpreted
request. Schema validation cannot prove that an AI translation preserved the
original question; the guarantee begins at the exact structured request.

Each rule declares its finite input scope, supported predicates, allowed kinds
and origins, temporal interpretation, eligibility conditions and execution limits.
Eligible premises require Active, Accepted assertions, valid review replay,
verified source pins and the existing access checks. Identity bindings used in a
derivation require their own applicable reviewed evidence. Acceptance never turns
a Thought, Hypothesis or attributed Assessment into an observed fact. Preserve
Explicit/Inferred origin and source attribution throughout.

Construct an immutable evaluation input manifest pinning rule code/configuration,
ontology version, assertion fingerprints, review and identity decisions, source
revisions/hashes, qualifications, temporal parameters and the accessible input
view. Reuse existing loaders and provenance validation. Verify a coherent read
or fail explicitly if inputs change; this proposes no whole-dataset transaction
across files or manual writers. A corrupt input is an integrity failure, never
evidence that no supporting claim exists.

### Results with defined limits

Use distinguishable outcomes rather than a single confidence score:

| Outcome | Meaning |
| --- | --- |
| Support found | Eligible premises satisfy this versioned rule. Preserve their attribution and qualifications. |
| No qualifying support | Enumeration finished for the rule's explicitly defined accessible scope, with no eligible support. This says nothing about unrecorded events or inaccessible knowledge. |
| Unknown | Scope enumeration, required premises, interpretation or evaluation is incomplete; include a permitted reason. |
| Conflict | An explicit incompatibility rule is satisfied by eligible claims about the same resolved referent and overlapping applicable temporal/contextual scope. |

Absence is not falsity. Multiple values, differing source dates or successive
project states are not automatically conflicts. A rule needing complete evidence
cannot certify a result from a truncated neighbourhood. Positive witnesses may
be reported during incomplete enumeration, but completeness stays explicit;
negative or universal conclusions require completion of their declared scope.
An execution or output budget must not remove an essential premise or its caveat
while retaining an apparently complete conclusion.

### Execution receipts and freshness

Return the normalised request, dependency versions, applicable scope, completion
status, supporting assertion/source references, rule steps and resulting bindings.
These are records of executed checks, not generated explanations. Fixed inputs
and rule versions produce the same ordered result and derivation; timing metadata
need not be identical. A fixed renderer can present this receipt without an LLM.

Apply access filtering before source reads and derivation. Receipts expose no
hidden source identifiers, hashes, quotations, member counts or global currentness
hints. Use scope-relative completeness and opaque scope-version tokens where
needed. A saved receipt grants no future access; replay still requires current
authorisation to every dependency.

Invalidate cached current results when rules, ontology, assertions, reviews,
identity bindings, source versions, qualifications or the scoped eligible view
change. Include newly eligible assertions, not only premises previously used:
otherwise an earlier absence result can remain incorrectly current. Historical
replay pins historical inputs explicitly. Source revision changes require
revalidation, not automatic transfer of acceptance or deletion of earlier evidence.

### First bounded use case

For a synthetic project and specified framework revision, report which criteria
have eligible reviewed `supports` mappings and their evidence. Enumerate the
selected criteria explicitly and retain each mapping's Assessment meaning,
reviewer, origin and sources. Report missing mappings using the outcomes above.
This measures recorded mapping coverage, not capability, achievement quality or
an objective assessment score. No rule infers a mapping from textual similarity.
The first coverage rule adds no general temporal or contradiction model; requests
requiring unsupported interpretations remain Unknown.

Results remain disposable derived records. Persisting a conclusion as knowledge
requires a separately authorised candidate/review workflow; it creates no new
Accepted assertion automatically. [ADR 0051](0051-reviewed-ontology-evolution.md)
governs proposed vocabulary changes without authorising this evaluator's rules.

## Alternatives

- Stronger prompts and repeated LLM checking can improve interpretation but do
  not provide reproducible rule execution.
- Existing exact graph queries remain useful; accepting arbitrary generated
  queries does not establish a stable, reviewed evaluation contract.
- General OWL reasoning, a universal semantic language or COA's complete platform
  would introduce substantially broader semantics and dependencies. None is
  required for the proposed finite rule catalogue.

## Consequences

Bounded evaluations become repeatable and inspectable while unknowns remain
visible. Costs include maintaining rules, dependency manifests, scoped replay
and explicit temporal semantics. Determinism cannot repair misleading sources,
incorrect mappings or flawed rules. Review responsibility remains separate from
execution. This proposal changes neither ordinary capture nor retrieval defaults.

## Validation and implementation

Nothing in this ADR has shipped. First specify the request, rule and receipt
schemas, then implement one coverage rule using existing source, access, identity
and review boundaries. Resolve snapshot construction and stale-read behaviour
before exposing an API or MCP operation.

Use synthetic fixtures to check repeatability, exact qualifications, missing
premises, incomplete enumeration, explicit conflicts versus legitimate multiple
values, temporal changes, corrupted citations and invalid review replay. Check
revoked grants, concealed metadata, new eligible evidence, stale receipts and
rule/ontology changes. Verify no capture, acceptance or source mutation occurs.
Passing these tests establishes the bounded contract's behaviour, not factual
truth, correct natural-language interpretation or acceptance of this proposal.
