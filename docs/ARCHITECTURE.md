# ResearchFlow Architecture

This document records cross-module boundaries that are already needed by the
implemented system. It is not a target-state inventory.

## Run, State, Event, and Recovery Boundary

**Decision:** D-008  
**Scope:** P2-003  
**Status:** Accepted

### Current Repository Facts

- `langgraph.json` registers the Agent graph as `researchflow` on LangGraph
  Agent Server.
- The current Graph State contains `messages`, internal `research_query` and
  validated JSON-safe `evidence`, plus the final `report` and run-local
  `citations`. The Writer appends the Report as the final AI message and updates
  that message, Report, and Citation list atomically.
- The Frontend uses `@langchain/langgraph-sdk` 1.8.10 `useStream`, explicitly
  requests `values`, enables `fetchStateHistory`, and sets
  `streamResumable: true` when submitting. Consuming `stream.messages` adds
  `messages-tuple`, while the registered `onCustomEvent` callback adds
  `custom`; the SDK sends their de-duplicated multi-mode union.
- `useStream` currently restores thread/checkpoint history, messages, and
  interrupts. Its `isLoading` value represents the current client stream, not
  durable execution status.
- The Frontend configures `reconnectOnMount: true`. In the installed SDK, this
  enables session storage of the current `run_id` and automatic
  `joinStream(...)` on remount. Both completed-thread refresh and in-flight
  refresh/rejoin have been smoke-tested against a local Agent Server.
- Product Backend now persists Projects and Project-scoped Research Sessions.
  No ResearchFlow Progress event, replay store, or stable Evidence product
  entity exists.

### Identity Boundary

| Identity              | Current meaning                                          | Boundary                                                                                                                                                     |
| --------------------- | -------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `thread_id`           | LangGraph thread and checkpoint-history identity         | Groups state across one or more runs. It is not a messages array and does not belong in `AgentState`.                                                        |
| `run_id`              | One LangGraph Agent Server run/invocation                | Generated and owned by Agent Server. It scopes execution status and stream rejoin; it does not identify a conversation or a future product research session. |
| activity identity     | One future progress activity, such as one Tool execution | Does not exist yet. It is required only if ResearchFlow persists an activity lifecycle.                                                                      |
| `research_session_id` | Product Backend research identity                         | Implemented by P4-001. D-010 maps one session to one thread and allows several runs under that thread; Report relationships remain deferred.               |

`run_id` is correlation metadata, not research input. It MUST NOT be added to
Graph State merely to select graph behavior. A resume, retry, regeneration, or
later turn can create another run under the same `thread_id`.

### Authoritative Sources

| Concern                                 | Authoritative source                                                             | Explicitly not authoritative                                                       |
| --------------------------------------- | -------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------- |
| Status of one current run               | Agent Server `Run.status`, addressed by `thread_id` + `run_id`                   | `useStream.isLoading`, spinner state, elapsed time, or an old `tool.started` event |
| Aggregate condition of a thread         | Agent Server `Thread.status` and latest `ThreadState`                            | The last rendered event                                                            |
| Messages and final Report after refresh | Latest checkpointed Thread State; Report is also exposed as the final AI message | Browser component state alone                                                      |
| Unresolved interrupt                    | Latest checkpoint tasks/interrupts and resumable thread state                    | A historical interrupt event or a previously rendered card                         |
| Live connection/loading presentation    | Current `useStream` instance                                                     | Server execution status after the browser disconnects                              |
| Product-persisted Evidence/Sources      | Not decided                                                                      | Current ToolMessage content and transient UI state                                 |

For the installed SDK, Agent Server run statuses are:

- active: `pending`, `running`;
- terminal for that `run_id`: `success`, `error`, `timeout`, `interrupted`.

`interrupted` is terminal for that particular run, while the checkpointed
thread can remain resumable through a later run. Thread status is useful for
discovering `busy`, `interrupted`, or `error` threads, but a run-specific status
display must use the Run resource.

Production recovery of Report and interrupts requires durable Agent Server
checkpoint storage. The current local development server proves the protocol;
it is not by itself a production retention guarantee.

### Three Different Data Classes

#### 1. Durable Graph State

Use checkpointed Graph State for values required to continue the graph or
reconstruct the latest user-visible result:

- conversation `messages`;
- final `report`;
- LangGraph interrupt state when interrupts are introduced.

