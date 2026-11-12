# Phase 2 — Minimal Frontend Integration

> Engineering goal: connect the existing ResearchFlow LangGraph Server to a minimally modified Agent Chat UI.  
> User priority: move quickly through Frontend and preserve attention for Backend.  
> Planning scope: only the next three executable tasks.

## Current Repository Facts

- Phase 1 provides the registered LangGraph graph ID `researchflow`, top-level `messages`, thread/checkpoint support, streamed Report/final AIMessage, and a repeatable SDK smoke script.
- The ResearchFlow repository has no Frontend code yet.
- `references/agent-chat-ui-main/` is a working Next.js snapshot without Git metadata. No commit SHA is asserted.
- The upstream UI already owns LangGraph Client, `useStream`, thread creation/history, message rendering, Tool rendering and Interrupt rendering.
- ResearchFlow has no approved Research Event, persistence or replay Contract.

## Dependency Order

```text
P2-001 adopt/build upstream UI
        ↓
P2-002 basic UI ↔ LangGraph smoke
        ↓
P2-003 define Research Event/persistence/replay boundary
        ↓
future Research Progress / Evidence UI
```

P2-003 does not block basic chat. It blocks adding ResearchFlow-specific progress/evidence rendering.

## P2-001 — Adopt Agent Chat UI Baseline

**Goal**

Create `frontend/` from the current Agent Chat UI reference snapshot and configure its local default connection for ResearchFlow.

**Why Now**

The server boundary already works. Reimplementing Client, `useStream`, thread state or message rendering would add risk without product value.

**Scope**

- Copy the upstream application source/configuration into `frontend/` without generated files, dependencies, logs, local secrets or upstream Git metadata.
- Retain the upstream MIT license and record snapshot provenance without inventing a commit SHA.
- Rename the package/readme for ResearchFlow ownership.
- Set `.env.example` defaults to `http://127.0.0.1:2024` and assistant/graph ID `researchflow`.
- Install from the copied lockfile and run formatting/type/build validation exposed by the application.

**Out of Scope**

- Visual redesign, Research dashboard, Evidence panel or progress timeline.
- Research Event/custom stream schema.
- FastAPI proxy, Auth, production deployment and Docker.
- Editing Agent Graph behavior to satisfy UI assumptions.

**Owner**

04-Frontend; 00-Architect reviews Contract/provenance.

**Development Mode**

DELEGATE

**Learning Importance**

LOW. This is mainly upstream adoption, package configuration and build hygiene.

**Learning Goal**

The user only needs to know the Frontend entrypoint, environment variables and where `useStream` is configured.

**Deliverables**

- `frontend/`
- Updated `docs/DECISIONS.md`

**Acceptance Criteria**

- `pnpm install --frozen-lockfile` succeeds.
- Formatting/type/build checks succeed.
- No `node_modules`, `.next`, local `.env`, logs or reference-only generated files enter the repository.
- Default local configuration selects graph ID `researchflow`.
- Upstream license and snapshot provenance are retained.

## P2-002 — Basic Agent Chat UI Integration Smoke

**Goal**

Prove the existing UI can submit a text request to the ResearchFlow graph, receive streamed messages, associate a server thread and render the final Report.

**Why Now**

A successful SDK smoke proves the protocol but not the browser-side `StreamContext/useStream → render` path.

**Scope**

- Run LangGraph Server and Next.js locally with the documented connection values.
- Verify `/info` connectivity and registered assistant/graph selection.
- Submit one basic research request and observe thread creation, URL `threadId`, Tool trace and final AIMessage/Report.
- Refresh/reopen the thread and verify server state is restored through existing history handling.
- Record a short repeatable smoke procedure.

**Out of Scope**

- ResearchFlow-specific progress/evidence UI.
- Automated browser suite unless a real regression requires it.
- Auth, production proxy, deployment and UI styling.

**Owner**

04-Frontend; 05-Quality validates smoke; 00-Architect reviews the boundary.

**Development Mode**

DELEGATE

**Learning Importance**

LOW. The important learning already occurred in Phase 0/1; this task validates integration rather than teaching Frontend internals.

**Learning Goal**

The user should be able to locate `apiUrl`, `assistantId`, `threadId` and the `useStream` entrypoint, but does not need to implement the UI personally.

