# ADR 0006: Grow the vocabulary from the initial source sample

- Status: Accepted
- Date: 2026-11-03
- Implementation: Implemented
- Documentation reviewed: 2026-11-07
- Related: [ADR 0004](0004-local-semantic-store-and-assistant-workflow.md)

Dataset-location policy was temporarily changed by ADR 0008. The public tool and
private datasets are now separated under [ADR 0038](0038-open-source-tool-and-private-datasets.md).
Local folder selection and optional standalone Git repositories are implemented in
[ADR 0043](0043-local-datasets-and-optional-git.md); authoritative personal data lives
outside the application checkout.

## Context

The initial entity and relationship lists are suggestions, not a complete schema.
The first conversion uses a small connected sample of existing notes and capability
assessments. Its vocabulary must capture what the sources support without forcing
ambiguous statements into stronger claims.

## Decision

Develop the initial vocabulary from the selected sample. Add entity types and
relationships as concrete source passages require them. Define each term's meaning
and use it consistently; do not create synonymous predicates for each document.
Reuse established RDF vocabulary where its semantics fit.

Keep source and review metadata distinct from domain terms. Preserve unsupported
or ambiguous interpretations as explicit uncertainty rather than inventing links.
Treat capability assessments as attributed claims; repetition of a personal account
does not establish independent corroboration.

Keep private source names, passages and extracted assertions outside the public
repository. Document vocabulary definitions using synthetic examples. The selected
sample informs the first version, but must not restrict KNOT to career evidence.

## Alternatives and consequences

- Defining the full ontology upfront would provide an early common schema but risks
  speculative terms and modelling decisions unsupported by actual use.
- Allowing arbitrary predicates during every extraction reduces initial effort but
  makes consistent querying and entity relationships harder to maintain.
- An incremental vocabulary keeps the first conversion small. Later sources may
  require new terms or revisions; changes must preserve the meaning of stored claims
  or include an explicit migration decision.
