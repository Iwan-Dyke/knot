# Retrieval measurement and focused curation evaluation

Date: 2026-11-14. Status: completed development experiment; no authoritative
knowledge changes or retrieval algorithm changes promoted.

The shared benchmark missed exact original quotations embedded in curated-note
provenance. Correcting that accounting explains much of the apparent retrieval
failure. Faithful titles and focused curation provide additional, smaller gains.
The evidence does not justify another retrieval architecture or selection algorithm.

## Accounting correction on unchanged historical responses

The historical audit retained five isolated datasets, pinned questions, complete
responses and candidate packages. Their saved artifact hashes were checked before
rescoring. All original reports remain intact. The previous scorer was retained
and run alongside the corrected scorer on the same saved responses and labels.

The main set has 17 questions, of which 16 have relevant labels: 23 source spans,
all marked as qualification-bearing. The empty-label negative control is excluded
from completeness denominators and does not prove global absence.

| Historical arm | Old delivered spans | Corrected delivered spans | Old complete cases | Corrected complete cases |
| --- | --- | --- | --- | --- |
| Baseline | 9/23 | 17/23 | 5/16 | 11/16 |
| Two title changes | 9/23 | 18/23 | 5/16 | 12/16 |
| Two graph relationships | 9/23 | 17/23 | 5/16 | 11/16 |
| Titles and graph relationships | 9/23 | 18/23 | 5/16 | 12/16 |
| Two focused notes | 9/23 | 17/23 | 5/16 | 11/16 |

Baseline source-span and qualification recall therefore change from 39.1% to 73.9%
without changing a single retrieval response. The audit's supplementary embedded-pin
analysis had already found the corrected totals; the shared benchmark now recognises
them itself. Citation checks rise from 73 top-level occurrences to 114 occurrences
including embedded pins, all valid. This change of denominator is not a citation gain.

On a separately labelled documentary subset of three existing questions, the baseline
delivers 1/4 spans and completes 1/3 cases. Focused notes deliver 4/4 and complete 3/3.
The old scorer reports 1/4 and 1/3 for both arms. These documentary labels concern
original documentation; they must not replace the original main-set labels, which
include the broader existing synthesis. A new focused restatement is not equivalent
to delivering that old synthesis's exact bytes.

