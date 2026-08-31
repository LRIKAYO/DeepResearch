# Phase 4 — Project-scoped Research Session Boundary

**Status:** DONE — P4-000 and P4-001 complete; batch stop reached.

> Engineering goal: connect the implemented Project resource to LangGraph
> conversation execution through one product-owned Research Session identity,
> without proxying chat streams through Product Backend.  
> Planning scope: only the first two executable tasks.  
> Learning strategy remains owned by the user / Project Mentor; the importance
> ratings below are Architect recommendations.

## Current Repository Facts

- Product Backend implements Project create/read/list and Research Session
  create/read/list through Alembic revisions `20260830_0001` and
  `20260831_0002`.
- The Frontend still talks directly to LangGraph Agent Server through
  `useStream` and stores `threadId` in the URL.
- With no current `threadId`, the installed JavaScript SDK 1.8.10 creates a
  LangGraph thread before starting the first run and invokes `onThreadId`.
- The installed Python `langgraph-sdk` 0.4.3 exposes synchronous
  `threads.create`, `threads.get`, and `threads.delete` operations suitable for
  the synchronous Backend.
- A LangGraph thread owns checkpointed conversation state across multiple runs.
  A run is one invocation and already has Agent Server authority under D-008.
- Product Backend provisions LangGraph threads through the official synchronous
  SDK and persists the Project/session/thread association in PostgreSQL.

## Engineering Phase Goal

Establish this identity and data flow:

```text
Project
  → Product Backend creates Research Session identity
  → Product Backend provisions one LangGraph thread
  → Product Backend persists the immutable association
  → Frontend receives thread_id
  → Frontend continues direct useStream execution on that thread
  → one or more Agent Server runs occur under the same session/thread
```

This Phase is about product/execution association. It does not introduce
Report, Evidence, Document, or Knowledge persistence.

## Constraints

- Product Backend owns `research_session_id` and the Project association.
- LangGraph Agent Server remains the authority that creates `thread_id` and
  every `run_id`.
- One Research Session maps to exactly one immutable LangGraph thread in this
  Phase. One thread cannot be attached to several sessions.
- One session/thread may have zero or many runs. Do not store a `last_run_id`
  or infer session status from one run.
- Product IDs and LangGraph IDs do not enter Agent Graph State.
- Backend may use LangGraph's official SDK for thread control-plane operations;
  it must not proxy messages, stream chunks, checkpoints, or run execution.
- Product Backend remains authoritative for session membership. LangGraph
  thread metadata is a diagnostic/search projection, not the business record.
- Do not introduce a distributed transaction framework. If database
  persistence fails after thread creation, make one best-effort thread delete
  and log an orphan if compensation fails.

## Dependency Order

```text
P4-000 Research Session identity and provisioning Contract
        ↓
P4-001 Backend Research Session vertical slice
        ↓
stop, inspect the real cross-service behavior, then plan Frontend adoption
```

## P4-000 — Research Session Identity and Provisioning Contract

**Status:** DONE — approved as D-010 and recorded in the architecture, API,
and Data Model documents.

**Goal**

Define the smallest product identity, cardinality, creation authority, failure
boundary, and HTTP Contract that associates a Project with LangGraph execution.

**Why Now**

Project persistence and Agent streaming both work, but nothing establishes
which LangGraph conversation belongs to which Project. Adding UI or Documents
before this boundary would preserve a global, unscoped thread model.

**Scope**

- Decide Project → Research Session → thread → run cardinality.
- Define ID/time authority and the minimum Research Session fields.
- Decide who provisions the LangGraph thread and how failures are compensated.
- Define create/read/list HTTP Contracts required by the next Backend slice.
- Define Backend/Agent Server/Frontend ownership without changing Graph State.
- Record explicitly deferred lifecycle and persistence concerns.

**Out of Scope**

- Backend or Frontend implementation.
- Messages, run creation, streaming proxy, checkpoint storage, or Agent graph
  changes.
- Session status/title/update/delete, Report/Evidence persistence, events,
  Auth, RAG, Documents, uploads, and Knowledge ingestion.
- General idempotency infrastructure or a distributed transaction coordinator.

**Owner**

00-Architect with 01-Agent, 03-Backend, and 04-Frontend boundary review.

**Development Mode**

PAIR

**Learning Importance**

HIGH. This is the first durable relationship between a product identity and
LangGraph execution identities.

**Learning Goal**

The user should be able to explain:

1. Why `research_session_id`, `thread_id`, and `run_id` are three identities.
2. Why one session can contain several runs without storing those runs now.
3. Why Backend provisions a thread but does not proxy its stream.
4. Which system is authoritative when thread metadata and PostgreSQL disagree.
5. What happens if Agent thread creation or database persistence fails.

