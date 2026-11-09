# ADR 0012: Use the career framework as competency authority

- Status: Accepted
- Date: 2026-11-03
- Implementation: Implemented
- Documentation reviewed: 2026-11-07
- Refines: ADR 0006

## Context

The dataset owner selected a career framework as the authority for competency
definitions within that dataset.
The existing extraction retained framework documents and passages but omitted
semantic definitions because it focused on personal achievements. Interview headings are not necessarily framework skill names.

## Decision

Use the selected career framework to define competency names, descriptions,
mastery levels, indicators and grade requirements. Preserve its document revision
and exact evidence for each extracted definition. Treat framework definitions as
knowledge in their own right, separately from claims about personal achievement.

Retain interview terminology and prior assessments with their provenance. Map
them to framework competencies only through explicit, reviewed relationships;
similar names do not establish equivalence or demonstrate a competency.

When a dataset includes multiple frameworks, preserve their schemes separately
and record its selected current framework explicitly. This is dataset policy:
KNOT does not prescribe a particular employer, role, grade or framework for all users.

## Alternatives and consequences

Using interview headings as the vocabulary would perpetuate ambiguous competency
labels. The framework provides defined criteria against which evidence can be
assessed, while keeping the evidence assessment itself reviewable. Importing its
definitions is a separate increment from resolving the remaining entity identities.
