# Checked answers

Use `knot answer` or MCP `knot_answer` to route a supported question and select
eligible evidence without asking the client to choose an execution tool or note.
The built-in templates and reviewed whole-question mappings do not provide
general natural-language understanding.

```sh
knot answer --question 'Does project "Example project" have reviewed support for criterion "Example criterion"?'
knot answer --question 'Why was decision "Example decision" chosen?' > /tmp/answer.json
knot answer --revalidate /tmp/answer.json
```

`just answer` takes the same arguments. All commands use the selected dataset;
`knot --data-root PATH answer ...` specifies an authorised root explicitly.

```python
knot_answer(question='Why was decision "Example decision" chosen?', max_chars=24000)
knot_answer(receipt=saved_receipt, max_chars=24000)
```

Names must match exactly, ignoring case, in the accessible view. Exact IRIs also
work. No fuzzy match, ranking or identity inference chooses an answer. Coverage
accepts both question templates and the optional framework/revision suffix in
the [evaluation guide](evaluation.md#ask-a-supported-question). Extra conditions
are unsupported; do not rewrite them away to obtain a result.

Decision explanations can also have [reviewed alternative wordings](explanations.md#review-alternative-question-wordings).
For example, `Why did we choose batching?` and `What made batching the preferred
option?` can lead to the same canonical decision request and exact approved answer.
Each complete wording must first be explicitly reviewed with that explanation.
Only surrounding whitespace is ignored for these mappings; case and punctuation
are significant. A new paraphrase is not automatically equivalent.

Without a built-in template, KNOT checks up to 1,000 visible current revision/entity
pairs for registered wordings. Exceeding this limit returns unknown; an explicit
`explanation_revision` can narrow the search. No matching visible wording returns
`unsupported_question`, including when a prior mapping is no longer accessible.
A matching withdrawn mapping returns unknown. Both results withhold answer text.
Multiple active decision meanings require selection before answer execution.

## Find a reviewed question

An unregistered question can return `unsupported_question` with an `alternatives`
list of related questions that KNOT can currently answer. For example, an
unregistered `Explain the batching choice` might offer the reviewed question
`Why did we choose batching?`.

The original question remains unchanged and unanswered, with null route/request.
Suggestions are not verified paraphrases: a question about successful delivery
may be related to a decision rationale without asking the same thing. Read the
complete proposed question and `alternatives_guidance`. Select a different question
only when that is what you intend to ask. AI clients must not make this substitution
automatically, even if only one suggestion is returned.

After the user explicitly selects an item, the client can submit:

```python
knot_answer(
    question=selected["question"],
    explanation_revision=selected["explanation_revision"],
)
```

Each option also identifies the decision, title and review event. KNOT checks
current approval, source validity and access before offering it, then checks again
when selected. No personal knowledge is modified by discovery or selection.
The relevance heuristic is lexical and can miss useful choices or suggest a related
question with a different scope.

At most five alternatives are returned and at most five distinct artifact requests
are verified for navigation. `alternatives_truncated` means further candidates
may remain unchecked. Empty alternatives do not establish absence of knowledge.
Revalidation removes withdrawn or inaccessible choices. If the complete response
cannot fit the MCP budget, the ordinary `output_budget` abstention contains no
partial alternatives. These suggestions are not counted as answers in evaluation.

## Select and verify an answer

For a decision, KNOT enumerates current, accessible curated revisions explicitly
associated with that decision and checks their separate answer approvals. A
curated note alone is insufficient. One eligible approved artifact returns its
exact wording and full provenance; several return `needs_selection` with bounded
choices and no answer text. Select an offered revision explicitly:

```sh
knot answer --question 'Why was decision "Example decision" chosen?' \
  --explanation-revision 'urn:knot:note-revision:REPLACE_WITH_MANIFEST_HASH'
```

In MCP pass `explanation_revision` alongside `question`. It cannot qualify a
coverage question or override a saved receipt. No eligible approved explanation
returns `unknown`. More than 100 candidate revisions also returns unknown rather
than choosing from an incomplete enumeration. Selection limits enumeration to
that revision. Missing or ambiguous names return `needs_selection`; no returned
choice establishes absence outside the visible scope.

The `checked-answer/1` envelope contains the route, interpreted request, executed
selection steps, complete nested evidence receipt and hash. `answered` means the
selected contract succeeded, not that an attributed account is independently true.
Preserve the nested qualifications, source authors, reviewers and scope. Approval,
currentness and transitive grants follow the [explanation contract](explanations.md).
This route cannot create knowledge, approve wording or change grants.
For an alternative question, `wording_review` records the matched full wording
and approval event hash. The nested review contains the approved question list.

MCP returns an unknown `output_budget` receipt when the complete package cannot
fit; it never retains a conclusion while clipping its proof. Revalidation repeats
name resolution, wording approval, routing and artifact selection under current access. It returns
only current content and the previous opaque hash. A formerly unique choice can
become ambiguous. Budget abstentions are `not_comparable`, even if a fresh answer
now fits. Hashes are not signatures, historical replay or access grants.

`just quality` checks explanation review event hashes, request directories and
history chains in addition to existing data integrity checks. It does not approve
meaning or certify that an old approval remains applicable; answering rechecks
eligibility and freshness. See the [STRIDE status](stride-status.md) for coverage
and remaining work.
