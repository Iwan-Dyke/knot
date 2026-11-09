# Presentation and evidence catalogues

Paths below are relative to the selected dataset root. Use these catalogues only
within authorised curation or review work.

## Entity names, types and values


Use [ADR 0028](../../design_decisions/0028-meaningful-entity-names-and-value-presentation.md)
for naming conventions and the [extraction checklist](../../AGENTS.md#check-referents-before-extracting-entities)
before proposing a new referent. Search current names and historical aliases, verify
identity, and consider a note, assertion or value before creating another entity.
Names must identify their subjects independently of neighbouring edges. Keep source
scope where necessary, especially for competencies defined by separate frameworks.
Keep a decision distinct from implementation and a reported outcome distinct from
independent verification. Natural writing and unlinked notes remain valid.

For a display correction, add or update the existing stable IRI's profile in
`curation/entity-labels.json`: `entity`, `preferred_label`, `aliases`, actual `agent`, `reason`
and exact source pins in `sources`. Preserve earlier names as aliases. Validate pins
with the provenance helpers used for curated notes; do not paraphrase a quotation.
The overlay changes display and search, not source assertions or identity bindings.
Do not rebuild or edit reviewed extraction records solely to rename their endpoints.

For generated type suggestions, use `entity_type_overrides` in
`organisation/catalogue.json`, keyed by exact IRI with a nonempty list of supported
types. Record the source and rationale in the curation ledger, then run `just organise`.
These overrides remain Inferred/Unreviewed organisation annotations; source RDF types
and accepted assertions retain their history. Do not use a type override to conceal
a questionable relationship or resolve an uncertain identity.

The graph viewer presents RDF literals as attributes of their subjects, preserving
the exact value, datatype, language and evidence. A numeric value remains an attribute with its units; it is not automatically
a distinct entity or a global rename rule.
Inspect numeric labels before deciding whether they are counts, titles or identifiers.
Preferred names and full labels appear in the viewer, historical aliases remain
searchable, and identifiers and original names remain inspectable.

For a whole-graph cleanup, capture a baseline and account for every actual node and
literal occurrence, including framework and canonical identity views. Work in bounded
batches with one coordinator. Apply supported naming corrections and queue uncertain
identities or assertion meaning with evidence and recommended options. Preserve source
bytes, note revisions, identity bindings and review fingerprints. Verify citations,
review replay, retrieval, alias search, attribute evidence and graph filters afterward.

`just quality` distinguishes current-name warnings from retained historical-label
collisions and counts literals separately from referents. Its numeric, generic,
context, granularity and duplicate warnings are review prompts, not proof of an error
or authority to merge. An empty warning list does not replace the complete inventory.

## Semantic corrections and account provenance

Follow [ADR 0029](../../design_decisions/0029-semantic-integrity-and-explicit-identity-resolution.md)
and the [relationship checklist](../../AGENTS.md#check-relationship-meaning-before-adding-a-triple).
Inspect both endpoints and the exact source before selecting a predicate. A project
is not a substitute for an unknown deciding actor. `decisionAbout` links a decision
to what it concerns; `proposed` attributes a proposal without implying completion.
An attributed or reported outcome remains qualified after source-fidelity acceptance.

Use the [review workflow](../reviews.md) for semantic corrections, including
corrections to Accepted assertions during authorised review work. Immutable events
retain the original claim and evidence; replacements default to Inferred/Unreviewed.
Do not modify reviewed extraction content to conceal an error. Optional correction
`additional_sources` provides exact pinned context from already registered revisions,
while all original citations remain attached and verified.

Accepted identity bindings belong in `curation/entities.json` and its explicit identity review
record, with the actual reviewer, time and supporting evidence. Rebuild through
`just migrate`; do not rewrite source-scoped assertions or native-note associations.
Historical profile aliases follow accepted bindings only when their own source grants
permit them. Similar wording remains a candidate for review, not a merge rule.

The optional `curation/evidence-accounts.json` catalogue has `schema_version: 1` and a `groups`
list. Each group contains these fields:

| Field | Required meaning |
| --- | --- |
| `id` | Stable, unique group identifier |
| `assertions` | Unique existing assertion IRIs for the reviewed accounts |
| `relationship` | `RepeatedAccount` for dependent retellings, or `OverlapUnresolved` for reports whose overlap cannot be established |
| `qualification` | A concise explanation preserving units, scope, attribution and uncertainty |
| `reviewer` | The actual reviewer, including an agent when it performed the review |
| `sources` | Exact `revision`, `sha256`, `text_sha256`, `quote`, `character_offset` and `start_line` pins supporting the qualification |

Use pins covering each member's relevant citation span, not just equal text at
another location. An absent numeric locator can be inferred only for a unique exact
quotation. Validation checks source bytes, quotation locations and assertion
targets. Scoped retrieval checks every pin's revision/body-hash grant before source
reads and returns only eligible groups' ID, relationship, qualification and reviewer;
it never exposes a hidden member list. A group is not an access grant.

Graph assertions and text/hybrid `source_context` can carry these qualifications.
A verified passage must contain or be contained by a pinned span in the same
revision and evidence-text hash. Partial overlap and equal wording elsewhere do not
match. Text context keeps `claim_review: null`, and selection reuses verified span
metadata without additional source reads.

These annotations do not merge identities, remove occurrences, change review status
or alter evidence-selection ranking. Identical text does not create a group
automatically. Reports using different units remain distinct while equivalence is unresolved; do not sum them or
treat repeated accounts as independent corroboration.

Run `just quality` to validate the catalogue and review semantic warnings. Subjective
checks flag suspicious actors, granularity or account interpretation for investigation;
they do not establish identity or reject free-form notes.