**Deliverables**

- Minimal configuration fixes, if the smoke reveals any.
- A repeatable local smoke procedure in the Frontend README.

**Acceptance Criteria**

- Browser request reaches graph ID `researchflow` without a custom adapter.
- First submit creates a server thread and updates the URL `threadId`.
- Standard AIMessage/ToolMessage updates render through existing components.
- Final Report renders as the final AIMessage.
- Refreshing the thread restores server-backed history.

## P2-003 — Research Event, Persistence and Replay Boundary

**Status:** DONE — accepted as D-008 and documented in
`docs/ARCHITECTURE.md`. No Progress/Evidence implementation was added.

**Goal**

Define the cross-module Contract that must exist before ResearchFlow adds run-level progress or Evidence UI.

**Why Now**

Basic messages/tool traces can be reused directly, but Research Progress and Evidence cannot safely be inferred from ToolMessage text or accidental subgraph events.

**Scope**

- Classify proposed data as durable Graph State, replayable domain event or transient UI-only state.
- Define ownership between Agent, LangGraph Server, Frontend and future Product Backend.
- Decide ordering/identity requirements and the minimum relationship to `thread_id` and a research run.
- Define what refresh/reconnect is expected to reconstruct.
- Record the decision in `docs/DECISIONS.md` and the relevant architecture/API contract document when concrete fields are approved.

**Out of Scope**

- Final Evidence Schema, database tables or retention policy.
- Implementing custom events, replay storage or UI components.
- RAG, PostgreSQL, FastAPI and Auth implementation.

**Owner**

00-Architect; reviewed by 01-Agent, 03-Backend and 04-Frontend owners.

**Development Mode**

PAIR

**Learning Importance**

HIGH. This decision controls future Agent/Backend/Frontend coupling even though the Frontend implementation itself is low priority.

**Learning Goal**

The user should be able to explain why Graph State, a streamed event and a persisted/replayed event are not interchangeable.

**Deliverables**

- Approved architecture decision and module ownership matrix.
- Contract questions explicitly deferred to the Evidence/Data Model phase.

**Acceptance Criteria**

- Frontend is not required to infer progress/evidence from ToolMessage text.
- The Contract distinguishes live streaming, refresh/reconnect and historical replay.
- Persistence ownership is explicit without prematurely selecting a database schema.
- No implementation begins until Agent, Backend and Frontend owners can consume the same Contract.

## Rolling Planning Stop

P2-003 identified one concrete closeout gap, so the Architect approved only the
following narrow follow-up. Do not plan a Research dashboard from this batch.

## P2-004 — Native In-flight Reconnect Closeout

**Status:** DONE

**Goal**

Use the installed SDK's native reconnect path so a remounted Frontend can rejoin
the same active Agent Server Run.

**Why Now**

P2-003 found that submissions were resumable on the Server, but the Frontend did
not preserve the active `run_id` across a remount.

**Scope**

- Enable `reconnectOnMount` in the existing `useStream` configuration.
- Smoke one active-run refresh and one terminal-run refresh.
- Keep `Run.status` authoritative and loading presentation transient.

**Out of Scope**

- Progress/Evidence UI, custom events, replay storage, or a custom reconnect
  implementation.
- Real Web-provider behavior; the reconnect smoke uses a deterministic local
  slow graph so it does not depend on paid credentials.

**Owner**

04-Frontend; 00-Architect reviews the recovery boundary.

**Development Mode**

DELEGATE

**Learning Goal**

Locate the single `useStream` option that connects session-stored `run_id` to
SDK `joinStream(...)`; no custom Frontend state machine is needed.

**Deliverables**

- Frontend reconnect configuration.
- Updated Frontend smoke procedure and architecture facts.

**Acceptance Criteria**

- Before refresh, Agent Server reports the run as `pending` or `running`.
- Remount rejoins the same `run_id` and renders the terminal output.
- After `success`, SDK reconnect metadata is removed.
- A later terminal refresh restores history without leaving loading active.

## Phase 2 Engineering Exit

Minimal Frontend integration, checkpoint refresh, and native in-flight rejoin
are complete. Stop Frontend expansion here. Research Progress/Evidence remain
future cross-module features, not Phase 2 cleanup.