The correction validates immutable source paths, hashes, quotations and locators;
matches serialized derivations to their recorded revisions; deduplicates span credit;
and separates curated text from original quotations. Transitive validation and receipt
normalisation cannot create credit for evidence absent from the response. See
[accounting version 2](coverage-benchmark.md#evidence-accounting-version-2).

## Fresh controlled curation comparison

Two physical copies of the frozen baseline were used. The experimental copy received
the two previously frozen title changes and two previously frozen focused notes,
through the existing note APIs. Titles preserve body bytes and derivation. The new
notes preserve attribution, exact source pins and limitations; neither is approved
as an answer. No entities, graph relationships, aliases, reviews or grants were added.

The retrieval engine, question texts and source/work limits were identical between
arms. Output limits remained 24,000 characters, four passages and ten assertions.
The main development set and separately reported documentary labels were retained.
Six new wordings were frozen before either arm ran; the proposals were not tuned
after seeing those results. Their source families were already familiar: this is a
wording holdout, not independent source or human-reviewed generalisation evidence.

### Main development set

| Measure | Baseline | Curated copy | Difference |
| --- | --- | --- | --- |
| Relevant evidence discovered | 21/23 spans | 23/23 spans | +2 spans |
| Complete evidence delivered | 11/16 cases | 12/16 cases | +1 case |
| Source-span recall | 17/23 (73.9%) | 18/23 (78.3%) | +4.4 percentage points |
| Qualification recall | 73.9% | 78.3% | +4.4 percentage points |
| Citation correctness | 114/114 | 114/114 | No invalid citations |
| Mean response size | 19,371 characters | 19,181 characters | −190 characters |
| Median instrumented retrieval latency | 3,071 ms | 3,066 ms | −5 ms |
| Lost labelled spans / discovered candidates | — | 0 / 0 | No measured regression |

### Documentary subset, reported separately

These three questions also occur in the main set; do not add their counts to it.

| Measure | Baseline | Curated copy | Difference |
| --- | --- | --- | --- |
| Relevant evidence discovered | 3/4 spans | 4/4 spans | +1 span |
| Complete evidence delivered | 1/3 cases | 3/3 cases | +2 cases |
| Source-span recall | 25% | 100% | +75 percentage points |
| Qualification recall | 25% | 100% | +75 percentage points |
| Citation correctness | 22/22 | 21/21 | No invalid citations |
| Mean response size | 22,281 characters | 21,189 characters | −1,092 characters |
| Median instrumented retrieval latency | 3,049 ms | 3,095 ms | +46 ms |
| Lost labelled spans / discovered candidates | — | 0 / 0 | No measured regression |

### Held-out wordings

| Measure | Baseline | Curated copy | Difference |
| --- | --- | --- | --- |
| Relevant evidence discovered | 9/9 spans | 9/9 spans | No change |
| Complete evidence delivered | 4/6 cases | 5/6 cases | +1 case |
| Source-span recall | 7/9 (77.8%) | 8/9 (88.9%) | +11.1 percentage points |
| Qualification recall | 77.8% | 88.9% | +11.1 percentage points |
| Citation correctness | 30/30 | 32/32 | No invalid citations |
| Mean response size | 21,538 characters | 21,703 characters | +166 characters |
| Median instrumented retrieval latency | 3,180 ms | 3,105 ms | −75 ms |
| Lost labelled spans / discovered candidates | — | 0 / 0 | No measured regression |

Latency uses one interleaved paired sample per question, alternating arm order,
including candidate capture and fresh API preparation. OS caches are uncontrolled;
these differences do not establish a performance improvement. All responses fit the
unchanged limit. The negative control remains empty. Completeness means completeness
against the frozen labels, not every relevant fact in the dataset.
All six held-out responses were rerun for both arms: all 12 repeated wire responses
were identical. Repeat timings were excluded from the paired comparison above.

## Diagnostic and remaining constraints

The [read-only diagnostic prototype](curation-diagnostic.md) groups verified misses by
exact source span, checks current titles and direct derivations, and identifies repeated
misses and wording sensitivity. It emits six source-span prompts on the baseline and
five after curation. These counts are workload observations, not quality scores.
Every recommendation includes its source evidence, observed deficiency, retrieval
rationale, smallest proposed correction and need for human review.

Remaining misses in the curated copy are attributable to specific constraints:

- Three original main-set labels require complete packages of 27,624–34,347 characters,
  beyond the 24,000-character limit. Focused documentation can answer their information
  need without delivering the old broad synthesis, but must not receive that synthesis's
  exact-span credit. Neither provenance truncation nor relabelling is warranted.
- A complementary two-span source has a 7,027-character package that fits individually
  but is displaced by other selected content. The returned response is 21,140 characters;
  its seven checked spans are distinct. Unjudged material is not automatically irrelevant.
- The remaining held-out validation question has a 6,900-character candidate, but a
  23,037-character response selects other evidence. The two selected spans are distinct.
  Better titles improved a development wording without fixing this broader selection
  case. Do not claim a universal title-based solution.

The two fitting-package failures have no duplicate exact spans in their delivered
citations, and selection reports zero redundant packages. Semantic repetition may
still exist; this experiment does not establish it as the cause. The evidence supports
a bounded future investigation of complementary selection if these failures matter
in use, not immediate implementation of another ranking scheme.

STRIDE checked-answer routing remains separate. The original eight unsupported
questions are outside supported contracts even when labelled evidence is complete.
This work does not turn retrieval results into approved explanations or checked answers.

## Integrity, reproduction and recommendation

The experiment retained its protocol, label and proposal hashes, historical and
corrected metrics, captured responses, package-size diagnostics, receipts and scripts
outside the application checkout. Historical artifacts were not overwritten. The
authoritative dataset and baseline copy remained byte-identical. In the experimental
copy, only the note registry changed among pre-existing files; new immutable manifests
and bodies were added through the note APIs. Source history, graphs, reviews, approvals
and grants were preserved. The retrieval implementation hashes remained unchanged.

`just check` passed Ruff lint, formatting and all 759 regression tests. The added
tests cover delivery representations, duplicated and contradictory labels, partial
qualifications, tampered hashes/paths/locators/provenance, repeated quotations,
unreturned ancestors, missing source grants, receipt normalisation, and deterministic
read-only diagnostic recommendations. Both experimental datasets have zero integrity
errors. Quality warnings changed from 847 to 849: the two new `shared_source_bytes`
notices concern the intentional title-only revisions sharing their original bodies.
All 847 earlier warnings persist. Those revisions are not independent corroboration;
no warning was silently cleared or historical source rewritten.

Reproduce with the frozen private artifacts where authorised; their questions and
source identifiers are intentionally absent from distributable documentation. For a
new dataset, follow the diagnostic's freeze/copy/review/evaluate workflow and retain
separate development and held-out sets. Never silently reuse altered labels as the
same measurement.

Retain the benchmark correction and diagnostic prototype. The combined curation
proposal demonstrates a bounded benefit and is suitable for an owner review before
any authoritative application. No personal knowledge has been changed by this work.
Keep the current retrieval architecture. Broader claims require independently reviewed
questions and sources; remaining package-budget tradeoffs do not justify added
complexity by themselves.
