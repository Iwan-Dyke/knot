# Deterministic coverage pilot

The read-only `framework-coverage` rule reports recorded mapping coverage for a
project and an explicit list of criteria. It checks existing reviewed assertions;
it does not interpret notes, infer capability or score achievement. See
[ADR 0052](../design_decisions/0052-bounded-deterministic-evaluation.md) for rationale.

For exact reusable prose about a decision, use the separate
[reviewed decision-explanation workflow](explanations.md).

## Run an evaluation

Save a request outside the dataset, replacing these synthetic IRIs with the exact
subject, framework, source revision and criteria you intend to inspect:

```json
{
  "rule": "framework-coverage",
  "version": "1",
  "subject": "urn:example:project",
  "framework": "urn:example:framework",
  "framework_revision": "urn:example:framework-revision",
  "criteria": ["urn:example:criterion:a", "urn:example:criterion:b"],
  "max_assertions": 1000,
  "max_sources": 100
}
```

```sh
knot evaluate /tmp/coverage-request.json
knot evaluate /tmp/coverage-request.json --format text
just evaluate /tmp/coverage-request.json
```

These commands use the selected dataset. `--data-root PATH` selects an explicitly
authorised dataset for this invocation; `./knot` works in an uninstalled checkout.
Output goes to stdout and creates no dataset records. JSON is the default. Text
adds a fixed summary followed by the complete receipt, retaining qualifications.

Python callers use `CoverageRequest` and `evaluate(root, request)` from
`knot.evaluation`. `CoverageRequest.from_dict(value)` accepts the JSON shape above.
Requests contain 1–100 distinct criterion IRIs. Unknown fields, malformed IRIs,
unsupported rule versions and invalid limits are errors, not silently ignored
instructions. An `as_of` string is recognised but returns unknown because temporal
evaluation is not implemented.

## Use through MCP

Restart the [KNOT MCP server](mcp.md) to load the read-only `knot_evaluate` tool.
Pass the same request object as its `request` argument, for example:

```python
knot_evaluate(request={
    "subject": "urn:example:project",
    "framework": "urn:example:framework",
    "framework_revision": "urn:example:framework-revision",
    "criteria": ["urn:example:criterion:a"]
}, max_chars=12000)
```

The operator's existing source grants apply. The call cannot choose a dataset,
widen a grant, publish assertions or accept claims. MCP requests allow 1–20
distinct criteria, IRIs up to 2,048 characters, at most 1,000 candidate assertions
and 100 verified source revisions. Unknown request fields are rejected. An AI
must resolve the exact IRIs first and show the interpreted request returned in
the receipt; natural-language translation is outside the rule engine.

For an ordinary question, use `knot_lookup` to identify relevant projects, then
retrieve their relationships and evidence before constructing an evaluation
request. Inspect the returned labels to disambiguate projects and frameworks.
Question-only hybrid search can now return existing direct mappings with matching
endpoint labels, prioritising recorded support for explicit support/demonstration
questions. Text-only search and discovery remain separate; all modes can miss
relevant evidence. An omitted mapping is not a negative coverage result; use
selected-subject retrieval and the explicit evaluation request to check it.

With revision-pinned access, a verified visible mapping can yield `support_found`.
Missing mappings yield `unknown` with `scope_limited`, even when all accessible
candidates were enumerated. They cannot establish absence in the whole dataset.
Definitions and mappings need all their evidence grants; curated evidence also
needs grants for its full derivation chain. If a mandatory evidence-account
qualification uses an inaccessible source, the affected assertion is withheld.
Its caveat is never silently dropped to make the assertion usable.

The response must fit the server's character ceiling, including tool-result
framing. If the full receipt does not fit, the tool returns an all-unknown
`output_budget` abstention with the interpreted request and no assertion evidence.
If even that cannot fit, it returns an error asking for fewer criteria or a larger
budget. It never removes evidence while retaining a coverage conclusion.

Python integrations can pass `scope=AccessScope(...)` to `evaluate` using
`knot.interfaces.access.AccessScope`. Omission remains owner-local access;
`AccessScope.all()` represents an explicit whole-dataset grant. Never serve an
owner-local receipt to a client with restricted grants.

## Ask a supported question

The checked question path accepts one project and one criterion using either form:

```sh
knot evaluate --question 'Does project "Falcon" have reviewed support for criterion "Safe changes"?'
knot evaluate --question 'What reviewed support does project "Falcon" have for criterion "Safe changes"?' --format text
```

Through MCP, supply `question` **instead of** `request` to the same tool:

```python
knot_evaluate(
    question='Does project "Falcon" have reviewed support for criterion "Safe changes"?',
    max_chars=24000,
)
```

Python callers use `answer_question(root, question, scope=...)` from `knot.evaluation`.
This is a deterministic template parser, not general prose interpretation. Questions
are limited to 2,000 characters. Unsupported wording or extra conditions return
`unsupported_question` without executing the evaluator.

Double-quoted values must be exact case-insensitive visible labels or explicit IRIs.
Missing or ambiguous names return `needs_selection`, up to ten choices per field,
and `choices_truncated` when applicable. Use an exact returned IRI to disambiguate.
Missing visible choices do not establish absence. Preferred-display overlays and
ordinary source-only notes are not automatically evaluation selections; use lookup
and an explicit IRI where needed.

