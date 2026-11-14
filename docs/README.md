# KNOT documentation

Use the [README quick start](../README.md#try-a-note-in-a-separate-folder) to try
KNOT without a pre-existing dataset. These guides document current behaviour;
unimplemented release work is listed separately in [release preparation](release.md).

## Using KNOT

| Guide | Covers |
| --- | --- |
| [Notes](notes.md) | Capture, revisions, guided organisation and agent handoffs |
| [Curation](curation.md) | Guided manual curation, separate derived notes, source pins, assertion candidates and quality checks |
| [Retrieval](retrieval.md) | Lookup, graph/text/hybrid retrieval, discovery, budgets and omissions |
| [Checked answers](checked-answers.md) | Deterministic routing, approved-artifact selection and revalidation |
| [STRIDE status](stride-status.md) | Acceptance matrix, implemented boundaries and remaining work |
| [Evaluation](evaluation.md) | Deterministic coverage via CLI and scoped MCP, checked question templates, requests, receipts and limits |
| [Decision explanations](explanations.md) | Preview, explicitly review, withdraw and reuse exact source-backed wording |
| [Viewer](viewer.md) | Graph/Library/Idle, optional local note editing, synthetic demo, visual themes and the supported legacy viewer |
| [Reviews](reviews.md) | Assertion acceptance/correction, history and identity review |
| [Organisation](organisation.md) | Add/import knowledge themes, type suggestions and separate theme review |
| [Datasets](datasets.md) | Folder selection, authoritative files, backups, import and Git limitations |
| [MCP](mcp.md) | Local client setup, scoped reads and optional owner authoring |

## Reference and development

- [Python API](reference/python-api.md): note persistence and retrieval contracts.
- [Catalogues](reference/catalogues.md): preferred labels and evidence-account qualifications.
- [Architecture](architecture.md): current component ownership and data flow.
- [Library performance](library-performance.md): synthetic profiles, browser checks and recorded measurement limits.
- [Coverage comparison](coverage-benchmark.md): frozen source-backed questions, retrieval versus evaluation, answer coverage and limitations.
- [Viewer licences](viewer-licences.md): exact embedded assets, complete notices and upgrade checks.
- [Contributing](../CONTRIBUTING.md): setup, checks and change expectations.
- [Architecture decision records](../design_decisions/README.md): rationale, alternatives and decision history.
- [Release preparation](release.md): remaining work before a public release.
- [Experiment outcomes](../design_decisions/0042-retire-experiments-and-export-tool-only.md): retained improvements, rejected approaches and cleanup decisions.

## Planned architecture

[Reviewed ontology evolution](../design_decisions/0051-reviewed-ontology-evolution.md)
remains proposed. [STRIDE-inspired evaluation](../design_decisions/0052-bounded-deterministic-evaluation.md)
has a [coverage pilot with checked questions and receipt revalidation](evaluation.md)
and [approved decision explanations](explanations.md), with [checked routing](checked-answers.md)
through CLI and scoped MCP. The [status matrix](stride-status.md) records remaining work,
including historical replay and broader rules. These records draw on AWS's Context
Ontology Accelerator and UnlikelyAI's STRIDE; they add no vendor dependency.

## Reading examples

Commands run from the repository root unless stated otherwise. `just` recipes use
the selected dataset, while the quick start uses an explicit temporary folder.
Use `./knot` in an uninstalled checkout; `knot` is available after installing the
launcher or package. The command families are intentionally distinct:

| Task | Command |
| --- | --- |
| Capture, revise or resume notes | `knot add`, `knot save`, `knot resume`; `just notes` exposes the same CLI |
| Write a curated note interactively | `knot curate` |
| Validate/publish an assertion candidate JSON file | `just curate check FILE`, `just curate publish FILE` |
| Open Graph and Library together | `knot view` or `just visualise`; add `example` for synthetic data |
| Create/edit ordinary notes in Library | `knot serve`; add `--no-open` to print the local session URL |
| Export that interface without opening it | `knot browse` or `just browse` |
| Select colours/fonts | `knot theme list`, `knot theme use NAME` |
| Define knowledge topics | `knot themes list`, `knot themes add ...`, `knot themes import FILE` |
| Rebuild organisation or summarise memberships | `just organise`, `just themes` |
| Retrieve evidence, review claims or check integrity | `just retrieval ...`, `just review ...`, `just quality` |
| Evaluate reviewed framework mappings | `knot evaluate REQUEST.json` or `just evaluate REQUEST.json` |
| Select data or synchronise its repository | `knot dataset ...`, `knot push`, `knot refresh` |

`knot` is not a wrapper for every `just` recipe: for example, use `just retrieval`
or the Python module in its recipe, not `knot retrieval`. See each guide for flags
and where `--data-root` goes; subcommand parsers differ.

`NOTE_IRI`, `ENTITY_IRI`, `ASSERTION_IRI`, revision IDs and hashes are placeholders:
replace them with values returned by your dataset. Do not fabricate provenance.

Examples and theme names illustrate the workflow; they are not preloaded user data.
The [dataset guide](datasets.md#select-a-dataset) explains the current differences
between command arguments. Notes, source evidence and accepted claims have different
meanings; reading or displaying a note never accepts its claims.
