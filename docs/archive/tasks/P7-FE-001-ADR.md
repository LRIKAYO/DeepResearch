# ADR-P7-FE-A — Frontend / Agent Server Streaming Protocol Alignment

**Status:** DECIDED — Option A accepted by 00-Architect on 2026-09-06

## Decision

Choose **A: align and pin the Agent Server boundary to the Frontend SDK's
multi-mode request**. Do not constrain ResearchFlow to a single stream mode and
do not fork `useStream`.

This is an alignment decision, not approval for a blind upgrade. The currently
running versions already advertise and validate the required request shape, so
the original `422` must be reproduced with its complete sanitized response
detail before any version is changed.

## Current Verified Facts

- Frontend resolves `@langchain/langgraph-sdk` to `1.8.10`.
- Its installed `useStream` source builds a de-duplicated array from explicit
  submit modes, modes tracked by consumed getters, and callback-required modes.
- ResearchFlow explicitly requests `values`; rendering `stream.messages`
  tracks `messages-tuple` and `values`; registering `onCustomEvent` adds
  `custom`. The current effective set is therefore
  `values + messages-tuple + custom`.
- The running local Server reports `langgraph-api==0.13.0` and
  `langgraph==1.2.11`. The local Python SDK is `0.4.3`, and the CLI is
  `0.4.31`.
- That Server's live OpenAPI schema accepts `stream_mode` as either one string
  or an array and includes all three modes above. It also accepts
  `stream_subgraphs` and `stream_resumable`.
- A diagnostic request using the exact three-mode array against a confirmed
  nonexistent thread passed request validation and returned `404`; replacing
  one entry with an invalid mode returned `422`. No Run or Thread was created.

These facts disprove the earlier statement that the running
`langgraph-api==0.13.0` rejects multi-mode arrays. The recorded browser `422`
is real evidence of a failed request, but its field-level cause remains
unproven because the response detail and exact payload were not retained.

## Approved Compatibility Baseline

The bug-fix task must preserve and make reproducible this measured tuple:

| Boundary | Approved baseline |
| --- | --- |
| Frontend SDK | `@langchain/langgraph-sdk==1.8.10` |
| Agent graph runtime | `langgraph==1.2.11` |
| Local Agent Server API | `langgraph-api==0.13.0` |
| Local Agent Server CLI | `langgraph-cli[inmem]==0.4.31` |
| Python SDK | `langgraph-sdk==0.4.3` |
| Required request modes | de-duplicated `values`, `messages-tuple`, `custom` |
| Required flags | `stream_subgraphs=true`, `stream_resumable=true` |

`package.json` and Python development dependencies must pin the compatibility
seam rather than relying only on the current `pnpm-lock.yaml` or an unconstrained
transitive `langgraph-api<1` installation. 01-Agent owns the Python Server
tuple; 04-Frontend owns the JavaScript SDK pin; 05-Quality owns the cross-version
regression evidence.

## Why Option B Is Rejected

Option B is not a local `streamMode: "values"` edit. The installed hook adds
modes when the UI reads `stream.messages` and when `onCustomEvent` is present.
Forcing a scalar request would therefore require a custom transport/fork or a
Frontend SDK downgrade.

That would intentionally discard or put at risk token/message merging,
Generative UI custom events, and the already accepted native stream/rejoin
path. It also conflicts with the upstream streaming model, which supports
multiple modes as a first-class array. ResearchFlow has no measured requirement
that justifies owning such a fork.

## Required Bug-Fix Sequence

Use one temporary cross-module `BUG-P7-STREAM-001` thread:

1. Restart Frontend and Agent Server from the declared dependency set.
2. Capture the failing browser request's URL, exact non-secret JSON shape,
   HTTP status, and sanitized response detail.
3. Compare `stream_mode` entries with the live Server OpenAPI enum. Do not infer
   the failing field from the status code alone.
4. If the measured tuple succeeds, pin it and classify the prior failure as
   stale environment/process drift or a different payload error. Do not
   upgrade merely to produce a diff.
5. If the tuple still fails, change only the Agent Server side to the smallest
   version that accepts the approved request and rerun the full matrix below.

## Required Regression Matrix

- Browser request carries `context.knowledge_scope`, not Graph input scope.
- Server accepts the multi-mode array and creates the Run.
- `values` produces final Report/checkpoint state.
- `messages-tuple` produces/merges AI and Tool messages without duplication.
- `custom` remains accepted even when this graph emits no ResearchFlow custom
  domain event yet.
- `stream_subgraphs` does not corrupt root-graph messages.
- `stream_resumable`, refresh/history restoration, and in-flight rejoin retain
  their existing behavior.
- Project A/B browser runs preserve Knowledge isolation and provenance.
- Normal submit, regenerate, message edit/branch, and interrupt-resume callers
  still route through the shared scoped submit wrapper.
- Existing Agent/Backend/Knowledge tests and Frontend typecheck/lint/build pass.

## Non-goals

- No change to D-015 scope authority or `knowledge_scope` placement.
- No Product Backend stream proxy.
- No Research Event Schema or replay store.
- No move of scope into Graph input, Agent State, Tool arguments, or thread
  metadata.
- No `tools`/`lifecycle` mode adoption in this bug fix.

## References

- [LangGraph JavaScript streaming: multiple modes](https://docs.langchain.com/oss/javascript/langgraph/streaming#stream-multiple-modes)
- [ResearchFlow upstream integration review](../source-review/integration-plan.md)
