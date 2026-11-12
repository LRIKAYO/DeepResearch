# BUG-P7-STREAM-001 — Multi-mode Browser Stream Alignment

**Status:** DONE — the pinned native multi-mode transport and every applicable
current-graph browser path are validated.

## Goal

Close the P7-FE-001 browser blocker by reproducing the exact `422`, making the
measured Frontend/Agent Server compatibility tuple reproducible, and proving
the approved multi-mode stream works end to end.

## Why Now

The recorded browser run failed before its final report rendered, but the
retained evidence does not include the `422` response detail. Architect checks
now prove that the currently running Server accepts the SDK's effective
multi-mode array. Changing SDK behavior or upgrading dependencies before
capturing the real failing field would treat a guess as root cause.

## Scope

- Capture one failing or succeeding browser `runs/stream` request with URL,
  non-secret payload shape, response status, and sanitized response detail.
- Confirm the effective modes are the de-duplicated set `values`,
  `messages-tuple`, and `custom` and that `knowledge_scope` remains top-level
  Run context.
- Pin `@langchain/langgraph-sdk==1.8.10` in Frontend package metadata.
- Pin the tested Python seam:
  `langgraph==1.2.11`, `langgraph-api==0.13.0`,
  `langgraph-cli[inmem]==0.4.31`, and `langgraph-sdk==0.4.3` in the appropriate
  runtime/development dependency groups.
- Reinstall/verify from declared dependencies, restart the local Frontend and
  Agent Server without deleting checkpoint or PostgreSQL data, and rerun the
  D-016 regression matrix.
- If the pinned tuple succeeds, make no version upgrade. Record whether the old
  failure came from stale process/environment drift or another captured field.
- If the exact failure persists and is not explained by the captured payload,
  return REVIEW to 00-Architect before changing the accepted tuple.

## Out of Scope

- Scalar-only stream adaptation, SDK fork, or SDK downgrade.
- Product Backend stream proxy or changes to `knowledge_scope` authority.
- Agent graph, Evidence, Knowledge retrieval, database, or authentication
  redesign.
- `tools`/`lifecycle` modes, Research Progress events, and replay persistence.
- Deleting LangGraph checkpoints, PostgreSQL volumes, Projects, or Documents.

## Owner

04-Frontend coordinates browser/request evidence and the JavaScript pin.
01-Agent owns Python Server/runtime pins. 05-Quality validates the cross-module
matrix. 00-Architect reviews only if the accepted tuple still fails.

## Development Mode

DELEGATE

## Learning Importance

MEDIUM. The important distinction is that explicit `streamMode` is not the
whole wire request: `useStream` adds modes required by consumed projections and
callbacks. This is worth understanding, but it does not require the user to
hand-write Frontend dependency or E2E boilerplate.

## Learning Goal

The user should be able to explain why a `422` status alone does not identify
the invalid field, why `stream.messages` causes `messages-tuple` to be requested,
and why a compatible Server boundary is smaller than maintaining a custom
single-mode Frontend transport.

## Deliverables

- Exact dependency pins and refreshed dependency metadata/lockfile.
- Credential-safe request/response evidence and root-cause classification.
- Passing D-016 browser/stream regression evidence.
- Updated P7-FE-001 Completion Report and Quality record.

## Acceptance Criteria

- A cleanly restarted Server reports the pinned versions and its live OpenAPI
  accepts the approved multi-mode array.
- Browser `runs/stream` returns success and creates a Run with
  `context.knowledge_scope` outside Graph input.
- AI/Tool messages merge without duplication, final Report/checkpoint values
  render, and `custom` remains an accepted transport mode.
- Refresh/history and in-flight rejoin retain their previously accepted
  behavior; subgraph mode does not corrupt root messages.
- Project A/B Knowledge browser runs remain isolated and preserve provenance.
- Normal submit, regenerate, edit/branch, and interrupt-resume paths still use
  the shared scoped wrapper.
- Existing Python tests and Frontend typecheck/lint/build pass.
- No SDK fork, scalar fallback, Backend proxy, scope relocation, data deletion,
  or unapproved version change appears.

## Reproducible Root Cause and Fix

The recorded browser `422` was reproduced against the pinned tuple. The Server
did not reject an array: it rejected the unexpected `tools` member in this
actual array:

```text
values, messages-tuple, tools, updates, custom
```

The Server's live `RunCreateStateful.stream_mode` enum accepts `values`,
`messages-tuple`, `updates`, and `custom`, but not `tools`; its sanitized
validation response named that array and the invalid `tools` value.

The extra modes came from the Frontend's own scoped wrapper. Object-spreading
the `useStream` return object evaluated its SDK getters while constructing
`{ ...streamValue, submit }`. That invoked the unused `toolProgress` and
subagent getters, which track `tools` and `updates` respectively. This was not
a Server-version incompatibility and did not require a version upgrade.

`Stream.tsx` now inherits `streamValue` and overrides only `submit`, without
enumerating SDK getters. The actual browser mode set is consequently the
approved `values`, `messages-tuple`, `custom` set.

## Current Validation Evidence

- Declared and installed tuple: Frontend SDK `1.8.10`; `langgraph` `1.2.11`;
  `langgraph-api` `0.13.0`; CLI `0.4.31`; Python SDK `0.4.3`.
- Real browser request: Graph input keys were `messages` only; top-level Run
  context contained `knowledge_scope`; scope was absent from input; flags were
  `stream_subgraphs=true` and `stream_resumable=true`.
- Before the fix, the captured browser request returned `422` with the
  sanitized `tools` enum failure above. After the fix it requested only the
  approved three modes and returned `200`.
- A real UI Run finished successfully: checkpoint state contained a non-empty
  `report`, three messages, no UI error, and no active loading state.
- A second real browser Project → Research Session run waited for the Report
  checkpoint, then reloaded the page. The Product URL retained both selection
  IDs, the user message remained visible, and the restored state still had a
  Report. Its subsequent UI **Refresh** (regenerate) request used the same
  thread and returned `200` with exactly the approved modes, top-level scope,
  `stream_resumable=true`, and `stream_subgraphs=true`; its resulting state
  also contained a Report and the UI had no error.
- A real UI **Edit** → **Submit** action issued a same-thread `runs/stream`
  request that returned `200` with the same three modes, top-level scope, and
  resumable/subgraph flags. The request carried the edited human message and
  its checkpoint identified a parent checkpoint; the resulting latest state
  contained that edited message and a Report. This verifies the edit branch
  entered the Agent checkpoint state.
- The full A/B browser Knowledge matrix used two real Backend-indexed Markdown
  Documents with distinct tokens. Each selected Project produced a `200` Run
  with only `values`, `messages-tuple`, and `custom`, matching top-level scope,
  no input scope, its own token in state, the other Project's token absent, and
  a final Report.
- A real in-flight Run was reloaded while its Report was absent. Native SDK
  recovery requested `/threads/:id/runs/:id/stream`; its final state contained
  a Report, the UI retained the user message, and no UI error appeared.
- `py -3.12 -m pytest tests/agent tests/backend tests/knowledge -q`: 92 passed.
- Frontend TypeScript, lint (0 errors; 16 pre-existing warnings), and production
  build passed.

## Boundary Note

The current graph has no `interrupt()` producer. Consequently,
interrupt/resume has no executable product scenario in this task; it must not
be fabricated by changing the Agent graph merely to extend a transport
regression. If an approved future graph introduces an interrupt, its owning
Agent task must add an interrupt/resume acceptance scenario.
