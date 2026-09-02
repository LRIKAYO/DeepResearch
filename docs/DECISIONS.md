# ResearchFlow Decisions

## D-001 — Root Python package layout

**Status:** Accepted for Phase 1

ResearchFlow uses a root `pyproject.toml` and `src/researchflow/agent/` package layout. An independent Agent service is deferred until a real separate deployment, lifecycle, or dependency-isolation need exists.

## D-002 — Graph State boundary

`messages` is the external conversation contract. `research_query` and `evidence` are internal, per-run research state. `report` is the graph's stable programmatic output. Thread, project, session, database, and authentication fields do not enter Graph State in Phase 1.

Only `messages` uses LangGraph's message reducer. `research_query`, `evidence`, and `report` each have one writer in the first graph slice and therefore use overwrite semantics.

In the current single-pass graph, `researcher` is also the run-entry owner that resets `evidence` to an empty list. If a future ReAct loop can revisit `researcher` within one run, reset ownership must move to a dedicated run-initialization boundary instead of silently clearing accumulated Evidence.

## D-003 — Provisional Evidence boundary

`Evidence` is a typed Tool result with required `source` and `content`, plus an optional provisional `relevance_note`. It is not a `ToolMessage.content` alias: Tools produce structured Evidence, and Writer reads `evidence` rather than parsing ToolMessage text.

`HumanMessage.content` is normalized at the Researcher boundary before model invocation. A non-empty string is stripped; a content-block list retains non-empty `{"type": "text", "text": "..."}` blocks in order and joins them with two newlines. Non-text blocks are ignored, and unsupported or textless input raises `ValueError`. The internal `research_query` contract therefore remains a non-empty string.

`relevance_note` is a Phase 1 contract-change exercise, not a retrieval score or final relevance model. Citation identifiers, retrieval scores, arbitrary metadata, document identifiers, and the final Evidence Schema are deferred until their cross-module Contracts are known.

One Tool call returns `list[Evidence]`, including an allowed empty list. The Tool execution boundary validates every list item before writing that exact list to Graph State. A dictionary is not accepted merely because it is structurally JSON-compatible.

## D-004 — Writer output boundary

The Writer writes `report` for programmatic callers and appends the same report as the final AI message for chat-compatible consumers. This is the implemented output boundary for P1-002.

## D-005 — Phase 1 concrete runtime

Phase 1 uses SiliconFlow's OpenAI-compatible endpoint with `deepseek-ai/DeepSeek-V4-Flash` for both Researcher and Writer, and Tavily for Web Search. `runtime.create_runtime()` reads `SILICONFLOW_API_KEY`, `SILICONFLOW_BASE_URL`, `SILICONFLOW_MODEL`, and `TAVILY_API_KEY` from the environment; none enter Graph State.

`build_graph(...)` remains dependency-injected for deterministic tests. The Tavily adapter normalizes provider results into `list[Evidence]`, so raw provider responses do not reach Graph State or Writer. A later provider replacement changes the runtime factory or Web Tool adapter, not the State/Evidence Contract.

One model response may contain several calls to the same concrete Web Tool. The executor first validates every call name, executes the valid calls sequentially, and flattens their individual `list[Evidence]` outputs into `state.evidence`. This is not a multi-tool registry or a ReAct loop.

## D-006 — Local LangGraph Server boundary

`langgraph.json` registers the single graph ID `researchflow` through `researchflow.agent.runtime:create_runtime`. The local `langgraph dev` server requires Python 3.11 or newer; ResearchFlow's core package remains compatible with Python 3.10+, while Phase 1 server validation uses Python 3.12.

The Server owns assistant selection, `thread_id`, and its local development checkpointer. SDK input remains top-level `messages`; `thread_id` is never added to `AgentState`. The future Agent Chat UI connection values are `apiUrl = http://127.0.0.1:2024`, `assistantId = researchflow`, and the `threadId` returned by the Server when a conversation starts.

The Phase 1 nodes use synchronous model and Web provider calls, so local development currently starts with `langgraph dev --allow-blocking`. This is a development constraint, not a custom server implementation; reconsider async nodes only when concurrent request throughput becomes a real requirement.

Server `updates` events are projected through `AgentOutputState`: the `execute_tool` update exposes its ToolMessage trace but not internal `evidence`. The smoke therefore uses streamed `values` to verify the public Report/final AIMessage, and checkpoint state to verify internal Evidence and the next-run reset.

## D-007 — Minimal Agent Chat UI adoption boundary

**Status:** Accepted for the first Frontend integration batch

ResearchFlow adopts the current `references/agent-chat-ui-main/` snapshot into an owned `frontend/` application. The snapshot has no Git metadata, so ResearchFlow records no commit SHA; the upstream MIT license is retained. Generated files, installed dependencies, logs and local environment files are not migrated.

The first integration reuses the upstream LangGraph Client, `useStream`, thread handling and standard Message/Tool/Interrupt rendering. Local configuration uses `apiUrl = http://127.0.0.1:2024` and `assistantId = researchflow`; `threadId` remains Server-owned and is created/associated by the SDK flow.

No FastAPI adapter, custom Frontend data layer or ResearchFlow-specific stream parser is introduced for basic chat. D-008 defines the later Research Progress, Evidence, persistence and replay boundary; no such feature is implemented, and the Frontend must not infer it from ToolMessage text or incidental stream payloads.

## D-008 — Run, state, event, and recovery authority

**Status:** Accepted for the P2-003 boundary

