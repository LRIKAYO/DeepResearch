# Phase 3 — Product Backend First Vertical Slice

**Status:** DONE — Engineering Exit Criteria passed on 2026-08-30.

> Engineering goal: establish the first product-owned API and persistence
> boundary without turning FastAPI into a proxy for LangGraph chat.  
> Planning scope: only the next two executable tasks.  
> Learning strategy remains owned by the user / Project Mentor; the importance
> ratings below are Architect recommendations.

## Current Repository Facts

- The repository now has a FastAPI application at
  `researchflow.backend.app:app`, a concrete Project module, synchronous
  SQLAlchemy/Psycopg persistence, Alembic, API Contracts, and a Product Data
  Model.
- `pyproject.toml` keeps Backend packages in the optional `backend` dependency
  group and constrains SQLAlchemy to 2.x.
- The Frontend talks directly to LangGraph Agent Server through `useStream`.
  Messages, threads, runs, checkpoint refresh, and in-flight reconnect already
  work without a Product Backend adapter.
- `project_id` is now an implemented Product Backend identity. `thread_id` and
  `run_id` remain Agent Server identities; `research_session_id`, `report_id`,
  and `user_id` do not exist in Product Backend code.
- The provisional Agent `Evidence` type is internal working state, not a
  Product Backend entity.
- The repository has one local `postgres:18.6` Compose service with persistent
  development data and a separate test database. Gate A validated the healthy
  service, both migrated databases, restart persistence, and 20 Backend + Agent
  tests.

## Engineering Phase Goal

Create one meaningful Product Backend vertical slice around the smallest
product-owned resource: a Project. The slice must prove:

```text
HTTP request
  → FastAPI request Contract
  → Project use case
  → business persistence
  → FastAPI response Contract
```

A health-only service or a pass-through chat proxy does not satisfy this goal.

## Constraints

- Basic chat and streaming remain Frontend → LangGraph Agent Server.
- FastAPI routes stay thin; Agent reasoning does not move into route handlers.
- LangGraph `thread_id` / `run_id` do not become Project primary keys.
- Do not introduce `research_session_id`, `report_id`, `user_id`, Auth, RAG, or
  Evidence persistence before their relationships are required.
- Do not create a repository interface, generic CRUD framework, or service
  split with only one implementation.
- Select the production and test persistence path from the real local
  environment in P3-000 before writing database code.

## Dependency Order

```text
P3-000 Product Backend Contract and persistence boundary
        ↓
P3-001 Project API vertical slice
        ↓
stop, inspect the repository, and choose the next product capability
```

## P3-000 — Product Backend Contract and Persistence Boundary

**Status:** DONE — approved as D-009 and recorded in
`docs/API_CONTRACTS.md`, `docs/DATA_MODEL.md`, and `docs/ARCHITECTURE.md`.

**Goal**

Approve the minimum Project resource, API boundary, persistence approach, and
Backend package/runtime location before implementation.

**Why Now**

The Product Backend currently owns nothing. Starting from FastAPI boilerplate
would leave its purpose undefined and risks duplicating LangGraph Server.

**Scope**

- Confirm Project as the first Product Backend-owned resource.
- Define the minimum Project fields, ID generation authority, timestamps, and
  create/read lifecycle.
- Define request, response, validation, not-found, and error Contracts for the
  first Project endpoints.
- Select the business persistence stack, migration mechanism, and repeatable
  local/test database prerequisite using the actual workspace environment.
- Decide the Backend package/runtime entrypoint and dependency grouping.
- Record that Frontend streaming continues to bypass Product Backend.
- Mark every ID/resource as current, approved-next, or deferred.

**Out of Scope**

- Backend implementation, migrations, Docker, deployment, and CI.
- Project update/delete, users, memberships, Auth, research sessions, reports,
  documents, RAG, Evidence, Agent invocation, and event replay.

**Owner**

00-Architect with 03-Backend review.

**Development Mode**

PAIR

**Learning Importance**

HIGH. This establishes where business identity and persistence live, and keeps
the Product Backend separate from LangGraph execution infrastructure.

**Learning Goal**

The user should be able to explain:

1. Why a Product Backend exists when LangGraph Server already serves runs.
2. Which module creates and validates `project_id`.
3. The request-to-database-to-response data flow.
4. Why `thread_id` and `run_id` cannot identify a Project.
5. Which decisions are intentionally deferred.

The user should personally draft the Project field/lifecycle table and one
request/response Contract. AI may inspect libraries/environment, propose
placement, and review the result.

**Deliverables**

