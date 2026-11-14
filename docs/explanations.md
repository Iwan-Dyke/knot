# Reviewed decision explanations

KNOT can reuse the exact text of a curated note after explicit review for one
decision question. A curated note alone is not an approved answer. This feature
does not accept graph claims, infer successful delivery or verify independent truth.

## Select an explanation

Use an existing [curated note](curation.md#curated-knowledge-notes), or create one
through the normal owner-authorised note workflow. Keep a coherent explanation
with source qualifications in its body, actual curator authorship and exact
derivation pins. Associate it with the resolved decision IRI. Preserve original
source heads and bytes. Association does not by itself prove that the note answers
the question; review must check that meaning.

Save this request outside the dataset, replacing the synthetic IRI and revision
placeholder with actual returned identifiers:

```json
{
  "decision": "urn:example:decision:batching",
  "revision": "REPLACE_WITH_CURATED_NOTE_REVISION_IRI",
  "question": "Why was decision \"urn:example:decision:batching\" chosen?"
}
```

The canonical request question uses the same decision IRI. Alternative wordings
can be reviewed below; extra conditions must not be silently narrowed. The revision must identify
a current curated native note associated with that exact decision. Each value is
limited to 2,048 characters. No automatic name or identity resolution occurs.

## Prepare and explicitly review

```sh
knot explain prepare /tmp/explanation-request.json > /tmp/explanation-preview.json
knot explain history /tmp/explanation-request.json
```

These operations are read-only. Inspect the entire preview: request applicability,
exact wording, original authorship, source quotations, qualification and dependencies.
Check that proposals remain proposals, reported reasons remain attributed, and
the text does not imply completion or corroboration that its sources lack.

Only after an actual authorised reviewer has approved that exact preview:

```sh
knot explain approve /tmp/explanation-preview.json \
  --reviewer 'ACTUAL_REVIEWER' --reason 'ACTUAL_REVIEW_RATIONALE'
```

This writes a separate immutable approval event. Use the real reviewer; an agent
must not supply the owner's name on its own initiative. Review means approval of
this wording for this question, not acceptance of every source claim. A changed
preview or review head fails. If a write result is uncertain, inspect `history`
before retrying; do not assume that repeating approval is harmless.

All commands use the selected dataset. `knot --data-root PATH explain ...` selects
an explicitly authorised dataset; `just explain --data-root PATH ...` is equivalent.
No new database, dependencies or migration is required.

## Review alternative question wordings

An explanation can answer several ordinary phrasings after their meaning and
applicability have been reviewed with its exact text:

```sh
knot explain prepare /tmp/explanation-request.json \
  --wording 'Why did we choose batching?' \
  --wording 'What made batching the preferred option?' > /tmp/explanation-preview.json
```

This prepares a proposal only. Inspect every question, the canonical decision
request and the full answer/source context, then use the explicit approval command
above with the actual reviewer. Reject a proposed wording that asks about delivery,
an additional date, another actor or anything else outside that answer's scope.
KNOT validates the record and exact match; it cannot verify semantic equivalence.

After approval, either reviewed wording can be sent unchanged:

```sh
knot answer --question 'Why did we choose batching?'
knot answer --question 'What made batching the preferred option?'
```

Pass at most 20 `--wording` options, each 1–2000 characters. They replace the list
in the proposed preview. Omitting both wording options retains the latest list.
Use `prepare --clear-wordings` and explicitly approve that preview to retire the
alternative questions while keeping the canonical explanation available. Withdrawing
the explanation disables both canonical and alternative reuse. New revisions
inherit neither approval nor question mappings.

Only surrounding whitespace is ignored; case, punctuation and complete wording
must otherwise match. Added conditions and unregistered paraphrases are unsupported.
Built-in question templates cannot be overridden. If several decisions share a
reviewed wording, KNOT returns choices instead of guessing. Several eligible
revisions for one decision likewise require selection. Review metadata travels
with a permitted answer, including its question list, reviewer and event hash;
include only wording appropriate for clients authorised to see that artifact.

Existing approvals without a question list continue to work. No history or source
is migrated. `just quality` checks the extended review records. The Python API is
`prepare(root, request, wordings=[...])`; `None` retains and `[]` clears the list.
See [ADR 0058](../design_decisions/0058-reviewed-alternative-question-wordings.md).

## Answer and revalidate

For selection by decision name or IRI, use [checked answers](checked-answers.md).
That route chooses a unique eligible approved revision or returns explicit choices.
The lower-level commands below require the exact revision in the request.

```sh
knot explain answer /tmp/explanation-request.json > /tmp/explanation-receipt.json
knot explain revalidate /tmp/explanation-receipt.json
```

The JSON response is `approved`, `unknown` or `unsupported_question`. Only an
approved result contains answer text. Preserve that text with its qualification,
source citations, original author and separate reviewer. Line endings and UTF-8
content are preserved in the decoded answer string. Sources retain their own
authorship. `unknown` does not establish that a decision or evidence is absent.

Through the read-only MCP tool:

```python
knot_explain(request=request_object, max_chars=24000)
knot_explain(receipt=saved_receipt, max_chars=24000)
```

Supply exactly one of `request` or `receipt`. The server cannot approve, withdraw,
edit notes or widen grants through this tool. Even owner-authoring MCP sessions
use the CLI for explanation reviews. Complete answer packages must fit the operator's
ceiling; otherwise the tool returns unknown with `output_budget` and no answer text.
If that cannot fit, it fails. Revalidation resets the comparison to `not_comparable`
when current evidence cannot fit or the saved receipt was an output-budget abstention.

Revalidation compares the fresh receipt, returning only current content plus the
previous opaque hash. Saved hashes are not signatures, grants or truth proofs.
To revalidate a report again, supply its `current` receipt. The input envelope limit
is 2,000,000 serialised characters, not a streaming file-read limit.

## Freshness, access and withdrawal

- Editing the explanation creates a revision with no inherited answer approval.
- A newer visible revision of any native source makes the old derivation ineligible.
  Recurate from the appropriate sources and explicitly review the new explanation.
- Whole-dataset access checks current committed native revisions. Pinned access
  checks only latest granted revisions and explicitly leaves global currentness
  unknown. Hidden successors do not leak through response changes.
- The explanation and every transitive source require separate grants. Approval
  does not grant access, and revalidation cannot restore revoked permissions.
- Imported inputs remain exact revision pins. KNOT does not infer newer archive
  versions or certify that there is no later contradictory account.

Withdraw an approval using its latest event hash from `history`:

```sh
knot explain withdraw /tmp/explanation-request.json --expected EVENT_SHA256 \
  --reviewer 'ACTUAL_REVIEWER' --reason 'ACTUAL_WITHDRAWAL_REASON'
```

Withdrawal appends an event and preserves the previous approval and sources. It
works even if the old explanation is stale or its body is corrupt. Reapproval
requires a fresh preview and explicit review. No review or access changes happen
automatically during answering.

Authoritative events live under `reviews/explanations/<request-hash>/<event-hash>.json`
inside the selected dataset. Include them with note manifests and source snapshots
in backups or an explicitly requested dataset commit. Never hand-edit them. The
workflow shares the existing `reviews/.lock`; locks are transient. Per-request hash
chains detect malformed or incomplete history, not a malicious rewrite of all local
state. Keep stable local files while evaluating; this is not a database transaction.

Python APIs live in `knot.evaluation.explanations`: `prepare`, `approve`, `withdraw`,
`history`, `answer` and `revalidate`. Each takes an explicit root; read APIs accept
`scope=AccessScope(...)`. Omitted scope is owner-local whole-dataset access. Never
serve an owner-local result to a restricted client. See [ADR 0056](../design_decisions/0056-reviewed-decision-explanations.md)
for the contract and tradeoffs.