LangGraph Agent Server owns `run_id`, the status of that Run, `thread_id`,
checkpointed Thread State, unresolved interrupts, and resumable stream
transport. `run_id` identifies one invocation and remains correlation metadata;
it is not `thread_id`, the product `research_session_id`, or an `AgentState`
field.
For one Run, `pending` and `running` are active; `success`, `error`, `timeout`,
and `interrupted` are terminal. An interrupted thread may be resumed by a later
Run.

The latest checkpointed state is authoritative for recoverable messages, the
final Report, and future unresolved interrupts. `useStream.isLoading`, spinner
state, elapsed-time animation, and bare `tool.started` notifications are
transient Frontend state. After refresh, the Frontend must not infer "running"
from historical events; it must render checkpointed state and rely on Agent
Server Run/Thread status plus a valid stream rejoin.

If ResearchFlow later exposes activity history, the Product Backend—not the
Frontend—will own durable event ingestion and replay. Such a history requires a
typed complete lifecycle, idempotent event identity, Run/activity correlation,
and deterministic per-Run ordering. LangGraph custom stream events and SSE
rejoin are valid live/reconnection transport, but are not by themselves the
product's historical event store.

Evidence/Sources recovery remains undecided until Evidence becomes a defined
product entity. The current provisional `evidence` checkpoint field is internal
Agent working state and is not a Frontend or long-term persistence Contract.

The detailed authority matrix and recovery flows are in
`docs/ARCHITECTURE.md`. The Frontend uses `streamResumable: true` together with
SDK `reconnectOnMount: true`; the native in-flight refresh/rejoin path has been
smoke-tested. This closes the transport gap without approving Progress/Evidence
code or a custom event framework.

## D-009 — Product Backend starts with a Project vertical slice

**Status:** Accepted in P3-000; implemented and verified by P3-001

Product Backend begins with a product-owned Project resource and PostgreSQL
persistence. It does not proxy the existing Frontend → LangGraph Agent Server
message/stream path. LangGraph `thread_id` and `run_id` remain execution
identities and are not Project identifiers or first-table columns.

The approved initial Project fields are application-generated UUID v4
`project_id`, trimmed 1–120 character `name`, and PostgreSQL-generated
timezone-aware `created_at`. Names are not unique because there is no approved
user/tenant uniqueness scope. `updated_at` is deferred until an update actually
exists. P3-001 deferred Project list/update/delete and all relationships; D-010
subsequently approves Project listing and the first child relationship.

The first Backend runtime remains in `src/researchflow/backend/` with ASGI
entrypoint `researchflow.backend.app:app`. It uses FastAPI, synchronous
SQLAlchemy 2.x, Alembic, Psycopg 3, and PostgreSQL 18. Backend dependencies stay
in an optional dependency group. No repository interface, generic CRUD layer,
settings framework, async database stack, or SQLite substitute is introduced
for the first resource.

P3-001 owns a validated repository-local Compose fixture with one PostgreSQL
service and separate development/test databases. PostgreSQL-backed tests and
Alembic metadata checks are required; SQLite is not accepted as proof. This
does not introduce a production Backend image, orchestration design, or
deployment Contract.

## D-010 — Research Session maps one Project to one LangGraph thread

**Decision status:** Accepted in P4-000  
**Implementation status:** Implemented and verified by P4-001

Research Session is the Product Backend identity for one interactive research
conversation within one Project. Product Backend generates
`research_session_id`; LangGraph Agent Server generates `thread_id`. One
session has exactly one immutable thread, while that thread may have zero or
many Server-owned runs. `run_id` is not persisted in the first session table
and none of these product identities enter Agent Graph State.

Product Backend provisions the thread with the official synchronous Python
LangGraph SDK, records the returned opaque `thread_id`, and returns it to the
Frontend. This is a control-plane call only: Frontend continues to send
messages and receive streams directly from LangGraph Agent Server through
`useStream`.

The `research_sessions` table initially contains only Backend-generated UUID v4
`research_session_id`, Project foreign key `project_id`, unique opaque
`thread_id`, and PostgreSQL-generated timezone-aware `created_at`. Session
title/status/update/delete, run rows, Reports, Evidence, Auth, and pagination
are deferred.

PostgreSQL is authoritative for Project/session membership. Product/session
values in LangGraph thread metadata are a projection. If thread creation fails,
no row is inserted. If persistence fails after thread creation, Backend rolls
back and attempts one best-effort thread deletion. A distributed transaction,
outbox, saga, retry framework, and orphan reconciler are not introduced before
real failure evidence requires them.

## D-011 — Product navigation selects sessions; `thread_id` is derived

**Decision status:** Accepted in P5-000  
**Implementation status:** Implemented by P5-001/P5-002 and verified by
`QUALITY-SCAN-003`

The Frontend's canonical conversation selection uses the product-owned
`projectId` and optional `researchSessionId`. After reading that session from
Product Backend, the Frontend passes its returned `thread_id` to `useStream`.
`thread_id` remains an opaque execution reference and is not an independent
product-navigation key.

The existing global LangGraph `threads.search` history and `threadId` URL
selection must be removed from the product flow. A standalone legacy
`threadId` cannot be reverse-attached to a Project from thread metadata because
PostgreSQL, not metadata, is the membership authority. ResearchFlow therefore
does not silently migrate or adopt such a thread.

For the first implementation, selecting **New research** provisions a Research
Session through Product Backend before the composer can submit. `useStream`
must not auto-create an unrecorded thread when no Product Session is selected.
The session list uses only the implemented Product Backend response; title and
message-derived previews remain deferred because Research Session has no title
Contract.

The browser calls Product Backend directly through a configured public base
URL and an explicit CORS allow-list. This does not introduce authentication and
does not add a Next.js product-API proxy. Agent messages and streams continue
directly between the Frontend and LangGraph Agent Server. No new Backend API or
data-model field is approved by this decision.
