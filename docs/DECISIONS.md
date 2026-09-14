# ResearchFlow Decisions

## D-001 — Root Python package layout

**Status:** Accepted for Phase 1

ResearchFlow uses a root `pyproject.toml` and `src/researchflow/agent/` package layout. An independent Agent service is deferred until a real separate deployment, lifecycle, or dependency-isolation need exists.

## D-002 — Graph State boundary

`messages` is the external conversation contract. `research_query` and `evidence` are internal, per-run research state. `report` is the graph's stable programmatic output. Thread, project, session, database, and authentication fields do not enter Graph State in Phase 1.

Only `messages` uses LangGraph's message reducer. `research_query`, `evidence`, and `report` each have one writer in the first graph slice and therefore use overwrite semantics.

In the current single-pass graph, `researcher` is also the run-entry owner that resets `evidence` to an empty list. If a future ReAct loop can revisit `researcher` within one run, reset ownership must move to a dedicated run-initialization boundary instead of silently clearing accumulated Evidence.

## D-003 — Provisional Evidence boundary

The original Phase 1 `Evidence` required `source` and `content`, with optional
`relevance_note`. D-015 supersedes that provisional shape with one
provenance-preserving discriminated union. The invariant remains: Evidence is
not a `ToolMessage.content` alias, and Writer reads `evidence` instead of parsing
ToolMessage text.

`HumanMessage.content` is normalized at the Researcher boundary before model invocation. A non-empty string is stripped; a content-block list retains non-empty `{"type": "text", "text": "..."}` blocks in order and joins them with two newlines. Non-text blocks are ignored, and unsupported or textless input raises `ValueError`. The internal `research_query` contract therefore remains a non-empty string.

`relevance_note` is a Phase 1 contract-change exercise, not a retrieval score or final relevance model. D-015 later defines the implemented retrieval score and document provenance fields inside the unified Evidence union. D-017 defines the implemented run-local Citation projection; neither decision makes Evidence a persisted Product entity.

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

Product-level Evidence/Sources recovery remains undecided. D-017 later approves
an Agent-output `citations` list as a recoverable latest-successful source
inventory, but the current `evidence` checkpoint field remains internal Agent
working state and no long-term Product persistence Contract exists.

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

## D-012 — Permanent Knowledge starts with atomic Project-scoped Markdown indexing

**Decision status:** Accepted in P6-000

**Implementation status:** Implemented by P6-002

A permanent Document belongs directly to one Project. It does not belong to a
Research Session, LangGraph thread, or run. Product Backend owns Document
identity, Project membership, upload validation, and the HTTP lifecycle;
02-Knowledge owns deterministic chunking, embedding, and retrieval behavior.

The first accepted source is one multipart UTF-8 Markdown file, limited to
1,048,576 raw bytes. Product Backend stores its validated text in PostgreSQL
with immutable metadata. The first create operation is synchronous and atomic
at the product-storage boundary: `201 Created` means the Document and all of its
Chunks/embeddings were committed and are searchable. Validation, chunking,
embedding, or database failure leaves no Document or Chunk row. No ingestion
status, job queue, retry worker, or partial-ready state is introduced.

Chunks are internal retrieval records, not general Product CRUD resources.
`KnowledgeHit` is the typed retrieval response and carries durable
`document_id`/`chunk_id` provenance. It is not Agent `Evidence`. A later Agent
Tool adapter may convert hits into a revised Evidence Contract, but it must not
parse ToolMessage text or discard provenance.

PostgreSQL with pgvector is the preferred minimal storage candidate because the
repository already operates PostgreSQL. P6-001 subsequently verified the
actual image, extension, embedding model/dimension, distance semantics, and
Project-filtered query; D-013 records the approved physical baseline.

The future Agent integration still requires an explicit Project-scope handoff.
Agent must not query pgvector directly, add product IDs to Graph State, or treat
LangGraph thread metadata as Project-membership authority. That integration is
outside P6-000 and the first Phase 6 batch.

## D-013 — First vector slice uses fixed bge-m3 vectors and exact cosine search

**Decision status:** Accepted at the P6-001 Architect checkpoint

**Implementation status:** Implemented by P6-002

P6-001 measured `pgvector/pgvector:0.8.6-pg18` locally as PostgreSQL 18.6
with pgvector 0.8.6. The first implementation uses that versioned image tag and
creates the `vector` extension through Alembic. The measured linux/amd64 image
digest remains reproducibility evidence; portable Compose does not pin that
platform-specific digest.

The accepted first embedding model is `BAAI/bge-m3` through the existing
SiliconFlow OpenAI-compatible base URL/key boundary and `OpenAIEmbeddings`.
P6-001 measured every sampled document/query vector at 1024 finite,
unit-normalized values. Chunk storage is therefore fixed `vector(1024)`, and
runtime ingestion/search must reject a missing, non-finite, wrong-count, or
wrong-dimension provider result, as well as a zero vector for which cosine is
undefined, before persistence or vector SQL. Changing the model to a different
dimension is a schema/re-indexing decision, not an environment-only
substitution.

