# Compare retrieval and coverage evaluation

Use a frozen, source-pinned question set to measure the coverage pilot's useful
scope. This owner-local diagnostic uses the selected dataset read-only. It is
not a scoped MCP service and must not be exposed to restricted clients. All
three routes use the whole-dataset view authorised by the local owner operation.

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

## Read the results

The benchmark runs fresh public API calls for each case:

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
