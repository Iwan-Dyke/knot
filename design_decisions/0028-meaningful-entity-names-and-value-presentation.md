# ADR 0028: Name referents clearly and present literals as values

- Status: Accepted
- Date: 2026-11-05
- Implementation: Implemented
- Documentation reviewed: 2026-11-07
- Extends: ADRs 0003, 0011, 0012, 0013, 0016, 0026 and 0027
- Supersedes: None

## Context

A graph node should explain what it represents without requiring its neighbouring
edges to supply its subject. Extracted headings, bare outcomes and framework skills
with identical names have made exploration unnecessarily difficult. The viewer also
rendered the integer `18` as a node, although its RDF already correctly represented
a numeric attribute of a reported outcome.

Renaming identifiers, rewriting evidence or merging similar labels would damage
traceability. The existing preferred-label overlay and generated organisation view
allow names and navigation to improve independently of assertion history.

## Decision

Audit the complete current graph: personal and professional knowledge, imported
documents, framework referents, canonical identity projections, native-note
associations, organisation views, preferred labels and actual viewer output.
Account for every visible node and every literal omitted from the canvas. Record
the stable identifier, original representation, source evidence, decision, aliases
and any required review. Apply supported changes in bounded batches, with one
coordinator reconciling domain proposals.

### Choose the representation before the name

An entity identifies a distinguishable referent useful for connection or retrieval.
A heading, sentence or noun phrase alone does not establish one. Prefer a note for
an idea or reflection, an assertion for a source-backed relationship, and a literal
for a count, description or other value belonging to a referent. A note needs no
entity or assertion. Keep closely related ideas together where splitting would
lose their meaning; do not impose a second mandatory note taxonomy.

Retain existing IRIs. Use `data/curation/entity-labels.json` for source-backed
preferred names and historical aliases. Its pins must verify against immutable
sources. A label correction changes presentation only: it does not correct an
assertion, accept a claim or confirm identity. Preserve exact original quotations
and historical assertion labels. Matching spellings are duplicate candidates,
never authority to merge. Keep source-scoped framework competencies separate even
when their names or descriptions overlap.

### Name each referent independently

Use concise, descriptive names with enough supported context to distinguish the
referent. Avoid bare `Result`, `Meeting`, issue numbers and phrases such as `Built
and reviewed by the team`. Add the subject, scope or activity that the source
establishes. Do not add an unverified date, expand an uncertain acronym or turn a
planned action into a completed outcome. Avoid repeating context that adds no
identifying value, and keep complete sentences in notes or assertion evidence.

| Referent | Naming convention and boundary |
| --- | --- |
| Person | Supported name; add role or scope only to distinguish people. Never infer a full identity from a first name. |
| Team or organisation | Supported collective name and necessary organisational scope. Keep an unnamed reported group distinct from its individual members. |
| Project or system | Project/system name, with a verified expansion or purpose where needed. Work performed on it is a separate activity or assertion. |
| Activity or event | Subject and undertaking, with project, location or date only where supported and useful. Preserve separate occurrences. |
| Decision | Identify the choice and its subject. A decision does not imply implementation, delivery or success. |
| Action | Identify the undertaking and target; preserve whether it is planned, ongoing or reported complete. |
| Outcome | Identify the activity and reported result. Retain attribution or uncertainty; accepted source fidelity is not independent corroboration. |
| Book or document | Supported title and distinguishing edition, author or document scope where necessary. Reading or applying it is a separate claim. |
| Concept | Name the reusable idea or phenomenon. Statements about it belong in notes or assertions. |
| Capability or competency | Skill name plus framework scope where it identifies a framework-specific referent; for example, `Mentoring · Example framework`. |
| Criterion or role grade | Skill, mastery level and framework for criteria; role and grade for grade nodes. Mark an explicitly undefined level as undefined. |
| Tool or technical artefact | Tool/artefact name and distinguishing purpose or project. Do not rename an artefact as a claim that it was delivered successfully. |

Use the narrowest supported existing type. Exact-IRI `entity_type_overrides` in
`data/organisation/catalogue.json` can replace misleading generated suggestions
through `just organise`. These remain Inferred/Unreviewed organisation annotations,
not corrections to source RDF types or accepted assertions. Keep the rationale and
evidence in the curation record. A suspected semantic error in a reviewed assertion
requires the existing explicit correction/review workflow.

### Keep values attached to their subjects

RDF literals are values, not independent entity identities. Preserve their exact
lexical value, datatype, language, units and source evidence. A number may also be
a legitimate title or domain identifier: inspect its RDF role before changing its
presentation. Never rename every occurrence of a number globally or invent units.

The offline viewer presents literal assertions as inspectable attributes of their
subjects, including definitions and numeric outcome attributes. Attribute evidence keeps
the assertion ID, status, origin, rationale and exact quotations. Claim filters
apply to these attributes too. Attribute counts remain distinct from graph edges
and entities; removing a synthetic value node does not remove its assertion.

Visible entities use preferred names. Search includes historical names and aliases,
while the inspector exposes original names and identifiers. Keep full labels;
wrapping may improve layout but truncation must not erase identifying context.
Neither visual filtering nor name changes alter facts, access grants or reviews.

### Gate extraction and authoring

Before adding an entity through Codex, Kiro, the CLI/API or an imported extraction:

1. Identify the distinguishable referent and the evidence establishing its scope.
2. Search existing names, aliases and IRIs; reuse only a supported identity.
3. Consider a note, assertion or literal instead of creating another node.
4. Read the proposed name on its own. Include its subject and necessary context.
5. Check type and granularity. Separate project, action, decision and outcome where
   the evidence distinguishes them; retain an unresolved or genuinely collective
   referent where it does not.
6. Check relationship meaning. Association is not causation, involvement is not
   ownership, and book advice is not evidence of personal application.
7. Preserve source wording, qualification and provenance; apply normal review
   rules and record uncertain identity or semantic decisions for focused review.

This gate guides extraction, not the user's writing. Free-form capture remains
valid, including unlinked notes. Deterministic spelling and display corrections
need no speculative identity decision. Review queues should concentrate on
uncertain referents, compound identities and changes to assertion meaning.

## Verification and tradeoffs

Take a baseline of source bytes, note heads/revisions, assertion fingerprints,
identity bindings and review events before cleanup. Compare after each batch and
verify citation locations, review replay, retrieval and scoped access. Check dense
project/framework views, full labels, aliases, attributes, filters and layout.
Record before/after counts and all retained or unresolved cases in the
dataset-specific naming audit.

`just quality` emits reviewable warnings for numeric-only named referents, generic
or context-dependent labels, sentence/compound granularity, current-name duplicates
and literals used under relationships that normally identify entities. These checks
use verified preferred names; historical alias collisions remain separate. Literal
counts measure assertion occurrences, not distinct entities or independent evidence.
Warnings do not reject valid numerical titles, natural prose or source-backed values.

The overlay preserves review fingerprints but requires maintained provenance and
aliases. Heuristics find candidates rather than settle semantic questions. The
inventory and review queue therefore remain necessary even when automated naming
warnings are absent. Rebuilding authoritative RDF solely to improve the picture
would introduce unnecessary identity and review risk.
