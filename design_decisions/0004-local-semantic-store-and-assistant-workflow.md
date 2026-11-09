# ADR 0004: Start with a local semantic RDF store and explicitly invoked assistants

- Status: Accepted
- Date: 2026-11-03
- Implementation: Partial; local storage and assistant workflows delivered, Emacs integration deferred
- Documentation reviewed: 2026-11-07
- Supersedes: [ADR 0001](0001-evidence-retrieval-proof-of-concept.md)

Dataset-location policy was temporarily changed by ADR 0008. The public tool and
private datasets are now separated under [ADR 0038](0038-open-source-tool-and-private-datasets.md).
Local folder selection and optional standalone Git repositories are implemented in
[ADR 0043](0043-local-datasets-and-optional-git.md); authoritative personal data lives
outside the application checkout.

## Context

The first useful result is a local RDF representation of existing personal data,
including its semantics. Storing only documents, headings and links would not meet
that requirement. AI assistants will work with this store, but KNOT need not run
its own model to make that possible.

## Decision

Phase 1 stores documents, source references, semantic entities and relationships
in local RDF. Begin with a small selection of source archives, initially
concentrating on Org and Markdown. Keep private sources and
their derived knowledge outside the public application repository; use synthetic
fixtures for committed tests. Do not convert the entire collection in one increment.

Keep source passages linked to extracted assertions. Preserve the distinction
between what a source records and what an assistant infers. Detailed assertion
modelling and review policy remain under discussion in ADR 0003.

Extraction may be performed by an assistant explicitly invoked by the user,
including a hosted assistant. The user permits that assistant to read selected
source passages and propose RDF assertions, understanding that hosted processing
takes those passages outside the machine. This is not permission for automatic
bulk uploads or background provider calls. Local storage and local model execution
are separate choices; no local model installation is required by this decision.

Phase 2 introduces Emacs/Org integration, including the workflow for authoring and
reviewing relationships. Phase 1 must retain source references suitable for that
integration. A bespoke Emacs package, provider integration, MCP server and API are
outside the initial increment.

## Alternatives and consequences

- A synthetic retrieval demonstration would isolate graph-query behaviour, but
  postpones the user's immediate need to represent existing knowledge in RDF.
- Structural conversion alone is easier to validate, but misses semantic relations.
- Requiring a local model offers local processing, but adds setup that is not needed
  for a user-directed assistant workflow.
- Hosted assistants can assist with extraction when explicitly invoked. Their output
  remains candidate knowledge; permission to process passages does not establish
  the truth or acceptance of the resulting assertions.
- Working with real data requires private local evaluation alongside public synthetic
  tests. Basic conversion does not yet demonstrate improved AI retrieval or reasoning.

## Remaining decisions

- Candidate persistence is settled by [ADR 0005](0005-persist-unreviewed-candidates.md);
  detailed review operations remain to be designed. Default visibility is recorded
  in ADR 0003.
- File-first storage is settled by [ADR 0002](0002-portable-rdf-storage.md).
- Assertion representation is agreed in ADR 0003; remaining metadata details are
  still proposed. Vocabulary development is settled by
  [ADR 0006](0006-grow-vocabulary-from-source-data.md).
- The first conversion increment and its acceptance criteria.
