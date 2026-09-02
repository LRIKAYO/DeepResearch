# Phase 5 — Project-scoped Frontend Adoption

**Status:** DONE — P5-000, P5-001, and P5-002 are complete; the Phase exit
criteria were verified by `QUALITY-SCAN-003`.

> Engineering goal: replace global LangGraph thread discovery with the
> implemented Project/Research Session control plane while preserving direct
> Frontend → Agent Server streaming.  
> Planning scope: this first batch contains three tasks only.  
> Learning strategy remains owned by the user / Project Mentor; the importance
> ratings below are Architect recommendations.

## Current Repository Facts

- Phase 5 is implemented and the current `QUALITY-SCAN-003` baseline is PASS
  WITH FINDINGS with no Blocker, High, or Medium finding.
- Product Backend implements Project create/read/list and Project-scoped
  Research Session create/read/list.
- Creating a Research Session provisions one LangGraph thread and persists the
  immutable association in PostgreSQL.
- The Frontend discovers Projects and Research Sessions through Product Backend,
  uses `projectId` / `researchSessionId` navigation, and derives `thread_id`
  from the selected Session.
- Direct local browser calls use `NEXT_PUBLIC_BACKEND_URL` and the Backend's
  exact-origin CORS allow-list.
- The current UI already renders messages, tool calls, interrupts, completed
  checkpoint state, and resumable streams; those capabilities should remain
  intact.

## Engineering Phase Goal

```text
projectId + optional researchSessionId
        ↓
Product Backend Project/Session discovery
        ↓
selected Research Session.thread_id
        ↓
useStream(thread_id)
        ↓
direct LangGraph run/stream and existing UI rendering
```

The Phase is only a thin product-scope bridge. It does not redesign Agent Chat
UI or introduce product Evidence, Progress, replay, or Report persistence.

## Constraints

- PostgreSQL remains the authority for Project/session membership.
- `thread_id` is derived from a selected Research Session, not treated as a
  product-navigation identity.
- Product Backend serves control-plane resources only; it does not proxy Agent
  runs or streams.
- `useStream` must not auto-create a thread before a Product Session exists.
- Existing Agent message/tool/interrupt rendering and reconnect behavior remain
  the data-plane implementation.
- CORS uses exact configured origins; wildcard origins and credentials are not
  introduced before Auth is designed.
- No code in this batch is required to be handwritten by the user. Because the
  user's learning priority is Backend, review should focus only on tracing the
  identity handoff across the three systems.

## Dependency Order

```text
P5-000 Frontend product-selection Contract (DONE)
        ↓
P5-001 Browser-to-Backend reachability
        ↓
P5-002 Project-scoped Frontend session adoption
        ↓
batch stop and Quality review
```

## P5-000 — Frontend Product-selection Contract

**Status:** DONE — recorded as D-011 and in `docs/ARCHITECTURE.md`.

**Goal**

Define the smallest navigation, discovery, provisioning, and streaming boundary
needed for the Frontend to consume the implemented Project/Research Session
APIs without overloading `thread_id`.

**Why Now**

Phase 4 proved the Backend-to-Agent association, but the current Frontend still
bypasses it by globally discovering Agent threads. Implementation must not
start until the product and execution identities have one unambiguous handoff.

**Scope**

- Define canonical URL selection using `projectId` and
  `researchSessionId`.
- Define `thread_id` as a value derived from the authoritative session response.
- Define Project/session discovery, new-session provisioning, refresh, invalid
  selection, and legacy `threadId` behavior.
- Choose direct browser Product Backend calls with exact CORS allow-listing.
- Preserve direct Frontend → Agent Server streaming.

**Out of Scope**

- Backend or Frontend implementation.
- New API endpoints, database fields, session title/status, or Auth.
- Agent changes, stream proxying, Progress/Evidence events, replay, and RAG.

**Owner**

00-Architect, with 03-Backend and 04-Frontend implementation review.

**Development Mode**

DELEGATE

**Learning Importance**

MEDIUM. The identity handoff matters architecturally, but this thin Frontend
bridge is not a priority implementation skill for the user.

**Learning Goal**

At review level, the user should be able to trace why product navigation uses
`researchSessionId` while `useStream` still needs the associated `thread_id`.
No personal code contribution or mastery claim is required.

**Deliverables**

- D-011 in `docs/DECISIONS.md`.
- Project-scoped Frontend adoption boundary in `docs/ARCHITECTURE.md`.
- This rolling plan.

**Acceptance Criteria**

- Product and execution identities are not overloaded.
- The flow cannot create an unrecorded LangGraph thread.
- Product discovery and Agent streaming authorities remain separate.
- Legacy standalone `threadId` is not adopted through diagnostic metadata.
- No new API, product field, or event schema is invented.

## P5-001 — Browser-to-Backend Reachability

**Status:** DONE — see `docs/tasks/P5-001.md`.

**Goal**

Allow the local browser Frontend to call Product Backend through one explicit,
minimal CORS configuration boundary.

**Why Now**

P5-002 needs direct browser calls to the already implemented Project and
Research Session endpoints. Without an approved origin policy, the Frontend
cannot exercise that control plane from `localhost:3000`.

**Scope**

- Add `RESEARCHFLOW_CORS_ORIGINS` as a comma-separated exact allow-list.
- Add FastAPI CORS middleware only when at least one origin is configured.
- Permit the methods and headers required by current GET/POST JSON requests and
  preflight; keep credentials disabled.
- Add local example values for `http://localhost:3000` and
  `http://127.0.0.1:3000`.