- `docs/API_CONTRACTS.md`
- `docs/DATA_MODEL.md`
- Updated `docs/ARCHITECTURE.md`
- Updated `docs/DECISIONS.md`

**Acceptance Criteria**

- Current facts and approved-next design are clearly separated.
- Project has one ID authority and an unambiguous minimal lifecycle.
- API request/response/error shapes are concrete enough to test.
- Persistence and migration choices name their trade-offs and local
  prerequisites.
- No FastAPI chat proxy or speculative product ID relationship is introduced.
- P3-001 can be implemented without inventing an additional Contract.

## P3-001 — Project API Vertical Slice

**Status:** DONE — initial Review findings were corrected and Architect
re-review passed. Final evidence is recorded in `docs/tasks/P3-001.md`.

**Runtime validation:** Gate A used reachable PostgreSQL 18 development and
test databases through `RESEARCHFLOW_DATABASE_URL` and
`RESEARCHFLOW_TEST_DATABASE_URL`.

**Goal**

Implement one persisted Project create/read path through a minimal FastAPI
application using the P3-000 Contracts.

**Why Now**

This is the smallest vertical slice that proves Product Backend ownership,
input validation, business persistence, migrations, and response stability.

**Scope**

- Add the approved Backend package/runtime entrypoint and dependencies.
- Add a minimal local Compose configuration with one PostgreSQL 18 service,
  persistent development data, a separate test database, and health check.
- Add explicit runtime/test database URL configuration and a local runbook.
- Add a health endpoint for service readiness.
- Add the initial Project migration.
- Implement `POST /projects` and `GET /projects/{project_id}`.
- Keep the route layer thin and use the shortest concrete persistence module
  that enforces the approved Contract.
- Add focused API and persistence tests, including validation and not-found.

**Out of Scope**

- Generic CRUD, Project update/delete/list unless a concrete caller requires
  it, repository interfaces, event buses, and background jobs.
- Frontend integration, Agent calls, Research Session association, Auth,
  Knowledge/RAG, Evidence, production Dockerfile/application container,
  deployment, and CI/CD.

**Owner**

03-Backend; 00-Architect reviews boundaries; 05-Quality reviews Contract tests.

**Development Mode**

DELEGATE

**Learning Importance**

HIGH. This is the first complete Product Backend request and persistence path;
its layering pattern will be reused by later business resources.

**Learning Goal**

The user should be able to locate and trace the FastAPI entrypoint, Pydantic
request/response Schemas, Project persistence mapping, transaction boundary,
migration, and Contract tests.

The Product Backend Engineer implements the slice. The user should review and
be able to trace the request/response Schemas, one create/read path, transaction
boundary, migration, and separation between runtime and test databases. A
later user-owned field-change challenge may validate modification ability; it
is not a completion blocker for this delegated task.

**Deliverables**

- Product Backend application package and runtime command.
- Root `compose.yaml`, PostgreSQL initialization script, environment examples,
  and `docs/BACKEND_LOCAL_DEV.md`.
- Initial Project migration and persistence implementation.
- Focused Backend tests.
- Updated setup documentation and decisions where implementation differs from
  P3-000 assumptions.
- Implementation instructions in `docs/tasks/P3-001.md`.

**Acceptance Criteria**

- `docker compose config` succeeds; with the engine running, PostgreSQL becomes
  healthy and exposes separate `researchflow` and `researchflow_test`
  databases.
- The approved migration applies cleanly to both empty databases.
- The FastAPI application starts and its health endpoint succeeds.
- Project create → persisted read round-trip matches the approved API Contract.
- Invalid input and missing Project behavior match the approved error Contract.
- Data survives application restart against the approved business database.
- Agent tests still pass and Frontend streaming requires no Product Backend.
- The completion handoff explains the request-to-database call chain and the
  runtime/test database boundary without claiming user mastery.

## Batch Stop and Exit Criteria

Phase 3 stops after P3-001. Repository inspection confirms the Engineering Exit
Criteria below. The next Phase Goal remains owned by the user / Project Mentor;
the Architect recommendation is to define the Research Session ↔ LangGraph
thread association before adding disconnected Document metadata.

**Engineering Exit Criteria**

- One Product Backend service and one persisted Project resource work end to
  end.
- API, migration, persistence, and tests agree on the same Contract.
- Existing Frontend → Agent Server streaming remains unchanged.

**Exit Result:** PASSED on 2026-08-30.

**Learning-relevant Findings to Capture**

- The request → Schema → use case → transaction → response call chain.
- Which Backend boundaries the user should reuse in the next resource.
- Any persistence or migration friction that changes the next rolling plan.

Do not claim the user has mastered these topics until explanation and a later
field-change exercise verify them.
