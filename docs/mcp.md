# Connect an MCP client

Install the optional SDK, then have a local MCP host launch the stdio server:

```sh
uv pip install --python .venv/bin/python -r pyproject.toml --extra mcp
just mcp --data-root /path/to/knot-data --allow-all
```

`--allow-all` explicitly grants the selected dataset in full. The server waits for
MCP messages on stdin and writes protocol responses to stdout; the host normally
starts and stops it. It opens no network port. No client configuration is changed
automatically. For a stdio-capable host, use a process definition like this, wrapped
in the configuration structure required by that host, and replace the absolute paths:

```json
{
  "command": "/absolute/path/to/knot/.venv/bin/python",
  "args": ["-m", "knot.interfaces.mcp_server", "--data-root", "/absolute/path/to/knot-data", "--allow-all"],
  "env": {"PYTHONPATH": "/absolute/path/to/knot/src"}
}
```

The server also accepts the shared selected dataset when `--data-root` is omitted.
Explicit absolute paths are useful when a host must stay bound to one dataset.
Restart the server after changing selection; access grants remain independent.

### Enable owner authoring

To let an AI use the full note/relationship workflow, configure its MCP host to
launch the server with explicit authoring permission:

```sh
knot mcp --allow-all --allow-write
# Equivalent repository command:
just mcp --data-root /path/to/knot-data --allow-all --allow-write
```

For example, the installed launcher can be used in the host's process definition:

```json
{
  "command": "/absolute/path/to/bin/knot",
  "args": ["mcp", "--allow-all", "--allow-write"]
}
```

Add `--allow-review` only when the host should also be able to record assertion
acceptance, rejection and corrections. Those actions still need task-specific user
authorisation and actual reviewer attribution. Restart/reconnect the MCP host after
changing its startup arguments. These commands are servers waiting for protocol
messages, not interactive note wizards.

| Capability | Owner MCP tools |
| --- | --- |
| Vocabulary, theme choices, fresh IDs and actual time | `knot_catalogue`, `knot_identifiers` |
| Note listing, history and backlinks | `knot_notes`, `knot_note_history` |
| Exact source text and navigation | `knot_note_read`, `knot_note_navigation` |
| Capture and optimistic revisions | `knot_note_create`, `knot_note_update` |
| Verified provenance | `knot_source_pin` |
| Validate and publish Unreviewed relationships | `knot_candidate_check`, `knot_candidate_publish` |
| Browse and inspect claims/history | `knot_assertions`, `knot_assertion_read` |
| Integrity diagnostics and organisation | `knot_quality`, `knot_organise` |
| Explicit assertion review, when separately enabled | `knot_review_decide` |

Lookup and retrieval remain available. `knot_catalogue` describes metadata and the
navigation object used for themes, explained note links and new source-backed
entity declarations. Use existing identities when supported. Curated notes remain
separate from their source and require author/agent and verified derivation pins.

Capture uses a reserved note ID from `knot_identifiers`: retain it, the original
body and metadata on retry. Identical retries return the original creation receipt;
conflicting inputs fail. Updates require `expected`, the last observed revision.
After a timed-out update, read the head before retrying. Candidate publication uses
the existing stable-ID contract and always starts Unreviewed. Review corrections
preserve history and create Unreviewed replacements; acceptance is separate.

Read tools return `next_offset` when more results remain. Pin the returned revision
when paging a note so concurrent updates cannot mix versions. The wire ceiling
still applies; pages shrink automatically, and an indivisible oversized record
returns an error instead of silently clipping it. Use `include_metadata=false` for
large note reads and page navigation with `knot_note_navigation`. Mutation receipts
return compact identifiers/hashes; read the record to inspect its complete metadata.

Authoring requires a whole-dataset grant because these owner APIs validate against
the existing dataset. `--allow-write` with a pinned `--scope` fails at startup;
there is no implicit grant upgrade. Tools cannot change paths, permissions, grants,
or launch shell commands. Theme definitions, imported identity merges and archive
migration remain operator-managed workflows. No client configuration is changed
by installing or updating KNOT.