A unique visible Active Accepted criterion definition supplies the framework and
revision. If several pairs are available, select explicitly with this suffix:

```text
Does project "urn:example:project" have reviewed support for criterion "urn:example:criterion:a" in framework "urn:example:framework" at revision "urn:example:framework-revision"?
```

The framework clause may omit the revision if it leaves one visible revision.
Framework/revision values must be IRIs. The route never chooses the newest revision
implicitly. Explicit selections still undergo the evaluator's eligibility checks.

An `evaluated` response contains the original `question`, `question_contract`, exact
interpreted `request`, fixed `answer`, and complete nested `evaluation` receipt.
`answer_sha256` hashes the envelope before that field is added. The fixed answer
describes mapping coverage, not capability. The receipt retains evidence and
qualifications. If it cannot fit, MCP returns unknown wording with an output-budget
abstention; if that cannot fit either, it returns an error. `--format text` prints
the fixed answer followed by the complete JSON envelope. Nothing is saved to KNOT.

General questions still use exploratory retrieval. Client-authored reformulations
into a supported template are outside this parser's guarantee; show the interpreted
request and do not silently substitute a narrower question. See
[ADR 0054](../design_decisions/0054-checked-coverage-question-answers.md).

## Revalidate a saved receipt

Save JSON output outside the dataset, then recompute it under current rules and
access when using it for a later answer:

```sh
knot evaluate /tmp/coverage-request.json > /tmp/coverage-receipt.json
knot evaluate --revalidate /tmp/coverage-receipt.json
knot evaluate --revalidate /tmp/coverage-receipt.json --format text
```

Through MCP, use `knot_evaluate(receipt=saved_receipt, max_chars=32768)`, subject
to the server ceiling. Supply exactly one of `request`, `question` or `receipt`.
Python callers use `revalidate(root, saved_receipt, scope=...)`. Omitted Python
scope and the CLI use owner-local access. Both raw evaluation receipts and
`evaluated` question envelopes are supported. Save the JSON object, not the text
summary or a revalidation report; to recheck a report, pass its `current` object.

The report includes the previous opaque hash and a complete `current` result:

| Status | Meaning |
| --- | --- |
| `unchanged` | The recomputed receipt or question envelope is identical. This does not establish truth. |
| `changed` | The receipt differs. Check reasons and current evidence; outcome categories may still match. |
| `not_comparable` | The old receipt was an output-budget abstention, the question no longer resolves, or the report could not fit. |

`interpretation_unchanged` compares the interpreted requests. `outcomes_unchanged`
compares criterion/outcome pairs only when those requests match; otherwise it is
null. Matching categories do not mean unchanged evidence or qualifications. Saved
questions repeat name resolution, so new ambiguity returns choices without
reusing the old interpretation.

Revalidation validates hashes and supported envelopes, then recomputes using only
current permissions, inputs and rules. Hashes are not signatures or grants. Old
manifest paths are never followed, and old quotations are not echoed. Corrupt
current sources and invalid saved envelopes fail without restoring an old answer.
Saved requests remain subject to the MCP execution limits. Input is limited to
2,000,000 serialised JSON characters; this is not a streaming transport limit.

If current evidence cannot fit, MCP returns `not_comparable`, null comparisons
and an all-unknown `output_budget` abstention. Increase the permitted budget to
obtain a comparison. If even the abstention cannot fit, the call fails. No dataset
records change. Historical replay and caching remain deferred; see
[ADR 0055](../design_decisions/0055-current-receipt-revalidation.md).

## Rule version 1

The evaluator enumerates the accessible graph after review replay, before identity
projection. It selects only Active, Accepted assertions:

- A criterion needs a `skos:definition` assertion marked `FrameworkDefinition`,
  with `k:framework` equal to the requested framework. Every evidence pin on that
  definition must refer to the requested framework revision. A missing or
  unreviewed definition makes the criterion unknown.
- A mapping must be exactly `subject supports criterion`. Activity-to-project
  joins, `demonstrates`, label matches and lexical similarity are outside this rule.
- Both definitions and mappings need a replayed acceptance event. A legacy
  Accepted flag without a corresponding event is insufficient and produces unknown.
- `supports` retains its attributed Assessment meaning. Explicit author
  classifications take precedence over organisation classifications whose
  per-assertion fingerprint still matches;
  a different kind excludes the mapping and is reported. When neither supplies a
  kind, the predicate's existing Assessment meaning applies. Both Explicit and
  Inferred origin are supported and retained.
  Unrelated changes do not invalidate an unchanged assertion's classification.
- Every selected premise needs verified source hashes, a matching quotation,
  character offset and start line. Native manifests, derivation chains and
  evidence-account qualifications use the existing verification APIs.
- An accepted identity binding touching the subject, framework or selected
  criteria produces unknown. Identity projection requires a later rule version.

The result concerns **only the selected criteria**. It never claims that they
exhaust the framework. Definitions from another revision cannot substitute for
the requested revision. Acceptance verifies the representation, not independent
truth; source authors, curators, reviewers, origin and qualifications remain in
the receipt.

