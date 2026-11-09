# ADR 0016: Organise one knowledge base with a small ontology and overlapping themes

- Status: Accepted
- Date: 2026-11-03
- Implementation: Implemented
- Documentation reviewed: 2026-11-07
- Implements: ADR 0014
- Retains: ADRs 0002, 0003, 0006, 0010, 0011 and 0013
- Subsequently extended by: ADR 0017 for explicit theme membership review

## Context

The user has prioritised reorganising the existing knowledge base around the basic
ontology: one interconnected mind with different themes. Most personal entities
currently have labels but no useful types. Frameworks and personal evidence share
storage but the default viewer hides the framework records.

Rewriting source assertions would invalidate their immutable review fingerprints.
Separating professional, personal and reading material into stores would work
against the agreed direction. Neither a shared theme nor a similar name establishes
an identity, factual relationship or independent corroboration.

## Decision

Keep the existing assertion graphs, evidence, reviews and confirmed identity
projection. Add a small RDF vocabulary defining entity types, existing domain
relationships, knowledge kinds and Theme. Use Entity as the fallback rather than
guessing a more specific type. Keep source-specific competency schemes distinct;
Competency is a kind of Capability, not a new universal competency authority.

Knowledge kind describes the assertion: Statement, Observation, Thought, Idea,
Hypothesis, Question, Assessment or Definition. Unspecified remains possible.
Acceptance does not change a kind or establish objective truth. Existing outcome
reports become Observations and capability judgements become Assessments; this
classification does not improve their evidence or review status.

Store organisation annotations in `urn:knot:organisation`, outside the immutable
assertion metadata. Themes have stable identifiers and may overlap. A local JSON
catalogue supplies labels, keyword rules and explicit classification overrides;
generated TriG is inspectable and portable. Record the method, input hash and
rationale. Initial classifications are Inferred and Unreviewed, independently of
the underlying assertions. This increment does not add a classification approval
workflow; corrections are edits to the version-controlled catalogue and rebuilds.

Use exact label rules only to suggest types, never to merge entities. Keyword
matches propose navigation themes, never semantic relationships. Unknown matches
stay unclassified. Preserve all assertions, including literal definitions, in the
unified query view. The viewer omits definition paragraphs as nodes and offers
theme and kind filters. Optional theme hubs are clearly labelled organisational
links, excluded from semantic claim counts and accepted-only views.

Rebuild organisation independently and after source migration. Guard generated
files against unnoticed edits. Detect changed assertion inputs before using their
saved annotations; expose affected records as unclassified until rebuilt. Rejected
and superseded assertions remain available through the existing history workflow.

## Alternatives and consequences

A destructive rewrite would simplify some queries but discard useful history.
An additive named graph preserves review integrity and is reversible, at the cost
of an extra graph join and a rebuild step. Keyword themes are explainable and local
but incomplete and sometimes noisy; they are navigation aids, not discovery proof.
Themes cannot serve as access controls.

The ontology can represent reading, personal reflections and professional work
together; this migration does not manufacture records for domains not yet ingested.
It does not claim complete semantic coverage of the preserved source documents.
ADR 0015 remains a proposed discovery experiment. No automatic concept equivalence,
causal inference, external model calls, MCP service or temporal belief engine is
introduced here.

## Acceptance criteria

1. All existing assertion identifiers, content fingerprints and review outcomes
   survive; source snapshots and identity decisions remain unchanged.
2. One query returns personal and framework records with types, kinds, themes,
   uncertainty and exact source evidence. A record can belong to multiple themes.
3. Shared labels and themes do not merge identities or create semantic claims.
   An accepted Thought remains a Thought.
4. Rebuilding is deterministic, modified outputs are protected, and stale or absent
   classification cannot hide an active assertion from the unfiltered view.
5. Synthetic tests cover these behaviours; the existing checks continue to pass.
