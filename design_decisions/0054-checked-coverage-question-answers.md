# ADR 0054: Check coverage questions before deterministic evaluation

- Status: Accepted for the initial bounded question contract
- Date: 2026-11-13
- Implementation: Implemented through the existing coverage CLI and MCP tool
- Extends: ADR 0052
- Supersedes: None

## Context

The coverage evaluator checks a typed request and produces an evidence receipt.
An AI client still chooses how an ordinary question becomes that request and how
to describe the result. Retrieval improvements do not validate those two steps.
KNOT needs a small checked path without adding an LLM provider or reasoning engine.

## Decision

Add `reviewed-support-question/1` for one project and one criterion. Accept two
fully matched templates: “Does project "PROJECT" have reviewed support for
criterion "CRITERION"?” and “What reviewed support does project "PROJECT" have
for criterion "CRITERION"?” Quoted values are exact case-insensitive visible
labels or explicit IRIs. Extra clauses, temporal conditions and stronger meanings
such as proven capability are unsupported, never silently discarded.

Optional `in framework "FRAMEWORK_IRI" at revision "REVISION_IRI"` selections pin
the definition explicitly. Otherwise require one visible framework/revision pair
among the criterion's Active Accepted definitions. Do not choose the newest revision
or first similarly named entity. Missing or ambiguous selections return bounded
choices without evaluation. Explicit IRIs do not establish existence or access.

Resolve names in the existing granted evaluation view before identity projection.
Display the typed request. Reuse the coverage rule, source verification, reviews,
qualifications and scope checks. Recheck the resolution view after execution so
a newly ambiguous name cannot produce a stale interpretation. Label metadata is
a selection aid, not proof of identity.

Use fixed answer wording for each returned outcome. Support remains an attributed
mapping assessment, never proof of capability or whole-criterion attainment.
Negative wording stays scoped; unknown stays unknown. Return the original question,
contract version, request, answer and complete receipt. Hash this envelope as well
as the nested receipt; hashes are reproducibility aids, not signatures or truth proofs.

Expose this through `knot evaluate --question` and `knot_evaluate`, accepting exactly
one of question or request. Keep structured-request behaviour compatible. If the
complete answer exceeds the MCP budget, use the existing output-budget abstention
and render the answer from it. Never retain a conclusion without its evidence.
If the abstention cannot fit either, fail explicitly.

## Alternatives and consequences

A finite language is less convenient than unrestricted conversation, but can reject
unsupported meaning without relying on a model to notice it. Client reformulations
remain outside this contract; they are not automatically equivalent to the original.
This adds no evaluation rules, general language understanding, identity or temporal
reasoning, policy trees, approved prose answers or replay. Quoted project names
select subjects; this is not a new project-type validator.

Resolution uses existing graph/view loading costs. Return at most ten choices per
field with explicit truncation; never choose one because others exceed the budget.
Grants remain operator-controlled. No dataset writes or acceptance occurs.

## Validation

Use synthetic expected requests and outcomes to check exact names and IRIs, missing
and ambiguous choices, multiple revisions, unsupported suffixes, scoped unknowns,
hidden-data noninterference, changed inputs, corrupt sources, fixed wording and no
writes. Exercise CLI, actual MCP transport, budget abstention and existing structured
requests. Replay live questions read-only without private examples in fixtures.
