# ADR 0030: Curate continuously through validated authoring boundaries

- Status: Proposed
- Date: 2026-11-05
- Implementation: Partial; validation and diagnostics delivered, broader standard remains proposed
- Documentation reviewed: 2026-11-07
- Extends: ADRs 0003, 0010, 0011, 0022, 0025, 0027–0029
- Supersedes: None

## Context

KNOT already separates immutable evidence, curated prose and reviewed assertions.
Native note writes verify revisions, associations and provenance. Review replay
checks immutable fingerprints; scoped retrieval verifies grants before exposing
derived knowledge. Preferred names preserve historical aliases and stable IRIs.
The remaining publication gap was supplementary assertions assembled by hand.
Corrections also admitted undefined predicates, and a failed import could write
extracted text before finding invalid claims. Full quality reports made newly
introduced issues difficult to distinguish from historical notices.

Use the existing Python APIs as the common curation boundary. Introduce no new
database, dependency, note taxonomy, schema migration or autonomous agent framework.
This decision does not authorise a cleanup or acceptance of historical records.

The following references distinguish standards, operational guidance, research
and practitioner conventions; they do not all carry the same authority:

- [SHACL](https://www.w3.org/TR/shacl/) separates constraint results and severity.
  Portable shapes would help external RDF producers, but do not replace verification
  of KNOT's files, exact Unicode locators, ancestry or review fingerprints. Retain
  Python validation now; revisit shapes when a concrete interoperability need exists.
- [PROV-O](https://www.w3.org/TR/prov-o/) distinguishes attribution and derivation.
  Preserve the author of an account separately from its curator; provenance is
  traceability, not proof of truth or independent corroboration.
- [SKOS](https://www.w3.org/TR/skos-reference/) distinguishes identifiers, preferred
  labels and alternatives. Retain KNOT's equivalent practical separation without
  turning people and projects into SKOS concepts or changing storage.
- [Wikidata constraints](https://www.wikidata.org/wiki/Help:Property_constraints_portal)
  guide editors and allow exceptions. Its [merge guidance](https://www.wikidata.org/wiki/Help:Merge)
  requires the same referent; similar wording is insufficient. KNOT retains explicit
  identity review and source-scoped originals rather than destructive merging.
- [Quality research](https://www.semantic-web-journal.net/system/files/swj773.pdf)
  treats quality as several dimensions and fitness for use. Report diagnostics with
  denominators rather than a single score or a demand to fill every missing field.
- [Atomic evergreen notes](https://notes.andymatuschak.org/Evergreen_notes_should_be_atomic)
  are a practitioner convention about coherent, reusable ideas. They do not justify
  mandatory sentence lengths, concept-only notes, entities or link counts.
- [Human-in-the-loop research](https://arxiv.org/abs/2212.05189) supports separating
  proposed knowledge from expert verification. Its particular models and tooling
  are not required for that separation.

## Knowledge Curation Standard

This section records the authoring guidance for the authorised implementation.
The broader standard retains Proposed status. ADRs 0027–0029 retain detailed
naming conventions, predicate meanings and historical decisions.

| Component | Expected representation | Limits and uncertainty |
| --- | --- | --- |
| Entity | A distinguishable referent, stable IRI, independently meaningful preferred name, historical aliases and supported type where known. Search identities before creating one; retain the evidence for identity decisions. | A noun phrase is not sufficient. Consider a literal, note, assertion or existing referent. Separate projects, activities, tools, decisions and outcomes. Missing types and similar names do not establish equivalence or falsity. |
| Knowledge note | One coherent idea, descriptive title, context-independent prose, actual authorship, relevant connections and qualifications. Derived notes use immutable source pins. | Free capture may be untitled, unclassified and unlinked. Use existing knowledge kinds. Atomicity is editorial judgement, not one sentence per note. Reading a concept does not establish applying it. |
| Relationship | A supported subject, predicate and object; exact source context; origin, rationale, authoring agent and independent review state. | Actor predicates need attributed actors; a decision is not its decision-maker. Preserve plan/completion, involvement/ownership, association/causation and reported/corroborated distinctions. Unknown meaning remains a candidate or no relationship. |
| Evidence | Original bytes and revisions remain immutable. Curated restatements have their own identities, authors and derivations. Structured assertions cite pinned evidence. | Paraphrases never enter exact-quotation fields. Repeated writing, native metadata revisions and AI restatements do not independently corroborate an account. Matching leaf hashes detect overlap, not all dependence. |

`madeDecision` attributes a choice to an actor; `decisionAbout` links the decision to
its subject without supplying an unknown actor. `reportedOutcome` preserves an
attributed report. `relatedTo` asserts association only. `implemented` needs an account
of implementation, not just a plan. `resultedIn` and `enabled` preserve the source's
causal attribution and uncertainty. Validation cannot prove these meanings true.

## Three enforcement levels

| Level | Automatic behaviour | Current implementation |
| --- | --- | --- |
| Hard integrity contract | Reject invalid structure, source pins, note ancestry, stale writes and unsupported review transitions before publishing. | Existing notes/provenance/access/review APIs; shared relationship node-kind/domain-vocabulary checks; candidate required metadata, stable namespace, collision checks and exact citations. Common XSD integer/decimal/boolean lexical forms are checked; other datatype IRIs/language tags are preserved, not comprehensively validated by an XML Schema engine. |
| Soft diagnostic | Return warnings without merging, inventing types, changing acceptance or blocking valid free writing. | Shared known-type actor/object checks, suspicious literal relationships, projected self-links, narrow plan/outcome clues, naming checks; whole-graph duplicate/name/association/derivation diagnostics. |
| Editorial guidance | Require deliberate author reasoning and communicate uncertainty. | Distinguish instructions from capture, search existing records, write coherent prose, select sufficient evidence, assess source independence and decide useful granularity/links. |

Missing real-world information is not false. Required fields describe the local
publication envelope, not a closed-world requirement that every entity has a known
type, complete history or all possible relationships. Types inferred by organisation
remain suggestions; a warning based on them is not a verdict. Heuristics neither
prove support nor infer an actor, responsibility, completion or causal conclusion.

## Lifecycle and internal contract

1. **Capture:** Establish the user's intent. Save authorised source text through
   `notes.create_note`/`save_note` or `just notes`, retaining exact bytes. An instruction
   to change knowledge is not automatically a permanent note. Reuse existing evidence
   when it supports the operation; preserve a new clarification only when authorised.
2. **Curate:** Search existing notes/entities. A readable source note may suffice.
   Otherwise create a separate derived note through the same note API with title,
   actual curator, saving agent, method, qualification and verified source pins.
   Use `provenance.source_pin` to construct pins; never guess offsets or hashes.
3. **Validate candidates:** `curation.prepare_candidate(root, candidate)` takes explicit
   caller-proposed knowledge and returns verified RDF, warnings and source overlap
   hashes without writing. It is a deterministic builder, not a language-model
   extractor. `curation_rules` is shared by authoring, corrections, imports and audit.
4. **Review meaning:** Inspect warnings with source context. Uncertain identities and
   substantive corrections require explicit review. An Unreviewed candidate can
   remain useful and discoverable. Publication and a clean report do not accept it.
5. **Publish:** `curation.publish_candidate` repeats validation and appends through
   the owning additions workflow. Use `review.decide` for accept/reject/correct and
   the established identity workflow for bindings. Notes retain their existing API;
   do not wrap them in another storage contract. Imported claims retain `migrate`.
6. **Maintain:** Run `just quality` read-only when a curation batch finishes or a
   diagnostic is needed. Compare against an explicit saved baseline. Refresh
   organisation/viewer projections when their inputs change; saving a native note
   alone requires neither migration nor a persisted note graph.

Codex, Kiro, the owner-local CLIs and future interfaces use these same Python
boundaries. MCP is read-only and scoped by default; ADR 0033 adds separately enabled owner
authoring and review permissions. In either mode, an owner-local API is not a workaround
for denied grants. No capture or publication alters access policy.

### Assertion candidate publication

The JSON contract requires `id`, `subject`, `predicate`, `object`, `origin`,
`rationale`, `agent`, `generated_at` and `sources`. Endpoint IRIs and labels are
explicit. An object may instead preserve a literal value, datatype or language.
New supplementary IDs use `urn:knot:assertion:`; existing historical identifiers
remain valid in their owning workflows. Types/identity decisions are not silently
created. The agent IRI and timezone-bearing timestamp identify the actual authoring
operation; they are not the source author or event date.

All candidates are Active and Unreviewed; there is no candidate acceptance option.
They contain one domain triple, complete metadata and exact source quotations.
Native snapshot/hash registration reuses the saved revision; retrieval-only adapter
metadata is never persisted. Original source-scoped identities are not rewritten.

Publication validates before acquiring a write lock, then revalidates under the
review writer's lock and atomically replaces additions with its original bytes plus
the new fragment. Existing review events must still replay against the combined
store. The caller retains its ID, timestamp and draft for retries: exact replay is
idempotent, including after acceptance or supersession; altered content under the
same ID fails. As with existing owner-local workflows, this assumes cooperating
single-machine writers. It is not a multi-process transaction across manual edits,
imports, source mutation and all files. Invalid input writes no authoritative data;
an operating-system failure is not a promised cross-file rollback.

Imported extraction retains historical quotation anchors and assertion fingerprints.
Deferring generated text writes until candidates and frameworks validate closes a
failure-before-validation gap without changing valid output bytes. Ordinary semantic
warnings do not modify extraction results. Repeated ambiguous quotes still need
source review; the new native candidate path requires an explicit offset.

## Diagnostics and evaluation

`just quality` retains errors/warnings and adds stable finding IDs, categories,
attention priorities, schema and rule versions. `--baseline` reports new, resolved
and persisting IDs while retaining the complete current report. IDs are diagnostic
references, not a new review database. Historical aliases and missing old generation
timestamps are informational; they are not counted as new unresolved identity work.
Outputs cannot overwrite files inside the data root or their own baseline.

Report provenance failures, current name/duplicate candidates, current semantic
warnings, current source/curated note counts, directly covered source notes,
immutable correction events and active replacements separately. Coverage counts
exact logical source note/body associations; it is not a target of 100%, a measure
of prose quality, or a claim of independent evidence. Correction counts do not imply
earlier mistakes: world changes and later understanding can also require corrections.
Diagnostic priority counts are not the owner's decision backlog; existing explicit
review records remain authoritative.

Rule-version differences can introduce findings on unchanged data. Compare original
records and versions before attributing a delta to improvement or degradation.
No retrieval algorithm changes are included. Synthetic engineering, leadership,
reading and reflection scenarios exercise capture, curation, publication, review,
retrieval and negative cases. Existing scope/citation/review regressions continue to
apply. Independent code review complements tests; neither proves semantic truth.

Remaining owner judgement includes identity, source independence beyond known
lineage, semantic support, qualification sufficiency, atomicity and whether a
connection is useful. The implementation deliberately leaves these decisions visible.
