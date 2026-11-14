# ADR 0058: Review alternative question wordings with decision explanations

- Status: Accepted for decision-explanation wording mappings
- Date: 2026-11-13
- Implementation: Preview/review CLI, checked answering, scoped MCP and revalidation
- Extends: [0056](0056-reviewed-decision-explanations.md), [0057](0057-checked-routing-and-artifact-selection.md)

## Context

The real-use exercise returned no answer for three ordinary decision questions,
even though one had an existing source-backed explanation. Exact templates alone
make repeated use awkward. Guessing at paraphrases would move interpretation back
outside the checked boundary. KNOT already has an explicit review lifecycle for
an exact decision, question, explanation revision and source dependencies.

## Decision

Extend that existing preview and approval with up to 20 complete alternative
question wordings, each 1–2000 characters. Reviewers check that every full question
has the same meaning and scope as the canonical decision question and that the
exact answer applies. They must reject wordings that add dates, actors, outcomes,
comparisons or other conditions the target contract cannot represent. Structural
validation cannot establish this semantic equivalence.

`knot explain prepare --wording ...` proposes the complete list for review without
activating it. Omission retains the latest list; `--clear-wordings` explicitly
proposes an empty list. Approval seals the wordings in the existing immutable
event, alongside the reviewed content hash, reviewer, reason and time. Withdrawal
retains the list for history but disables reuse. A reapproval replaces the list.
No new store, dependency, grant or automatic personal-knowledge review is added.

Existing events without a `wordings` field remain valid and mean an empty list.
Do not rewrite historical events. The event validator also checks wording shape,
limits, duplicates and withdrawal consistency. Updated previews require fresh
preparation before approval. Old code does not understand the extended event shape.

The checked router first recognises its existing templates. Otherwise it matches
the entire reviewed wording, ignoring only surrounding whitespace. Case and
punctuation remain significant. A wording cannot override a built-in template.
No lexical ranking, embedding or generated translation chooses a mapping.

Enumerate only visible current curated revisions and their immutable entity
associations; inspect each possible request's approval history after access
filtering. Require all transitive source grants before an artifact is visible.
Bound this search to 1,000 visible revision/entity pairs; return unknown if the
bound is exceeded. An explicit explanation revision can narrow enumeration.
Never consult a dataset-wide hidden-wording index or read denied review histories.

Several active mappings to different decisions require selection before executing
an answer, even if one answer would be stale. Several eligible explanations for
one decision follow the existing artifact-selection rules. A matched withdrawn
mapping returns unknown; no visible registered mapping returns unsupported.
Missing grants and removed wordings cannot restore old text through revalidation.

Receipts retain the original question, canonical request, exact answer, existing
evidence and the matching approval event hash. Recheck all inspected histories,
including nonmatching candidates, so a concurrent mapping cannot create unnoticed
ambiguity. Source, snapshot and complete-output-budget checks remain in force.

## Tradeoffs and verification

Reviewed whole-question mappings permit natural wording for recurring questions
without claiming general language understanding. Each new phrasing has a review
cost; applicability errors remain possible if the reviewer approves a bad mapping.
The first extension covers decision explanations only. Coverage aliases and general
policy or temporal interpretation remain outside this decision.

Tests cover multiple phrasings, unchanged answer bytes, unapproved previews,
extra conditions, ambiguity across decisions, withdrawal, explicit clearing,
old events, source changes, missing grants, hidden mappings, concurrent changes,
enumeration/output budgets, quality auditing, CLI and real MCP stdio transport.
All authoring fixtures are synthetic. Personal knowledge is not changed to make
these implementation checks pass.
