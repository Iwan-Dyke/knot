# ADR 0021: Expose bounded retrieval through a scoped local MCP server

- Status: Accepted
- Date: 2026-11-04
- Implementation: Implemented; owner authoring added by ADR 0033
- Documentation reviewed: 2026-11-07
- Extends: ADRs 0019 and 0020

## Context

The user explicitly requested an MCP server over the existing retrieval interface.
Retrieval quality remains a development result, with documented misses; a transport
must not imply that independent relevance or support validation has been completed.
The user has explicitly advanced a local adapter while that quality review remains
pending; clients receive the documented limitations rather than a quality guarantee.
The existing API has no access boundary and must not expose hidden neighbours,
aliases, source passages or omission counts through an adapter.

## Decision

Use the official Python SDK as an optional pinned dependency, and serve stdio only.
The local MCP host launches and owns a process; no network port, bearer token or
OAuth endpoint is needed for this transport. HTTP deployment and multi-user
authorisation remain separate work. Do not change any client configuration globally.

Expose only entity/note lookup and bounded retrieval. Fix the dataset root and access
grant at process startup. Require either an explicit whole-dataset grant or a JSON
allowlist mapping source revision IRIs to snapshot SHA-256 hashes. An empty allowlist
grants nothing. The model cannot select another dataset, edit the scope, run raw
SPARQL, read arbitrary files, inspect ungranted history or write/review assertions.

Replay normal reviews and identity projection, then form an isolated eligible view
before collecting labels, computing scores, counting degrees, expanding neighbours
or scanning source text. Include an assertion only when all its evidence revisions
are allowed and match the pinned hashes. Keep original endpoints and the identity
receipts needed to explain their canonical projection. Restrict entity aliases to
labels on eligible assertions. Keep only allowed revision/document occurrences;
same-document lexical context cannot route through a denied revision. Do not disclose
denied IDs or counts as omissions. Lookup and retrieval use the same view.

A revision grant includes the full source revision, provenance and metadata of its
eligible assertions and relevant identity receipts. This is record-level selection,
not semantic redaction of free-form quotations or rationales. Themes, output budgets
and keyword filters are not access controls. Whole-dataset mode explicitly grants
the selected local dataset in full.

Keep server-side ceilings for context size and lookup count; clients may request
smaller budgets. Preserve complete paths, source integrity checks and review/kind
semantics. Accepted-only mode still excludes source-only context. Return one JSON
text block, disabling duplicated structured output. Bound the serialised tool result
as well as its inner retrieval payload, removing whole result packages if framing
does not fit. JSON-RPC request IDs and SDK protocol metadata are transport overhead.

Use read-only/closed-world tool annotations as descriptive hints, not authorisation.
Return generic errors for data loading, denied/unknown seeds and scope failures so
hidden identifiers cannot leak in error messages. Reload the current dataset for
every call; pinned grants do not automatically include new revisions. Keep stdout reserved
for MCP protocol messages, with operational messages on stderr.

## Validation

Use synthetic tests for default denial, source pins, mixed-source assertions,
hidden aliases/identities, source-only records, same-document revisions, review
replay, whole-dataset opt-in, wire budgets and error sanitisation. Exercise the
actual SDK client/server protocol in memory and through a stdio subprocess, including
tool discovery and invalid arguments. Existing tests must pass and personal source,
RDF and review data must remain unchanged. Optional SDK installation is required for
protocol tests; core access tests must not depend on the SDK.

Implemented with the pinned SDK v2.3.0. Validation includes in-memory modern and
legacy clients, an actual stdio subprocess, scope/pin negatives, hidden alias and
degree checks, full-path framing budgets and the complete project checks. Source,
RDF and review data remain unchanged. The optional SDK was installed in the existing
development environment; no lockfile or model provider was introduced.

## Tradeoffs

Stdio fits the current local CLI and avoids deploying an unauthenticated endpoint.
Explicit revision pins are conservative: granting only one of two cited images
can exclude an entire assertion, and new revisions require a deliberate scope edit.
Loading the full local graph before restricting the query view keeps review replay
consistent, but does not isolate memory, timing or underlying filesystem access from
the local process owner. Scopes constrain tool output, not a hostile host that can
already run arbitrary code as the same OS user.

## Native-note access amendment

ADR 0022 extends the same two read-only tools to native sources. A seed may identify
a permitted note; omitting it with a question searches eligible source text. Optional
`note_revision` requests one exact committed historical version. It grants nothing.
No note-write, raw file, scope mutation or history-enumeration tool is added.

A native grant maps a revision IRI containing the manifest digest to its body hash.
Verify the immutable manifest, note ownership, committed membership and body pin before
adapting the permitted revision metadata to the existing source view. Verify actual
body/manifest bytes again when reading evidence. A shared body hash is not a grant
to another note. Original text remains source-only with null claim review.
Native document identity, attribution and source context come from that manifest,
not other RDF documents referencing the same body. Existing RDF registrations must
match native manifests/pins. A historical native citation used by a graph assertion
is marked `EvidenceRevision` and does not become a default current-note text result.

Default unrestricted reads select committed heads. A restricted view selects the
latest granted revision by publication order, marked `LatestGrantedRevision`, with
global currentness unknown. It never probes a denied descendant to establish global
head state. An explicit request requires the exact revision grant and is marked
`ExplicitHistoricalRevision`; it does not establish whether that version is globally
current. Return no denied parent/head IDs or history counts. A grant still includes
the author, timestamps and other metadata recorded in that permitted revision.

The note registry's atomic publication index makes committed membership checkable
without traversing denied history. The owner upgrades a legacy index explicitly or
through a real save; MCP performs no index writes. Filter before reading native
manifests/bodies, labels, ranking statistics, candidate caps and omissions. Identity
projection for navigation uses only eligible identity receipts, with recorded IRIs
as the label fallback. Corrupt denied manifests/bodies cannot influence the view.

The selector and MCP framing remove complete evidence packages. Accepted-only still
excludes native source text. Rejected/superseded graph edges stay inactive even when
a native passage mentions their former claims. Tests exercise the SDK and actual
stdio transport, shared-body denials, explicit history, corruption and wire limits.

The SDK handles framing, negotiation and validation. Independent retrieval-quality
review remains pending; no transport changes claim origin, acceptance or confidence.

## Broad discovery extension (ADR 0023)

The same two tools support `knot_lookup(mode="discovery")` and
`knot_retrieve(subjects=[...], objective="all", exclude=[...])`. Strict list and
string bounds limit four selected subjects and 128 exclusion handles. Historical
native revisions retain the explicit revision interface. Scope projection precedes
all sampling, scoring, alias use and coverage counts. Discovery cards carry verified
source references and routing assertion receipts, not new factual relationships.
When transport framing drops a card, its unused source references are removed too.
Unknown and denied subject failures use the same generic error. SDK, in-memory and
actual stdio tests preserve the two-tool surface and complete-package budgets.

## References

- [Official Python SDK](https://py.sdk.modelcontextprotocol.io/)
- [SDK structured output](https://py.sdk.modelcontextprotocol.io/servers/structured-output/)
- [MCP stdio transport](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports)
