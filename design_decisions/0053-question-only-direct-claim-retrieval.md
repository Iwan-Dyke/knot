# ADR 0053: Include direct claims in question-only hybrid retrieval

- Status: Accepted for bounded question-only hybrid retrieval
- Date: 2026-11-13
- Decision updated: 2026-11-14
- Implementation: Bounded default hybrid change implemented under authorised retrieval work
- Extends: ADRs 0020, 0021, 0023 and 0052
- Supersedes: The text-only channel description for question-only hybrid requests

## Context

Question-only hybrid requests previously searched only source sections. Reviewed
relationships were unreachable unless a client first selected a subject. General
framework passages could therefore displace the evidence sought by a question
such as “What supports my release engineering skills?”

A second problem was packaging: a mapping could cite a reviewed criterion
definition, while a qualification cue anywhere in its unstructured framework
document caused that entire document to become mandatory project context. The
complete package could then exceed the response budget even though the mapping,
its source qualifications and its definition citation fit.

## Decision

Search existing direct substantive claims alongside text for question-only hybrid
requests. Require a lexical endpoint-label match, honour the existing outgoing
predicate policy, omit navigation-only and framework-definition edges from this
new channel, and retain one-hop paths without choosing or inferring a seed.
Identity bindings, authorship, origin, kind and review state remain explicit.
The words “my” and “I” do not identify the owner as a claim's actor.

Use the existing scoped preparation, citation verifier and complete-package
selector. Bound direct candidates to the hybrid graph allocation and share the
existing source-revision budget. Rescore retained claims using the same lexical
weights as text; preserve text relevance without cross-channel rank fusion.

For explicit support/demonstration wording, prioritise recorded `supports` and
`demonstrates` relationships with matching endpoint labels before candidate
retention and use existing ranked selection for the complete packages. Report
this relevance cue; do not boost or change acceptance. Other question-only queries
retain relevance-first selection. Explicit seeds, selected-subject gathering,
text-only requests and opt-in definition ordering retain their routing/selection.

Distinguish a mapping's exact reviewed target-definition pin from project evidence.
For `supports`/`demonstrates`, a whole-document context cue alone cannot expand that
pin into the entire framework. Match target criterion, source revision and exact
quotation against an Accepted framework definition. Keep the original pin,
qualifications in it, smaller qualifying units and explicit account qualifications.
Without that exact reviewed match, retain the existing context requirement.

## Alternatives and consequences

Requiring manual lookup leaves ordinary questions unable to retrieve existing
claims. Broadly changing keyword weights or adding embeddings would change more
behaviour and dependencies than the identified failure requires. Dropping evidence
to fit would weaken the contract and is excluded.

The new channel can consume source budget before text search. Candidate, source,
passage and response limits can still omit relevant records. Relationship wording
and endpoint labels are heuristic relevance cues, not general language
understanding, independent truth or proof of whole-criterion attainment. A missing
search result is not a negative evaluation result. The evaluator still needs an
explicit typed request.

## Validation

Use invented projects and criteria to test unseeded mapping discovery, explicit
relationship priority before caps, retained Unreviewed states, denied-source
noninterference, complete qualifications, corrupted sources and response budgets.
Test the exact reviewed-definition distinction and preserve same-source context
requirements for other claims. Run existing retrieval, provenance, access and MCP
checks, then replay bounded private ordinary-question cases without copying
private data into fixtures or changing knowledge to improve search results.

### Follow-up: fresh question checks

A bounded batch froze questions and expected source pins before retrieval, covering
technical choices, performance, prioritisation, onboarding, completion uncertainty
and an invented absent project. One comparison missed relevant measurements because
its wording asked whether an improvement occurred while the source described costs
and runtime in different terms. An invented-data regression reproduced the miss.

Extend the existing lexical intent groups narrowly: speed comparisons seek runtime,
latency, duration or throughput; cost comparisons seek cost measurements. Include
opposite directions in the same measurement group without treating them as factual
agreement. This reuses existing ranking and verification, with no new dependencies,
identity inference or changes to evidence. Test both positive and negative question
premises, complete qualifications and conflicting source-only accounts.

The original first-pass results remain separate from the tuned replay. This is an
agent-prepared diagnostic batch, not an independent human benchmark. The absent
project control initially yielded unrelated keyword matches; it established a relevance
limitation, not support for the invented project or a general absence conclusion.

### Follow-up: explicit subject constraints

Generic delivery terms could retrieve unrelated evidence when a question named an
absent project. Preserve broad lexical retrieval, but recognise a conservative explicit
syntax in question-only text/hybrid requests: a capitalised single-token name after
`project`, a quoted project name, or a hyphen/underscore identifier containing letters
and digits. Do not infer identities from arbitrary capitalisation or select a seed.

Prioritise literal mentions in eligible routing hints and retained candidates. Direct
claims must match in their evidence or eligible endpoint names/aliases. Source-only
units may match in verified text, section headings or native metadata titles. Build
complete evidence packages before excluding unrelated packages so required caveats
without the subject's name remain attached. Multiple explicit subjects use any-match
semantics, allowing comparison without claiming every subject has evidence.

Expose the applied `subject_constraint`, including `absence_not_established`, outside
optional diagnostics. A bounded or scoped miss is not a negative coverage evaluation.
Keep the existing grants, source verification, review states and byte budgets. Broad
questions, explicit selections and opt-in definition ordering retain their routing.

This deliberately sacrifices some paraphrase recall for explicit literal subjects.
It does not solve unmarked names, typos, pronouns or entity resolution. A global rule
requiring every query word would incorrectly suppress broad questions and contrary
evidence. A new entity recogniser would add substantially more behaviour than this
reproducible failure requires.

Regression checks cover unknown subjects, source-only notes, identifier boundaries,
visible aliases, attached caveats, multiple names, denied-source noninterference,
changed bytes, quoted names containing identifiers, and compact MCP response budgets.
Replay the original negative control alongside broad and known-subject positive cases.
