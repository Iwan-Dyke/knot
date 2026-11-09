# Architecture decision records

ADRs explain significant decisions and their tradeoffs. The [current architecture](../docs/architecture.md)
describes delivered components; the [usage guides](../docs/README.md) describe how to
operate them. The [release checklist](../docs/release.md) tracks pending delivery.

## Read by topic

| Topic | Start here |
| --- | --- |
| Open-source distribution and data separation | [0038](0038-open-source-tool-and-private-datasets.md), [0042](0042-retire-experiments-and-export-tool-only.md), [0043](0043-local-datasets-and-optional-git.md) |
| Storage, source preservation and native notes | [0002](0002-portable-rdf-storage.md), [0009](0009-auditable-archive-migration.md), [0022](0022-native-free-text-knowledge-and-entity-notes.md) |
| Claims, reviews and identity | [0003](0003-assertions-and-provenance.md), [0010](0010-persistent-assertion-review.md), [0011](0011-resolve-confirmed-identities-in-query-view.md), [0029](0029-semantic-integrity-and-explicit-identity-resolution.md) |
| Organisation and frameworks | [0012](0012-use-career-framework-for-competencies.md), [0013](0013-preserve-framework-definitions-as-assertions.md), [0016](0016-basic-ontology-and-overlapping-themes.md), [0017](0017-review-theme-membership-separately.md) |
| Retrieval and discovery | [0019](0019-bounded-knowledge-retrieval-for-ai-context.md), [0020](0020-question-aware-hybrid-retrieval.md), [0023](0023-broad-discovery-and-selected-subject-retrieval.md), [0039](0039-share-retrieval-provenance-without-dropping-evidence.md) |
| Authoring and AI access | [0021](0021-scoped-local-mcp-server.md), [0025](0025-owner-local-note-cli.md), [0032](0032-guided-zettelkasten-authoring.md), [0033](0033-owner-mcp-authoring-and-runtime-diagnostics.md) |
| Curation and naming | [0027](0027-source-preserving-knowledge-curation.md), [0028](0028-meaningful-entity-names-and-value-presentation.md), [0030](0030-continuous-knowledge-curation.md), [0046](0046-guided-source-backed-curation.md) |
| Viewer and navigation | [0047](0047-unified-knowledge-library-and-graph-exploration.md), [0026](0026-live-offline-graph-filters.md), [0035](0035-notes-in-the-unified-graph.md), [0044](0044-extensible-visual-and-knowledge-themes.md), [0045](0045-persistent-visual-themes-and-css-palettes.md) |
| Implemented module boundaries | [0036](0036-modular-retrieval-and-shared-boundaries.md), [0037](0037-feature-packages-for-the-whole-application.md) |

## Status and history

- **Proposed:** a direction still under discussion. A separately authorised experiment
  or bounded implementation does not accept the full proposal.
- **Accepted:** the decision is agreed within its stated scope. Implementation may be partial.
- **Partially accepted:** only the explicitly identified portions are agreed.
- **Superseded:** another ADR replaces the stated scope; preserve the earlier record.
- **Rejected:** considered but not adopted. No current ADR uses this status.

The **Implementation** field records delivery independently. An accepted design is
not proof that every planned feature exists. **Documentation reviewed** records an
editorial update, not a new acceptance date. Earlier implementation-only statuses
are represented as Accepted for their already authorised scope; open standards in
0027 and 0030 remain Proposed.

Important relationships:

- 0004 supersedes 0001's initial experiment sequence.
- 0008 temporarily replaced the separate-data location in 0002, 0003, 0004 and 0006.
  0038 supersedes that distribution direction. Data separation is complete; 0043
  implements external dataset selection and standalone Git synchronisation.
- 0011 applies identities after review replay without rewriting original assertions.
- 0023 provides ephemeral discovery; it does not implement 0015's persistent inference proposal.
- 0033 extends read-only MCP with separately enabled owner writes and reviews.
- 0036 and 0037 implement bounded refactors; the broader proposal in 0024 remains open.
  0037 supersedes 0036's temporary top-level layout, retaining its dependency rules.
- 0047 makes Graph/Library the default viewer, retaining 0026/0035's earlier viewer
  through `--legacy` and reusing its knowledge/filtering contracts.

## Decision register