| Outcome | Meaning |
| --- | --- |
| `support_found` | At least one qualifying direct assessment was verified, and the criterion definition and scope checks completed. |
| `no_qualifying_support` | Enumeration finished for this criterion and scope, with no qualifying direct assessment. This is not evidence of incapability or absence outside the scope. |
| `unknown` | A required definition/review is missing, access cannot establish absence, a limit was reached, or the request needs unsupported temporal or identity interpretation. |

`missing_reviewed_definition` is reported only after enumeration finishes. When
an unsupported request or execution limit stops enumeration, the receipt reports
that blocker without treating an unchecked definition as missing.

Corrupt sources, invalid review replay and changes detected during execution fail
the command without publishing a receipt. Conflict detection is not implemented;
multiple assessments do not establish contradiction. Arbitrary queries, unrestricted prose
questions, new predicates and AI-authored rules are not executable inputs.

## Receipts and limits

Each JSON receipt includes the normalised request, overall completion, one result
and executed check list per criterion, supporting assertions, review events,
exact source quotations and qualifications, including evidence-account source
spans. Its manifest pins code, shipped ontology and runtime versions, candidate
assertion fingerprints and verified source files. Owner-local receipts also pin
graph/review/note/catalogue file hashes. Scoped receipts instead hash the granted
view and omit the global file inventory and review predecessor links. Unrelated hidden
records and newer ungranted note revisions do not change that view hash or appear
as currentness hints. `receipt_sha256` hashes the
canonical JSON of the receipt before that field is added. Equal inputs produce
equal receipts; no time-dependent metadata is inserted.

Metadata membership and hashes are checked before and after evaluation; scoped
calls rebuild and compare the granted view. Verified sources are checked again
before returning. A new accessible assertion or review changes the manifest even
if it was not a previous witness. This detects changes across the
read window; it is not a transaction or protection against an uncooperative writer
changing a file and restoring it between checks. Run against stable local files.

`max_assertions` bounds selected candidate assertions (maximum 10,000).
`max_sources` bounds verified source revisions, including derivation and
qualification dependencies (maximum 1,000). Exhaustion makes the result unknown;
it never truncates evidence while reporting complete absence. These are execution
limits, not whole-dataset loading or byte limits: the pilot still loads the graph
and inspects local metadata. Receipts preserve full quotations and may be large.

Caching, historical replay, identity evaluation and general temporal/conflict
rules remain unimplemented. Each invocation, including receipt revalidation,
evaluates afresh; a saved receipt alone does not establish currentness.

## Verify the pilot

Use the [frozen-question comparison](coverage-benchmark.md) to compare ordinary
hybrid retrieval, checked questions and explicitly supplied coverage requests.
It measures source recall, expected outcomes, abstentions and repeatability
without treating retrieval output or manual request selection as an answered question.

```sh
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p 'test_evaluation*.py' -v
just check
```

The tests use temporary synthetic datasets and the real review and source APIs.
They cover mappings and absence, incomplete scopes, review changes, native notes,
classification/qualification preservation, corrupt or changed inputs,
repeatability, CLI routing, scoped source isolation, grant revocation, derivation
closure, hidden qualifications, MCP budgets, actual stdio transport and no dataset
writes. MCP tests need the optional SDK and local asyncio socket support. They do not establish real-world
answer quality or natural-language translation accuracy.

The [finite contract matrix](../tests/test_evaluation_matrix.py) checks 240
combinations: four definition states (absent, unreviewed, rejected, accepted),
three mapping review states, two origins, two authored kinds and five access
modes. Expected results come from the declared fixture states rather than the
evaluator's selection helpers. Additional checks exercise criterion reordering
and partitioning, predicate direction and exclusion of other relationship types.
The MCP suite checks the twenty-criterion limit with exactly enough assertion
and source capacity, then one fewer permitted assertion. Existing tests cover
review corrections, corrupt evidence, changing inputs, grants, derivation chains,
qualifications and response-size abstention.

These checks establish behaviour for their tested cases, not universal correctness.
Keep three questions separate when assessing readiness:

| Question | Evidence needed |
| --- | --- |
| Does the rule follow its contract? | Synthetic expected outcomes, boundary cases, provenance and access tests. |
| Can it answer the selected dataset questions? | Exact interpreted requests, reviewed definitions and eligible mappings, with unknown reasons recorded. |
| Are those assessments justified in the real world? | Source interpretation and independent review; acceptance and passing tests do not establish this. |

For a live audit, freeze the request set before execution and report supported,
no-qualifying-support and unknown results separately. Preserve unpublished drafts
as drafts. Never accept knowledge merely to make an evaluation return support.
Natural-language translation, indirect joins, identity reasoning, historical
queries, causal rules and conflict rules need their own contracts and validation.

A synthetic comparison gives bounded retrieval a one-assertion budget while two
reviewed mappings exist. Retrieval correctly reports an omission; evaluation
enumerates both mappings. Evaluation with an insufficient budget instead reports
unknown. This checks the completeness boundary, not general retrieval relevance.
