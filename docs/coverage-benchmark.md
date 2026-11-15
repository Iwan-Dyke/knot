# Compare retrieval, coverage evaluation and checked answers

Use a frozen, source-pinned question set to measure the coverage pilot's useful
scope. This owner-local diagnostic uses the selected dataset read-only. It is
not a scoped MCP service and must not be exposed to restricted clients. All
routes use the whole-dataset view authorised by the local owner operation.

```sh
just benchmark-coverage --questions /tmp/questions.json --runs 2 \
  --max-chars 24000 --output /tmp/coverage-comparison.json
```

Add `--include-context` to retain the complete responses that fit the budget.
Reports can contain private questions, source paths, identifiers and quotations;
keep manifests and reports outside distributable code. The output path must be
outside the dataset and distinct from the question manifest. `--data-root PATH`
uses an explicitly authorised dataset. No notes, reviews or grants are changed.

## Prepare expectations before running

Select questions across actual tasks, including negative premises, uncertainty
and unsupported requests. Inspect sources and review state before writing labels.
Do not use the evaluated result as its own expected answer. A synthetic example:

```json
{
  "version": 1,
  "label_author": "Actual label author",
  "independently_reviewed": false,
  "selection": "Explain sampling, reused questions and known selection bias.",
  "curation_minutes": null,
  "independent_review_minutes": null,
  "questions": [{
    "id": "coverage-positive",
    "category": "coverage",
    "question": "Does project \"Falcon\" have reviewed support for criterion \"Safe changes\"?",
    "judgements": [{
      "path": "sources/example.txt",
      "sha256": "REPLACE_WITH_VERIFIED_TEXT_HASH",
      "quote": "Replace with exact source text, including relevant qualifications.",
      "character_offset": 0,
      "start_line": 1,
      "judgement": "Relevant",
      "qualification": true
    }],
    "expected": {
      "question_status": "evaluated",
      "request": {
        "subject": "urn:example:project",
        "framework": "urn:example:framework",
        "framework_revision": "urn:example:framework-revision",
        "criteria": ["urn:example:criterion:a"]
      },
      "outcomes": ["support_found"],
      "rationale": "Explain the inspected definition, mapping, review state and qualifications."
    }
  }]
}
```

Replace every placeholder; hashes and offsets must match the exact text file.
Judgements can also be `Irrelevant`. Empty labels mean that evidence recall is
unassessed, not that absence is proven. An invented-identifier control can have
empty labels, with its limited meaning explained in the rationale.

Expected question statuses are `evaluated`, `needs_selection` and
`unsupported_question`. Supply expected criterion outcomes in request order:
`support_found`, `no_qualifying_support` or `unknown`. Use null `request` and
`outcomes` when no coverage request represents the task. For unsupported wording
that can be mapped manually, an optional explicit request permits a separate
structured comparison. Document any narrowing in the rationale; supplying that
request does not validate natural-language translation.

Use null effort times when not measured. Existing source pinning does not establish
independent review or semantic truth. Record the actual author and review state.

## Evaluate the current checked-answer router

Use manifest `version: 2` to compare `hybrid` retrieval with `checked_answer`, the
same public router used by `knot answer`. This covers reviewed explanations,
registered alternative wordings, related-question navigation and coverage questions.
Version 1 retains the original three-route coverage comparison below; its
`checked_question` route does not measure decision explanations.

Keep the manifest's authorship, selection, effort and source-judgement fields. In
each version 2 case, replace `expected` with this shape:

```json
{
  "status": "answered",
  "route": "decision_explanation",
  "request": {
    "decision": "urn:example:decision:batching",
    "revision": "REPLACE_WITH_THE_REVIEWED_NOTE_REVISION",
    "question": "Why was decision \"urn:example:decision:batching\" chosen?"
  },
  "outcomes": null,
  "answer": "Replace with the exact independently inspected explanation, preserving line endings.",
  "rationale": "Explain why this full question has this qualified answer and review state."
}
```

Replace the revision placeholder with an actual immutable revision before running.
The case's `question` is the ordinary question submitted unchanged to the router;
`expected.request` records the canonical interpretation and is never submitted in
its place. No alternative is selected or executed by the benchmark.

Allowed statuses are `answered`, `unknown`, `needs_selection` and
`unsupported_question`. Unsupported questions have null `route`, `request`,
`outcomes` and `answer`. For an unresolved or unapproved explanation, use route
`decision_explanation`, with null request, outcomes and answer. For coverage, use
route `framework_coverage`, the expected coverage request and criterion outcomes,
and null answer; unresolved coverage names have null request and outcomes. A
coverage result with unknown evidence has status `unknown`, not `answered`.
An exact expected answer is required only for an answered decision explanation.

