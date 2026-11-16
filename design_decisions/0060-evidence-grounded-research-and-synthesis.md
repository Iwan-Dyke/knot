# ADR 0060: Evaluate evidence-grounded research before adding orchestration

- Status: Proposed
- Date: 2026-11-15
- Implementation: Limited opt-in client finalisation implemented; broader research protocol remains unvalidated
- Related: [0020](0020-question-aware-hybrid-retrieval.md), [0023](0023-broad-discovery-and-selected-subject-retrieval.md), [0042](0042-retire-experiments-and-export-tool-only.md), [0052](0052-bounded-deterministic-evaluation.md), [0057](0057-checked-routing-and-artifact-selection.md)
- Supersedes: None

## Context

KNOT has three distinct capabilities: source-preserving knowledge representation,
bounded evidence retrieval, and deterministic evaluation of explicit contracts.
They do not together guarantee a useful answer to an ordinary question. An
unsupported checked question can already receive its complete labelled evidence
through retrieval. This is a contract limitation, not necessarily a retrieval
failure; labelled completeness is not proof that every necessary fact is known.

The [retrieval evaluation](../docs/retrieval-curation-evaluation.md) separates
accounting corrections from retrieval gains. The [STRIDE status](../docs/stride-status.md)
separates checked-answer coverage from retrieved evidence. These development
findings motivate investigating synthesis, but do not establish its accuracy.
Private question sets, source quotations and audit records remain outside this ADR.

