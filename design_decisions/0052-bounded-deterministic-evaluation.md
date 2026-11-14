# ADR 0052: Adopt STRIDE-inspired evaluation of reviewed knowledge

- Status: Accepted for the bounded evaluator and initial coverage rule; later capabilities require separate decisions
- Date: 2026-11-12
- Decision updated: 2026-11-13
- Implementation: Partial; coverage, checked routing, artifact selection, receipt revalidation and reviewed decision explanations implemented; historical replay and broader rules deferred
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
and executing consequential reasoning deterministically. Its examples include
policy trees and validated, self-contained responses reproduced at query time.
The useful investment is a representation checked once and reused across many
questions, with revalidation when its dependencies change. This motivates a
bounded evaluation contract; it supplies neither KNOT's implementation nor proof
that extraction, sources or rules are correct.

The public material inspected on 2026-11-13 describes the architecture and a
commercial platform. UnlikelyAI advertises self-service integration, but this
research did not find a public STRIDE engine, artifact specification or developer
API documentation. This decision adopts the published architectural pattern in
KNOT's existing stack. It selects no UnlikelyAI service or Universal Language
dependency and makes no claim of compatibility with their implementation.

AWS Context Ontology Accelerator provides related practical ideas. Its
[routing design](https://github.com/aws/context-ontology-accelerator/blob/d28c001cfcc0460cbd1ec1b356a63dcad272790e/packages/context-manager/docs/query-routing.md)
separates governed metric execution from generated queries and synthesis. Its
[SPARQL validator](https://github.com/aws/context-ontology-accelerator/blob/d28c001cfcc0460cbd1ec1b356a63dcad272790e/packages/context-manager/src/coa_serve/tier2/ontop/sparql_validator.py)
checks specified structural and semantic constraints; its
[planner](https://github.com/aws/context-ontology-accelerator/blob/d28c001cfcc0460cbd1ec1b356a63dcad272790e/packages/context-manager/src/coa_serve/tier3/agentic/planner.py)
still uses an LLM for tool proposals and sufficiency judgements. These are
inspirations for explicit boundaries, not equivalent guarantees or dependencies.

## Decision

Adopt an optional, read-only evaluator for a small catalogue of versioned rules.
Retain authoritative RDF/TriG files, existing review workflows and Oxigraph.
Application code owns rule selection validation, execution and result assembly.
An AI client may propose a structured request or discuss its result; those acts
remain outside the execution guarantee. No arbitrary AI-authored query, code or
new rule runs in this route. Existing exploratory retrieval remains available.

The accepted scope is the evaluation contract below and one framework-coverage
rule. It establishes a reusable execution boundary for subsequent knowledge
questions. Broader relationship queries, policy trees and general approved prose
answers require separate contracts; this decision does not approve their semantics
or implementation implicitly. ADR 0056 now supplies the first bounded decision-
explanation contract. ADR 0051 remains a separate proposal.

### Reusable meaning and translation

Use the existing source-preserving curation workflow to prepare representations.
An assistant may propose assertions with exact evidence; the existing explicit
review workflow determines their eligibility for evaluation. Manual authoring
uses the same contracts. Do not silently reinterpret prose during execution.

Curated notes already provide coherent, attributed accounts with immutable
derivation metadata. That verifies provenance, not approval of their wording as
reusable answers. They remain available as source material, but do not become
Accepted premises or validated responses merely because their pins verify.
[ADR 0056](0056-reviewed-decision-explanations.md) supplies a first bounded
approved-response contract for exact decision explanations, with revision-specific
review, applicability, withdrawal and freshness. It retains qualifications when
presenting approved text; exact reproduction alone cannot establish that an answer
addresses the question. Approval remains an explicit semantic review.

Ordinary notes remain useful without formalisation. Formalise a distinction when
a concrete question needs it, preserving uncertainty and attribution in the
representation. Follow ADR 0051 if existing vocabulary cannot express the needed
meaning; do not create predicates or infer equivalence merely to execute a rule.

### Exact requests and eligible inputs

A typed request identifies the rule and version, subject IRIs, framework or other
definition revisions, supported qualifiers and any explicit temporal scope.
Resolve ambiguous names before evaluation. Unsupported fields, unresolved
identities and unrepresented qualifications require abstention or disambiguation;
never silently drop them or substitute a broader question. Display the interpreted
request. Schema validation cannot prove that an AI translation preserved the
original question; the guarantee begins at the exact structured request.

[ADR 0054](0054-checked-coverage-question-answers.md) adds a finite question-template
adapter with exact visible-name resolution and fixed receipt-derived answers.
It does not extend the guarantee to arbitrary prose or client-authored reformulations.

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

This first rule exercises eligibility, complete enumeration and traceable results
using existing vocabulary. It is an engineering pilot for the broader evaluation
boundary, not a decision to make framework assessment KNOT's primary purpose.
After measuring the pilot, consider an exact relationship-listing rule such as
which reviewed decisions concern a selected project and which sources support
them. Define its direction, scope and completeness before implementation.
Motivation, causality and changes in beliefs require additional representations
and semantics; graph connectivity alone cannot establish those conclusions.

Results remain disposable derived records. Persisting a conclusion as knowledge
requires a separately authorised candidate/review workflow; it creates no new
Accepted assertion automatically. [ADR 0051](0051-reviewed-ontology-evolution.md)
governs proposed vocabulary changes without authorising this evaluator's rules.

## Alternatives

- Stronger prompts and repeated LLM checking can improve interpretation but do
  not provide reproducible rule execution.
- Existing exact graph queries remain useful; accepting arbitrary generated
  queries does not establish a stable, reviewed evaluation contract.
- Reproducing approved prose could reduce repeated interpretation for recurring
  questions. ADR 0056 now provides approval and applicability for one exact
  decision-explanation contract; ADR 0057 adds checked routing and selection.
  Policy trees still need explicit operators, exception handling and unknown-value
  semantics, justified by demonstrated questions.
- Integrating UnlikelyAI's platform would require evaluating its interfaces,
  deployment, data-access and licensing arrangements. The inspected public
  material is insufficient to select it as a dependency for this local tool.
- General OWL reasoning, a universal semantic language or COA's complete platform
  would introduce substantially broader semantics and dependencies. None is
  required for the proposed finite rule catalogue.

The [implementation status matrix](../docs/stride-status.md) separates implemented
contracts from outstanding proposals and adoption evidence.

## Consequences

Bounded evaluations become repeatable and inspectable while unknowns remain
visible. Costs include maintaining rules, dependency manifests, scoped replay
and explicit temporal semantics. Determinism cannot repair misleading sources,
incorrect mappings or flawed rules. Review responsibility remains separate from
execution. The approach fits KNOT's existing investment in stable identities,
source preservation and review, while adding a distinct responsibility for
computed conclusions. The likely benefit depends on how often reviewed knowledge
is reused and how much interpretation and maintenance it requires. Ordinary
capture and retrieval defaults remain unchanged.

## Validation and implementation

The coverage pilot implements stages 1–4.
The [evaluation guide](../docs/evaluation.md) specifies rule version 1, its exact
eligibility contract and command/API usage. Identity-dependent requests and
temporal questions abstain; arbitrary unsupported fields are rejected. Scoped
MCP calls enforce the existing source grants and derivation closure before source
reads. They hash and recheck the permitted view rather than exposing owner-level
file inventories, hidden note heads or global review-chain links. Missing support
under pinned access is unknown. A witness with an inaccessible mandatory
qualification is withheld. This remains a subset of the accepted contract.

Coverage uses each assertion's own organisation fingerprint when considering a
generated kind. An unrelated change must not invalidate a still-matching Thought
classification and promote it to Assessment via the predicate fallback. Author
classifications retain precedence; generated classifications remain Unreviewed.

The MCP output budget applies to a complete receipt. Oversized receipts become
explicit all-unknown abstentions; partial proof cannot retain a conclusion.

Implemented synthetic checks cover support and absence, missing definitions,
budget exhaustion, new acceptance/rejection/correction, invalid review replay,
changed sources, native evidence, authored kinds, evidence-account qualifications,
determinism and no dataset writes. Scoped tests additionally cover denied body
reads, hidden successors, grant revocation, derivation closure, qualification
withholding, error redaction, output limits and the real stdio transport. Metadata
or granted-view hashes plus verified-source rechecks detect changes across
evaluation; this is not a whole-dataset transaction.

The finite contract suite also crosses definition/review state, mapping origin,
authored kind and access mode in 240 synthetic combinations. Criterion ordering,
partitioning, predicate direction and the MCP twenty-criterion execution boundary
have explicit checks. This increases coverage of the existing rule; it neither
extends its semantics nor establishes universal correctness or independent truth.

[ADR 0055](0055-current-receipt-revalidation.md) implements current-receipt
revalidation under current access, including repeated question interpretation.
The [coverage comparison](../docs/coverage-benchmark.md) implements a repeatable
stage-5 diagnostic with frozen source labels and expected outcomes. It separates
ordinary hybrid retrieval, checked questions and manually supplied structured
requests. Correct abstention does not count as a conclusive answer; structured
success does not count as natural-language interpretation. Reports preserve label
authorship, independent-review state and unmeasured effort rather than inventing
them. Private live manifests and reports remain outside the application.

Historical replay, identity evaluation and independently reviewed, representative
use-case measurement remain outstanding. The implementation stages are:

1. Specify the typed request, finite input scope, eligibility rules, input manifest
   and receipt using synthetic examples with expected outcomes. Show how
   qualifications and incomplete enumeration affect each result.
2. Add a `knot.evaluation` feature package using Python and Oxigraph, with a small
   versioned rule catalogue and a fixed result renderer. Reuse loaders, access
   checks, source verification and review replay through explicit shared
   boundaries. Extract shared verification only where necessary; do not duplicate
   it or depend on ranked retrieval output as the complete input set.
3. Implement the coverage rule against synthetic data. Establish coherent input
   capture and detect changes before publishing a receipt. Start with fresh
   evaluations; defer persistent caching and saved-receipt replay until their
   invalidation and authorisation contracts are implemented.
4. Expose the validated contract through a thin CLI, then an optional read-only
   MCP operation using the same scope checks. Any AI translation must show the
   interpreted request; measure translation errors separately from rule errors.
5. Compare the pilot with existing retrieval on a fixed set of questions. Record
   answer coverage, abstentions, citation integrity, repeatability and review
   effort. Use those results to choose the next rule or artifact type.

Use existing `just` checks and synthetic fixtures. No new dependency, model
provider, database, general rule language or whole-dataset migration is required
for the initial rule. Runtime command names and APIs remain implementation choices.

Use synthetic fixtures to check repeatability, exact qualifications, missing
premises, incomplete enumeration, explicit conflicts versus legitimate multiple
values, temporal changes, corrupted citations and invalid review replay. Check
revoked grants, concealed metadata, new eligible evidence, stale receipts and
rule/ontology changes. Verify no capture, acceptance or source mutation occurs.
For the first rule, temporal requests remain Unknown. Conflict questions have no
supported request shape and are rejected rather than silently answered as coverage;
test full conflict semantics only when a rule defining them is introduced.
Passing these tests establishes the bounded contract's behaviour, not factual
truth or correct natural-language interpretation. Record actual validation results
before advancing the implementation status.

### Development comparison, 2026-11-13

A frozen local batch contained 14 purposively selected questions and 25 exact
source-span labels, with two runs per applicable route at 24,000 compact JSON
characters. The checked route matched all 14 expected contract behaviours:
two conclusive answers, one unknown, one unresolved selection and ten unsupported
questions. Four manually selected structured requests produced three conclusive
answers and one unknown, all matching their expectations. These counts measure
different denominators; manually supplied requests are not language understanding.

Hybrid retrieval contained 16 of the 25 complete labelled spans. Inspecting misses
showed useful partial source passages even in some zero-recall cases, so 64% is
exact-span recall, not answer accuracy. All repeated responses were identical;
58 returned citation occurrences were rechecked against source hashes and locators.
Dataset metadata remained unchanged. The project suite passed 657 tests.

Five unsupported cases asked for decision explanations, spanning three underlying
decisions rather than five independent examples. For this batch, the next useful
artifact to design is a revision-reviewed decision explanation: explicit question
applicability and decision selection, source-backed approved wording, preserved
qualifications, withdrawal and freshness checks. Existing curated notes supply
source material, not implicit answer approval. This recommendation does not approve
that new contract or knowledge reviews; it needs a separate design decision.

Subsequent implementation: [ADR 0056](0056-reviewed-decision-explanations.md)
defines and delivers this bounded artifact workflow. Real answer approvals remain
explicit owner review tasks, separate from implementing the capability.

The batch reuses development questions and assistant-authored source labels. It is
not held out, independently reviewed or representative of all owner queries.
Total curation and independent-review effort were not measured; no effort saving
is established. Timing was uncontrolled and overlapped other checks, so it supports
no performance claim. Historical replay remains deferred.

## Research references

Inspected 2026-11-13. These are architectural inputs and vendor descriptions,
not independently verified guarantees for KNOT.

- [STRIDE and reusable semantic artifacts](https://williamtp.substack.com/p/breaking-through-ai-trust-ceiling): policy trees, self-contained responses and the limits of neural translation.
- [UnlikelyAI's STRIDE overview](https://unlikely.ai/newsroom/stride-and-the-way-forward-for-trustworthy-ai-our-founder-s-new-essay): structured meaning and execution traces.
- [Platform](https://unlikely.ai/how-it-works/platform) and [service FAQ](https://unlikely.ai/faqs): rule approval, uncertainty and advertised integration options.
- [Public repositories](https://github.com/UnlikelyAI): no STRIDE engine identified during this research.
