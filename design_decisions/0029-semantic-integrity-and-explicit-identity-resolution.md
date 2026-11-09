# ADR 0029: Preserve semantic distinctions through explicit reviews

- Status: Accepted
- Date: 2026-11-05
- Implementation: Implemented
- Documentation reviewed: 2026-11-07
- Extends: ADRs 0003, 0010, 0011, 0027 and 0028
- Supersedes: None

## Context

Clear names do not establish correct identities or relationships. The graph contained
separate entities for a library and its explicitly stated new name, projects and
models represented as decision-makers, proposals represented as decisions, and
repeated accounts liable to be mistaken for independent evidence. These require
semantic review rather than another presentation-only rename.

KNOT already preserves source-scoped assertion occurrences, accepted identity
bindings and immutable correction events. Extend those workflows instead of
rewriting historical triples, replacing source notes or creating another graph.

## Decision

### Resolve referents explicitly

Classify investigated overlaps as the same referent, distinct but related referents,
a compound referent requiring separation, or insufficient evidence. Compare exact
source passages, dates, named identifiers and surrounding context. Matching names,
types or numerical counts alone never establish equivalence. A repeated description
can identify one event without establishing independent corroboration of that event.

Record supported identity decisions in the existing `entities.json` workflow, with
the actual reviewer, time, rationale and evidence retained in the review ledger.
Regenerate imported identity proposals through the owning migrator. Accepted bindings
change disposable query endpoints and native-note navigation; original source IRIs,
assertion endpoints, note manifests and review fingerprints stay intact. Identity
acceptance confirms the chosen referent, not the truth of every attached assertion.

Preserve previous accepted decisions and investigate contrary evidence. A mapping
withdrawal or correction needs an explicit recorded decision, not a label edit.
When a merge makes an old association a self-link, review its usefulness explicitly;
do not delete the original assertion. Keep projects, individual activities, tools,
decisions and time-specific scope states separate where the source distinguishes them.

Verified profiles on accepted source identities contribute historical search aliases
to the canonical entity without overriding its own preferred name. Each profile's
source grants still apply. Label similarity remains a retrieval aid, not an identity
mechanism or a means of exposing names from denied sources.

### Express the source's relationship

Evaluate both endpoints before selecting a predicate. Add two narrow vocabulary terms
where the existing actor-choice predicates cannot preserve the intended meaning:

| Relationship | Meaning and boundary |
| --- | --- |
| `actor madeDecision decision` | The source attributes the choice to that person, group or agent. A project, model or meeting is not substituted for an unknown actor. |
| `decision decisionAbout subject` | The choice concerns this project, model, activity or other subject. The object is what the decision concerns, not merely the meeting where it was recorded. This names neither a decision-maker nor an implementation. |
| `actor proposed proposal` | The source attributes a proposal to the actor. It does not establish agreement, authority to decide, implementation or completion. |

Retain a contextual `relatedTo` relationship when that is all the source establishes.
Use an existing precise predicate when its meaning is supported; do not strengthen
an association into ownership, causality or successful delivery. Source-attributed
causal explanations remain attributed. A reported outcome is not independently
verified merely because its representation was Accepted.

### Correct through history

Use `review.decide` / `just review correct` for an established semantic error,
including an Accepted assertion when the owner has authorised correction work.
The immutable event records the reviewer, time, reason, old content fingerprint,
replacement and supersession. Original assertions and events remain inspectable;
the ordinary view excludes superseded triples. Replacements remain Inferred and
Unreviewed unless acceptance is separately authorised. Do not infer acceptance
from the old assertion, an identity decision or a curated note.

Every correction verifies its original citations. Optional `additional_sources`
pins supply necessary context from already registered immutable revisions. They
use the existing revision/hash/text-hash/quote/offset/line validation and may add
context without rewriting the original quotation. This is not a source-ingestion
path and cannot invent a revision or bypass native provenance validation.

Distinguish correcting an extraction error from a real change over time. Later
project scope states can remain valid alongside earlier states. A later account's
qualification may expose an earlier interpretation as too strong, but does not
silently erase the earlier source or its history.

### Qualify repeated and overlapping accounts

Keep assertion occurrences and all source revisions. Use the provenance-backed
`curation/evidence-accounts.json` catalogue for explicit account qualifications:

- `RepeatedAccount`: the reviewed evidence identifies dependent retellings of an
  account. Multiple documents or revisions do not add independent corroboration.
- `OverlapUnresolved`: reports may overlap but the source does not establish their
  equivalence. Preserve each unit, period, scope and attribution; do not sum them.

Each group has stable `id`, unique assertion IRIs, relationship, qualification,
reviewer and exact source pins. Validate target existence and require each visible
member to have a citation span covered by a verified group pin. These annotations
do not merge entities, deduplicate assertions, change review status, create causal
links or alter evidence-selection ranking. Equal text alone creates no group.

Retrieval exposes only the group's ID, relationship, qualification and reviewer on
eligible assertions and matching text/hybrid `source_context`. A verified text passage
must contain or be contained by a group pin's exact span in the same revision and
evidence-text hash. Partial overlaps and equal text at another location do not match.
Source context keeps `claim_review: null`; the qualification does not accept a claim.
Reuse verified spans during selection rather than rereading sources per candidate.

Check every group pin's revision/body-hash grant before reading its source; validate
against the already eligible store. A hidden group exposes no qualification or member
list. All source pins are required even if only one group member is visible.
Repeated-account membership is not an access grant.

Equal counts of events, migrations and replications remain separate measurements
while unit equivalence is unresolved. A shared project and matching numbers do not
establish interchangeable quantities.

## Verification and tradeoffs

Take a baseline before semantic changes. Apply bounded batches centrally, preserving
source bytes, immutable native revisions, original assertion fingerprints and prior
review events. Verify intentional projection changes through explicit identity and
correction ledgers; replay reviews and rebuild organisation data through its owner.
Check historical and active retrieval, citations, aliases, native associations,
scoped access and the viewer. Include negative identity, actor, completion and
corroboration cases. Automated checks support, but do not replace, source review.

Semantic quality checks are warnings where judgement is required. They must not
invent an actor, infer completion or reject free-form note capture. A note still
requires no graph association or assertion. Uncertain cases receive focused review
options; source-supported corrections proceed within authorised review work.

The small vocabulary extension avoids hiding known distinctions in generic links.
Explicit account annotations require maintained provenance but preserve uncertainty
without automatic semantic deduplication. Rebuildable projections retain old evidence
and reversibility at the cost of displaying historical and current interpretations
clearly. Applied semantic changes and outstanding decisions belong in the dataset
review records, independently of this architectural decision.
