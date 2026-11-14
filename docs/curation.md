# Curate notes and source-backed claims

Run commands from the repository root after [setup](../README.md#installation).
Examples use the selected dataset; see
[dataset selection](datasets.md#select-a-dataset) for external folders. Replace
uppercase identifiers with values returned by your own dataset.

## Guided manual curation

Run `knot curate` to write a separate curated note using saved evidence. No agent
or hand-written provenance JSON is required. If the original text is not saved yet,
capture it first with `knot add /path/to/source.md`, supplying its actual author
when known. Then start curation:

```sh
knot curate
# Optional: supply details before the prompts.
knot curate --title 'A reading reflection' --author 'Your name'
```

1. Search sources by title or ID, or enter `*` to list them. The picker includes
   current native notes and registered imported document revisions. Imported sources
   can also be found by snapshot path; their readable evidence text must already be
   registered. Unreadable or invalid sources report an error and let you choose again.
2. Read the numbered source text. Select an inclusive line range, or paste an exact
   passage. Repeated passages prompt you to choose the occurrence. Add more passages
   from that source or select another source; Enter finishes selection. At least
   one passage is required. `/remove` removes a selected passage; `/cancel` leaves
   the draft for later.
3. Choose **Faithful restatement** or **Synthesis**, and describe what the evidence
   establishes and what remains uncertain. Enter the curated note's title and actual
   author. The saving tool is recorded as `knot-cli`; `--agent` can identify another
   actual saving agent. Source authorship remains separate.
4. Write the curated text, ending with `/done`. Choose themes, link related notes,
   and reuse or create entities using the ordinary organisation menu. A new entity
   needs an exact supporting passage in the curated text. Optional relationships
   cite that curated note, whose provenance retains the original evidence.
5. Review the writing, qualification, source revisions, exact quotations and proposed
   connections before saving. **Edit sources and qualification** lets you revise
   evidence choices before publication. New relationships remain Unreviewed.

KNOT computes and verifies the source hashes, Unicode offsets and line numbers.
Line ranges preserve the original line endings. Selecting the same passage twice
does not duplicate its pin. Multiple passages or retellings do not automatically
establish independent corroboration. Transcription evidence retains separate hashes
for the preserved original and its text; it does not certify the original wording.

Drafts retain their dataset, identifiers, selected passages and completed steps.
After EOF, Ctrl-C, cancellation or leaving the menu, use `knot resume` to continue.
Unfinished body input before `/done` is not retained. A later edit to a source does
not move an existing pin to its new revision. Sources are verified again before
publication, and retries reuse the same note and relationship IDs. Once published,
use `knot save` for revisions; resuming a saved draft only completes publication.

Successful saves print a JSON receipt and a graph refresh command. Run
`knot view --open` to see the updated snapshot. The existing `just curate check FILE`
and `just curate publish FILE` commands below still operate on assertion candidates.
The design and boundaries are recorded in
[ADR 0046](../design_decisions/0046-guided-source-backed-curation.md).

## Curated knowledge notes

Keep original writing as an exact source. When a conversational capture needs clearer
wording or context, save a separate curated note with a descriptive title, the actual
curator as author, and pinned source evidence. An instruction such as “add an edge”
requests an operation; preserve it as source evidence only when needed, and express
the supported knowledge or navigation intent in the curated note. Existing evidence
may already support the requested operation.

Put the readable text in `/tmp/curated-note.md` and the provenance in
`/tmp/curation-provenance.json`. The following JSON is a template: replace every
uppercase placeholder with verified source metadata and exact text before saving.
The example locators select an initial passage; update them if quoting elsewhere.

```json
{
  "method": "faithful_restatement",
  "qualification": "STATE WHAT THE SOURCE ESTABLISHES AND WHAT REMAINS UNCERTAIN",
  "sources": [
    {
      "revision": "SOURCE_REVISION_IRI",
      "sha256": "ORIGINAL_SNAPSHOT_SHA256",
      "text_sha256": "EVIDENCE_TEXT_SHA256",
      "quote": "EXACT_INITIAL_SOURCE_PASSAGE",
      "character_offset": 0,
      "start_line": 1
    }
  ]
}
```

Use `just notes show SOURCE_NOTE_IRI` to inspect a native source's revision and body
hash, and `show --revision SOURCE_REVISION_IRI --body-only` for its exact bytes.
For native text, `sha256` and `text_sha256` are the body hash; the revision IRI
contains the separate manifest hash. For imported evidence, use the verified source
record: `sha256` pins the original snapshot and `text_sha256` pins its evidence text,
which can be a transcription. Offsets count Unicode characters from zero; lines
start at one. A transcription quote does not claim to be verified original handwriting.

```sh
just notes add /tmp/curated-note.md --title 'A source-backed reflection' --author Codex --agent Codex --kind Thought --derivation /tmp/curation-provenance.json
just notes show CURATED_NOTE_IRI
just notes save CURATED_NOTE_IRI /tmp/curated-note.md --expected CURATED_REVISION_IRI --agent Codex --derivation /tmp/curation-provenance.json
just quality
```

Replace the returned note/revision placeholders before using `show` or `save`.
Use the actual author and saving agent; for example, Kiro-written curation is authored
by Kiro. `method` is `faithful_restatement` or `synthesis`. Curated notes require a
title, author, saving agent and valid derivation, but still need no kind, entity or
assertion. The original source keeps its author, identity, head and exact text.
An existing source note cannot be converted into curated knowledge in place.

Keep one coherent idea and its necessary context, without mechanically splitting
every sentence. Preserve uncertainty and distinguish observations, interpretations,
plans and reported results. Curation does not accept an assertion or make repeated
accounts independent evidence. `just quality` is read-only: integrity errors identify
broken evidence or references; subjective warnings identify work to review and do
not reject free-form writing or make identity/review decisions. The rationale and
standards are in [ADR 0027](../design_decisions/0027-source-preserving-knowledge-curation.md).

## Source-backed assertion candidates

Use `just curate` when graph enrichment is requested. It builds and validates an
explicit candidate; it does not extract or accept knowledge automatically.
Save a JSON draft with the following fields (replace placeholders with real values):

```json
{
  "id": "urn:knot:assertion:YOUR_STABLE_UUID",
  "subject": {"id": "EXISTING_OR_SOURCE_SCOPED_IRI", "label": "Identifiable subject"},
  "predicate": "urn:knot:vocab:proposed",
  "object": {"id": "PROPOSAL_IRI", "label": "Specific proposal"},
  "origin": "Explicit",
  "rationale": "The source describes a proposal; implementation is not established.",
  "agent": "urn:knot:agent:codex",
  "generated_at": "ACTUAL_ISO_8601_TIME_WITH_TIMEZONE",
  "sources": ["REPLACE_WITH_VERIFIED_SOURCE_PIN_OBJECTS"]
}
```

Construct source objects with
`knot.curating.provenance.source_pin(root, revision, exact_quote, character_offset)`; their
fields match the derivation pins above. Use the actual saving agent and retain the
draft's ID/time for retries. `origin` is `Explicit` or `Inferred`, not a review status.
For a literal object, use `{"value": "18", "label": "18 events", "datatype":
"http://www.w3.org/2001/XMLSchema#integer"}` instead of `id`; `language` may replace
`datatype`. Keep values and units faithful to their source.

```sh
just curate check /tmp/knot-candidate.json
just curate publish /tmp/knot-candidate.json
just review show ASSERTION_IRI
```

`check` returns a read-only RDF preview, warnings and leaf source hashes used to
detect overlap. Hashes are not counts of independent accounts. Inspect meaning and
qualifications before `publish`. Publication verifies sources again, preserves the
existing additions bytes and review history, and writes Active/Unreviewed candidates.
An identical retry writes nothing; changed content under the same ID fails. Correct
an existing assertion through `just review`, not by changing its candidate file.
The corresponding Python functions are `knot.curating.candidates.prepare_candidate(root, draft)`
and `publish_candidate(root, draft)`. This owner-local path does not alter MCP grants.

## Repeatable quality checks

```sh
just quality --output /tmp/knot-quality-before.json
# Capture or curate through the owning APIs.
just quality --baseline /tmp/knot-quality-before.json --output /tmp/knot-quality-after.json
```

Reports retain all errors/warnings and add stable finding IDs, categories, attention
priorities and new/resolved/persisting comparisons. Errors fail the command; warnings
do not. Rule versions distinguish detector changes from data changes. Current curated
coverage has explicit note denominators; an unlinked source note is not a defect.
Historical label and timestamp notices are informational. These diagnostics are not
an owner decision queue or a knowledge-quality score. Output must be outside the
data root and must not overwrite its baseline.

An audit reuses its entity view and verified source reader within that run, while
checking every committed note revision and derivation pin. It does not retain a
cache between runs or change source, review or access records. Large histories
still take longer; let the command finish before interpreting its report.

The [continuous curation standard](../design_decisions/0030-continuous-knowledge-curation.md)
defines what is enforced, what is advisory and what requires human judgement.