- Add focused tests for an allowed preflight and an unlisted origin.
- Update the Backend local runbook.

**Out of Scope**

- Auth, cookies, wildcard origins, deployment ingress, reverse proxies, HTTPS,
  rate limits, or a settings framework.
- Any Product API, data-model, Agent, or Frontend component change.
- Proxying LangGraph messages or streams.

**Owner**

03-Backend; 00-Architect reviews transport and security boundaries; 05-Quality
reviews regression evidence.

**Development Mode**

DELEGATE

**Learning Importance**

LOW. This is browser transport configuration, not a core Agent or Backend
domain boundary.

**Learning Goal**

The user only needs to distinguish CORS permission from authentication and know
where local allowed origins are configured. AI may implement the complete task.

**Deliverables**

- Minimal Backend CORS configuration.
- Updated `.env.example` and `docs/BACKEND_LOCAL_DEV.md`.
- Focused Backend regression tests.
- `docs/tasks/P5-001.md` Completion Report.

**Acceptance Criteria**

- A preflight from each configured local origin receives the expected CORS
  allow-origin response.
- An unlisted origin receives no allow-origin response.
- Credentials and wildcard origins are not enabled.
- Project and Research Session response/error Contracts are unchanged.
- Backend and Agent tests pass; Alembic still reports no drift.

## P5-002 — Project-scoped Frontend Session Adoption

**Status:** DONE — Gate A, Product/session control-plane smoke, direct Agent
report-stream smoke, and `QUALITY-SCAN-003` review passed.

**Goal**

Replace global Agent thread history with minimal Project/Research Session
selection and bind the selected session's thread to the existing `useStream`.

**Why Now**

The product association now exists end to end. Continuing to discover global
Agent threads would bypass Project scope and let the SDK create conversations
that Product Backend does not know about.

**Scope**

- Add `NEXT_PUBLIC_BACKEND_URL` and a small typed client for the existing
  Project/Research Session endpoints.
- Add minimal Project list/select/create behavior.
- List only Research Sessions returned under the selected Project.
- Add **New research** provisioning; prevent repeat clicks while it is pending.
- Store canonical `projectId` and optional `researchSessionId` navigation state.
- Derive `thread_id` from the selected session and pass it to `useStream`.
- Disable message submission until a session/thread is selected.
- Remove global `client.threads.search`, the delayed history refetch, and
  standalone `threadId` product selection.
- Keep existing message, tool, interrupt, checkpoint refresh, and in-flight
  reconnect behavior.
- Show minimal loading, empty, and sanitized error states. Use creation time and
  shortened session ID as the temporary list label.
- Update the Frontend README and add focused tests where the current test shape
  supports them; record one local browser smoke.

**Out of Scope**

- UI redesign, styling cleanup, existing unrelated lint-warning cleanup, and
  session title/status/delete/pagination.
- Auth, Next.js Product Backend proxy/BFF, or Agent stream proxying.
- Agent Graph changes, Progress/Evidence rendering, replay, Report persistence,
  Documents, Knowledge, and RAG.
- Reverse-mapping or adopting a standalone legacy LangGraph thread.

**Owner**

04-Frontend; 00-Architect reviews the identity/authority handoff; 03-Backend
supports only Contract defects; 05-Quality reviews the final smoke.

**Development Mode**

DELEGATE

**Learning Importance**

MEDIUM. The implementation is Frontend work, but the Project → Session → thread
handoff is important for later Backend-owned resources.

**Learning Goal**

The user should review one trace from URL product IDs to the Backend session
response and then to `useStream(thread_id)`. AI may implement the Frontend code;
the user is not required to handwrite it.

**Deliverables**

- Minimal Product Backend client and Project/Research Session UI state.
- Project-scoped history and new-session flow.
- Updated stream binding and Frontend configuration documentation.
- Focused automated checks plus a recorded local browser smoke.
- `docs/tasks/P5-002.md` Completion Report.

**Acceptance Criteria**

- No global LangGraph thread-search request occurs in the product history flow.
- Selecting a Project shows only that Project's sessions.
- **New research** returns one Backend-owned session before message submission
  can occur; rapid repeat interaction does not create a second session.
- The URL contains product selection, not a standalone `threadId`.
- Selecting or refreshing a valid session binds its persisted `thread_id` to
  `useStream` and restores existing checkpointed messages.
- Switching Project clears an incompatible session and cannot display another
  Project's thread.
- A message run and its streamed final output still travel directly between
  Frontend and Agent Server; Product Backend receives no message/stream request.
- Existing tool/interrupt rendering and native reconnect configuration remain.
- Type check, production build, lint, Backend/Agent regressions, and the local
  Project → Session → stream smoke pass with no new error-level finding.

## Phase Exit Criteria

### Engineering Exit Criteria

- Browser, Product Backend, PostgreSQL association, and direct Agent stream form
  one verified Project-scoped path.
- Product navigation no longer depends on global Agent thread discovery.
- Refresh uses Product Backend for membership and Agent Server for checkpointed
  conversation state.
- Quality has reviewed the recorded smoke and regression evidence.

### Learning-relevant Findings

- The Project/session/thread identity handoff is worth tracing once because
  later Report, Evidence, and Knowledge relationships will attach at product
  boundaries rather than to arbitrary UI state.
- No Frontend mastery is claimed or required by this Phase. Any later learning
  assessment must use explanation or modification evidence, not task completion.

## Batch Stop

The batch stop was reached after P5-002 and `QUALITY-SCAN-003`. The real
browser-to-control-plane and browser-to-data-plane behavior has been inspected;
Phase 6 planning may begin from the resulting repository baseline.
