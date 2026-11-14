# Retrieve and discover evidence

Run commands from the repository root after [setup](../README.md#installation).
Examples use the selected dataset; see
[dataset selection](datasets.md#select-a-dataset) for external folders. Replace
uppercase identifiers with values returned by your own dataset.

```sh
just retrieval lookup "Example project"
just retrieval get ENTITY_IRI --max-chars 12000
just retrieval get ENTITY_IRI --accepted-only
just retrieval get ENTITY_IRI --question 'Which unresolved dependencies threaten this project?' --mode hybrid --max-chars 12000
just retrieval get --question 'What did reading teach me about throughput?' --mode text --max-chars 12000
```

`lookup` returns candidate IRIs from active entity labels and confirmed aliases.
Exact matches take priority over a case-insensitive substring fallback. Ambiguous
labels return separate candidates; select an IRI explicitly for `get`. Lookup
defaults to ten candidates (`--limit` changes this). Literal definitions are not seeds.

`get` returns compact JSON with canonical and original assertion endpoints, identity
receipts, ordered paths, per-assertion review/origin/kind, exact passages, revision
hashes, source locators and omissions. Without `--question` it retrieves the existing
deterministic neighbourhood around the seed. Traversal is
breadth-first, ordered by predicate, direction and assertion IRI. Substantive claims
are followed outwards; `relatedTo` and `decisionAbout` can be followed in either direction.
Each assertion is one hop, and each entity is expanded at most once. Use
`--include-frameworks` to make framework definitions eligible.

With `--question`, graph mode ranks eligible routes and complete substantive paths
before degree/frontier limits and output selection. Ranking uses distinct question
terms weighted by corpus frequency, declared word forms, bounded passage-length
normalisation, intent concepts and small predicate bonuses. Section context helps
rank project evidence ahead of unrelated material in the same document. `matches`
explains each selected path or source unit through its score, matched terms,
concepts, locality and predicate bonus. Scores
describe relevance heuristics; they do not assess truth or the strength of an achievement.

Questions explicitly asking for `measurable`, `measured` or `measurement` outcomes
also recognise targets/baselines and completion language. Their hybrid ranking
preserves the scorer's locality and interpretation adjustments, and can use required
qualifying source context to rank a short RDF claim. A mention of an entity in an
unrelated passage's body has weaker locality than an entity heading or a verified
assertion anchor. These are relevance cues, not verification of a number or its cause.
Other questions retain the established ranking; this is a limited increment, not
general semantic understanding.

Comparative wording also recognises the measurement being sought: `faster`,
`slower` and `slowdown` look for runtime, latency, duration or throughput evidence;
`cheaper` and `costlier` look for cost evidence. Either direction can retrieve a
contrary finding. These are relevance cues only; quotations, qualifications and
review states retain the recorded meaning.

Question-only text/hybrid searches recognise explicit subject syntax: `project Falcon`,
`project "Blue Ember"`, or an identifier containing letters, digits and hyphens or
underscores, such as `TASK-42`. They prioritise literal subject mentions before bounded
candidate retention and exclude unrelated complete packages. Matching can use verified
text, section headings, native-note titles or eligible claim endpoint labels/aliases.
Required qualifications remain attached even when they do not repeat the name.
With several explicit subjects, evidence mentioning any one can qualify.

`subject_constraint` records the case-insensitive literal filter and remains present
when diagnostics are omitted. It is not identity resolution, proof of support or a
dataset-wide presence test. Empty results do not establish absence: grants, lexical
wording and search budgets still limit retrieval. Unmarked names, misspellings and
implicit references can still yield unrelated keyword matches. Use lookup and an
explicit seed when a particular entity is intended. Broad questions, explicit seeds,
selected-subject gathering and opt-in definition ordering retain their existing routing.

For a broad question spanning decisions, outcomes and qualifications, a larger
budget can be necessary:

```sh
just retrieval get ENTITY_IRI --question 'Which project decisions and reported outcomes have supporting evidence and qualifications?' --mode hybrid --max-chars 24000 --max-passages 6 --max-assertions 20
```

Hybrid may select source context without structured assertions when complete graph
paths cost more than their additional information. Such context keeps null claim
review. Use `--mode graph` for structured claims and their paths; use `--accepted-only`
when every returned assertion must be accepted. MCP requests remain subject to the
server's configured ceiling (12,000 characters by default).

`--mode text` searches verified source sections, including preserved documents with
no assertions. `--mode hybrid` combines graph and text ranks, rewarding overlapping
evidence and preferring surrounding source context on equal supporting ranks, in
one response budget. Question-ranked text and hybrid retrieval require a question; entity text mode
without a question instead browses associated notes. Long sections with explicit
`Why this matters:` or `Interview lens` boundaries can yield a complete evidence
body and a separate interpretation unit. Recorded qualifications stay with the
body; recognised caveats in the tail prevent splitting. Other sections remain
whole. Units retain ancestor headings and exact character/line locations;
`section_complete` and `document_complete` describe their boundaries. Oversized
units are omitted intact.

Final selection evaluates complete evidence packages against the character,
assertion and passage limits. It considers relevance, additional question terms,
content already represented and qualification cues, using serialized retrieval JSON
costs with conservative diagnostic and omission reservations. MCP framing and its
optional presentation changes are applied later, so this selection estimate is
not the exact final MCP cost. `selection` reports the strategy, package count and
bounded trial count. A higher-ranked candidate may lose to a more useful combination.
After selecting a combination, actual omission metadata can release enough space
for one additional complete package. The final response is checked at its exact
wire size; qualifications and provenance are never shortened to make it fit.

An otherwise fitting package may still be excluded by the intermediate reservations
or by selection order. Measuring every trial in the MCP representation alone did
not safely resolve this: it displaced qualifying evidence in regression cases.
The [experiment summary](../design_decisions/0042-retire-experiments-and-export-tool-only.md#retrieval-alternatives-7-november)
records the findings and promotion decision. The production selector remains
unchanged.

Overlapping quotations in the same revision can share one containing passage.
When present, a source's `passage_span: [start, end]` gives its **exact quotation**
within that passage, using zero-based Unicode characters and an exclusive end.
Without that field, the quotation is the entire passage. Source locators still
refer to the original quotation in the source file. Clients should honour the range
when quoting or checking a citation; surrounding context does not inherit an
assertion's review status.

An assertion or text/hybrid `source_context` may include `evidence_accounts` with a
reviewed group's `id`, `relationship`, `qualification` and `reviewer`.
`RepeatedAccount` identifies dependent
retellings; `OverlapUnresolved` preserves uncertainty about potentially overlapping
reports. Neither establishes independent corroboration or changes the assertion's
review status. These annotations do not merge or automatically deduplicate results.
They require verified source pins and grants for every cited group revision; hidden
groups expose no qualification or member list. Text passages receive the qualification
only when their verified source span contains
or is contained by a group pin; partial overlaps and other occurrences of the same
words do not match. Source context retains `claim_review: null`. See the
[account catalogue guide](reference/catalogues.md#semantic-corrections-and-account-provenance).

In hybrid mode, a retained containing source unit with a qualification cue can become
required context for its graph claim. The graph match records `context_sources` and
`context_reason`; that context remains unreviewed source text and survives response
trimming with the claim. This is a same-source presentation hint, not a new graph
relationship or a determination that two accounts contradict each other.

For a `supports`/`demonstrates` mapping, an exact quotation already registered as
the Accepted definition of its target criterion remains a definitional citation.
A qualification cue elsewhere in that whole framework document does not make the
entire document mandatory project context. The exact pin, qualifications within
it, smaller qualifying units and explicit evidence-account qualifications remain
intact. Different criteria, revisions or quotations and Unreviewed definitions do
not receive this exception.

Text context requires meaningful seed-label terms (excluding descriptors such as
`account`), a verified active assertion involving the seed, or context in another
verified revision of the same logical document. `source_context` records this as
`seed_context`, including `EntityAssertionInRevision`; its `entity_link`
remains `LexicalOnly`, and `claim_review` is null. Same-name matches do not resolve
identities. Sources without headings, including stored image transcriptions, remain
whole sections. Source context can retain original statements later corrected or
rejected as assertions; it never restores those active domain triples.

Accepted-only mode excludes all source-only context and still requires every hop
of a graph path to be Accepted. The response flags this exclusion, including for
accepted-only text mode, which returns no source-only passages.

Question retrieval additionally bounds source revisions (64), source sections
(1,024) and retained candidates (128), configurable with `--max-source-revisions`,
`--max-source-sections` and `--max-candidates`. Hybrid reserves half the candidate
capacity for graph exploration, then uses the remaining capacity for text. Candidates
are ranked within the bounded scan, with stable ties; omissions remain visible.

Default limits are two hops, ten assertion IDs including association steps, four
stored evidence passages and **12,000 Unicode characters in the complete JSON,
including its newline**. The response reports UTF-8 bytes separately. Complete
provenance can exceed this budget. Increase it explicitly when omissions indicate
that complete evidence cannot fit. A result can contain
only omissions when no complete path fits. Quotations are never clipped.
Legacy passages are distinct quotations; ranked results can share one containing
passage among several exact citation ranges.

Expansion is also bounded: sixteen expanded entities, sixteen queued entities and
twelve eligible edges per node. Persons and nodes with more than twenty-four eligible
edges cannot route intermediate paths; explicitly selecting one limits its expansion
to four edges. Corresponding `--max-*`, `--hub-degree` and `--seed-hub-degree` options
change these limits. With a question, high-degree project nodes instead use the
ordinary per-node cap and relevance-aware lookahead bounded by requested depth and
expanded-entity limits. Generic intermediate nodes remain excluded; generic seeds
retain the stricter cap. `hub_degree` triggers selective expansion of ranked edges.
`omissions.limits` counts encountered excluded edges or pending
expansions, not the total missing assertions. `further_unknown` means unexplored
branches may hide additional material. `alternate_routes` counts skipped repeated
entity expansions. The response does not claim a complete neighbourhood.

Every evidence-bearing hop must be Accepted in accepted-only mode. In ordinary mode,
an Unreviewed association stays Unreviewed even when it leads to an Accepted claim.
Themes and type metadata cannot supply factual path steps. Classification remains
separate from claim review; a Thought remains a Thought.

Snapshot hashes, quotation text and available numeric locators are checked before a
path is returned. Extracted text requires its conversion-ledger hash; images require
their recorded transcription hash. Invalid citations exclude the whole affected
path extension and appear as aggregated failure categories under `omissions`.
`StoredTranscription` verifies consistency with stored text, not the image's meaning.
Repeated quotations share a passage while source occurrences and revisions remain
separate. Hashes, document IDs and image overlap groups support comparison;
source independence remains Unknown.

The Python API is `knot.retrieval_engine.service.retrieve(data_root, canonical_iri, Policy(...))`;
optional `question=...` and `mode='graph'|'text'|'hybrid'` enable ranked selection.
Omit the seed for question-only retrieval, or pass a native note ID to select a
note. Question-only hybrid retrieval searches source sections and existing direct
claims with matching endpoint-label terms. Text mode remains source-only.
Optional `note_revision=...` reads an exact committed native revision.
Pass `limits=knot.retrieval_engine.search.Limits(...)` to change the question-specific scan bounds.
`lookup` selects candidates and `serialise` produces the measured retrieval JSON.
The MCP adapter adds tool-result framing and enforces that representation's limit.
Each public retrieval call reloads the current graph and reviews. Results are local
and read-only. Without a scope, the API uses the whole dataset. Optional
`scope=knot.interfaces.access.AccessScope(...)` applies the same revision grants as the MCP adapter;
it constrains results, not the underlying filesystem privileges of the local process.
Relevance is heuristic and can miss valid evidence. Use synthetic regression tests
for behaviour; independent relevance evaluation remains incomplete.

## Discover subjects before retrieving evidence

For a broad question without an entity name, inspect compact suggestions first:

```sh
just retrieval discover --question 'Which engineering choices protected data pipelines against failure and data loss?' --max-chars 4000
just retrieval gather --subject SUBJECT_IRI --question 'Which engineering choices protected data pipelines against failure and data loss?' --max-chars 8000
```

Select identifiers from the discovery response rather than guessing them. Repeat
`--subject` for up to four entities, notes or exact source units. Unassociated notes
and sources without RDF assertions are eligible. Source-unit identifiers bind an
entire evidence unit to its revision, location and quotation hash; pass them verbatim.
Native notes default to their current permitted revision; use the existing
`get NOTE_IRI --note-revision REVISION_IRI` interface for explicit historical reads.

Discovery includes verified source locators, supporting assertion review states,
identity resolution status, relevance reasons, coverage and omissions. Suggestions indicate
possible relevance, not established facts or inferred connections. Inspect them,
refine the question where needed, and retrieve promising subjects. Inspect suggestions rather than assuming the first few cover the question.
Focused `get` remains available.

`gather` shares work and response budgets across subjects and deduplicates matches.
Use `--objective relationships`, `context` or `qualifications` (repeatable) to inspect
complementary evidence perspectives. These filters do not infer contradictions or
split arbitrary questions into semantic subquestions. Returned matches include
stable `handle` values; repeat `--exclude HANDLE` to skip already examined matches.
Required qualifying context remains attached to a returned claim.

Python callers use `knot.retrieval_engine.discovery.discover(...)` and
`knot.retrieval_engine.discovery.gather(data_root, subjects, question, Policy(...), ...)`, with the
same `scope` and `Limits` objects as existing retrieval. When the full revision cap
binds, eligible metadata and bounded source samples choose revisions before evidence
loading. `--max-revision-previews` (256) and `--max-preview-bytes` (8192 per revision)
bound this routing work. Samples are not evidence; selected sources still require
complete integrity verification. Unsampled revisions and content between sample
windows may remain undiscovered.

Broad recall remains limited; no production embedding model is required.

For a question without a seed, hybrid retrieval also considers bounded, one-hop
substantive claims whose endpoint labels match question terms. It does not select
an entity identity, join paths or infer that an actor is the owner. Source grants,
review filters and citation verification apply before a claim can be returned.
Half the candidate cap is available for these claims; text uses the remaining
capacity and shares the source-revision budget. Definition claims remain available
through explicit seeds; framework text follows `--include-frameworks`.

Questions using `support`, `supports`, `demonstrate` or `demonstrates` prioritise
matching recorded `supports`/`demonstrates` relationships before general topic
passages, both before candidate retention and in final ranked selection. The
response reports `selection.strategy: "rank"` and the matches expose
`ranking.direct_relation_match`. This priority does not depend on acceptance and
does not verify capability. An Unreviewed claim stays Unreviewed.

Other question-only requests retain the highest-ranked complete package that fits,
then fill remaining space with complementary context (`relevance_first`). Claims
and text share lexical weights without reciprocal-rank fusion. Explicit-seed
queries, selected-subject gathering, text-only search and opt-in definition ordering
retain their selection behaviour. See [ADR 0053](../design_decisions/0053-question-only-direct-claim-retrieval.md).

This helps prevent several cheap, weaker passages from displacing the primary
account. Ranking still depends on wording: a top result may be incomplete or
irrelevant, and later clarifications are not automatically discovered or treated
as verified truth. Inspect the citations and omissions; use targeted lookup or
gathering when a broad response misses necessary evidence. Complete evidence that
does not fit is omitted rather than shortened.

### Optional definition ordering

For question-only requests, MCP accepts `definition_order=true`; Python accepts
`retrieve(root, question=question, mode='hybrid', definition_order=True)`.
The default remains `False`. The option gives a more specific matching Definition
title precedence over a less specific title from the same original source revision.
It uses already verified packages, preserves scores and quotations, and retains
the existing selector and strict MCP budget enforcement. Non-definition positions
stay fixed; original rank breaks ties among eligible candidates. The selector still
reports `relevance_first`; per-match scores remain the original lexical scores.

This option is bounded to 128 candidates and is limited to question-only text/hybrid
retrieval. It rejects seeded, historical-note and selected-subject requests. Titles
are relevance signals, not identity decisions or proof of answer sufficiency.
Multi-part questions, incorrectly ranked primary subjects and missing corrections
remain limitations. See [ADR 0041](../design_decisions/0041-opt-in-definition-specificity-ordering.md)
for the measured scope and promotion decision.

## Share repeated provenance

Use `--compact` with `get` or `gather`, or `compact=true` on MCP `knot_retrieve`,
to share identical provenance records within the response:

```sh
just retrieval get ENTITY_IRI --question 'What supports this decision?' --mode hybrid --compact
```

A smaller response uses `format: "shared-provenance-v1"`:

- Each `sources` entry retains its locator, passage and optional `passage_span`.
  Its `metadata` reference selects a complete entry in `source_metadata`.
- Within that metadata, `native_note.derivation.sources` references complete pins
  in `derivation_sources`, including every exact input quotation and qualification.
- Resolve these references before interpreting a citation. They are local to this
  response, whereas note/revision identifiers and hashes remain stable references.

The response remains self-contained. Nothing is accepted, summarised or removed.
When sharing would be larger, the server returns the usual full format. Selection
still uses the original budgets; this option does not promise additional recall.
MCP's configured ceiling and source grants still apply.

Python callers can use `compact(retrieve(...))` and `expand(response)` from
`knot.retrieval_engine.wire`. Expansion restores the full response and its size
counters without reading files. To inspect more context, use the existing explicit
note revision or selected-source retrieval interfaces with an appropriate budget;
permission to read one revision does not grant another. See [ADR 0039](../design_decisions/0039-share-retrieval-provenance-without-dropping-evidence.md)
for the format's rationale and limits.

### Omit retrieval diagnostics from AI context

For `get` and `gather`, add `--no-diagnostics` to omit ranking explanations,
selection statistics, match scores and work counters. MCP callers use
`diagnostics=false`; Python callers can use `wire.evidence_view(result)`.
The default retains diagnostics.

```sh
just retrieval get --question 'What supports this decision?' --mode text --no-diagnostics --compact
```

All selected quotations, original derivation pins, authorship, review state,
qualifications, relationships, applied policy and omission information remain.
`usage` retains output characters/UTF-8 bytes and assertion/passage counts;
`diagnostics_omitted` identifies the omitted administrative fields. This option
changes presentation after selection, so it does not promise to find or select
additional evidence. MCP still enforces its complete result-size ceiling.
