# ADR 0042: Retire experiment artifacts and export the tool separately

- Status: Accepted
- Date: 2026-11-08
- Implementation: Implemented for v0.1.0; standalone dataset sync delivered separately by ADR 0043
- Extends: [ADR 0038](0038-open-source-tool-and-private-datasets.md)

## Context

The development checkout accumulated 29 experiment directories with 11,511 tracked
files, about 718 MB including local generated files. They mix prototypes, private
question manifests, source quotations, dataset copies and recorded responses.
Three application test modules import those directories, and development commands
enumerate their paths. Removing the directories alone breaks the behaviour suite.

The owner requested their deletion while retaining a summary of what was tried
and why it was or was not adopted. The code already has feature packages under
`src/knot/`; another application-wide rearrangement would add churn without helping
the code/data boundary.

## Decision

Remove `experiments/` and its commands from the working tree. Retain the two generic
synthetic evaluation helpers in `tests/support/`, together with their existing
behaviour regressions. Remove tests of private frozen-manifest contents and the
retired experimental interval metric. Keep the supported benchmark command, but
require an explicit question manifest instead of a private default path.

Keep source, tests, scripts, queries, usage documentation and ADRs in their existing
folders. Export only these tool directories and an explicit set of root files into
a new directory. Do not copy `.git`, datasets, environments or build output. Reject
symlinks and existing destinations. The exporter copies current working files,
including uncommitted changes; it does not create a repository, commit or push.
Selected file contents still need review; a directory allowlist is not a secret scanner.

Preserve authoritative `data/` bytes. Private Git history was initially retained;
the owner subsequently requested a fresh repository, so the old local `.git`
metadata was removed. Ignore `data/` and the runtime link in the new code repository. Existing
knowledge corrections remain valid independently of the experiment that measured
them. Deleting results is not a rollback of notes, source revisions or reviews.
The clean export can use this dataset through explicit external paths. Dataset
initialisation, shared configuration and standalone Git sync are not implemented
by this cleanup.

## Experiment outcomes retained

These summaries were checked against the experiment READMEs and result reports
before deletion. The old local Git history was subsequently discarded at the
owner's request; detailed experiment artifacts are no longer retained here.
The summary preserves engineering conclusions, not private
evidence, complete measurement tables or a reproducible public benchmark.

Most evaluations used one private corpus and assistant-authored, provisional
judgements. Splits were often previously exposed or revised after inspection.
Counts below are labelled records, source spans or provisionally complete question
sets as stated, not independently measured answer accuracy. Character budgets are
serialized response characters, not model tokens. Do not compare scores across
different datasets, label versions or response contracts as a single trend.

### Foundations and implemented changes, 4–5 November

| Experiment | Observed result and disposition |
| --- | --- |
| Initial project traversal | Canonical associations recovered source-backed claims that literal search alone did not organise. Useful evidence routing, not general relevance or answer completeness. Retain bounded retrieval under ADR 0019. |
| `bounded-retrieval` | The synthetic graph found a connected dependency but missed unlinked retry evidence; lexical and hybrid retrieval found the latter while admitting distractors. Retain this synthetic regression; no universal winning method was established. |
| `question-retrieval` | Compared legacy graph, ranked graph, text and hybrid using exact source-span labels. Supported question-aware retrieval under ADR 0020; no generated-answer or independent support assessment was performed. |
| `retrieval-quality` | Diagnosed candidate generation, retention and packing losses separately. Retain the implemented selection refinements and synthetic candidate-position regression; discard the private question set. |
| `evidence-selection` | Complete-package selection and shared passages improved budget use without clipping evidence. Stable content fingerprints replaced positional sampling after a small edit incorrectly appeared novel. Retain the production selector and its tests, not the private benchmark harness. |
| `selection-simplification` | The simpler selector preserved development labelled spans and qualifications at four budgets. A single-pass rank control was cheaper but lost evidence in several configurations. Retain simplification and bounded final-package reconciliation; do not replace it with rank-only selection. |
| `hybrid-ranking` | A narrow measurable-outcome intent fix preserved the frozen suite. Universal score replacement improved some aggregates but lost five held-out spans at 8k and two at 12k; reciprocal-rank fusion also regressed. Retain the narrow implementation, reject the broader scoring replacement. |
| `native-note-retrieval` | Native revisions worked through existing candidate generation and evidence packing with immutable history and revision-specific scope checks. Retain integration under ADR 0022; no separate retrieval backend was needed. |
| `broad-discovery` | Discovery plus automatic first-three gathering regressed held-out targets from 2/22 to 0/22. A development-only LSA prototype found 0/44 targets versus lexical discovery's 2/44 at matched budgets and took longer. Retain explicit discovery/gathering and relevance-first source selection under ADR 0023; reject automatic replacement and the semantic dependency. |
| `knowledge-quality` | Source-preserving curation and integrity audits improved the dataset without making warnings truth judgements. Retain API-owned curation and diagnostics under ADR 0027; private audit records belong to the dataset. |
| `entity-naming` | Preferred labels and literal inspector attributes improved navigation without rewriting assertion evidence or merging identities. Retain ADR 0028 and the dataset-owned label catalogue. |
| `semantics` | Explicit identity decisions, immutable corrections and repeated-account qualifications preserved distinctions that display renaming could not. Retain ADR 0029; do not infer identity or corroboration from similar labels or counts. |
| `continuous-curation` | Candidate validation, source pins, idempotent publication and quality baselines worked through existing boundaries. Retain the bounded implementation in ADR 0030; the broader standard keeps its existing Proposed status. |
| `entity-descriptions` | Evidence-supported curated descriptions used existing notes and derivation metadata. Retain the saved notes and unresolved qualifications; a description is not an accepted assertion or permission to describe unsupported entities. |