**Deliverables**

- D-010 in `docs/DECISIONS.md`.
- Research Session boundary in `docs/ARCHITECTURE.md`.
- Approved-next resource in `docs/DATA_MODEL.md`.
- Approved-next endpoints in `docs/API_CONTRACTS.md`.
- This rolling plan.

**Acceptance Criteria**

- Cardinality and authority are explicit and do not overload any ID.
- The creation flow has a concrete failure/compensation boundary.
- API and Data Model shapes are testable without inventing frontend behavior.
- Basic streaming remains Frontend → LangGraph Agent Server.
- No Product ID is added to Agent State and no `run_id` column is introduced.

## P4-001 — Backend Research Session Vertical Slice

**Status:** DONE — engineering Gate A and PAIR learning Gate B verified on
2026-08-31.

**Goal**

Implement Project listing and the first Project-scoped Research Session
create/read/list flow, including real LangGraph thread provisioning.

**Why Now**

The Contract is approved. This is the smallest slice that proves PostgreSQL can
own product membership while LangGraph Agent Server continues to own execution.
Project listing is included because the following Frontend batch has a concrete
need to select a Project before listing its sessions.

**Scope**

- Add `GET /projects` using the existing Project response shape, ordered newest
  first.
- Add required `RESEARCHFLOW_LANGGRAPH_URL` and `RESEARCHFLOW_GRAPH_ID`
  configuration examples without introducing a settings framework.
- Add the verified Python LangGraph SDK to the Backend dependency boundary.
- Add an `agent_server.py` control-plane module using the synchronous official
  SDK; do not import `researchflow.agent` implementation modules.
- Add the Research Session mapping and a second Alembic migration.
- Implement the approved create/read/list endpoints.
- On create: validate Project, generate `research_session_id`, provision the
  thread with Project/session metadata and configured graph ID, then persist
  the association.
- Sanitize Agent service failures. If persistence fails after thread creation,
  attempt one compensating thread delete without hiding the original failure.
- Add focused PostgreSQL API tests with a fake Agent client plus one real local
  Backend ↔ Agent Server smoke.
- Keep all existing Backend, Agent, and migration checks green.

**Out of Scope**

- Frontend changes or CORS policy.
- FastAPI message/run/stream proxy endpoints.
- Persisting messages, checkpoints, run rows, session status, latest run,
  title, Report, Evidence, events, or progress.
- Session update/delete, Project delete, pagination, Auth, multi-tenant access,
  generalized retries, outbox, saga, or background reconciliation.

**Owner**

03-Backend; 00-Architect reviews identity and failure boundaries; 05-Quality
reviews Contract and cross-service smoke evidence.

**Development Mode**

PAIR

**Learning Importance**

HIGH. The important part is not another table; it is the synchronous boundary
between a product transaction and an externally owned execution resource.

**Learning Goal**

The user should personally trace and preferably implement the create path from
Project validation through thread provisioning and database commit. AI may
assist with migration boilerplate, fake client setup, list endpoints, and
regression checks.

The user should be able to locate:

- Product and Research Session validation;
- the LangGraph SDK boundary;
- the transaction boundary;
- best-effort compensation;
- the point where the returned `thread_id` becomes usable by `useStream`.

**Deliverables**

- Updated Backend dependencies and environment examples.
- Minimal Agent Server control-plane module.
- Research Session mapping and Alembic migration.
- Project list and Research Session create/read/list endpoints.
- Focused tests and real local cross-service smoke evidence.
- Updated local Backend runbook.

**Acceptance Criteria**

- Migration upgrades both PostgreSQL databases and `alembic check` reports no
  drift.
- `GET /projects` returns Project responses newest first.
- Creating a session under a missing Project returns the approved `404` and
  does not call Agent Server.
- With a real local Agent Server, create returns `201`; the returned thread
  exists on Agent Server with matching Project/session metadata and one
  matching PostgreSQL row.
- Agent Server failure returns the approved sanitized `503` and creates no
  Research Session row.
- A simulated database failure after thread creation attempts exactly one
  delete of that thread.
- A session can be read only under its owning Project; list results are scoped
  to that Project and ordered newest first.
- Reusing one returned thread for several Agent runs requires no database row
  or Graph State change per run.
- All existing Backend and Agent tests pass.
- The user can explain the five P4-000 Learning Goal questions. A later small
  list-filter change may be used as Gate C; it is not part of this slice.

## Batch Stop

Stop after P4-001 and inspect the real service-to-service behavior. Only then
plan the small Frontend batch that replaces global Agent thread discovery with
Project-scoped Research Session discovery while retaining direct `useStream`.
