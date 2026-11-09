# Review claims and identities

Run commands from the repository root after [setup](../README.md#installation).
Examples use the selected dataset; see
[dataset selection](datasets.md#select-a-dataset) for external folders. Replace
uppercase identifiers with values returned by your own dataset.

```sh
just review list --status Unreviewed
just review show ASSERTION_IRI
just review accept ASSERTION_IRI --reviewer 'Your name' --reason 'Checked against the source'
just review reject ASSERTION_IRI --reviewer 'Your name' --reason 'Unsupported interpretation'
just review correct ASSERTION_IRI --replacement correction.json --reviewer 'Your name' --reason 'Corrected attribution'
```

Replace `ASSERTION_IRI` with an identifier from `list`. `show` includes the domain
triple, quotation, snapshot hash, origin, rationale and review history. Acceptance
approves the representation of a claim; it does not independently verify an event
or accept an entity identity proposal. Use the actual reviewer in place of the example
name: an agent's review must not be attributed to the owner. Identity review remains
a separate [file-based workflow](#review-identity), retaining
source-scoped identities and rebuilding the canonical query projection.

A correction file uses explicit RDF identifiers and labels:

```json
{
  "subject": "urn:example:person:alex",
  "predicate": "urn:knot:vocab:selected",
  "object": "urn:example:project:atlas",
  "subject_label": "Alex",
  "object_label": "Atlas",
  "rationale": "Corrected attribution after reviewing the source"
}
```

Corrections preserve the original assertion and evidence, supersede its active
triple and create an Inferred, Unreviewed replacement. Framework classification and
scope are retained. Use `--accept-replacement` only when acceptance is separately
authorised, or `"object_is_literal": true` for a literal object. Correcting an Accepted
assertion does not transfer its acceptance to the new interpretation.

Every correction verifies the original citations. To add necessary source context,
include an optional `additional_sources` list in the replacement JSON. Each entry
uses the same exact `revision`, `sha256`, `text_sha256`, `quote`, `character_offset`
and `start_line` pins as [curated-note provenance](curation.md#curated-knowledge-notes). The
revision must already be registered in KNOT; the correction command does not ingest
new source evidence. Original evidence remains attached alongside the added context.

Check the meaning of both endpoints before choosing a relationship. Use
`decision decisionAbout subject` when the decision's subject is known but its actor
is not; use `actor proposed proposal` when the source establishes a proposal without
agreement or completion. `madeDecision` and `selected` require a supported deciding
actor. See the [semantic standard](../design_decisions/0029-semantic-integrity-and-explicit-identity-resolution.md).

Ordinary queries exclude rejected and superseded domain triples. `show` and
`list --history` retain historical inspection with original source endpoints.
Changed reviewed content or conflicting review histories produce an explicit
reconciliation error. Pass the `latest_event` token from `show` using `--expected`
to detect an intervening decision. Local writes use a file lock; conflicting Git
histories require explicit reconciliation.

## Review identity

Compare original passages, dates, context and identifiers. Classify candidates as
the same referent, distinct but related, a compound referent requiring separation,
or insufficient evidence. A shared label, count or type alone is insufficient.

For supported imported identities, update the matching `source_sha256` and `label`
binding in `curation/entities.json`, preserving source identity and using the
supported canonical `entity_id`, review `status`, rationale, actual `reviewer` and
`time`. Retain the previous state, exact source evidence and reasoning in an identity
review record under `reviews/`, then run `just migrate`. Do not hand-edit generated identity RDF.
Canonicalisation changes query endpoints and navigation without rewriting original
assertions, native-note association manifests or review fingerprints.

Identity acceptance establishes a referent, not the truth of all linked claims.
Review any association that becomes a self-link explicitly. A contrary source may
justify revisiting an earlier accepted identity, but requires a recorded correction;
a preferred-label edit cannot withdraw or establish identity. Preserve distinct
projects, tools, activities and time-specific states where evidence distinguishes them.

Verified source profiles can supply historical search aliases to their accepted
canonical target. Their own source grants still apply, and the canonical preferred
name takes precedence. Do not change grants to make an alias or relationship visible.

Repeated accounts require separate evidence qualification, not an identity merge.
Use the [account catalogue](reference/catalogues.md#semantic-corrections-and-account-provenance)
for reviewed dependence or unresolved overlap. Matching text or equal numbers do not
prove that sources are independent or measurements interchangeable.