### Retrieval alternatives, 7 November

| Experiment | Observed result and disposition |
| --- | --- |
| `reasoning-quality` | Source-backed note revisions improved recorded reasoning; broad question answering remained incomplete. Retain saved revisions and optional lossless provenance sharing under ADR 0039. No general reasoning-quality claim follows. |
| `retrieval-relevance` | Preserving primary evidence improved the original development record count at 12k from 2/34 to 7/34; 24k stayed at 9/34. Retain the narrow production correction. Routing and complementary-evidence gaps remained. |
| `indexed-retrieval` | BM25, contextual, mixed and linked routes found different candidates but the reported current/BM25/mixed/linked routes still delivered 7/34 at 12k. Keep the default; indexing also needs scope-aware invalidation and revocation handling before adoption. |
| `adaptive-retrieval` | Routing and adaptive selectors had mixed gains and losses. The gap-follow-up prototype made 84 additional corpus follow-ups with no coverage gain over its predecessor and two losses. Reject default routing/follow-up; deferred-provenance cards trade initial size for extra calls. |
| `evidence-packaging` | Sharing and diagnostic omission saved context but left the original 12k result at 7/34. Retain only the implemented opt-in evidence view under ADR 0040, with complete provenance. Do not adopt experimental selectors or treat deferred evidence as free compression. |
| `complementary-selection` | The offline oracle could deliver 15/34 original records at 12k versus the default's 7/34. None of three bounded runtime selectors passed the individual regression gate; even the least harmful lost three baseline targets. Reject promotion: a larger search does not fix a weak relevance objective. |
| `semantic-evidence` | Supplied semantic assessments improved original 12k delivery from 7/34 to 8/34 and the broader set from 39/77 to 43/77, but lost justification at 8k and lacked independent validation. Reject a production semantic judge or mandatory model service. |
| `deep-candidates` | Deeper assessment helped some precise lookups without safely improving the original reasoning set. Raising the cap added only one discoverable record. Stop increasing breadth; complete evidence selection and qualification dependencies remained the limiting problems. |
| `budget-correctness` | A wire-cost callback exposed real mismatches between internal reservations and final MCP size. Changing package eligibility nevertheless displaced necessary qualifications. Reject promotion of the callback, larger window and semantic assessments; retain exact final size enforcement and document conservative intermediate selection. |

### Sufficiency, curation and client behaviour, 8 November

| Experiment | Observed result and disposition |
| --- | --- |
| `evidence-sufficiency` | A 55-question audit distinguished record hits from complete answers, missing corrections and equivalent support. One exact-question dependency guard changed six risk-flagged contexts to unsupported, adding no complete answer. Keep retrieval unchanged; provisional materiality labels need independent review. |
| `definition-selection` | Narrow definition ordering improved provisionally complete questions at 12k from 35/55 to 36/55 without observed labelled losses; it added no complete answer at 24k. Retain only the opt-in MCP/Python option under ADR 0041; do not replace the default. |
| `ai-workflows` | Prepared paired evidence packets, adapter contracts and grading workflows. No authorised model/provider was run, so answer quality, tokens, cost and generation latency were unmeasured. Do not treat offline preparation as a successful live AI evaluation. |
| `semantic-enrichment` | Eight curated-note revisions improved fidelity and navigation with mixed delivery effects. Existing diagnostic omission recovered a response-budget regression. Retain the notes and existing options; no new ranking change was justified. |
| `evidence-gaps` | Four further source-backed note revisions improved explanation and attribution but changed no annotated evidence units or question outcomes at any budget. Retain meaningful corrections; stop curating to improve benchmark scores or manufacturing links for missed targets. |
| `agentic-investigation` | Six interactive cases produced twelve answers and 32 lookup/retrieval calls. Three compliant cases clearly improved, one introduced an unsupported interpretation, one stayed unresolved and one exceeded its work bound. Keep investigation in the AI client, with verification and stopping limits; no autonomous planner or dependable answer-quality improvement was established. |

## Alternatives and consequences

Keeping the experiments in another repository folder would preserve the same bulk,
private content and maintenance coupling. Deleting everything without inspection
would lose useful regression coverage and the reasons rejected approaches failed.
The chosen boundary retains a small amount of synthetic support and this decision
record while removing prototypes and outputs from the working tree.

Starting a clean repository from selected current files avoids carrying private
history into a new remote. Adding a new remote to the old checkout or deleting data
in a later commit would still publish its earlier history. Removing the old `.git`
metadata permits a fresh repository while preserving all current dataset files.
The former Git remote, index and local history are no longer available here.

## Validation

The starting tree passed 442 tests. A code-only copy reproduced missing experiment
imports before extraction. After cleanup, `just check` passes 444 tests in both the
working checkout and an isolated 218-file export, using the existing development
environment. Three experiment-only checks were retired and five boundary checks
added. Uncached lint, formatting and local documentation file links pass. A temporary
external dataset passes note capture, exact body/hash verification and text retrieval.
All 2,249 existing dataset files match the pre-cleanup hashes. Export tests cover
exclusions, executable permissions, existing destinations and symlinks, including a
symlink in the parent of an allowed directory. This is not a fresh dependency install
or a wheel/source-distribution release test.

The fresh-repository follow-up passes 445 tests, including a temporary Git staging
check proving that private data and the runtime symlink are ignored. Legacy private
repository sync tests explicitly opt into tracking their synthetic data.

The retained summary replaces the removed experiment artifacts and local Git
history; retired commands are not supported in a fresh code checkout. Standalone
dataset setup and Git sync were subsequently delivered by
[ADR 0043](0043-local-datasets-and-optional-git.md). Public distribution and the
remaining dependency-notice audit stay on the [release checklist](../docs/release.md).
