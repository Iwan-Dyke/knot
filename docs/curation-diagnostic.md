# Diagnose focused curation opportunities

Use this owner-local prototype after measuring retrieval against frozen, source-pinned
questions. It produces review prompts from evidence delivery failures; it does not
edit notes, propose assertions, grant access or approve knowledge. It uses the existing
note, provenance and retrieval components, with no new service or model dependency.

```sh
just diagnose-curation --questions /tmp/questions.json \
  --responses /tmp/responses.json --output /tmp/curation-prompts.json
```

The question manifest uses the source judgements described in
[coverage comparison](coverage-benchmark.md). The response file is a JSON list with
exactly one `{"id": "question-id", "result": RETRIEVAL_RESPONSE}` entry per question.
Supply the complete captured retrieval response, including its sources and passages;
do not reconstruct missing provenance. For a benchmark run with `--include-context`,
extract `case.methods.hybrid.context` as `result` and retain the case ID. Checked-answer
receipts are not retrieval responses and must not be substituted here.

The selected dataset must still contain the pinned revisions and source files.
`--data-root PATH` selects an explicitly authorised local copy. This is not a scoped
MCP service; do not expose its owner-local reads to restricted clients. Reports include
private evidence and current note identifiers. Keep inputs and outputs outside the
application repository; the CLI rejects outputs inside the dataset or over its inputs.

## What the prompts mean

Only relevant labelled spans with at least one observed miss generate prompts. Each
prompt includes verified source text, path, hash, offsets, successful and unsuccessful
question IDs, related current notes, a reason curation might help, a smallest proposed
correction and an explicit human-review requirement.

| Signal | Evidence and limit |
| --- | --- |
| `generic_title` | A relevant current native note has no title or a conventional generic title such as “Notes”. This is a narrow heuristic, not a judgement of all short titles. |
| `no_covering_curated_span` | Neither a current curated body nor an inspected current direct derivation contains the entire labelled span. This does not establish that no useful description exists elsewhere. |
| `partial_qualified_context` | A current derivation overlaps, but does not contain, a qualification-labelled span. Read the complete sources and note before concluding that context is missing. |
| `repeated_failure` | More than one frozen question misses the same exact source span. Rewordings are not independent evidence. |
| `wording_sensitivity` | Some questions deliver that span and others do not. This motivates a description review; it does not prove exact-match dependence or equal question intent. |
| `existing_description_review` | A covering derived note exists but the labelled context was not delivered. Inspect its title, context and retrieval omissions before creating anything else. |

The diagnostic deliberately does not score graph density, note length or metadata
quantity. It cannot judge the semantic adequacy of a paraphrase, identify every generic
title, infer identity equivalence or prove that curation will help. Imported source
labels are covered, but automatic title checks concern native notes; entity display
names and aliases require the existing source-backed naming and identity workflows.

## Review and test the smallest correction

1. Freeze questions, source labels, original responses, input hashes, code revision,
   output/source budgets and development versus held-out membership. Do not overwrite
   earlier measurements when changing the scorer.
2. Inspect the exact source and surrounding qualifications. Read any current derived
   note before proposing another. Distinguish missing discoverability from a candidate
   excluded by a response budget. A valid untitled capture need not be “fixed”.
3. Prefer a faithful descriptive title or a small correction to an existing derived
   note when that suffices. A separate coherent summary is appropriate only when it
   serves an independently useful purpose and preserves sufficient exact evidence.
   Keep attribution, uncertainty, limitations and the distinction between plans and
   outcomes. Use aliases only after establishing the same referent.
4. Test on a physical isolated copy using `read_note`, `save_note` with the observed
   revision, `source_pin` and `create_note`. Preserve original source heads and bytes.
   Follow [curation](curation.md) and ADRs 0027–0030. A derived note is not an approved
   answer; identity changes and assertion acceptance remain separate review operations.
5. Rerun identical questions and budgets with unchanged retrieval code. Freeze held-out
   wording before testing; do not revise proposals in response to held-out results.
   A wording holdout on familiar sources is weaker than independent source validation.
6. Compare discovered and delivered evidence, complete labelled cases, source-span and
   qualification recall, exact citation checks, response size, latency and regressions.
   Record sample counts and timing conditions. Report old and corrected accounting
   separately from actual retrieval gains. Inspect both lost spans and lost candidates.
7. Retain the existing behaviour if gains do not survive these checks. Any promotion
   into authoritative personal knowledge requires the corresponding authorisation.

Keep STRIDE routing outcomes separate: an unsupported checked question can still
retrieve complete labelled evidence. A label match establishes neither semantic truth
nor approval. If remaining misses concern oversized or displaced complete packages,
record those constraints before proposing more curation or changing selection.