The current validated `evidence` is internal graph working state. Its
presence in a checkpoint does not make it an approved Frontend or long-term
product Contract.

#### 2. Transient UI State

The following remain browser-local and disposable by default:

- `tool.started` presentation;
- spinner visibility;
- elapsed-time animation;
- first-token and connection indicators.

They may be driven by a live or rejoined stream, but refresh clears them unless
the Server confirms that a run is active and the client rejoins it. The
Frontend MUST NOT scan old events and infer that work is still running.

#### 3. Replayable Domain Events

A Tool activity timeline is a product feature, not a side effect of consuming
custom stream chunks. It becomes replayable only if ResearchFlow persists the
complete lifecycle from `tool.started` to exactly one terminal outcome such as
`tool.completed` or `tool.failed`.

Any future replayable envelope must provide semantic equivalents of:

- a unique event identity for idempotency;
- the Agent Server `run_id` for run correlation;
- an activity identity that pairs start and terminal events;
- a monotonically increasing sequence within a run;
- event type, occurrence time, and typed payload.

Consumers order by the sequence, not by client receipt time or wall-clock
timestamp. Events received after a terminal lifecycle event cannot reopen that
activity. A terminal Agent Server Run status also prevents the UI from showing
the run as active, but it does not synthesize a missing Tool activity history.
Cancellation/timeout mapping and the serialized field names belong to the
future event Schema decision.

LangGraph `custom` stream mode is an eligible live delivery mechanism. Its SSE
event ID / `Last-Event-ID` cursor and `joinStream(...)` support transport
reconnection; they are not ResearchFlow's indefinite historical event store.
Likewise, checkpoint history is state history and time-travel input, not a
product activity-event log.

### Live, Refresh, and Replay Flows

```mermaid
flowchart TD
    S[Frontend submit] --> T{thread_id exists?}
    T -->|no| CT[SDK creates LangGraph thread]
    T -->|yes| CR[SDK creates run on thread]
    CT --> CR
    CR -->|Agent Server returns run_id| RUN[pending / running]
    RUN --> G[Graph execution and checkpoints]
    G --> LS[Live values / messages / tool / custom stream]
    LS --> UI[useStream projection and transient UI]
    G --> TS[Latest Thread State]
    G --> RS[Terminal Run.status]

    R[Refresh or remount] --> L[Load thread by thread_id]
    L --> TS
    L --> C{Known active run confirmed by Server?}
    C -->|yes| J[joinStream with run_id and stream cursor]
    J --> UI
    C -->|no| SNAP[Render checkpointed state; transient activity is idle]
```

There are three distinct guarantees:

1. **Live streaming:** `useStream` merges incoming values/messages/events into
   its current Frontend projection.
2. **Refresh/reconnect:** `thread_id` restores checkpointed state. Rejoining
   in-flight output additionally requires a known `run_id`, Server-backed
   resumable streaming, and `joinStream`. ResearchFlow uses and has smoke-tested
   the SDK's native reconnect path.
3. **Historical replay:** requires a durable Product Backend event store and
   replay API if the product chooses to expose activity history. It is not
   implemented and is not required for basic chat.

### Module Ownership

| Module                      | Owns                                                                                                                     | Must not own                                                                                           |
| --------------------------- | ------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------ |
| 01 Agent                    | Domain meaning of progress, durable graph-state updates, and future typed event production                               | Browser animation, event database, or LangGraph run-status authority                                   |
| LangGraph Agent Server      | `thread_id`, `run_id`, Run/Thread status, checkpoints, interrupts, live stream and run rejoin                            | ResearchFlow's long-term activity-history product policy                                               |
| 04 Frontend                 | `useStream` projection, transient presentation, and rendering current authoritative state                                | Inventing run status, parsing ToolMessage text into Evidence/Progress, or acting as replay persistence |
| 03 Product Backend          | Product identity/persistence and, if later approved, durable event ingestion/replay                                      | Reimplementing Agent graph orchestration or proxying the basic message stream                           |
| 05 Quality                  | Contract tests for live, refresh, reconnect, terminal status, and replay invariants                                      | Changing ownership boundaries merely to make a test pass                                               |

### Immediate Consequences

- Do not implement Research Progress or Evidence UI from ToolMessage text.
- Do not persist spinners, timers, or bare `tool.started` events.
- Do not add `run_id` to `AgentState`.
- Keep final Report and future unresolved interrupts in checkpoint-recoverable
  authoritative state.
