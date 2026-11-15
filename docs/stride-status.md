# STRIDE implementation status

Reviewed 2026-11-14. KNOT implements the STRIDE-inspired path for two bounded
contracts: reviewed framework coverage and explicitly approved decision explanations.
It does **not** implement a general STRIDE engine or every proposed capability in
ADR 0052. This document is a scope and acceptance record, not vendor certification.

The public proposal describes reusable semantic artifacts, validation before
reuse, deterministic control/execution and traceable results. Policy trees and
context-free responses illustrate that pattern; they are not a published finite
compliance checklist. KNOT's interpretation is to cover those architectural roles
within explicit question contracts. See the [founder's essay](https://williamtp.substack.com/p/breaking-through-ai-trust-ceiling)
and [UnlikelyAI's introduction](https://unlikely.ai/newsroom/stride-and-the-way-forward-for-trustworthy-ai-our-founder-s-new-essay).

## Implemented and tested

| Architectural role | KNOT implementation | Acceptance evidence and limit |
| --- | --- | --- |
| Translate source meaning into reusable artifacts | Source-pinned assertions and curated native-note revisions | Curation/provenance tests; semantic fidelity still requires human judgement |
| Validate before reuse | Assertion reviews; separate explanation applicability/wording approvals and withdrawal | `test_explanations`, `test_explanation_quality`; curated does not mean approved |
| Check the question and choose a route | Full finite-template matching and exact visible names/IRIs | `test_answering`; extra conditions abstain, arbitrary prose unsupported |
| Select eligible artifacts | Deterministic enumeration, unique approved revision or explicit selection | `test_answering`; ambiguity, candidate limits and hidden artifacts tested |
| Execute without generated reasoning | Coverage rule; exact approved explanation reproduction | Evaluation matrix and explanation tests; no new inference from wording |
| Preserve uncertainty and bounded outcomes | Unknown, unsupported and selection-required results; scoped negative coverage | Scope/matrix tests; absence outside evaluated scope is never established |
| Trace and reproduce current results | Normalised requests, executed steps, nested evidence, review/code/source hashes | Repeated-result and receipt tests; hashes are neither signatures nor truth proofs |
| Recheck changed dependencies | Current revalidation, native freshness, withdrawal, grant checks and concurrent-change detection | Revalidation/answering tests; new approvals can make selection ambiguous |
| Enforce transport boundaries | Read-only CLI/MCP, complete-package budgets, no approval through answering | CLI/MCP and actual stdio tests; truncated proof cannot retain a conclusion |

The 2026-11-13 review closed two gaps: client-controlled tool/artifact selection
for these question contracts, and missing whole-dataset integrity checks for
explanation review histories. Selection also rechecks source bytes after nested
artifact execution so a detected concurrent change cannot return stale text.

Verification for this change: `just check` passed all 694 tests, Ruff lint and
formatting. Eight read-only checks against a fresh MCP process using the saved
local configuration passed: coverage, identical repeat, unchanged revalidation,
unapproved explanation abstention, unsupported conditions, output-budget abstention,
non-comparable budget revalidation and tampered-receipt rejection. All 1,298
tracked dataset metadata files were unchanged. Approved explanation reuse was
verified in synthetic fixtures, including real stdio transport; these checks do
not establish general semantic accuracy. The whole-dataset quality audit returned
zero integrity errors and 847 curation warnings; these warnings were not treated
as permission to change knowledge. At that checkpoint, no real explanation approval
events existed.

A subsequent real-use review on 2026-11-13 inspected one existing explanation,
both pinned accounts and their surrounding context, then froze expected results
before execution. Thirteen read-only checks passed: ten calls through the saved
MCP configuration and three local scope checks. All 1,298 tracked metadata files
remained unchanged. The explanation remained unapproved, so these results do not
demonstrate approved reuse on real data.

All three reused ordinary decision questions were unsupported: useful answers
were **0/3**, despite matching the expected contract refusals. This identifies
question phrasing as an adoption gap. The source review and labels were authored
by Codex, not independently human-reviewed; the cases were not held out. A future
extension could bind reviewed ordinary question wording to an exact contract,
but must preserve conditions and ambiguity rather than silently paraphrasing.
No such extension or persistent explanation approval was made during this review.

## Reviewed wording extension

Following that exercise, [ADR 0058](../design_decisions/0058-reviewed-alternative-question-wordings.md)
adds reviewed whole-question mappings for decision explanations. The preview can
include several ordinary phrasings; explicit approval binds them to the same exact
decision, answer revision and source dependencies. The router matches complete
wordings, records the approval event, preserves ambiguity and rechecks access,
freshness and withdrawal. It does not infer equivalence for unseen paraphrases.
The implementation was tested with synthetic data; no personal explanation or
question mapping was approved as part of the code change. The earlier 0/3 live
result remains an adoption baseline, not a post-approval effectiveness score.

Verification for the extension: `just check` passed 711 tests, Ruff lint and
formatting. A separate real-stdio demonstration passed seven synthetic checks:
unapproved wording, two approved phrasings returning identical answer text, an
added condition, output-budget abstention, withdrawal and receipt revalidation.
Four read-only calls using the saved personal MCP configuration also passed.
All 1,298 tracked personal metadata files remained unchanged, with no approval
or wording mapping written to that dataset.

## Small real activation

On 2026-11-14, the owner requested activation of a small explicitly reviewed real
set. Codex reviewed two existing decision explanations against their pinned source
accounts and surrounding context, and approved four complete alternative question
wordings. The immutable events record Codex as reviewer; these are not independent
human reviews. No source note, association, graph assertion or access grant changed.

Expectations were frozen before activation. Across a before/after measurement:

| Measure | Before | After |
| --- | --- | --- |
| Four explicitly reviewed question wordings returning their exact approved answer | 0/4 | 4/4 |
| Original three-question sample receiving an answer | 0/3 | 1/3 |
| Added-condition and unregistered-wording controls correctly withheld | 3/3 | 3/3 |

The two remaining original questions were not silently narrowed. One required
decision modelling beyond an analysis-note association; the other phrased a design
choice as an implemented action without adequate completion evidence. Those remain
outside this activated set.

All 32 checks passed: 26 calls through the saved read-only MCP configuration and
six local scope checks. Checks included repeatability, transition from pre-approval
receipts, exact wording and source locators, output budgets, complete dependency
grants, missing-source grants and revalidation after revocation. All 1,298 existing
tracked metadata files were unchanged; exactly two explanation approval records
were added. The post-activation quality audit found zero integrity errors, no new
warnings and the same 847 existing curation warnings.

This establishes working reuse for the reviewed set. It is not a held-out accuracy
test, proof of the source accounts' truth or general paraphrase recognition. The
next evaluation should use independently reviewed expected answers and additional
ordinary questions without first registering those questions as supported wordings.

## Related-question navigation

A further frozen development exercise used twelve questions: two registered
controls and ten constructed or reused phrasings, scope changes and unrelated
controls. Before the change, the controls answered and all other questions were
unsupported without navigation choices. Expected statuses and relevant decision
references were fixed before execution; no new question mappings were approved.
The question set and labels were authored by Codex, not independently reviewed or
collected as representative user traffic.

[ADR 0059](../design_decisions/0059-related-reviewed-question-navigation.md) adds
bounded suggestions of related reviewed questions to unsupported responses. The
original request stays unsupported and unanswered. Suggestions are not verified
paraphrases; the user must explicitly choose a different question before a client
submits it. Approval, source freshness, transitive grants, concurrent-change checks
and output budgets apply to the suggestions as well.

Repeating the same twelve questions left direct answer coverage at **2/12**.
Seven unsupported responses now offered related reviewed questions, including six
new phrasings/format variants about the intended decisions. One delivery question
offered a related rationale question while remaining unanswered; that suggestion
does not establish delivery or equivalent intent. The remaining three cases had
no alternatives. This measures discoverability, not increased answer accuracy.

`just check` passed 724 tests, Ruff lint and formatting. The before/after exercise
made 24 calls through the saved read-only MCP configuration. All 1,300 tracked
dataset metadata files were unchanged. No source, assertion, approval or question
mapping was added or changed.

## Repeatable measurement of the current router

The [comparison diagnostic](coverage-benchmark.md#evaluate-the-current-checked-answer-router)
now accepts version 2 manifests for the current checked-answer router. The original
version 1 route only measured coverage questions, so it could not assess the newer
explanation and navigation contracts. Version 2 compares frozen expected status,
route, canonical request, coverage outcomes and exact explanation text; suggestions
are counted separately and never selected automatically. Source verification,
repeatability, output budgets and dataset-change checks remain in place. Declared
independent review requires attribution distinct from the label author, without
claiming to authenticate that declaration.

A 2026-11-14 integration check reused the twelve-question development exercise
above, transferring expectations from its frozen manifest and source-backed
previews before running the diagnostic. All twelve checked outcomes matched; two
returned the expected approved answer and seven unsupported questions offered
navigation choices. Two runs per route made 48 owner-local API calls with a
24,000-character ceiling. Responses repeated identically, all 58 citation occurrences
in the retained results verified, and all 1,306 tracked dataset metadata files
remained unchanged. No approvals, wordings or source notes were changed.
`just check` passed 733 tests, Ruff lint and formatting. The full check needed a
run outside the sandbox after an existing in-process MCP test stalled there;
the focused benchmark tests passed within the sandbox.

This validates the reusable measurement path, not an improvement in answer coverage.
The questions and expectations remain reused, assistant-authored development
material. Additional ordinary questions with independently reviewed expectations
are still needed; running this diagnostic does not supply that review.

## Fresh-question development exercise and transcription fix

A further 2026-11-14 exercise froze eight new assistant-authored question wordings
after source inspection, with substantive answer expectations, exact source labels
and expected router outcomes recorded separately. The questions covered existing
decision explanations, another decision rationale, source qualifications, coding
preferences and product behaviour. Two previously registered controls were kept
outside the fresh-question denominator. Independent review was requested but had
not been received; the manifest explicitly records that limitation. These are new
wordings, not independently collected or held-out user traffic.

All eight fresh questions were unsupported; one offered two related questions.
Both registered controls returned their exact approved answers. This matched the
frozen contract expectations but gave **0/8 direct answers on the fresh questions**.
Hybrid retrieval returned four of eleven complete labelled source spans. That
metric excludes useful partial passages and separately curated restatements; it
is not answer accuracy or proof that other knowledge is absent.

Inspecting the misses exposed a format-handling defect: Markdown transcriptions
of binary documents were segmented using the original snapshot's extension,
treating a multi-section notebook as one large passage. A synthetic regression
reproduced an omitted relevant section under a tight budget. Retrieval now uses
the verified transcription's format, preserving original snapshots, both hashes,
warnings and exact offsets. Native and ordinary extracted-source handling is
unchanged. See [ADR 0020](../design_decisions/0020-question-aware-hybrid-retrieval.md).

The frozen before/after comparison made 80 read-only owner-local API calls. Fresh
answer coverage remained 0/8, controls remained 2/2, and full-span recall remained
4/11 with no per-case full-span regressions. Post-run inspection found that one
relevant curated prioritisation account now appeared; this was not retroactively
added to the source labels or counted as an independently validated accuracy gain.
Both runs per route were identical within each implementation. All 50 citation
occurrences in the retained after-results verified, and all 1,306 tracked dataset
metadata files remained unchanged. No questions or reusable answers were approved.
`just check` passed 734 tests, Ruff lint and formatting outside the sandbox; all
72 focused retrieval tests passed within it.

The evidence supports the transcription correction. It does not establish broader
question understanding. Unregistered wording, missing approved artifacts and
unimplemented question contracts remain distinct coverage gaps; independent
expectation review is still pending. Do not silently map those questions or tune
the labels to make this development set pass.

## Discovery through decision names and recorded context

Navigation now compares reviewed wordings with visible decision labels, alternate
labels and curated titles. A decision-label term can surface choices for a longer
question without requiring its extra conditions to match the reviewed wording.
Generic metadata descriptors are filtered; shared labels remain distinct choices.
This extends [ADR 0059](../design_decisions/0059-related-reviewed-question-navigation.md),
with the same explicit-selection boundary and bounded eligibility checks.

Repeating the frozen eight-question exercise increased responses with alternatives
from **1/8 to 3/8**. Both fresh questions about already approved rationales now offer
their intended artifacts. The third asks about completion and receives a related
rationale option, which does not answer the completion question. Fresh direct
answers remain **0/8**, and both registered controls still return their exact answers.

The earlier twelve-question regression set still returns two direct answers;
responses with alternatives increased from seven to nine. Inspection found a
false positive: shared migration terminology offered a rationale for a different
decision on a performance question. This is a limitation of broader lexical
discovery, not verified relevance or equivalent intent. No wording or expectation
was changed to make the result count as an answer. Actual user selection and task
completion have not been measured, and independent expectation review is pending.

The two reruns made 88 read-only owner-local API calls. Every frozen router contract
expectation matched, repeated responses were identical, all 108 citation occurrences
in retained results verified, and no response exceeded the output budget. Both
manifests and all 1,306 tracked dataset metadata files were unchanged. No suggestion
was automatically selected and no source, approval, wording or grant changed.
`just check` passed 741 tests, Ruff lint and formatting. Seven new synthetic tests
cover long questions, alternate/shared labels, titles, generic metadata, hidden
labels and current approval/evidence checks.

## Still not implemented or established

| Capability or evidence | Status / what would be required |
| --- | --- |
| General questions, arbitrary semantic translation and planning | Unsupported; define and test another bounded contract before execution |
| General policy trees, temporal rules, contradiction handling, identity-dependent reasoning | No evaluator for these; each needs explicit semantics and examples, including unknowns and exceptions |
| Historical receipt replay / archived executable rule versions | Current recomputation only; no restoration of historical code, grants or state |
| Reviewed ontology evolution | ADR 0051 remains proposed; no automatic vocabulary mutation |
| Broad independent usefulness/accuracy validation | Existing frozen comparison is small and not independently labelled; it cannot establish universal improvement |
| Production adoption of explanation artifacts | Two real explanations and four wordings activated after explicit requested review; broader adoption and independent validation remain pending |
| UnlikelyAI interoperability or Universal Language implementation | No such dependency or compatibility claim |

The bounded path is implemented when its listed checks pass. “Fully implemented
STRIDE for every KNOT question” is not a claim supported by this work. Remaining
architectural proposals are deliberately visible above. The next practical
validation step is ordinary-user question evaluation against independently
reviewed expected answers beyond the small activated set. Adding a
policy engine without an actual policy use case would not resolve that evidence gap.

Use the [checked-answer guide](checked-answers.md), [coverage guide](evaluation.md)
and [explanation workflow](explanations.md). The [coverage comparison](coverage-benchmark.md)
records the limitations of the existing usefulness experiment.
