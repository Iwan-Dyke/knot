# ADR 0013: Preserve framework definitions as source-backed assertions

- Status: Accepted
- Date: 2026-11-03
- Implementation: Implemented
- Documentation reviewed: 2026-11-07
- Implements: ADR 0012

## Context

The framework sources were preserved but their competency definitions were omitted
by extraction focused on personal achievements. Definitions need to be retrievable
in their own right while retaining distinct framework schemes.

## Decision

Keep an inspectable extraction catalogue in `data/curation/frameworks.json`
(originally `data/migration/frameworks.json`; relocated during folder housekeeping).
Validate source hashes and every exact quotation before generating
`data/graph/frameworks.trig` through the existing migration command. Include the
output in the conversion ledger's protection against overwriting manual changes.

Give each source revision its own SKOS concept scheme and competency identifiers.
Use SKOS definitions for competency descriptions and mastery criteria; preserve
description and indicator text together to avoid guessing bullet boundaries in
wrapped PDF text. Represent each grade's required competency/mastery combination
as an explicit relationship. `n/a` does not create a requirement.

Use the existing one-triple assertion graphs and evidence metadata. Framework
assertions start unreviewed and have record kind FrameworkDefinition. Definition
imports do not accept personal achievement assessments. The current framework is
an explicit queryable policy selection, with the user's authority record retained.

Expose a framework query and separate viewer mode so the personal evidence view
remains manageable. Framework terms are not automatically equated across sources
or with interview labels. Framework changes retain distinct revision identifiers.

## Alternatives and consequences

A generic PDF parser would add complexity and still require layout review. A
curated catalogue is small, source-checkable and sufficient for reviewed source imports.
Every quotation and required criterion is checked on rebuild, while semantic
interpretation and PDF layout remain reviewable. Literal criterion blocks support
retrieval now; individual indicators can be modelled later if useful.
