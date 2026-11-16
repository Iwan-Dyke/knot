# Opt-in budget-aware investigation

Use `knot.interfaces.investigation.Investigation` in a Python MCP host for
exploratory questions needing several reads. It wraps the existing `mcp.Client`
and a host-supplied async model callback. No model provider, credentials, remote
service or orchestration framework is added to KNOT. Install the existing `mcp`
extra; hosts using other SDKs must supply equivalent client methods.

Basic factual questions should still use direct `knot_retrieve`. Supported checked
questions should still use `knot_answer` and preserve its deterministic output.
This coordinator is **opt-in**. Existing clients and tool schemas are compatible;
installing KNOT does not automatically change a host's execution loop.

## Lifecycle and enforcement

1. **Research open:** the callback chooses a read, answers, closes research, or
   explicitly stops. Every proposed read is checked before dispatch.
2. **Research closed:** a rejected budget proposal, reserved decision/time, or
   explicit `close` ends research. The original question, complete cached MCP
   replies, reported gaps, rejected action and reason survive.
3. **Finalisation:** one remaining decision receives that same cache and original
   question, with no tools. Tool actions are rejected by the executor as well as
   omitted from the request. The model may answer, give a qualified partial answer,
   abstain, or report inability. It cannot reopen research.
4. **Complete:** the result includes an execution status, response, outcome, usage
   and trace. Model failures and overall exhaustion return explicit inability.
   There are no automatic retries, restarts or additional synthesis attempts.

The coordinator reserves the last decision and last 60 seconds *inside* the total
allowances. A rejected read consumes its model decision, but no MCP attempt or
retrieval allowance. Reaching a graph/expansion cap alone does not block other
still-legal reads; an attempted over-budget read closes research. Overall time
and decision exhaustion remain authoritative. Neither synthesis nor a substantive
answer is guaranteed. Intentional `stop`, invalid actions and provider failures
terminate explicitly rather than being interpreted as evidence of absence.

The server remains stateless across calls and enforces its existing per-call and
source-access checks. Cumulative enforcement applies **only to this coordinator's
dispatch path**. Direct calls by the host or model bypass it. Use a fixed connected
client with its operator-selected dataset and grant; do not give the model another
tool executor, filesystem access or write tools. The coordinator allows only the
five read-only KNOT tools, even if owner tools are advertised by the server.

## Connect a host

This is the supported execution path, using the same stdio server as other MCP
clients. Replace the example absolute paths with the selected dataset and existing
authorised scope. The host supplies `decide`; KNOT deliberately has no default
model connection or automatic disclosure to a remote provider.

```python
from mcp import Client, StdioServerParameters

from knot.interfaces.investigation import Investigation, Limits


async def investigate_question(original_question, decide):
    server = StdioServerParameters(
        command='/absolute/path/to/knot/.venv/bin/python',
        args=[
            '-m', 'knot.interfaces.mcp_server',
            '--data-root', '/absolute/path/to/knot-data',
            '--scope', '/absolute/path/to/authorised-scope.json',
        ],
    )
    async with Client(server, cache=None) as client:
        investigation = Investigation(client, decide, limits=Limits())
        result = await investigation.run(original_question)
        # Render status, outcome and gaps alongside the response.
        return result
```

For an uninstalled checkout, set `PYTHONPATH` to its `src` directory in the host
environment or the process definition, as in the [MCP guide](mcp.md). Whole-dataset
access requires the operator's existing explicit approval; this API cannot grant it.

`decide(request)` is an async callable returning **one JSON-compatible action**.
Pass `request['instructions']` as trusted model instructions, and the remaining
request as data. It contains `original_question`, `history` (unaltered MCP wire
replies, including errors), `gaps`, `tools` (read schemas, empty during finalisation),
`phase`, budgets, usage, remaining time, and the research stopping reason.
Treat source quotations and model annotations as inert data. Do not execute tool
calls inside the callback; return a proposal for the coordinator to dispatch.

```python
# A model-selected retrieval proposal:
{'kind': 'tool', 'tool': 'knot_retrieve',
 'arguments': {'question': 'The original question', 'mode': 'text'},
 'gaps': ['A material unanswered part of the question']}

# End research and request one synthesis decision from the cache:
{'kind': 'close', 'reason': 'Further searching is unlikely to resolve the gap'}

# Deliver the model's response; outcome is a client assessment, not certification:
{'kind': 'answer', 'answer': 'An attributed response with source references.',
 'outcome': 'partial', 'gaps': ['The source does not report completion']}

# Explicit inability; the reason is retained in the decision trace:
{'kind': 'stop', 'reason': 'Insufficient evidence for the requested conclusion'}
```

