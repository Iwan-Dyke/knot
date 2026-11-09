# Organise knowledge with themes and types

Run commands from the repository root after [setup](../README.md#installation).
Examples use the selected dataset; see
[dataset selection](datasets.md#select-a-dataset) for external folders. Replace
uppercase identifiers with values returned by your own dataset.


This is the navigation catalogue for one logical knowledge base. Personal evidence,
career frameworks and future reading/reflection material share entity identities
where explicitly confirmed. Themes overlap; they do not create separate stores.

Run `just organise` to regenerate `graph/organisation.trig` and `graph/ontology.trig`.
`organisation/generated.json` protects those outputs from accidental overwrite after manual
edits. Keep the catalogue and all RDF files together when moving the dataset.
Raw RDF queries must inspect each `ThemeMembership` resource's review status.
Kind/type suggestions remain unreviewed; theme membership can be reviewed
independently. Membership is not evidence for a new factual relationship.

## Add your own knowledge themes

Knowledge themes are overlapping topic categories. A category such as Concepts
does not change an entity's ontology type or accept the claims assigned to it.
Visual palettes are configured separately in the [viewer](viewer.md#visual-themes).

```sh
knot themes list
knot themes add concepts --label Concepts --description 'Ideas and mental models.' --keyword concept --keyword 'mental model'
```

Use `./knot` from an uninstalled source checkout. Commands use the selected dataset;
`knot themes --data-root /path/to/store list` addresses another explicitly.
Labels are free text; identifiers are stable lowercase slugs. Omit keywords for
a category assigned manually in the note-writing workflow. `--include-frameworks`
also suggests membership for framework records. Membership suggestions remain
Unreviewed; topic relevance and claim acceptance are separate decisions.

To share several definitions, put a JSON array in a file and import it:

```json
[
  {
    "id": "concepts",
    "label": "Concepts",
    "description": "Ideas and mental models.",
    "keywords": ["concept", "mental model"],
    "include_frameworks": false
  }
]
```

```sh
knot themes import /path/to/themes.json
just organise
knot view --visual-theme paper
```

Open **Library → Themes** or use Graph's **Relationship filters → Theme** to
explore Concepts. For a legacy export restricted to that topic, use
`knot view --legacy --theme concepts --visual-theme paper`.

Import validates the complete array before updating `organisation/catalogue.json`.
Identical definitions are safe to import again; a conflicting existing ID fails
without replacing its meaning. Other catalogue fields, saved notes and review
registers are preserved. New themes are immediately available for note capture.
Run `just organise` afterwards to apply keyword rules and update graph filters;
package users can run `python -m knot.graph.knowledge build` in their environment.
Adding or importing definitions never commits, pushes, assigns themes to old note
revisions or accepts memberships. Existing definition edits still use the catalogue
and review workflow below.

## Adjust classifications

Edit `organisation/catalogue.json`, then rebuild. A theme has a stable lowercase slug, display
label and case-insensitive whole-word/phrase keywords. Keywords match entity labels
and quoted passages. `include_frameworks` includes framework definitions explicitly.
The rules are deliberately simple and can be noisy. No match leaves a record
without a theme; it still appears in the unified unfiltered query.

`entity_types` maps a type to exact labels. This suggests types for matching mentions
without changing their identities. Existing framework types and selected relationship
roles also supply types. Ambiguous entities retain the generic `Entity` type.

For a source-supported correction affecting one identity, use `entity_type_overrides`
instead of matching a label shared by several entities:

```json
{"entity_type_overrides": {"urn:example:existing-tool": ["Tool"]}}
```

Use an actual canonical IRI from the graph and existing supported types. The override
replaces that entity's generated type suggestions; it does not edit source RDF types,
assertions or reviews. Record the evidence and rationale in the curation ledger, then
run `just organise`. Unknown identities, unknown types and empty type lists fail
validation. These annotations remain Inferred and Unreviewed.
An `overrides` entry can assign a kind or replace the theme list for one assertion:

```json
{
  "urn:example:assertion:reflection": {
    "kind": "Thought",
    "themes": ["learning-and-development", "systems-and-flow"]
  }
}
```

Use an actual assertion identifier from `just knowledge show`. Omitted keys retain
the rule result; an empty theme list explicitly removes theme membership. An optional
`rationale` explains the override in the generated RDF. Unknown
assertions, themes or kinds fail validation. If a correction supersedes an overridden
assertion, reconcile that override with the replacement before rebuilding.

Kind/type classification remains Inferred and Unreviewed, including overrides.
Theme suggestions start unreviewed and can be accepted or rejected separately.
Rule rationales and catalogue hashes are in RDF. Version control preserves changes
to the catalogue. Rejected and superseded assertions remain in review history;
the organisation layer covers active records.

## Theme review

`organisation/theme-reviews.json` stores explicit decisions, reasons, reviewer
attribution and source checks for assertion/theme pairs, with the actual reviewer recorded. These are judgements of topic relevance, not verification
of the underlying claims. Use `just themes` for current counts.

Run `just organise` after changing a theme decision. Accepted assignments remain
active even if a keyword rule no longer matches. Rejected assignments remain
inspectable under `theme_reviews` in `just knowledge show` and in RDF, but are
excluded from active theme links. Unreviewed assignments stay visibly uncertain.
Origin remains Inferred after acceptance.

The register pins the projected record and the theme's identifier, label and scope.
Content/identity changes or changed theme meanings make previous decisions stale;
they become unreviewed on rebuild. Keywords alone do not invalidate explicit review.
Do not refresh a stored fingerprint without rechecking every decision that uses it.

Each decision can override the batch's `reviewer`, `reviewer_kind` and `reviewed_at`
fields when another person reviews it. Keep the batch defaults unchanged so a later
human decision does not relabel earlier assistant reviews. Git retains register
history; there is no dedicated theme-review editing command yet.

`just themes` separates `review_status` (source claims), `classification_status`
(kind/type suggestions), and `theme_review_status` (memberships, including rejected
ones). Theme acceptance does not change either of the first two. The current
interface shows declared navigation and claim theme/classification status separately
from claim review. It uses virtual theme groups, with no theme hub nodes. The legacy
viewer additionally displays aggregate entity/theme links, including mixed membership
review states and reviewer details.

Kinds currently supported are Statement, Observation, Thought, Idea, Hypothesis,
Question, Assessment, Definition and Unspecified. A reported outcome is initially
an Observation; an attributed capability judgement is an Assessment; framework
records are Definitions. The remaining imported claims start as Statements. No
claim becomes a verified fact merely through classification or acceptance.

## Browse

```sh
just themes
just knowledge show --theme learning-and-development
just knowledge show --theme learning-and-development --theme systems-and-flow
just knowledge show --kind Observation
just visualise-theme leadership-and-collaboration
```

Repeated themes select their union. The JSON output includes review/origin,
classification uncertainty, original assertion identity, projected entity identities
and source quotations. Rebuild after identity or source changes; stale annotations
are withheld, while the assertion remains visible as Unspecified. Theme summaries
count assertions, not independent evidence or distinct entities. Theme totals overlap.

`just visualise-theme` launches the legacy graph-only viewer. Use `knot view` for
the shared Graph/Library page and choose the topic in its navigation or filters.

The rationale and limits are recorded in
[ADR 0016](../design_decisions/0016-basic-ontology-and-overlapping-themes.md) and
[ADR 0017](../design_decisions/0017-review-theme-membership-separately.md).