- Before any Progress/Evidence implementation, all consuming modules must agree
  on the typed state/event Contract.
- Frontend recovery uses the SDK-native path; no custom reconnect or event
  framework is justified now.

### Deferred Decisions

- Whether Evidence/Sources become session entities, report-owned entities, or
  permanent Project Knowledge.
- The relationship from Research Session/run to a future `report_id`.
- The final event Schema, cancellation/timeout outcome mapping, storage
  technology, retention, authorization, and replay pagination.
- Whether a final Report also becomes a Product Backend entity beyond its
  checkpointed Graph State representation.

No `docs/API_CONTRACTS.md` event payload is created yet: semantic invariants are
approved here, but the serialized event fields and an owning API do not yet
exist.

### Upstream Semantics Used

- [LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/persistence)
- [LangGraph interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts)
- [Join and rejoin streams](https://docs.langchain.com/oss/python/langchain/frontend/join-rejoin)
- [LangGraph SDK `joinStream`](https://reference.langchain.com/javascript/langchain-langgraph-sdk/client/RunsClient/joinStream)

### Streaming Protocol Compatibility

**Decision:** D-016

ResearchFlow preserves the native `useStream` multi-mode boundary rather than
forking the Frontend SDK into a scalar-only transport. The required current
mode set is `values`, `messages-tuple`, and `custom`; subgraph and resumable
flags remain enabled. The accepted measured tuple is:

```text
@langchain/langgraph-sdk 1.8.10
        ↕ runs/stream: [values, messages-tuple, custom]
langgraph-api 0.13.0 / langgraph 1.2.11
langgraph-cli[inmem] 0.4.31 / Python langgraph-sdk 0.4.3
```

The live Server OpenAPI accepts this array shape. A valid diagnostic payload
passed schema validation, while an intentionally invalid mode produced `422`.
Consequently, a browser `422` alone cannot be classified as a multi-mode
incompatibility: the exact request and response detail must be retained before
the version boundary changes. `BUG-P7-STREAM-001` owns that diagnosis and the
pinning/regression work. Product Backend is not inserted into this stream path.

## Product Backend First Slice

**Decision:** D-009  
**Scope:** P3-000  
**Status:** Implemented and verified by P3-001

### Why the Backend Exists

LangGraph Agent Server already owns graph invocation, runs, threads,
checkpoints, interrupts, and stream transport. Product Backend begins with
product-owned resources and business persistence; it is not inserted into the
working chat path merely to proxy bytes.

The first approved request path is:

```mermaid
flowchart LR
    C[API client] --> F[FastAPI Project Contract]
    F --> U[Concrete Project use case]
    U --> S[SQLAlchemy Session / transaction]
    S --> P[(PostgreSQL projects table)]
    P --> S --> F --> C

    UI[Agent Chat UI] -->|messages / stream| LG[LangGraph Agent Server]
```

There is no Product Backend edge in the Agent Chat UI → LangGraph stream path
in this slice.

### Runtime and Package Boundary

- Package location: `src/researchflow/backend/` inside the current Python
  project. A separate repository/package is not justified yet.
- ASGI entrypoint: `researchflow.backend.app:app`.
- Local command: `uvicorn researchflow.backend.app:app --reload --port 8000`.
- Backend-only packages belong in a `backend` optional dependency group so the
  Agent runtime does not acquire them accidentally.
- Configuration uses the required `RESEARCHFLOW_DATABASE_URL` environment
  variable in SQLAlchemy's `postgresql+psycopg://...` URL form. Tests use the
  same form through `RESEARCHFLOW_TEST_DATABASE_URL`. No settings framework is
  added for two values.

### Persistence Boundary

- PostgreSQL 18 is the approved business database for this slice; local/test
  setup pins the official `postgres:18.6` image.
- P3-001 owns one repository-local Compose service for PostgreSQL, with a
  persistent development database and a separate PostgreSQL test database.
  This developer fixture is not a production deployment Contract.
- SQLAlchemy 2.x owns concrete mapping and transaction/session mechanics.
- Alembic owns schema migrations. Migration configuration lives in
  `pyproject.toml`; revision scripts live under `migrations/`.
- Psycopg 3 (`psycopg[binary]` for local development) is the PostgreSQL driver.
- The first slice uses synchronous SQLAlchemy/Psycopg calls and synchronous
  FastAPI path operations. Async persistence is deferred until measured
  concurrency needs justify its extra lifecycle complexity.
- P3-001 tests run against PostgreSQL through
  `RESEARCHFLOW_TEST_DATABASE_URL`; SQLite is not treated as proof of the
  PostgreSQL mapping/migration Contract.

P3-001 Gate A used Docker CLI 28.5.1, Compose 2.40.0, and the Docker Desktop
Linux engine to validate the pinned PostgreSQL service, both databases,
migrations, API behavior, and restart persistence. The Compose fixture remains
developer infrastructure rather than a production deployment Contract.

### Minimal Code Shape

The first slice needs only the application entrypoint, database/session setup,
one concrete Project module, Alembic migration files, and focused tests. It does
not need a repository interface, generic CRUD base class, event bus, or
separate microservice package.

### Contract Locations

- HTTP shapes and errors: `docs/API_CONTRACTS.md`
- Product fields, authority, and relationships: `docs/DATA_MODEL.md`
- Architectural decision: D-009 in `docs/DECISIONS.md`

### Backend References

- [FastAPI response models](https://fastapi.tiangolo.com/tutorial/response-model/)
- [SQLAlchemy declarative mapping](https://docs.sqlalchemy.org/en/20/orm/declarative_tables.html)
- [Alembic migration documentation](https://alembic.sqlalchemy.org/en/latest/)
- [Psycopg 3 installation](https://www.psycopg.org/psycopg3/docs/basic/install.html)
- [PostgreSQL version support](https://www.postgresql.org/support/versioning/)

## Project-scoped Research Session Boundary

**Decision:** D-010  
**Scope:** P4-000  
**Decision status:** Accepted in P4-000  
**Implementation status:** Implemented and verified by P4-001

### Current Integration Facts

- The JavaScript SDK 1.8.10 used by the Frontend calls
  `client.threads.create()` before the first run when `useStream` has no
  `threadId`, then reports the Server-generated ID through `onThreadId`.
- The Python SDK 0.4.3 installed in the Backend environment provides
  synchronous thread create/get/delete operations.
- `useStream` already accepts an existing `threadId`. Product Backend therefore
  does not need to transport messages or stream events merely because it
  provisions that thread.
- Agent Server supports several runs under one checkpointed thread. Run status
  and stream rejoin remain governed by D-008.

### Identity and Cardinality

```text
Product Backend                         LangGraph Agent Server

Project 1
  └── 0..N Research Sessions
             └── exactly 1 thread_id
                         └── 0..N run_id values
```

- `research_session_id` is a Backend-generated UUID v4 and the product identity
  used for Project membership.
- `thread_id` is a Server-generated opaque string persisted as an immutable,
  unique external reference.
- `run_id` remains Server-owned correlation for one invocation. It is not a
  Research Session field, a database row, or Agent State input in P4.
- PostgreSQL is authoritative for whether a Research Session belongs to a
  Project. Project/session IDs copied into thread metadata are a projection for
  diagnostics/search only.

### Provisioning Flow

```mermaid
sequenceDiagram
    participant UI as Frontend
    participant BE as Product Backend
    participant DB as PostgreSQL
    participant LG as LangGraph Agent Server

    UI->>BE: POST /projects/{project_id}/research-sessions
    BE->>DB: verify Project
    BE->>BE: generate research_session_id
    BE->>LG: threads.create(graph_id, Project/session metadata)
    LG-->>BE: thread_id
    BE->>DB: insert Research Session association
    DB-->>BE: committed row
    BE-->>UI: 201 Research Session + thread_id
    UI->>LG: useStream(thread_id), direct messages/runs/stream
```

This Backend → Agent Server edge is a control-plane provisioning call. It does
not change the Frontend → Agent Server data-plane streaming edge.

### Failure Boundary

- Missing Project: return Product `404`; do not call Agent Server.
- Thread creation failure: return sanitized `503`; do not create a session row.
- Database failure after thread creation: roll back the row and attempt one
  best-effort thread deletion. Preserve/log the original database failure.
- Failed compensation may leave an Agent Server orphan, but never a Product
  Session that points at an unconfirmed thread. A distributed transaction,
  outbox, saga, retries, and reconciler are deferred until observed failure
  frequency justifies them.
- Run success/failure/interruption does not mutate a session status because no
  such aggregate status is approved.

### Module Ownership

| Module | Owns | Must not own |
| --- | --- | --- |
| Product Backend | Research Session identity, Project membership, provisioning coordination, persisted `thread_id` association | Messages, checkpoints, run status, or stream transport |
| LangGraph Agent Server | Thread/run creation, thread/run status, checkpoints, interrupts, resumable stream | Product Project membership authority |
| Frontend | Calling session APIs, selecting the returned session/thread, direct `useStream` rendering | Creating an unrecorded Product Session mapping or treating thread metadata as business authority |
| Agent Graph | Research reasoning and Graph State | Product/session identity association |

### Configuration Boundary

P4-001 adds required `RESEARCHFLOW_LANGGRAPH_URL` and
`RESEARCHFLOW_GRAPH_ID` values to Product Backend. It uses the verified official
Python SDK through one small control-plane module. No generic gateway interface,
service mesh, or settings framework is required.

## Project-scoped Frontend Adoption Boundary

**Decision:** D-011  
**Scope:** P5-000  
**Decision status:** Accepted  
**Implementation status:** Implemented by P5-001/P5-002 and verified by
`QUALITY-SCAN-003`

### Canonical Selection Flow

```mermaid
flowchart LR
    URL[URL: projectId + optional researchSessionId]
    BE[Product Backend]
    RS[Research Session response]
    LG[LangGraph Agent Server]
    UI[useStream and UI]

    URL -->|list/read product resources| BE
    BE -->|research_session_id + thread_id| RS
    RS -->|derived thread_id| UI
    UI <-->|messages and direct stream| LG
```

- `projectId` and `researchSessionId` identify product navigation state.
- `thread_id` is read from the selected Research Session and supplied to
  `useStream`; it is not independently selected from the URL.
- Changing Project clears the selected Research Session. A session returned
  outside that Project is rejected by the existing nested Backend Contract.
- Refresh restores the product selection from the URL, reads the authoritative
  mapping from Product Backend, then lets `useStream` recover checkpointed
  state from Agent Server.

### New Research Flow

The first Frontend slice uses an explicit **New research** action:

1. The user selects an existing Project or creates one through Product Backend.
2. The Frontend posts to that Project's Research Session collection.
3. After `201`, it stores `projectId` and `researchSessionId` as navigation state
   and binds `useStream` to the returned `thread_id`.
4. Only then may the composer submit a message directly to Agent Server.

While provisioning is pending, repeated creation and message submission are
disabled. This is a client-side duplicate guard, not an idempotency guarantee.
The SDK must not create a thread from a null `threadId`, because such a thread
would have no Product Backend association.

### Discovery and Transport Boundaries

- Project and Research Session discovery uses Product Backend. The Frontend no
  longer performs global LangGraph `threads.search` for product history.
- A standalone legacy `threadId` is not reverse-mapped through thread metadata;
  metadata is not membership authority.
- The browser reaches Product Backend through `NEXT_PUBLIC_BACKEND_URL` and an
  exact Backend CORS allow-list. CORS is transport policy, not authentication.
- Agent traffic remains Frontend → LangGraph Agent Server. Product Backend and
  a Next.js product-API route do not proxy messages, checkpoints, run status,
  or stream chunks.
- With no approved session title, list labels use `created_at` and a shortened
  `research_session_id`. Reading Agent messages merely to invent a title is
  deferred.

### Still Deferred

Research Progress, Evidence/Sources UI, event replay, session title/status,
session deletion, pagination, Product-managed password/login/token issuance,
Report persistence, RAG, and any final product URL hierarchy remain outside
this slice. D-014 later adds a trusted upstream user identity boundary.

## Permanent Project Knowledge Boundary

**Decision:** D-012

**Scope:** P6-000

**Decision status:** Accepted

**Implementation status:** Implemented and user-validated by P6-002

### Ownership and Meaning

```text
Upstream Authenticated User ID 1
  └── 0..N Projects
             └── 0..N Documents
                        └── 1..N Chunks after a successful create
```

- Product Backend obtains `user_id` from the trusted identity dependency and
  owns `document_id`, Project ownership enforcement, upload/API validation,
  and the transaction outcome.
- 02-Knowledge owns Markdown-to-Chunk transformation, embeddings, similarity
  behavior, and Project-scoped retrieval.
- PostgreSQL remains Product ownership authority. A Chunk derives Project and
  User scope through its Document and Project; no session/thread/run identity
  participates.
- `KnowledgeHit` is a retrieval result. Agent `Evidence` remains a separate,
  provisional graph working Contract until a later adapter is approved.

### Atomic Ingestion Boundary

```mermaid
sequenceDiagram
    participant C as Caller
    participant BE as Product Backend
    participant K as Knowledge
    participant E as Embedding Provider
    participant DB as PostgreSQL / pgvector

    C->>BE: trusted user context + POST Project Markdown Document
    BE->>DB: verify Project owner_user_id + project_id
    BE->>BE: validate filename, media type, bytes, UTF-8, non-empty text
    BE->>K: deterministic chunk(text)
    K->>E: embed all chunks
    E-->>K: vectors
    BE->>DB: one transaction: Document + all Chunks/vectors
    DB-->>BE: commit
    BE-->>C: 201 Document metadata
```

The embedding call occurs before opening the write transaction. It creates no
durable external resource requiring compensation. `201` means the Document is
fully indexed. Any validation, chunking, embedding, or commit failure creates
no Document/Chunk row. This is a bounded synchronous MVP, not a distributed
transaction or asynchronous ingestion design.

### Retrieval Boundary

```mermaid
sequenceDiagram
    participant C as Caller
    participant BE as Product Backend
    participant K as Knowledge
    participant E as Embedding Provider
    participant DB as PostgreSQL / pgvector

    C->>BE: trusted user context + POST /projects/{project_id}/knowledge/search
    BE->>DB: verify Project owner_user_id + project_id
    BE->>K: query + bounded limit
    K->>E: embed query
    K->>DB: Chunks join Documents join Projects; filter user_id + project_id
    DB-->>K: ranked rows
    K-->>BE: typed KnowledgeHit list
    BE-->>C: ordered hits
```

User and Project filtering are part of the authoritative retrieval query.
Frontend selection, path/body user IDs, and LangGraph metadata are not security
or membership filters.

### Contract Shapes

- Document is a Product entity; its validated source text is stored internally
  but is not returned by the first metadata APIs.
- Chunk is an internal indexed record with stable `chunk_id`, `document_id`,
  zero-based order, content, and one embedding vector.
- `KnowledgeHit` contains `document_id`, `chunk_id`, filename, chunk content,
  and a provisional higher-is-better diagnostic score. It is ordered output,
  not a persisted Product entity or final Citation Schema.

### Approved First Physical Baseline

P6-001 verified `pgvector/pgvector:0.8.6-pg18` locally as PostgreSQL 18.6
with pgvector 0.8.6. P6-002 may use the versioned image tag and create the
extension through Alembic. The measured platform digest is retained as Spike
evidence but is not a portable Compose pin.

The configured `BAAI/bge-m3` path returned fixed 1024-dimensional finite
vectors. P6-002 therefore uses `vector(1024)`, verifies every provider result
before persistence/query (including non-zero norm for cosine), and orders exact
cosine distance with `<=>` ascending. The authoritative SQL shape is:

```text
Document Chunk
  JOIN Document ON document_id
  JOIN Project ON project_id
  WHERE Document.project_id = requested project_id
    AND Project.owner_user_id = current user_id
  ORDER BY Chunk.embedding <=> query_vector ASC, Chunk.chunk_id ASC
  LIMIT validated_limit
```

The external diagnostic score is `1 - cosine_distance` and is returned in
descending score order. No approximate vector index is part of the first
slice; the P6-001 HNSW check established operator/index compatibility only.
This keeps Project isolation and exact result ordering independently testable
before scale or recall creates a reason to tune an ANN index.

The first deterministic chunker is structure-aware and domain-independent.
Markdown heading hierarchy and paragraph boundaries are preferred over raw
character windows. Normal blocks are packed up to 2,000 Python characters;
only an overlong structural block uses 2,000-character windows with
200-character overlap. Emitted non-empty chunks retain stable source order and
consecutive zero-based indexes.

### P6-002 Activation — Accepted D-014 Boundary

The user selected both Option A decisions on 2026-09-04. P6-002 implements
Document create/read/list plus search and adds immutable Project
`owner_user_id`. Product Backend receives the opaque UUID through the trusted
`X-ResearchFlow-User-Id` dependency; it does not accept user identity from a
resource path or body and does not implement passwords, login, or token
issuance.

Every Project and nested-resource query filters the current owner. Unknown and
other-user Projects share the same 404 response. The retrieval query independently
joins Project and applies both `owner_user_id` and `project_id` before ordering
and limit. Existing Project rows require explicit
`RESEARCHFLOW_LEGACY_OWNER_USER_ID` migration ownership rather than an invented
default. These decisions activate P6-002.

### Agent Knowledge Boundary — Accepted D-015

The first integration is local/test only. Trusted LangGraph Run context carries
immutable `knowledge_scope` (`user_id + project_id`) outside Agent State, Tool
arguments, and thread metadata. This carrier is not authorization authority and
does not make the direct browser topology production-safe.

Agent `knowledge_search()` calls Product Backend through a typed HTTP client;
Backend remains the authoritative owner/Project filter and Knowledge remains
hidden behind its API. Agent Evidence becomes one discriminated Pydantic union
for temporary research and user uploads, retaining Document/Chunk provenance.
Agent owns the explicit Web/Knowledge Tool registry and deterministic execution
policy. P7-001 implements the adapter and shared Evidence validator; validated
models are dumped to JSON-safe payloads before checkpointed State. P7-002 binds
both Tools using a frozen `AgentContext.knowledge_scope`, validates every Tool
name before side effects, then executes sequentially in model-call order. Any
failure aborts the node without a partial State update or Writer execution.
P7-FE-001 supplies the local-only carrier through one Frontend stream-submit
wrapper. It derives the Project UUID from Product selection and the user UUID
from the existing public local-development setting, and places both in SDK Run
context rather than Graph input, checkpoint State, or thread metadata.
`BUG-P7-STREAM-001` and the final browser matrix are DONE. The fix preserved the
SDK's native multi-mode stream and proved top-level Project scope, reload,
in-flight rejoin, edit/regenerate, and Project A/B Knowledge isolation without
constraining the Frontend to a scalar mode.

## Citation and Retrieval Evaluation Boundary

**Decision:** D-017

**Scope:** P7-003

**Decision status:** Accepted

**Implementation status:** Implemented and validated by P7-003B and P7-003C;
Phase 7 exit remains subject to the D-017 Architect evidence review.

### Citation Projection

```text
validated Evidence[]
  → pure ordered projection
  → Citation(c1), Citation(c2), ...
  → Writer State update { report, citations, final AIMessage }
  → AgentOutputState / latest checkpoint
```

01-Agent owns the Citation models, mapper, and State/output wiring. The mapper
preserves Evidence order and duplicates and copies only source label, a
deterministic bounded excerpt, and approved source-specific provenance. It does
not parse ToolMessage or Report text, use retrieval score as authority, or
create Product identities. Report and Citation list are updated together so a
later failed/in-flight run does not pair a new Report with old Citations or the
reverse.

Run-local `c1...` values identify entries only within one successful output.
They do not identify a LangGraph Run, thread, Research Session, persisted
Evidence, or Product Citation. Without inline Report markers, the list means
“sources available to this Writer run,” not “each Report claim is correctly
attributed.” Frontend rendering, Report persistence, claim mapping, and event
replay are separate future Contracts.

### Retrieval Evaluation

```text
versioned logical JSON fixture
  → isolated Backend Document ingestion
  → runtime UUID resolution in test setup only
  → scoped POST knowledge/search (limit=5)
  → logical returned passages
  → per-case + macro Recall@5 baseline
```

05-Quality owns the fixture, metric implementation, and reported baseline.
02-Knowledge reviews deterministic chunk identity and retrieval semantics;
03-Backend reviews that the harness exercises the existing scoped API and test
database. Checked-in relevance uses `project_key + document_key + chunk_index`,
never generated UUIDs. No production Chunk API or evaluation table is created.

The first run used the current `BAAI/bge-m3` exact-vector path and recorded
macro Recall@5 = 1.0 across three synthetic AI-reviewed cases, without a
pass/fail threshold. A poor future score is evidence, not a reason
to relabel the fixture or change the retriever inside the evaluation task. MRR,
NDCG, Precision@K, citation correctness, LangSmith, and retrieval optimization
remain unapproved until this baseline is reviewed.