[ADR 0023](0023-broad-discovery-and-selected-subject-retrieval.md#normal-use-client-guidance)
already adopted client-directed research guidance. The retained
[experiment history](0042-retire-experiments-and-export-tool-only.md#experiment-outcomes-retained)
records useful investigations, an unsupported interpretation after missed continuity
context, incorrect cumulative accounting, and automatic follow-ups without gains.
These limited observations justify an experiment, not a general agent. Some
original artifacts were retired; summaries cannot supply a reproducible baseline.

The gap is an evaluated, reusable process for relating a question to necessary
claims, assessing evidence and gaps, choosing useful follow-ups, and producing an
attributed answer with unresolved uncertainty. Delivering instructions does not
establish that a client follows them or reasons correctly.

### Existing capabilities and constraints

The [architecture](../docs/architecture.md) remains one local Python application
over authoritative files and an in-memory query projection, without a required
model provider. The relevant implemented boundaries are:

| Component | Responsibility and limit |
| --- | --- |
| [MCP server](../src/knot/interfaces/mcp_server.py) | `create_server` supplies the canonical initialization instructions, fixes root/scope at startup and bounds individual responses. It holds no cross-call investigation ledger. |
| [Retrieval](../src/knot/retrieval_engine/service.py) and [discovery](../src/knot/retrieval_engine/discovery.py) | Scoped graph/text/hybrid evidence, discovery, selected-subject gathering, exact source-unit selectors, exclusion handles and complete-package selection. Relevance and qualification objectives do not establish semantic completeness. |
| [Checked answering](../src/knot/evaluation/answering.py) | Full supported question matching, eligible approved artifacts, explicit choices and current revalidation. Unsupported wording remains unsupported. |
| [Access](../src/knot/interfaces/access.py) and provenance owners | Revision grants, derivation closure, source verification and scoped metadata. Provenance validity is not semantic truth. |
| [Existing benchmark](../docs/coverage-benchmark.md) | Exact-span accounting and checked-contract comparisons. Owner-local API runs do not measure AI synthesis or scoped MCP client compliance. |
| [MCP tests](../tests/test_mcp_server.py) | Instruction delivery and evidence/transport behaviour, not model adherence or answer quality. |

Current cumulative allowances are documented in the
[MCP guide](../docs/mcp.md#investigating-knowledge) and managed by the client.
Server-side per-call limits remain independent. No ontology change, SHACL,
database, hosted service, persistent index or mandatory AI dependency is needed
to evaluate better guidance.

## Decision

Propose **B first: evaluate an explicit research protocol through the existing MCP
initialization instructions**. Retain A as the baseline and fallback. Consider C
only if B repeatedly fails for reasons deterministic workflow state could address.
Do not select D.

KNOT owns the protocol specification, evidence verification and enforced tool
boundaries. The connected AI client owns interpretation, research choices,
semantic sufficiency judgements and natural-language synthesis. During stage 1,
cumulative protocol compliance remains the client's responsibility and must be
measured; KNOT must not claim enforcement that does not exist.

The broader protocol below remains a proposal. The limited production implementation
described next corrects termination only; it does not adopt that protocol or extend
tools, checked contracts or authoritative knowledge.

## Limited production implementation

Added 2026-11-16 following explicit authorisation to implement the engineering
correction while retaining opt-in use. ADR 0060 remains **Proposed**; its general
research-protocol adoption gates have not been met.

The experimental coordinator raised a terminal stop when a proposed retrieval
exceeded a category budget. Its loop exited even when cached evidence and overall
resources remained. A private controlled study of 30 questions, three repetitions
per condition, produced 49/90 versus 55/90 fully correct substantive answers and
19/90 versus 0/90 missing final responses. Missing responses despite complete
labelled material evidence fell from 13/90 to 0/90. However, the correction added
one unsupported material claim, and held-out correctness was unchanged at 15/18
per condition. It failed the trustworthiness gate. These Codex-authored assessments,
without independent human validation, justify no general answer-quality claim.
A cached-evidence recovery diagnostic obtained 25/28 fully qualified correct
outcomes, with failures retained; this was not literal continuation of the old runs.
Private questions, source records and traces remain outside the public repository.

The subsequent self/independent verification experiments did not establish useful
improvement. Neither verification workflow is adopted. There is no second model,
claim-extraction gate, new STRIDE contract or automatic knowledge publication.

The supported opt-in [Python MCP client coordinator](../docs/investigation.md)
implements only `research_open -> research_closed -> finalisation -> complete`.
It rejects over-budget proposals before dispatch, retains the original question
and complete replies, records the rejected action/reason, and reserves one decision
and 60 seconds within the original eight-decision/600-second limits. Finalisation
cannot dispatch tools and may yield a supported answer, qualified partial answer,
abstention or explicit inability. Hard deadlines and overall limits prevail.

Unlike the experimental subclass, this is a standalone, single-use client API
using the existing MCP SDK and host-supplied callback, without experiment imports,
model adapters, frozen benchmarks, token estimates or private file brokers.
It reuses server verification and packaging unchanged. MCP initialization guidance
explains the distinction, but only this dispatch path enforces cumulative limits;
the server remains stateless. Existing direct/checked clients are not replaced.

Synthetic public-interface tests cover exhaustion, rejected graph/source requests,
evidence and question preservation, finalisation without tools, scope/write
isolation, checked replies, deadline and cancellation behaviour. They establish
mechanics, not semantic accuracy. Timeouts are cooperative; provider tokens,
hidden retries, connection startup and an outer hard process deadline remain
host responsibilities. No LangGraph or GraphRAG integration is justified here.

The stages below describe the broader unaccepted research proposal. The narrow
termination correction is an explicit implementation exception, not completion
or acceptance of those stages.
Future experimental success supports an explicit adoption decision; it does not
automatically accept this ADR or authorise coordinator implementation.

### Stage 1: candidate client protocol

These are requirements for an experimental instruction revision, not a second
runtime prompt catalogue. Keep executable guidance in `create_server` and link
to it from usage documentation. Retain the exact text used by each experimental
arm outside the authoritative dataset.

1. Preserve the original question and all conditions. Check applicability of
   supported STRIDE contracts first. For applicable or uncertain cases, submit
   the unchanged question to `knot_answer`; never construct a narrower substitute.
   An obviously out-of-contract factual question can proceed directly to retrieval
   after this applicability check. Charge routing calls to the investigation budget.
   A complete checked answer can finish the task without a research loop. Preserve
   ambiguity, unknown and output-budget outcomes.
2. Retrieve initial evidence with existing tools. Prefer direct `knot_retrieve`
   for straightforward facts. If subjects are unclear, use
   `knot_lookup(mode=discovery)`, inspect candidates and deliberately select subjects.
   Do not automatically gather the highest-ranked cards.
3. Identify the material claims needed to answer, including actor, scope and time
   where relevant. Record a concise interpreted scope separately from the original
   question. Seek clarification when ambiguity changes the answer; do not silently
   resolve identities or invent intent.
4. Relate each necessary claim to exact returned evidence. Check support,
   attribution, review state, qualifications, corrections, counterevidence and
   chronology. Distinguish event time from note/revision time. Before claiming
   change, inspect earlier/later accounts and continuity. Graph connections suggest
   where to look; they do not establish causality, agreement or identity.
5. Name material gaps: the missing claim/context, why it matters, what could resolve
   it, and whether omission or access limits apply. Existing evidence may suffice
   for a qualified partial answer.
6. Follow up only for a named gap with a plausible retrieval action. Reuse source-unit
   selectors, subjects, objectives and exclusion handles. Count every selected
   source expansion, including repeats and multi-source requests. Exclusions must
   not strip qualifications required by a returned claim.
7. Stop when evidence suffices for the stated answer scope, further search is
   unlikely to help, clarification is needed, or any allowance is exhausted.
   Record the reason, unresolved gaps and omissions. Never restart to reset a
   budget. Failed verification is an integrity error, not evidence of absence.
8. Present an explicitly **exploratory synthesis** with claim-level citations,
   attribution and material qualifications. Distinguish recorded statements,
   source-backed interpretations and hypotheses. Retrieval does not make a source
   independently true. State what cannot be concluded; abstain on unsupported
   central claims and identify the limits of partial answers. Do not burden a
   simple factual answer with a research transcript.

[Related reviewed questions](0059-related-reviewed-question-navigation.md) are
navigation only. Show the complete option and obtain explicit user selection
before executing it. Never silently reinterpret unsupported wording, select among
ambiguous approved artifacts, or call exploratory prose an approved STRIDE answer.
Keep checked wording/receipts separate from commentary. A checked output-budget
abstention contains no partial proof to reconstruct.

### Stage 2: conditional investigation coordinator

Investigate C only after B failures implicate lost state, miscounted work, repeated
reads or forgotten gaps. Missing sources, ranking misses, unsupported contracts
and poor semantic judgement do not by themselves justify it. Define the smallest
failure it would address and compare against frozen B under equal limits.

A possible design is an optional read-only state machine with ephemeral session
state, delegating to existing retrieval and verification. Its proposed record is:

- Original question, separately attributed client interpretation, selected subjects,
  candidate handles, necessary claims and outstanding questions/gaps.
- Examined evidence and verified revision/hash/locator references, retaining
  authorship, review/origin, qualifications, account dependence and omissions.
- Client assessments of support, conflict, insufficiency and scope-relative
  sufficiency, each with evidence and a concise rationale. These remain assessments,
  never KNOT-certified semantic conclusions or an authoritative completeness flag.
- Cumulative coordinated calls, returned characters, source expansions, graph work,
  elapsed time, remaining allowances, status and stopping reason.
- A bounded evidence packet for synthesis that separates verified references from
  client annotations. Unexamined candidates are not evidence; the packet is neither
  an approved answer nor a STRIDE execution receipt.

Bind sessions to server, dataset and effective scope. Handles confer neither access
nor approval. Recheck applicable dependencies and authorisation before packet
export; invalidate or fail on detected changes. Current `AccessScope` is immutable
and loaded at startup: editing its file does not dynamically revoke an active
server's grant. Changed scope or restart must not silently reuse a prior session.
Resumption and continued budget accounting need an explicit contract before use;
durable sessions, caches and historical replay are not initial requirements.
Evidence already disclosed to a client cannot be recalled.

A coordinator enforces only calls routed through it. Direct tools would bypass
its ledger. An experiment must specify whether entry points are restricted or
bypasses are measured; it cannot claim global enforcement over arbitrary clients,
reconnects or other tools. State needs bounded size, expiry, isolation and
cancellation. Do not execute generated code/queries, mutate reviews, save synthesis
as knowledge, widen grants or automatically decide semantic truth.

## Alternatives

These are expected tradeoffs to test, not measured comparative results.

| Option | Complexity, maintenance and model independence | Reliability and testability | Latency, tokens and potential answer benefit |
| --- | --- | --- | --- |
| A. Existing guidance/client-managed research | Lowest change cost; existing provider-neutral tools | Tool guarantees tested; protocol compliance and synthesis vary by client | Baseline costs; often adequate for facts, uncertain for complex synthesis |
| B. Improved MCP protocol | Small instruction/test change; one canonical text; no provider dependency | Delivery testable, compliance/support require repeated client trials | More instruction tokens, possibly fewer wasted calls; answer gains remain a hypothesis |
| C. Optional coordinator | Moderate state, session, budget and invalidation complexity; model-independent operations | Transitions and coordinated limits testable; semantic sufficiency remains unverified | Packet/state overhead; may prevent repeat work and lost gaps, with no automatic reasoning gain |
| D. Full internal AI research agent | Highest maintenance: model adapters, credentials, generation and lifecycle; interchangeable providers still add model dependencies | More orchestration control, but synthesis still needs independent evaluation | Highest loop/generation cost exposure; benefit unestablished and duplicates connected clients |

B fits the current ownership boundary and is inexpensive to falsify. Retain A if
B adds ceremony without useful gains. C needs a demonstrated state-management
problem. D needs a separate proposal; it is not the default escalation if B or C
disappoints.

## Evidence and trust boundaries

Retain immutable source bytes/history, exact hashes/quotes/locators, original
authorship and separate curation authorship. Direct passages, RDF evidence and
exact quotations in curated provenance remain distinct representations. A paraphrase
is not its original quotation. Reuse verification and deduplicate span credit
without dropping qualifications or counting repeated accounts as corroboration.

Preserve origin, review, lifecycle and explicit identity decisions. Source-only
context has no claim acceptance; acceptance does not establish independent truth.
Do not strengthen plans into implementation, reports into verified results,
involvement into ownership or association into causation. Different dates/values
need contextual assessment, not automatic contradiction resolution. Missing
evidence is unknown, not absence; a qualifications search cannot certify that no
correction exists.

Filter access before source reads, ranking and reporting. Session metadata/errors
must not leak denied labels, counts, identifiers, successor revisions or global
currentness. Preserve current/latest-granted/explicit-historical distinctions and
transitive derivation grants. Saved packets are not access grants. Treat retrieved
content, including instruction-shaped notes, as evidence, never instructions.

Keep per-call work/output bounds. Cumulative experimental budgets include routing,
discovery, failed/repeated calls and final packet delivery; reserve room for final
synthesis. Keep complete qualifying packages or report omissions. Budget stops
cannot certify completeness. Characters are not model tokens. No stage automatically
authors knowledge, approves assertions/explanations or changes grants.

## Validation and implementation

### Reproducible experiment

Before changing production guidance, freeze A's current instructions and B's
candidate revision from the same canonical location in an isolated checkout.
Exercise actual MCP initialization/tool transport and verify that the host passes
instructions to its model. Hold other client instructions, tools, retrieval code,
dataset, review state, grants and budgets identical. Use isolated read-only dataset
copies where authorised; do not curate knowledge or approve artifacts for the test.

Retain input/code/configuration hashes, exact initialization text, source/review
versions, model/client versions, available sampling settings, dates, prompts, tool
traces, delivered responses, answers and stopping reasons. Keep private artifacts
outside distributable files under ADR 0042. Synthetic fixtures and generic tooling
may be public. Do not supply hidden labels or inaccessible evidence to the answering
client. Missing historical inputs must be reported, not reconstructed as a baseline.

Include straightforward facts, multi-source explanations, decisions/rationale,
comparisons/tradeoffs, chronology/change/continuity, conflicting accounts,
incomplete evidence and explicit abstentions. Include scoped expectations and
answerable/negative cases. Add synthetic controls for source-instruction attacks,
hidden revisions, repeated accounts, oversized packages and withdrawn approvals;
these test guarantees, not real-world usefulness.

Refine B on development questions; reserve untouched held-out questions and source
families where possible. Previously exposed questions are regression controls only.
Pre-register sample size, strata, primary metric, thresholds and analysis before
opening holdout results, using development variability to justify sample size.
Small pilots and familiar-source wording holdouts are exploratory, not generalisation
evidence. Without a suitable independent set, do not claim an adoption-quality result.

Prepare independently source-reviewed expectations before execution: material
claims, acceptable qualified interpretations, necessary spans, chronology,
counterevidence, limitations and proper abstentions. Record actual authors,
reviewers and disagreements privately. Do not fabricate human review or equate
another model's agreement with independent human validation. Disputed labels stay
unassessed with their counts reported; never silently remove them from denominators.
Artifact approval and independent benchmark review are separate.

Run paired A/B trials in fresh conversations with counterbalanced order, no shared
conversation memory, identical allowances and at least three runs per question/arm.
For clarification requests, freeze identical scripted user replies or stop and
score the request separately; do not give one arm additional information ad hoc.
Record caching conditions and available telemetry. Grade blind to arm where feasible,
using source-informed reviewers independent of the instruction author. Resolve
disagreements without tuning the holdout. Repeat the frozen comparison with another
supported client/model before claiming cross-client reliability; provider-neutral
architecture does not imply equal model performance.

### Measures and acceptance criteria

| Measure | Operational definition |
| --- | --- |
| Correct answer coverage | Supported substantive answers addressing every material part of the original question / all assessed questions; also report answerable-subset coverage and partial answers separately |
| Evidence completeness | Delivery of labelled necessary evidence sets, including valid alternative support sets and counterevidence; distinguish discovery from delivery |
| Citation correctness | Mechanical revision/hash/quote/offset validity and semantic claim support, reported separately with denominators |
| Qualification preservation | Retention of material limitations, uncertainty, attribution and scope in the answer |
| Unsupported claims | Unsupported/overstated claims per claim and per answer, with severity |
| Contradiction handling | Recognition and faithful presentation of conflicts, false conflicts and unjustified resolution |
| Follow-up effectiveness | Newly recovered necessary evidence and named gaps resolved per added call, including unproductive searches and evidence subsequently omitted |
| Tool calls and token usage | All attempts, repeats, expansions, graph work, response/packet characters; actual input/output/cache tokens where available, otherwise explicitly unmeasured |
| Latency | Retrieval, generation and end-to-end duration, medians/tails and timing conditions |
| Repeatability | Variation in material conclusions, support, caveats, abstentions and compliance; identical wording is not required |

A correct refusal is not a successfully answered question. Report appropriate
abstentions, unsupported contracts and clarification requests separately. Retrieval
relevance, span recall, checked-contract matches and semantic answer correctness
are different measures. Reuse the corrected evidence-accounting verifier; the
existing benchmark is not a synthesis grader.

Report raw correctness separately from within-budget, protocol-compliant answer
coverage, which is the primary adoption metric. Predeclare violation scoring;
an answer obtained through excess calls or a prohibited action is not an admissible
success, even if its wording is correct. Retain that trial and its violation.

Assess compliance from observable gap statements, cited assessments, requests,
counters and stops, not private chain-of-thought disclosure. Attribute failures
to interpretation, discovery, packaging, workflow, synthesis or checked contracts;
mark uncertain attribution. This determines whether curation, guidance or state
management could help.

Proposed gates to freeze before a held-out run:

- Zero observed critical trust violations: denied evidence disclosure, source/review
  mutation, fabricated citations/approval, silent question substitution, or exploratory
  output presented as checked. Preserve synthetic access, provenance, qualification
  and checked-answer regressions. Zero observations is not proof of universal safety.
- A useful paired gain in correct answer coverage, without material deterioration
  in unsupported claims, qualifications, contradiction handling or appropriate
  abstention. Predeclare a numeric minimum useful gain and non-inferiority margins
  with the evaluation owner. Report case-level wins/losses and paired uncertainty
  clustered by source family; repeated runs are not independent new questions.
  An inconclusive comparison retains A rather than justifying more complexity.
- Unchanged per-investigation allowances, with budget failures retained in results.
  Freeze acceptable token, latency and simple-fact overhead margins before testing.
  Missing telemetry cannot establish an efficiency gain.
- For C, repeatable B failures addressable by explicit state/cumulative enforcement,
  then incremental benefit against frozen B under the same quality/cost gates.
  A more complete ledger alone is not improved answer quality or reason to ship.

Numeric thresholds and independent review are prerequisites, not permission to
choose favourable cutoffs later. If review or sufficient cases are unavailable,
retain current behaviour and label the proposal unvalidated. Do not repeatedly
inspect and tune a held-out set.

### Stages and dependencies

| Stage | Deliverable and gate | Current status |
| --- | --- | --- |
| 0. Baseline/protocol | Frozen A, reviewed labels, scope-specific evidence, numeric decision thresholds, allowances and trace format | Private studies completed with Codex labels; no independent human review |
| 1. Instruction experiment | Isolated B, delivery/contract tests, paired client trials and independently graded failure analysis | No demonstrated adoption gain; broader protocol remains unaccepted |
| 1 adoption decision | Adopt B only after gates; update canonical instructions and linked guide without broadening contracts | Not authorised by this ADR |
| 2. Conditional coordinator design | Identify machine-addressable B failures; specify state, enforcement, packet and disposal in a separately accepted bounded design | Deferred; unnecessary if B is adequate |
| 2 experiment/adoption | Synthetic state/isolation/budget tests, C-versus-B evaluation and explicit adoption decision | Broader coordinator deferred; only opt-in termination correction implemented above |

Future instruction changes must retain MCP initialization/transport, source,
scope and checked-answer tests and pass `just check`. A coordinator additionally
needs deterministic transition, retry accounting, exhaustion, bypass, isolation,
expiry/restart, changed-input and packet-budget tests. Reuse existing APIs, not
a second ranker, contradiction engine, evidence store or approval mechanism.

The original ADR recorded a proposal, not an answer-quality gain. The limited
implementation above does not establish that gain either. Keep behaviour tests,
documentation links and implementation status aligned without treating engineering
regressions as semantic validation.

## Consequences and rejection conditions

This makes the synthesis gap testable while keeping KNOT free of model integration.
It may improve evidence use without another retrieval architecture, but adds
instruction tokens, evaluation effort and possibly latency. Clients may ignore
guidance, overload context or mistake a well-formed packet for proof. Reviewers can
disagree; client/model updates can invalidate results. Maintain synthetic regressions
and rerun frozen, versioned evaluations when relevant clients or protocols change,
retaining earlier results.

Reject B or retain A if gains are absent, uncertain, limited to exposed questions,
dependent on weakened guarantees, or outweighed by routine-task cost. Limit adoption
claims to tested clients. Stop architecture work if instructions and curation are
adequate. Abandon C if remaining failures are semantic or lack evidence, direct-call
bypass makes enforcement misleading, or gains do not justify session complexity.
Do not automatically build D in response. New model services, broader deterministic
semantics or persistent research state require their own evidence and decision.