The first retrieval query is exact cosine search. It joins Document Chunk to
Document and Project, filters both `documents.project_id` and
`projects.owner_user_id` at that authoritative boundary, orders by cosine
distance ascending using `<=>`, uses `chunk_id` ascending only as a
deterministic tie-break, and applies the validated limit. `KnowledgeHit.score`
is `1 - cosine_distance`, so response order is score descending. P6-001 proved
that `vector_cosine_ops` and HNSW syntax are compatible with the measured
dimension, but no HNSW/IVFFlat index, recall claim, or index tuning is approved
for P6-002. Ordinary indexes on Project membership and the Document foreign-key
join are sufficient for the bounded first slice.

P6-001 did not evaluate chunking quality and therefore does not approve a
fixed-width whole-document sliding window. The first chunker must remain
domain-independent and structure-aware: Markdown heading hierarchy and
paragraph boundaries take precedence. Normal structural blocks are packed
without crossing 2,000 Python characters; only one overlong structural block
uses deterministic 2,000-character windows with 200-character overlap.
Changing those persisted rules requires explicit re-indexing behavior and
Retrieval Eval evidence.

## D-014 — P6-002 retains Document lifecycle and adds trusted Project ownership

**Decision status:** Accepted by the user on 2026-09-04

**Implementation status:** Implemented by P6-002

P6-002 retains the P6-000 Document create, read, list, and Knowledge search
scope. Read/list are not silently deferred from the atomic vertical slice.

The authenticated user identity remains owned by an upstream identity layer.
ResearchFlow treats its normalized UUID as an opaque `user_id`; it does not add
passwords, login, token issuing, or a Product User CRUD table in P6-002. Product
Backend obtains the identity only through one trusted request dependency backed
by `X-ResearchFlow-User-Id`. The header must be injected or protected by the
trusted deployment boundary; accepting an arbitrary browser-supplied header on
a publicly exposed Backend is not an authentication system.

Project adds immutable, non-null `owner_user_id`. Create assigns it from the
trusted request identity; list/read and every nested Research Session,
Document, and Knowledge operation first select the Project by both
`project_id` and `owner_user_id`. Missing identity returns sanitized `401
Authentication required`. A missing Project and a Project owned by another user
both return `404 Project not found` to avoid resource enumeration.

Document and Chunk do not duplicate `user_id`. The authoritative retrieval
query joins Chunk to Document to Project and filters both the requested
`documents.project_id` and current `projects.owner_user_id` before ordering and
limit. PostgreSQL remains the ownership authority; Frontend selection,
LangGraph metadata, path/body user IDs, and Agent State are not authority.

The migration adds Project ownership safely. If the database already contains
Projects, `RESEARCHFLOW_LEGACY_OWNER_USER_ID` must contain the UUID that owns
those local-MVP rows; the migration backfills them before making the column
non-null. It fails instead of inventing ownership when the setting is absent or
invalid. Fresh empty databases need no legacy value. The column has no server
default, so every later Project must receive identity from the request boundary.

The local Frontend may send `NEXT_PUBLIC_RESEARCHFLOW_USER_ID` for the trusted
development setup, and Backend CORS may allow the normalized identity header.
That development convenience is not a credential and is not a substitute for
an upstream production authenticator that strips untrusted client values and
injects the verified identity.

## D-015 — Agent Knowledge uses scoped Backend HTTP and unified Evidence

**Decision status:** Accepted by 00-Architect on 2026-09-05

**Implementation status:** P7-001, P7-002, and P7-FE-001 DONE; the D-016
stream regression and browser Project A/B Knowledge matrix passed

The first Agent Knowledge integration is local/test only. An immutable
`knowledge_scope` containing `user_id` and `project_id` enters through
LangGraph Run context, outside Agent State, thread metadata, user messages, and
model-generated Tool arguments. The carrier is not authorization authority.
No production security claim is made until a trusted upstream injector, signed
capability, or gateway/proxy boundary is approved.

Agent `knowledge_search()` uses a typed HTTP client to call Product Backend. It
does not import Knowledge persistence or pgvector code. The client has a
10-second total timeout and no retry. Only a successful empty Backend response
maps to empty Evidence; authorization, validation, timeout, network, and
Backend errors remain sanitized explicit Tool failures.

Agent Evidence becomes one discriminated Pydantic union. The first accepted
variants are `temporary_research` and `user_upload`; the latter preserves
`document_id`, `chunk_id`, and `filename` provenance from `KnowledgeHit`.
The shared validator dumps accepted models to JSON-safe payloads before Graph
State writes. Existing provisional checkpoints receive a clean schema break.
Saved Web Source is not implemented or permanently embedded by this decision.