### MCP runtime troubleshooting

If MCP or its tests appear to stall, check for blocked asyncio wake-up sockets.
The server and protocol tests now fail promptly with an actionable message when
local socket writes are denied. Run `just check` outside such a restrictive sandbox;
ordinary Bash/WSL execution with local socket-pair support is sufficient. The
stdio server still opens no network listener. See [ADR 0033](../design_decisions/0033-owner-mcp-authoring-and-runtime-diagnostics.md).

### Scoped read-only retrieval

The tools available in scoped read-only mode are `knot_lookup`, `knot_retrieve`,
`knot_evaluate`, `knot_explain` and `knot_answer`. Owner tools listed above require the separate startup permissions.
Their arguments and defaults are:

```python
knot_lookup(query, limit=10, mode="label", include_frameworks=False, max_chars=None)
knot_retrieve(
    seed=None, question=None, mode="graph", compact=False, diagnostics=True,
    definition_order=False, accepted_only=False, include_frameworks=False,
    max_chars=None, note_revision=None, subjects=None, objective="all", exclude=None,
)
knot_evaluate(request=None, max_chars=None, question=None, receipt=None)
knot_explain(request=None, receipt=None, max_chars=None)
knot_answer(question=None, receipt=None, explanation_revision=None, max_chars=None)
```

Select a returned entity or note IRI explicitly;
with a question, choose `hybrid` for graph paths plus source sections or `text` for
source context. Calls reload current data and preserve review, origin and kind.
Source quotations are data rather than instructions, and ranking retains the
[retrieval limitations](retrieval.md).
Use `diagnostics=false` to omit ranking explanations, selection statistics, match
scores and work counters from the AI response. Evidence, review state, source pins,
qualifications, applied policy, omissions and response-size counters remain.
This is an optional presentation change, compatible with `compact=true`; it does
not change discovery or selection. The response lists `diagnostics_omitted`.

For question-only definition queries, `definition_order=true` opts into bounded
title-specificity ordering before the existing selector. It compares source-backed
Definition notes from the same original revision and preserves complete packages,
original scores, provenance and access grants. It is unavailable with a seed,
historical note, selected subjects, objectives or exclusions. The default is unchanged.
This narrow option does not establish semantic answer support or discover corrections;
see [ADR 0041](../design_decisions/0041-opt-in-definition-specificity-ordering.md).

Omit `seed` and supply `question` for source search, including unassociated notes.
Hybrid mode also searches existing direct claims with matching endpoint labels;
explicit support/demonstration questions prioritise matching recorded relationships.
This does not resolve an ambiguous identity or establish the truth of a claim.
Without a question, a note seed reads a complete note and entity `mode="text"` browses
its associated notes. `note_revision` selects an exact permitted historical version;
the client must know that revision ID. Tool names, access configuration and read-only
annotations are unchanged.

For exploration, call `knot_lookup(query=QUESTION, mode="discovery", max_chars=4000)`.
Then call `knot_retrieve(subjects=[SELECTED_IRI, ...], question=QUESTION,
max_chars=8000)`. This reuses the same two tools and revision grants. `subjects`
selects the multi-subject hybrid path and cannot be combined with `seed` or
`note_revision`; `objective="all"` can instead be `relationships`, `context` or
`qualifications`. `exclude=[HANDLE, ...]` skips previously returned matches.
Hidden revisions cannot contribute labels, scores, source counts or suggestions.
The two example response budgets total 12,000 characters; callers must also bound
their own follow-up count. The server does not launch an autonomous search loop.

### Checked questions