Freeze expectations from sources and review records before execution. Do not copy
the evaluated response into the labels or register the test questions merely to
make them pass. If `independently_reviewed` is true, supply `independent_reviewer`
with the actual reviewer, distinct from `label_author`. This records an attestation;
the software cannot authenticate the reviewer or establish their independence.
Approval of a reusable explanation is separate from independent benchmark review.

The report checks status, route, canonical request, coverage outcomes and exact
explanation text against those expectations. `correct_conclusive_answers` means
matching the supplied labels, not independently established truth. Per-case
`answer_match` records the exact text comparison. Source citations and qualification
recall use the existing verifier. `questions_with_alternatives` and
`alternatives_offered` measure navigation availability only; neither measures
relevance, equivalent intent or increased answer coverage. Oversized responses
contribute no answers, navigation choices or retained response context.

## Read the results

Version 1 runs fresh public API calls for each case:

| Route | What is measured |
| --- | --- |
| `hybrid` | Evidence retrieval for the original question, with no seed supplied. It does not generate an answer. |
| `checked_question` | Parsing, selection, rule execution and fixed answer for that same question. |
| `structured_request` | Rule execution using the label author's explicit request, when supplied. This is not a translation score. |

The report separates expected-contract matches, interpretation mismatches,
conclusive answers, unknowns, unsupported wording, unresolved names and budget
failures. A correct rejection is a contract match but is not a useful conclusive
answer. Wrong expected labels remain visible as mismatches; the benchmark never
rewrites them. Inspect disagreements against sources rather than assuming either
the implementation or the labels must be right.

Source metrics reuse the retrieval benchmark's citation and locator checks.
Relevant-span recall requires a returned citation to contain the complete labelled
span at its pinned text path, hash and offset. Qualification recall uses labels
marked `qualification`. Unjudged passages remain unjudged; partial labels do not
establish overall precision. Derived accounts and paraphrase questions are not
independent corroboration. An empty result cannot prove global absence.

All routes share a compact-JSON character ceiling, excluding MCP transport framing.
Retrieval retains its normal graph/passage limits; evaluation retains its rule
limits. A complete evaluation receipt exceeding the ceiling is scored as
`output_budget`, with no available answer or evidence. This diagnostic does not
simulate the MCP fallback envelope. Inspect sizes and denominators when comparing
routes; evidence search and coverage checking perform different jobs.

Use 1–50 cases, 1–5 runs and a 2,048–131,072 character ceiling. Two or more runs
check response determinism; one run leaves repeatability unmeasured. Timing includes
fresh API loading but excludes label validation and scoring. OS caches and other
machine activity are uncontrolled, so timing is diagnostic, not a performance claim.

The report pins the label manifest, implementation and dataset metadata. Invalid
labels, changed inputs, citation failures and non-identical repeats stop the run.
These checks detect changes across the measurement window, not transactional
snapshots. Keep the original manifest hash when comparing later runs; report
changes to labels or sources as a new benchmark version.

Use recurring gaps by task category to propose the next rule or reusable artifact.
Keep source availability, checked interpretation and semantic approval separate.
Human review and held-out questions remain necessary for stronger quality claims.

## Evidence accounting version 2

Both retrieval and coverage comparisons use the shared source-span scorer. It now
recognises exact quotations actually delivered inside native curated-note derivation
metadata, alongside direct passages and RDF assertion citations. The previous scorer
only inspected top-level sources and could miss original evidence embedded in a
curated response. This is a measurement correction, not a retrieval change.

For each citation, the scorer verifies the recorded source paths, original and text
hashes, quotation and character locator, including a supplied line locator. Embedded
derivation metadata must match the immutable curated revision, and its exact pins
must verify against their registered sources. Loading an ancestor to validate a
derivation does not earn evidence credit: its quotation must actually be returned.
The receipt adapter likewise cannot introduce credit from metadata loaded only for
verification. No owner-local fallback is used to resolve a missing scoped source.

Each labelled source span earns credit once per question regardless of how many
delivery routes contain it. Duplicate labels use their first index and combine the
qualification flag; contradictory judgements for the same span fail. A quotation
must contain the entire labelled span, including its labelled qualifications. A
curated paraphrase, an identical sentence at a different source location, and an
unreturned transitive ancestor do not substitute for that source span.

`evidence_accounting.version` is `2`. `by_representation` identifies relevant label
indices found through `source_passage`, `assertion_evidence`, `curated_text` and
`curated_provenance`; these sets can overlap and must not be summed. `unique_spans`
deduplicates exact delivered locations, not independent accounts. Citation integrity
counts every checked occurrence, including embedded pins; its denominator therefore
differs from the old top-level-only count. Attribution and review state remain
unchanged, and successful checks do not establish semantic truth.

Retain historical reports. Where frozen responses and source bytes remain available,
score the same responses again and save a separate report containing both results,
input hashes and scorer versions. Report this correction before comparing retrieval
arms. See the [curation diagnostic](curation-diagnostic.md) for a bounded follow-up
workflow and its limits.
