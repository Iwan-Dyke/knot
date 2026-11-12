# ADR 0051: Evolve the ontology through reviewed proposals

- Status: Proposed
- Date: 2026-11-12
- Implementation: Not started
- Related: [ADR 0006](0006-grow-vocabulary-from-source-data.md), [ADR 0016](0016-basic-ontology-and-overlapping-themes.md), [ADR 0029](0029-semantic-integrity-and-explicit-identity-resolution.md), [ADR 0030](0030-continuous-knowledge-curation.md), [ADR 0052](0052-bounded-deterministic-evaluation.md)
- Supersedes: None

## Context

KNOT already has a small ontology; defining one is not new work. Its
[vocabulary](../src/knot/graph/ontology.ttl) describes referents, relationships and
knowledge kinds. [Candidate validation](../src/knot/curating/candidates.py) checks
source pins and the [supported predicate set](../src/knot/curating/rules.py), while
claim review remains separate. These checks do not establish semantic truth or
provide a workflow for reviewing changes to the vocabulary itself.

New sources and questions may expose distinctions the current terms cannot express.
An assistant could suggest additions, but plausible names and embedding similarity
cannot decide their meaning or compatibility with existing claims. Uncontrolled
growth would make the same relationship mean different things across records.

The AWS Context Ontology Accelerator (COA) demonstrates ontology proposals,
inspection and validation. Its current implementation also illustrates limits:
unstructured entailment is unfinished, and its validation subsystem is separate
from induction. This proposal adapts the review pattern to KNOT's existing
contracts; it does not adopt COA's infrastructure or treat generated axioms as
validated knowledge. References below identify the inspected revision.

## Decision

Propose a bounded workflow for vocabulary evolution. AI assistance may prepare
alternatives and examples; authorised review determines which meanings are adopted.
Manual proposals use the same process. Evaluation rules consuming the resulting
vocabulary are a separate proposal in ADR 0052.

### Describe a concrete gap

Each proposal would identify its authoring agent, revision, base vocabulary version
or fingerprint, motivating question, existing terms considered, and why notes,
literals or current predicates are insufficient. It would contain:

- Proposed IRIs, labels, definitions, predicate direction and intended scope.
- Positive and negative examples, including uncertainty and attribution boundaries.
- Source references supporting the distinction, with exact pins where dataset
  evidence is used; public examples remain synthetic.
- Affected validators, authoring interfaces, retrieval policies and consumers.
- Compatibility classification, migration implications and unresolved questions.

For example, a request to distinguish a planned activity from an implemented one
should first discover that existing predicates already preserve that distinction.
A synonym, frequently used heading or disconnected graph node alone does not
justify another term. External vocabulary alignments remain proposals until their
semantics are reviewed; a similarity score is neither identity nor equivalence.

### Separate validation, review and publication

Validation would check the proposal's structure, referenced definitions, examples
and compatibility with its declared base. It must distinguish hard integrity
failures from semantic warnings and checks not performed. Passing checks means
the declared checks passed; it does not approve a meaning or independently verify
the motivating account.

Schema review would record the actual reviewer, reviewed proposal revision,
rationale and decision. A changed proposal or base invalidates an earlier readiness
assessment until the affected checks and review are reconsidered. Schema approval
does not accept assertions, resolve entity identities, approve theme membership or
authorise dataset migration. Existing review workflows retain those responsibilities.

For the initial scope, core vocabulary changes require repository code review,
coordinated code changes and a release. Dataset-owner approval alone cannot install
a predicate. The bundled ontology and predicate allowlist remain authoritative;
dynamic per-dataset schemas are outside this proposal. Record the published
vocabulary revision and check results in repository history. Validation, schema
review and publication remain distinct even when one person performs all three.
This ADR introduces no runtime command or automatic publication path.

### Preserve meaning and history

Keep stable IRIs and their established meanings. A clearer label or explanation
must preserve denotation; a materially different meaning needs a new term and an
explicit relationship or migration decision. Deprecation must retain readable
historical definitions and must not silently reinterpret earlier assertions.

Review a domain-predicate change together with the ontology, shared validation
allowlist, relevant retrieval routing policies and caller-facing catalogues. Their
roles differ: accepting a predicate's structure does not automatically permit it
to route graph traversal. Synthetic examples must demonstrate the intended choices
and show existing terms retain their behaviour. Compatibility inspection must also
cover declared types and knowledge kinds where applicable.

Original sources, note revisions, assertion fingerprints and review events remain
immutable. New schema versions do not upgrade Unreviewed claims, turn an attributed
assessment into fact, or make repeated accounts independent. Historical claims
remain interpretable under their original meanings. Any required dataset change
uses its owning workflow with separately authorised scope and retained history.

### Keep adoption optional and local

Ordinary notes remain valid without types, assertions, links or schema proposals.
Schema checks must not require a fully connected graph or complete real-world
information. Access filtering applies before inspecting private examples; proposals
and diagnostics must not reveal denied sources or expand grants.

Retain existing Python checks initially. Consider portable SHACL shapes only for a
demonstrated interoperability or maintenance need, with reviewed semantics and
parity against existing contracts. Shapes cannot replace source-hash, locator,
ancestry or review verification. No mandatory model provider, hosted service,
reasoner, replacement database or new dependency is selected.

## Alternatives

Keeping all vocabulary changes informal avoids another review artefact, but makes
semantic impact easy to miss. Automatic induction offers faster additions while
leaving interpretation and compatibility unresolved. Importing a large foundational
ontology introduces distinctions without demonstrating their use in KNOT. Reviewed,
source-motivated changes retain the incremental approach of ADR 0006.

## Consequences

The workflow would make vocabulary changes explainable and testable, at the cost
of preparing examples and reviewing compatibility. Overly broad proposals could
create a review backlog; start with one demonstrated gap. Logical consistency and
clean diagnostics remain weaker than faithful modelling. Whether dataset-specific
extensions are needed, and how older vocabulary versions are distributed, remain
implementation questions rather than implied features.

## Validation and implementation

No implementation ships with this ADR. Proposed stages are: define a minimal
proposal contract and synthetic fixtures; add read-only validation and compatibility
reports; pilot one reviewed vocabulary change through the existing release process.
Decide any publication mechanism only after that pilot.

Before promotion, demonstrate rejection of a stale base, mismatched predicate
allowlists and incompatible meaning changes; preserve valid unlinked notes and denied-source
boundaries; and verify old assertions, citations and review histories still replay.
Keep warnings, skipped checks and unresolved meanings visible. Record observed
results and remaining limitations before updating implementation status. Passing
tests does not accept this ADR or authorise a dataset migration.

## References

COA references are pinned to commit `d28c001cfcc0460cbd1ec1b356a63dcad272790e`;
they describe design inputs, not dependencies or guarantees adopted by KNOT.

- [Ontology Engine: proposals and unstructured-induction limitations](https://github.com/aws/context-ontology-accelerator/blob/d28c001cfcc0460cbd1ec1b356a63dcad272790e/packages/ontology-engine/README.md).
- [Validation implementation: HermiT and caller-supplied SHACL shapes](https://github.com/aws/context-ontology-accelerator/blob/d28c001cfcc0460cbd1ec1b356a63dcad272790e/packages/ontology-engine/src/coa_ontology/validation/validators/tier1.py).
- [Proposal validation and acceptance are separate operations](https://github.com/aws/context-ontology-accelerator/blob/d28c001cfcc0460cbd1ec1b356a63dcad272790e/packages/ontology-engine/src/coa_ontology/proposals.py).