Numbers and filenames remain stable so links and historical references keep working.
Dataset-specific selections are scoped to their dataset, not defaults imposed on
all users. Private benchmark outcomes and source quotations belong with private
research records; technical rationale remains here. The old local Git history was
discarded as recorded in 0042. Historical contexts and original decisions below are
not current command references; use the linked guides for today's behaviour.

| ADR | Decision | Status | Implementation |
| --- | --- | --- | --- |
| [0001](0001-evidence-retrieval-proof-of-concept.md) | Start with an evidence retrieval proof of concept | Superseded | Not implemented; replaced before delivery |
| [0002](0002-portable-rdf-storage.md) | Keep RDF files authoritative and rebuild the query store | Accepted | Implemented |
| [0003](0003-assertions-and-provenance.md) | Preserve assertion provenance and separate review from origin | Partially accepted | Partial; accepted and provisional portions are identified below |
| [0004](0004-local-semantic-store-and-assistant-workflow.md) | Start with a local semantic RDF store and explicitly invoked assistants | Accepted | Partial; local storage and assistant workflows delivered, Emacs integration deferred |
| [0005](0005-persist-unreviewed-candidates.md) | Persist extracted assertions as unreviewed candidates | Accepted | Implemented |
| [0006](0006-grow-vocabulary-from-source-data.md) | Grow the vocabulary from the initial source sample | Accepted | Implemented |
| [0007](0007-preserve-org-heading-identity.md) | Preserve Org heading identity across revisions | Accepted | Implemented |
| [0008](0008-keep-personal-data-in-knot-repository.md) | Keep personal data in this repository initially | Superseded | Replaced by external datasets; legacy mixed-repository sync remains supported |
| [0009](0009-auditable-archive-migration.md) | Track migration coverage separately from claim review | Accepted | Implemented |
| [0010](0010-persistent-assertion-review.md) | Preserve review decisions independently of extraction | Accepted | Implemented |
| [0011](0011-resolve-confirmed-identities-in-query-view.md) | Resolve confirmed identities in the query view | Accepted | Implemented |
| [0012](0012-use-career-framework-for-competencies.md) | Use the career framework as competency authority | Accepted | Implemented |
| [0013](0013-preserve-framework-definitions-as-assertions.md) | Preserve framework definitions as source-backed assertions | Accepted | Implemented |
| [0014](0014-one-logical-personal-knowledge-graph.md) | Keep one logical personal knowledge graph | Accepted | Partial; organisation and bounded retrieval delivered by later ADRs |
| [0015](0015-bounded-cross-domain-discovery.md) | Start discovery with a bounded shared-concept experiment | Proposed | Not implemented; persistent inference proposal remains open |
| [0016](0016-basic-ontology-and-overlapping-themes.md) | Organise one knowledge base with a small ontology and overlapping themes | Accepted | Implemented |
| [0017](0017-review-theme-membership-separately.md) | Review theme membership independently of claims | Accepted | Implemented |
| [0018](0018-retire-verified-source-archives.md) | Retire verified source archives | Accepted | Implemented |
| [0019](0019-bounded-knowledge-retrieval-for-ai-context.md) | Bounded Knowledge Retrieval for AI Context | Accepted | Implemented; independent relevance evaluation pending |
| [0020](0020-question-aware-hybrid-retrieval.md) | Rank question-aware graph paths and source context together | Accepted | Implemented; independent relevance evaluation pending |
| [0021](0021-scoped-local-mcp-server.md) | Expose bounded retrieval through a scoped local MCP server | Accepted | Implemented; owner authoring added by ADR 0033 |
| [0022](0022-native-free-text-knowledge-and-entity-notes.md) | Preserve native free-text knowledge and entity notes | Accepted | Partial; native lifecycle and interfaces delivered, general external editing deferred |
| [0023](0023-broad-discovery-and-selected-subject-retrieval.md) | Discover subjects before retrieving their evidence | Accepted | Implemented; independent broad-relevance evaluation pending |
| [0024](0024-modular-local-first-knowledge-architecture.md) | Evolve KNOT as a modular, local-first knowledge system | Proposed | Partial; bounded refactors separately accepted in ADRs 0036 and 0037 |
| [0025](0025-owner-local-note-cli.md) | Add an owner-local note CLI over the existing API | Accepted | Implemented |
| [0026](0026-live-offline-graph-filters.md) | Filter the offline graph interactively | Accepted | Implemented |
| [0027](0027-source-preserving-knowledge-curation.md) | Preserve sources and curate readable knowledge | Proposed | Partial; provenance and curation APIs delivered, broader standard remains proposed |
| [0028](0028-meaningful-entity-names-and-value-presentation.md) | Name referents clearly and present literals as values | Accepted | Implemented |
| [0029](0029-semantic-integrity-and-explicit-identity-resolution.md) | Preserve semantic distinctions through explicit reviews | Accepted | Implemented |
| [0030](0030-continuous-knowledge-curation.md) | Curate continuously through validated authoring boundaries | Proposed | Partial; validation and diagnostics delivered, broader standard remains proposed |
| [0031](0031-guided-personal-note-capture.md) | Guide personal note capture through the existing CLI | Accepted | Implemented |
| [0032](0032-guided-zettelkasten-authoring.md) | Guide Zettelkasten notes, entities and relationships together | Accepted | Implemented |
| [0033](0033-owner-mcp-authoring-and-runtime-diagnostics.md) | Expose owner authoring through MCP and diagnose blocked runtimes | Accepted | Implemented |
| [0034](0034-knowledge-commit-and-push.md) | Commit and push knowledge through the local CLI | Accepted | Implemented |
| [0035](0035-notes-in-the-unified-graph.md) | Show notes as nodes in the unified graph | Accepted | Implemented |
| [0036](0036-modular-retrieval-and-shared-boundaries.md) | Separate retrieval coordination from reusable engines | Accepted | Implemented |
| [0037](0037-feature-packages-for-the-whole-application.md) | Organise the whole application into feature packages | Accepted | Implemented |
| [0038](0038-open-source-tool-and-private-datasets.md) | Publish the tool separately from personal datasets | Accepted | Implemented for v0.1.0; licensing, documentation, data separation and dataset selection/sync delivered |
| [0039](0039-share-retrieval-provenance-without-dropping-evidence.md) | Share repeated retrieval provenance without removing evidence | Accepted | Implemented; opt-in wire format |
| [0040](0040-optional-retrieval-diagnostics.md) | Make retrieval diagnostics optional in AI responses | Proposed | Implemented opt-in view; default unchanged |
| [0041](0041-opt-in-definition-specificity-ordering.md) | Refine source-backed definition ordering using title specificity | Proposed | Implemented opt-in MCP/Python option; default unchanged |
| [0042](0042-retire-experiments-and-export-tool-only.md) | Retire experiment artifacts and export the tool separately | Accepted | Implemented for v0.1.0; standalone dataset sync delivered separately by ADR 0043 |
| [0043](0043-local-datasets-and-optional-git.md) | Select local datasets with optional Git synchronisation | Accepted | Implemented |
| [0044](0044-extensible-visual-and-knowledge-themes.md) | Extend visual palettes and knowledge themes independently | Accepted | Implemented |
| [0045](0045-persistent-visual-themes-and-css-palettes.md) | Save visual preferences and discover CSS palettes | Accepted | Implemented |
| [0046](0046-guided-source-backed-curation.md) | Guide manual curation through source selection and existing authoring | Accepted | Implemented |
| [0047](0047-unified-knowledge-library-and-graph-exploration.md) | Explore one knowledge system through a library and focused graph | Accepted | Implemented browsing release; authoring deferred |
| [0048](0048-idle-mode-autonomous-knowledge-exploration.md) | Cinematic exploration of existing knowledge in Idle | Accepted | Implemented; extended performance and accessibility validation pending |

## Add or revise a decision

Use the [template](TEMPLATE.md) for one significant decision or coherent theme.
Do not create an ADR automatically for every module or routine refactor. Use the
next unused number, an actual decision date, a concise title and explicit scope.

Start new directions as Proposed until agreed. Acceptance does not authorise data
review, source publication, access changes or a deployment. Record implementation
progress independently. When direction changes, add a superseding ADR and link
both records; do not silently replace the old choice. Clarifications and removal of
private examples may update prose without rewriting the decision's meaning.

Prefer Context, Decision, Alternatives, Consequences, and Validation/implementation
sections. Older records retain additional sections when they preserve qualifications
or decision history. Move long usage examples and mutable command defaults to `docs/`.