Agent owns an explicit registry containing Web and Knowledge Tools. It validates
all requested names before execution, then runs calls sequentially in model
call order. Repeated calls are allowed. Any Tool failure fails the node; retries
and partial-success Evidence are not part of the first integration.

P7-001 implemented the unbound Knowledge Tool/client and Evidence models;
P7-002 bound both Tools into the Research Graph under this boundary.

## D-016 — Frontend and Agent Server preserve the native multi-mode stream contract

**Decision status:** Accepted by 00-Architect on 2026-09-06

**Implementation status:** DONE through `BUG-P7-STREAM-001` and P7-FE-001

ResearchFlow selects P7-FE Option A: align and pin the local Agent Server to
the installed Frontend SDK's native multi-mode request. It rejects a
single-mode Frontend fork or downgrade. The accepted effective request modes
are `values`, `messages-tuple`, and `custom`, with subgraph streaming and
resumable streaming retained. This preserves SDK-owned state snapshots,
message chunk merging, custom-event transport, and native refresh/rejoin
behavior already assumed by D-007 and D-008.

The measured compatibility baseline is
`@langchain/langgraph-sdk==1.8.10`, `langgraph==1.2.11`,
`langgraph-api==0.13.0`, `langgraph-cli[inmem]==0.4.31`, and Python
`langgraph-sdk==0.4.3`. 04-Frontend owns the JavaScript pin; 01-Agent owns the
Python Server/runtime pins; 05-Quality owns the cross-boundary regression.
Changing this tuple later requires the same stream/thread/rejoin compatibility
checks, not an unreviewed transitive upgrade.

Architect verification first established that the live Server schema accepts a
string or array for `stream_mode`. `BUG-P7-STREAM-001` then captured the exact
browser failure: object-spreading the SDK stream object evaluated unused
getters and added `tools`/`updates`; `tools` was unsupported. Preserving the SDK
object and overriding only `submit` restored the approved three-mode request.
The pinned tuple passed normal, regenerate, edit, rejoin, and Project-isolation
browser checks, so no version upgrade or scalar Frontend fallback was needed.

D-016 changes no `knowledge_scope`, Agent State, Evidence, Backend, persistence,
or authentication boundary. It does not approve `tools`/`lifecycle` modes,
Research Progress events, or a Product Backend stream proxy.

## D-017 — Run-local Citation output and logical retrieval evaluation ground truth

**Decision status:** Accepted by 00-Architect on 2026-09-13

**Implementation status:** Implemented and validated by P7-003B and P7-003C on
2026-09-14; Architect phase-exit review remains required

ResearchFlow selects P7-003 Option A1. 01-Agent projects the already
validated, ordered Evidence list into a separate ordered `citations` field in
Agent State and output. IDs are contiguous run-local ordinals (`c1`, `c2`, ...)
and are neither Product identities nor durable cross-run references. The pure
mapper preserves order and duplicates, copies only source label plus approved
source-specific provenance, and creates a bounded excerpt by trimming the
Evidence content and retaining at most 500 Unicode code points (first 499 plus
`…` when truncated). It never infers provenance from ToolMessage content,
Report prose, filenames alone, or retrieval scores.

Writer returns `report` and `citations` in one State update, so the latest
successful pair remains coherent. A successful no-Tool path returns an empty
Citation list. This projection is a recoverable latest-run source inventory;
without inline claim markers it does not establish claim-to-source attribution,
faithfulness, or citation correctness. Citation UI, Product persistence,
replay, `report_id`, and `run_id` association remain undecided. Existing local
development checkpoints receive a clean schema break with no migration or
fallback parser, and implementation acceptance uses a fresh thread without
deleting existing data.

ResearchFlow also selects P7-003 Option B1. 05-Quality owns a source-controlled
logical JSON fixture and evaluation results; 02-Knowledge reviews chunk and
retrieval semantics, and 03-Backend reviews use of the existing scoped API.
Fixture references use `project_key`, `document_key`, and deterministic
zero-based `chunk_index`, never generated runtime UUIDs. An isolated test setup
ingests through the Product Backend and resolves generated Document/Chunk IDs
only for evaluation; no production Chunk endpoint or schema change is added.

The first measured retrieval metric is per-case and macro Recall@5 against the
existing `BAAI/bge-m3` exact-vector scoped search. The frozen `retrieval-v1`
fixture measured 1.0 for all three cases and macro Recall@5 = 1.0, establishing
a baseline without a pass/fail threshold. MRR, NDCG, Precision@K, citation correctness,
LangSmith, and retrieval-algorithm changes require later evidence and separate
tasks. P7-003B and P7-003C are separated because Agent output ownership and
Quality ground-truth ownership are independent boundaries.