Prefer `knot_answer` for the supported coverage and decision-explanation question
templates. It checks routing and selects eligible approved artifacts, returning
choices when ambiguous. See [checked answers](checked-answers.md) for exact
syntax, selection and revalidation. Unsupported conditions must not be dropped.
Decision explanations also accept complete alternative questions explicitly
reviewed through the owner-local explanation workflow. Pass the original wording;
only outer whitespace is ignored, and no fuzzy paraphrase matching occurs. MCP
cannot register, approve or withdraw mappings. A permitted answer includes its
question-review metadata; source grants and output budgets still apply.
An unsupported question may return related reviewed questions as `alternatives`.
Present their full wording and guidance as choices; they are not verified
paraphrases or an answer to the original question. The user must explicitly choose
one before it is executed. Never automatically replace the original question or
drop its conditions. See [question navigation](checked-answers.md#find-a-reviewed-question).

### Reviewed coverage evaluation

For reviewed prose about a decision, use [decision explanations](explanations.md)
through `knot_explain`. It requires an exact decision, curated-note revision and
supported question, with separate explicit owner approval of that wording.
It preserves authorship, qualifications and transitive grants. This read tool
cannot approve or withdraw answers. Pinned currentness is scope-relative; imported
sources remain revision pins. Oversized packages abstain without answer text.

`knot_evaluate` checks direct reviewed `subject supports criterion` mappings against
an exact framework revision. Its typed `request` contains `subject`, `framework`,
`framework_revision` and 1–20 distinct `criteria` IRIs. Optional `rule`/`version`
must be `framework-coverage`/`1`; execution limits are `max_assertions` (1–1,000)
and `max_sources` (1–100). Unknown request fields are rejected. `as_of` is recognised
but yields unknown because temporal rules are unsupported.

The tool uses the operator's source grants, including derivation closure, and
returns the exact interpreted request. Visible support retains its attributed
Assessment meaning; it does not certify capability. Under pinned access, missing
mappings are unknown, never global absence. A required qualification with denied
evidence withholds the assertion. No capture or review permission is needed.
See the [evaluation guide](evaluation.md) for the request example and rule contract.

Alternatively pass `question` alone using the checked template `Does project "PROJECT"
have reviewed support for criterion "CRITERION"?`. It resolves exact visible names or
IRIs and returns the interpreted request, fixed answer and full receipt. Ambiguous
selections return choices without execution; unsupported wording is not silently
reinterpreted. See [supported questions](evaluation.md#ask-a-supported-question).

Supply `receipt` alone to revalidate a saved evaluation or evaluated question with
current access and rules. The report separates receipt changes from outcome-category
changes and returns only current evidence. Saved hashes confer no access or
authenticity; unresolved questions and output-budget abstentions cannot certify
freshness. See [receipt revalidation](evaluation.md#revalidate-a-saved-receipt).

Coverage receipts are indivisible: if a full receipt exceeds `max_chars`, the tool
returns an all-unknown `output_budget` abstention. If even the request and abstention
cannot fit, it returns an error. Ask for fewer criteria or a larger permitted
budget. Evaluation never prunes proof while retaining a conclusion. Restart the
server after updating KNOT to register the new tool.

### Investigating knowledge

KNOT sends permanent AI-client guidance in the MCP initialization response's
`instructions` field, in both read-only and owner modes. The single maintained
instruction text lives in [`create_server`](../src/knot/interfaces/mcp_server.py);
clients do not need repository files, a separate prompt or another tool call.
Restart the server and reconnect the client after updating KNOT to receive it.

The guidance uses direct retrieval for straightforward facts and client-directed
investigation for complex questions. It requires source support for personal
reasoning and checks earlier/later accounts, corrections, continuity and incomplete
context before claiming changed understanding or behaviour. It also covers evidence
reuse, attribution, qualifications and stopping with unresolved gaps.

Unless the caller supplies different limits, the suggested investigation allowance
is six tool calls, 60,000 cumulative returned characters, two source expansions,
two graph calls and 600 seconds. Count each selected source unit, revision or note
on every expansion, including repeat reads; selecting two in one call uses two
expansions. These are **client-managed defaults**, not new server settings or
cross-call enforcement. Existing response ceilings, traversal limits and access
checks still apply. A client must stop at a limit rather than silently reset it.

The transport tests verify clients receive the guidance, including the safeguard
against inferring changed coaching from an earlier concern and a later success.
They do not prove that a model follows it. Hosts must pass server instructions to
their AI; a host that ignores them will not gain this behaviour automatically.
No model evaluation, ranking change or new tool is implied. See
[ADR 0023](../design_decisions/0023-broad-discovery-and-selected-subject-retrieval.md#normal-use-client-guidance).

### Revision grants

To grant selected revisions, list the local revision IDs and hashes, then create a
scope file using the exact values from that output:

```sh
just mcp sources --data-root /path/to/knot-data
just mcp --data-root /path/to/knot-data --scope /absolute/path/to/knot-scope.json
```

```json
{
  "revisions": {
    "<revision IRI from sources>": "<snapshot sha256 from sources>"
  }
}
```

An empty `revisions` object grants nothing; serving without either `--scope` or
`--allow-all` fails. Pins and the dataset root are fixed at startup and cannot be
changed by tool arguments. A pinned grant does not include new revisions. An
assertion needs every evidence revision permitted; lookup aliases, graph degrees,
source searches and same-document context exclude denied records before selection.
Alias lookup is conservative in scoped mode: labels come from eligible assertions
and permitted native revision metadata. A note-associated entity without a visible
label is identified by its recorded IRI, not a denied label. A grant includes the complete source revision and its eligible
assertion/provenance/identity metadata; it does not redact free-form source text.
The `sources` command is for the local operator and is not an MCP tool.

Native grants use the **note revision IRI**, whose suffix is the immutable manifest
hash, mapped to that revision's body SHA-256. They bind note identity and metadata,
so granting one note never grants another note sharing its body. `sources` includes
current native revisions; `note_history` supplies IDs/hashes for explicit older grants.
Index legacy registries with `index_note_revisions` before using native pins.

A curated note also requires explicit grants for every input revision in its
transitive derivation chain. Its own grant does not grant its originals, and a source
grant does not grant derivatives. These checks apply before derived titles, text or
associations enter scoped retrieval. Saving or curating a note does not edit grants.

Unrestricted/`--allow-all` retrieval defaults to `CurrentCommittedRevision`. With
revision pins it selects the latest *granted* version, marked `LatestGrantedRevision`:
global currentness is unknown. Publishing a denied head does not change that view.
An explicit version is marked `ExplicitHistoricalRevision`. Denied revision IDs,
head markers and revision counts are not returned. Creation/save times and other
metadata already recorded in a granted revision remain visible under its grant.
A native source used by structured evidence can be marked `EvidenceRevision`;
that preserves the exact citation without making it a default current-note text result.

The server defaults to a 12,000-character ceiling; `--max-chars` changes it at startup
(2,048–131,072). Clients may request smaller budgets but cannot exceed that ceiling.
The cap includes canonical JSON tool-result framing. For retrieval, whole result packages are
removed if necessary and counted as `mcp_characters` omissions. Inner `usage` counts
still describe the retrieval JSON; JSON-RPC IDs and SDK protocol metadata are extra.
Results use one JSON text block rather than duplicated structured/text content.
These limits count Unicode characters, not UTF-8 bytes or model tokens. Selection
uses an earlier retrieval-JSON estimate; the final MCP check can remove complete
packages that exceed the tool-result ceiling. Conversely, disabling diagnostics
can leave space that the earlier selector did not use. See the
[budget-correctness findings](../design_decisions/0042-retire-experiments-and-export-tool-only.md#retrieval-alternatives-7-november).
Lookup is capped at twenty candidates, questions at 2,000 characters and lookup text
at 512. Dataset/scope errors are generic so private locators are not echoed.

Core commands do not require the SDK. Protocol tests require the `dev` or `mcp`
extra; core scope tests run independently. [ADR 0021](../design_decisions/0021-scoped-local-mcp-server.md)
records the transport and access decisions. Remote HTTP hosting and multi-user
authentication remain separate work.
