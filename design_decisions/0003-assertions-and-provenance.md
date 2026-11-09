# ADR 0003: Preserve assertion provenance and separate review from origin

- Status: Partially accepted
- Date: 2026-11-03
- Implementation: Partial; accepted and provisional portions are identified below
- Documentation reviewed: 2026-11-07
- Related: [ADR 0004](0004-local-semantic-store-and-assistant-workflow.md),
  [ADR 0002](0002-portable-rdf-storage.md)

Dataset-location policy was temporarily changed by ADR 0008. The public tool and
private datasets are now separated under [ADR 0038](0038-open-source-tool-and-private-datasets.md).
Local folder selection and optional standalone Git repositories are implemented in
[ADR 0043](0043-local-datasets-and-optional-git.md); authoritative personal data lives
outside the application checkout.

## Context

A document recording a statement does not establish that the statement is true.
The same relationship can appear in multiple sources with different provenance,
and an AI inference can later be accepted by a human. A single triple or a single
status field cannot preserve those distinctions.

AI consumers need evidence for every relationship used in an answer. They must be
able to distinguish a recorded claim, an interpretation and a supported conclusion.

## Accepted decision: assertion representation

Represent each assertion occurrence as a named graph with a stable IRI and one
domain triple. Describe that assertion in a separate metadata graph. The same
subject-predicate-object triple may occur in several assertion graphs, preserving
each source's contribution without treating repetition as independent corroboration.
Each occurrence retains its own source references and review status.

## Accepted decision: retrieval visibility

Default retrieval exposes both accepted assertions and unreviewed candidates, with
their review status, source evidence and origin distinguishable in the response.
Provide an accepted-only filter. Visibility does not change acceptance: a path that
uses an unreviewed assertion must not be presented as wholly accepted knowledge.

This allows an AI assistant to surface uncertain connections, ask the user for
clarification and explore new ideas during a conversation. A question or suggestion
does not itself confirm an assertion. If a new idea is persisted, it enters as an
unreviewed candidate under ADR 0005. Confirmation and correction operations remain
to be designed; this decision does not bring a review UI or MCP into Phase 1.

Rejected and superseded claims remain inspectable as history. How they are surfaced
alongside active results remains a separate policy decision.

## Accepted decision: correction history

Preserve the original assertion when a claim is corrected. Record a replacement
assertion and an explicit supersession link, retaining the original evidence and
review history. Attribute the correction and record its time and rationale where
provided. A replacement does not inherit acceptance merely because the original
was accepted; its review status must be explicit.

Supersession records a correction to knowledge. A fact changing in the world is
different: an earlier assertion may still be valid for its original time period.
Do not automatically supersede claims simply because their source document changed.
Detailed commands for correction and review remain outside this decision.

## Provisionally accepted decision: source snapshots

Keep an unchanged local copy of each ingested source revision alongside the private
RDF dataset. Link passage references to the specific revision so citations remain
verifiable if the working notes are edited, moved or removed. Keep these copies
outside the public application repository and preserve the original working files.

This choice is provisional and may be overturned. Revisit it after the first real
conversion, considering storage overhead, duplicate content and whether a lighter
approach can still resolve citations reliably. Do not remove existing snapshots
automatically if the policy changes; agree a migration separately.

## Proposed details: metadata and retrieval policy

Existing Org heading IDs are reused under the accepted identity decision in
[ADR 0007](0007-preserve-org-heading-identity.md). The remaining metadata details
below are still proposed.

Use standard RDF terms and a small KNOT vocabulary. Reuse PROV-O relationships for
attribution and derivation where their meaning fits. Named-graph placement has no
built-in review or trust meaning; the following conventions are KNOT policy.

Keep these dimensions separate:

| Dimension | Initial values or meaning |
| --- | --- |
| Origin | Explicitly recorded, inferred, or derived from multiple assertions |
| Review | Unreviewed, accepted, or rejected |
| Lifecycle | Active or superseded |
| Attribution | Source author and extracting agent, where known |
| Review event | Reviewer, time and optional rationale |

Acceptance means approval for use under KNOT's retrieval policy; it is not proof
of truth or independent verification. Preserve origin after review. Record human
confirmation as an attributed review event rather than replacing origin with
"human-confirmed". Defer numeric confidence until its interpretation is defined.

An explicit assertion must reference a passage in a particular document revision.
Inferred or derived assertions must identify their supporting assertion IDs and
record their rationale and generating agent. Preserve derivation links so several
claims copied from one source cannot be presented as independent evidence.

Do not query a union of all graphs as accepted knowledge. Surface explicitly
conflicting claims with their status when relevant. Neither a derivation label nor
an accepted supporting assertion automatically accepts a conclusion.

Assign a stable logical ID to a document and a content hash to each revision.
Identify a passage by revision, location and exact quoted text. Entity IDs remain
stable when labels change; do not merge entities solely because names match.

Keep event or validity time separate from document, extraction and review times.
Preserve contradictory assertions rather than overwriting one with the other;
use explicit conflict links for the fixture. Conflict alone does not establish
which assertion should supersede another.

## Alternatives and consequences

- One graph per document uses fewer graphs but needs an additional mechanism for
  assertion-specific review, duplicate occurrences and derivation.
- RDF reification keeps statement descriptions separate from asserted domain
  triples, but makes relationship traversal more verbose. It remains an alternative
  if named-graph policy proves too easy to misuse.
- Triple-term approaches may offer concise statement annotations, but would need
  a separate interoperability decision and tests across intended consumers.
- One graph per assertion occurrence increases metadata and query verbosity. The
  proof of concept must show that evidence paths remain understandable and traceable.

## Questions to settle through the fixture

- Which domain predicates are actually required for the leadership example?
- Can explicit conflict links and supporting assertions expose uncertainty clearly
  without implementing general contradiction detection?
- Is the minimum passage metadata sufficient to verify every returned relationship?

## References

- [W3C discussion of RDF dataset semantics](https://www.w3.org/TR/rdf11-datasets/)
- [PROV-O](https://www.w3.org/TR/prov-o/)