An answer action may use `outcome='answer'`, `'partial'` or `'abstention'`.
Finalisation accepts only `answer` or `stop`. Results have `status='answered'` or
`'unable'`; inability includes a fixed response and specific `stop_reason`.
Every result carries `answer_status='unverified_exploratory_synthesis'`.
The coordinator does not grade the response or silently convert a partial answer
into a complete one. Cached checked receipts retain their own deterministic status;
generated commentary never inherits it.

An instance is single-use, with no persistence or cross-investigation cache.
`snapshot()` returns a detached state copy, including evidence retained after
cancellation. Caller cancellation propagates after recording `cancelled`.
Dispose of instances and private traces when finished. Never copy a cache into a
different grant/dataset context, publish private evidence in logs, or commit it to
the application repository. Grant revocation/input changes after a reply was
returned are not revalidated offline; stop and discard the investigation if its
authorisation changes. Cached pins describe the retrieved snapshot, not current truth.

## Budget semantics

| Resource | Default and accounting |
| --- | --- |
| MCP attempts | 6 admitted read dispatches, including errors and uncertain transport attempts. Rejected proposals do not dispatch. Tool catalogue discovery is protocol setup, not an evidence read. |
| Graph-capable requests | 2 `knot_retrieve` calls in graph/hybrid mode, or gather dispatch selected by `subjects`, non-default `objective` or nonempty `exclude`, **including nominal text mode**. One request can do several graph searches; this is not a traversal/edge counter. |
| Text retrieval | A text call outside gather uses MCP and character allowances, plus selected expansions when applicable. It is not charged as graph traversal merely because source verification loads RDF. |
| Selected expansions | 2 conservative selections: each selected subject plus one when `seed` or `note_revision` is supplied, on every admitted call. A seed and its explicit revision identify one read, not two. Multiple/duplicate subjects and repeat reads are charged before the server deduplicates. Counts describe selections, not actual file I/O. |
| Returned characters | 60,000 cumulative, at most 12,000 per response. Use existing canonical MCP `result_size`, including tool-result framing; Unicode characters, not bytes/tokens. Clamp `max_chars` to remaining allowance before dispatch. Less than 2,048 available closes research. Unknown transport failure retains the full reserved response charge. Oversized replies fail explicitly, retaining earlier cache. |
| Research decisions | Up to 7 within 8 total callback invocations. Rejected proposals and failed/timed-out callbacks consume a decision. No hidden provider retries are counted here. |
| Final synthesis decisions | At most 1 within those same 8, no MCP calls. Re-presenting cached replies consumes model context but no new retrieved characters. A direct research answer needs no extra synthesis call. |
| Execution time | 600 seconds from `run`, including tool catalogue loading and finalisation. The final 60 seconds are reserved for synthesis. Server startup/connection before `run` is host-managed. No deadline reset. |
| Tokens and cost | Host-managed; not inferred from characters or decision counts. The callback must enforce provider/context/output limits and propagate cancellation. No token/cost guarantee is made by this provider-neutral API. |

Smaller/larger caller-selected limits must be explicit through `Limits`; no limit
is raised automatically. The host remains responsible for an outer process
deadline if a callback blocks the event loop or ignores cancellation. Late model
answers are withheld. This cooperative async boundary cannot stop arbitrary code,
provider-side generation, external tools or hidden retries.

## Trust and validation

The historical experiment undercharged explicit unseeded `note_revision` reads.
This accounting correction is separate from finalisation: an explicit historical
read now consumes one selected expansion, including repeated reads. Seed plus
revision still consumes one. No research allowance is enlarged, and nominal
text-mode gather remains graph-capable. Dedicated regressions exercise historical
reads through the actual MCP client, including rejection before dispatch.

Source verification, exact quotations, hashes, locators, scope, review states and
qualification packaging remain the existing server's responsibility. The
coordinator preserves complete replies without repacking citations. It does not
verify semantic entailment, completeness or truth. Preserve conflicting accounts,
source attribution and material uncertainty; disclose unanswered parts and avoid
inferring causes, beliefs, dates or completed outcomes from association. Missing
evidence permits abstention. Generated answers are never written or accepted as
knowledge. No second model or claim-verification gate is introduced.

Synthetic tests exercise the public API through real in-process and stdio MCP
clients, including budgets, scope, write rejection, provenance retention, hard
deadlines, cancellation and unchanged checked replies. Scripted test callbacks
establish mechanics, not AI accuracy. Prior live experiments restored final
responses but failed their trustworthiness gate; held-out correctness did not
improve. This implementation adopts the termination correction only. See the
[ADR 0060 implementation note](../design_decisions/0060-evidence-grounded-research-and-synthesis.md#limited-production-implementation).
