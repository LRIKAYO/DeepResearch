# Quality Report

> Owner: 05-Quality / Quality Evaluation Engineer  
> Current baseline: `QUALITY-SCAN-002` (Post-P4-001 validation)  
> Status: **PASS WITH FINDINGS**

This document is the maintained quality baseline for ResearchFlow. It records
observed evidence, validation results, known findings, and readiness conditions.
It is not a product roadmap and does not replace the architecture or API source
of truth.

## Maintenance rules

- Update this report only after a named quality task or a reproducible validation.
- Distinguish **validated**, **observed**, **deferred**, and **unverified** states.
- Do not change an evaluation dataset merely to improve a metric.
- Never include secret values or local `.env` contents in this report.
- Do not describe an approved-next item as implemented before its acceptance
  evidence exists.
- Keep lasting conclusions here: root cause, fix, regression coverage, and any
  required architecture decision. Do not retain exploratory debugging logs.

When documents and implementation differ, quality review uses this source order:

1. `docs/API_CONTRACTS.md`
2. `docs/DATA_MODEL.md`
3. `docs/ARCHITECTURE.md`
4. `docs/DECISIONS.md`
5. `docs/PHASE_1_PLAN.md` through `docs/PHASE_4_PLAN.md`
6. `docs/tasks/`
7. Code and tests

## Current baseline — QUALITY-SCAN-002 (Post-P4-001)

This is the current quality baseline. It supersedes `QUALITY-SCAN-001` for
statements about P4 implementation, migration head, test counts, and
Backend↔Agent Server verification. The Pre-P4 scan remains below as a dated
historical record only.

| Area | Status | Evidence / note |
| --- | --- | --- |
| Overall repository quality | PASS WITH FINDINGS | P4-001 engineering and PAIR learning acceptance are complete; remaining findings are non-blocking. |
| P4-001 implementation | **Validated** | Project list and Research Session create/read/list are implemented with PostgreSQL and real Agent thread provisioning. |
| Backend persistence contract | **Validated** | Development and test databases are at `20260831_0002 (head)` with no Alembic drift. |
| Backend↔Agent control plane | **Validated** | Real Uvicorn→Agent Server `threads.create/get` smoke matched Agent metadata and the PostgreSQL association. QF-002 is closed. |
| Failure boundary | **Validated** | Sanitized Agent `503` creates no row; a simulated database failure attempts exactly one thread delete. |
| P4-001 Gate B | **Validated** | The user explicitly explained the create chain, three identities, multi-run cardinality, membership authority, and asymmetric failure/compensation boundary. |
| Frontend stream integration | Observed / unchanged | P4-001 changed no Frontend file. Project-scoped Frontend adoption remains a later batch. |

Current open finding counts: **Blocker 0 / High 0 / Medium 0 / Low 1 / Info 1**.
QF-002 and QF-004 are closed and are not included in the open count.

## Current validated evidence

| Validation | Result |
| --- | --- |
| `docker compose config --quiet` | Passed. |
| Alembic current | Development and test databases both at `20260831_0002 (head)`. |
| Alembic check | Both databases: `No new upgrade operations detected.` |
| `py -3.12 -m pytest tests/backend tests/agent -q` | Passed: **26 passed in 2.13s**. |
| Focused Agent-unavailable and DB-compensation tests | Passed: **2 passed in 0.59s**. |
| `py -3.12 -m pip check` | Passed: no broken requirements. |
| Backend LangGraph SDK | Installed and verified at `langgraph-sdk 0.4.3`. |
| Real Backend→Agent Server smoke | Uvicorn POST returned `201`; SDK `threads.get` returned the same thread and matching metadata; the PostgreSQL row matched all three IDs. |
| Real model / Web Search | Not invoked; the smoke provisioned and read a thread only. |

The durable smoke evidence is recorded in `docs/tasks/P4-001.md`. The verified
identity tuple was:

```text
project_id          8ac084f2-a516-497e-811b-7a670679dc07
research_session_id 5746a588-38cd-4df2-9fb6-27221935d8b1
thread_id           01a05850-a03f-7eb2-8b80-707da521ae83
graph_id            researchflow
```

## Current findings

### QF-001 — Persistence restart coverage is manual rather than automated

- Severity: **Low**
- Status: Accepted test gap; unchanged from `QUALITY-SCAN-001`.
- Current action: none. Revisit only if Backend adds startup cache,
  process-local state, or a more complex connection lifecycle.

### QF-002 — P4 Backend-to-Agent control-plane smoke

- Severity: **Info**
- Status: **Closed by P4-001**
- Closure evidence: a real local Agent Server and real Uvicorn Backend executed
  `threads.create/get`; Project/session metadata matched the persisted
  PostgreSQL association. No model or Web Search call occurred.
- Regression evidence: focused fake-client API tests plus the durable smoke
  record in `docs/tasks/P4-001.md`.

### QF-003 — Frontend lint warnings remain in adopted UI code

- Severity: **Info**
- Status: Observed; unchanged from `QUALITY-SCAN-001`.
- Current action: keep outside the P4 Backend slice and address only in a
  dedicated Frontend-quality task.

### QF-004 — P4-001 PAIR learning Gate B evidence

- Severity: **Medium**
- Status: **Closed on 2026-08-31**
- Evidence present: the user personally authored the initial
  `agent_server.py` and `research_sessions.py` create path and participated in
  review/fix decisions.
- Closure evidence: the user explicitly explained Project validation→thread
  provisioning→mapping persistence; the distinct product/thread/run identities;
  multi-run cardinality without run persistence; PostgreSQL membership
  authority versus diagnostic metadata; and the difference between Agent
  creation failure and one-attempt database-failure compensation.
- Durable record: `docs/tasks/P4-001.md`, Gate B section.

## Historical baseline — QUALITY-SCAN-001 (Pre-P4)

> Historical snapshot only. Statements below such as “P4-001 not implemented,”
> migration head `20260830_0001`, `20 passed`, or “Agent Server unverified”
> describe the Pre-P4 repository and must not be used as the current baseline.

| Area | Status | Evidence / note |
| --- | --- | --- |
| Overall repository quality | PASS WITH FINDINGS | No blocking, high, or medium-severity findings in `QUALITY-SCAN-001`. |
| P4-001 implementation | Deferred / expected | P4-001 is approved-next, not yet implemented; its absence is not a defect. |
| P4-001 readiness | **READY** | The approved contract and the current validation baseline are sufficient to begin the Backend vertical slice. |
| Backend persistence contract | Validated | Project **create/read**, migration head, and database constraints passed current checks. |
| Agent evidence contract | Validated by unit tests | Structured `Evidence` flow, tool-result validation, and writer output behavior are covered by current agent tests. |
| Frontend stream integration | Observed | The UI uses the direct LangGraph stream path; its product-scoped end-to-end smoke is deferred to the later Frontend batch. |

Finding counts: **Blocker 0 / High 0 / Medium 0 / Low 1 / Info 2**.

### Historical validated evidence

The following commands were run against the current repository baseline. Runtime
database connection values were supplied only to the command process and are not
recorded here.

| Validation | Result |
| --- | --- |
| `docker version` / `docker compose config` | Docker Engine available; Compose configuration valid. |
| `docker compose ps` | PostgreSQL service healthy at validation time. |
| `py -3.12 -m alembic -c pyproject.toml check` | Passed: no new upgrade operations detected. |
| `py -3.12 -m alembic -c pyproject.toml current` | Runtime and test databases both at `20260830_0001 (head)`. |
| ORM schema inspection | `projects` has `project_id`, `name`, `created_at`, plus the named non-empty-name constraint. |
| Real PostgreSQL Project create/read and restart smoke | Validated manually: Project data remained accessible after an application restart. |
| `py -3.12 -m pytest tests/backend tests/agent -q` | Passed: **20 passed**. |
| `py -3.12 -m pip check` | Passed: no broken requirements. |
| `npm ls @langchain/langgraph-sdk` | Installed SDK resolved to `1.8.10`. |
| `npm exec -- tsc --noEmit` | Passed. |
| `npm run build` | Passed with 18 existing lint warnings. |
| `npm run lint` | Passed: 0 errors, 18 warnings. |
| Agent Server availability | Unverified: no Agent Server was listening at `http://127.0.0.1:2024/info`; no real model or Web Search request was made. |

### Historical Contract Consistency Matrix

| Contract | Authoritative source | Observed implementation / evidence | Status |
| --- | --- | --- | --- |
| Project create/read only | `docs/API_CONTRACTS.md:84,123-125` | `src/researchflow/backend/projects.py:60-80` provides create and read routes; no unapproved update/delete surface was observed. | Consistent |
| Provisional Agent Evidence is internal structured state | `docs/DECISIONS.md:19-25` | `src/researchflow/agent/state.py:9-25` defines `Evidence` and internal `AgentState`. | Consistent |
| `thread_id` is not an Agent State or Product Project identifier | `docs/DECISIONS.md:43-47`; `docs/ARCHITECTURE.md:37-40` | Current `AgentState` has no product or thread identifiers (`src/researchflow/agent/state.py:21-25`). | Consistent |
| Approved Research Session ownership and thread association | `docs/DATA_MODEL.md:91-120`; `docs/ARCHITECTURE.md:321-352` | Approved-next only; `docs/PHASE_4_PLAN.md:25-26` correctly records that no association is implemented yet. | Consistent / deferred |
| Backend control plane; Frontend direct stream data plane | `docs/DECISIONS.md:136-140`; `docs/ARCHITECTURE.md:351-352` | Direct `useStream` configuration is present at `frontend/src/providers/Stream.tsx:86-97`; no Product Backend stream proxy was observed. | Consistent |

### Historical findings

### QF-001 — Persistence restart coverage is manual rather than automated

- Severity: **Low**
- Status: Accepted test gap
- Evidence: Real PostgreSQL Project create/read and an application restart smoke
  have been performed. The automated test uses a module-level `TestClient`
  (`tests/backend/test_projects.py:9`) and covers create/read in-process
  (`tests/backend/test_projects.py:35-47`). The corresponding manual smoke and
  restart acceptance boundary are recorded at `docs/tasks/P3-001.md:218-219,242`.
- Impact: Current evidence supports persistence; the remaining gap is only the
  absence of a deterministic subprocess/restart regression test.
- Owner: 05-Quality
- Required follow-up: no new restart automation is required now. Re-evaluate
  and upgrade this coverage when Backend introduces a startup cache, process
  local state, or a complex connection lifecycle.
- P4 impact: non-blocking.

### QF-002 — P4 Backend-to-Agent control-plane smoke is unverified

- Severity: **Info**
- Status: Open
- Evidence: The Agent Server was not running during the scan. The P4 scope
  requires thread provisioning and one real local Backend↔Agent Server smoke
  (`docs/PHASE_4_PLAN.md:171-177`); its required successful association is
  specified at `docs/PHASE_4_PLAN.md:234-236`. The existing direct Frontend
  stream boundary is at `frontend/src/providers/Stream.tsx:86-97`.
- Impact: Current build and unit-test evidence cannot prove the new cross-service
  association before P4-001 is implemented.
- Owner: 03-Backend / P4 implementation owner
- Required follow-up: after P4-001, run a real **Backend → Agent Server**
  `threads.create` then `threads.get` smoke. Verify matching Project/session
  metadata on the thread and the matching PostgreSQL association. Do not invoke
  a real model or Web Search.
- Explicitly out of this smoke: Frontend `useStream` end-to-end validation. It
  is deferred to the later Frontend batch after P4-001.
- P4 impact: required P4-001 acceptance evidence; not a readiness blocker.

### QF-003 — Frontend lint warnings remain in adopted UI code

- Severity: **Info**
- Status: Observed
- Evidence: `npm run lint` completed with 0 errors and 18 warnings. Concrete
  warning locations include ref access during render at
  `frontend/src/components/thread/index.tsx:58,63`, effect state updates at
  `frontend/src/components/thread/agent-inbox/components/state-view.tsx:182`,
  and a Fast Refresh export warning at `frontend/src/providers/Stream.tsx:319`.
- Impact: No current build failure or contract drift was found.
- Owner: 04-Frontend
- Required follow-up: address in a dedicated frontend-quality task rather than
  folding unrelated cleanup into P4-001.
- P4 impact: non-blocking.

### Historical Test Gap Matrix

| Area | Current evidence | Gap / boundary | Required next action |
| --- | --- | --- | --- |
| Project persistence across restart | Real PostgreSQL create/read plus manual restart smoke; in-process regression coverage. | No subprocess/restart automation. | Accepted; revisit only after startup cache, process-local state, or complex connection lifecycle is introduced. |
| P4 Research Session provisioning | Not implemented; no cross-service result can exist yet. | `threads.create/get`, thread metadata, and PostgreSQL association are unverified. | P4-001 must add focused fake-client tests and one real local Backend→Agent Server smoke without model/Search execution. |
| Frontend project-scoped stream | Direct `useStream` is present. | No project-scoped Frontend end-to-end smoke. | Defer to the Frontend batch after P4-001; do not add it to the P4-001 gate. |
| Retrieval, answer, citation evaluation | Not started. | No fixed evaluation dataset or metrics. | Establish a versioned dataset before comparing vector, hybrid, and reranked retrieval. |
| Agent evaluation and observability | Not validated. | No scenario suite, LangSmith traces, latency, token, cost, or error evidence. | Add only when the runtime instrumentation and evaluation task are explicitly scoped. |
| Rate limiting, retries, failure recovery | Not validated. | No deterministic controlled-service tests. | Scope separately after the relevant reliability behavior exists. |

### Historical P4 quality gate conditions

P4-001 is **READY** to begin. Its implementation acceptance evidence must:

1. Preserve the approved Research Session contract; do not introduce unapproved
   product identifiers into Agent State.
2. Add focused PostgreSQL API tests with a fake Agent client for the new
   configuration and provisioning behavior.
3. Run backend and agent tests, Alembic drift check, frontend type check, and
   production build.
4. Start a real local Agent Server and run the Backend→Agent Server
   `threads.create` / `threads.get` smoke. Verify thread metadata and the
   matching PostgreSQL association; do not call a real model or Web Search.
5. Defer Frontend `useStream` end-to-end smoke to the later Frontend batch.
6. Record latency, error, token, cost, or trace evidence only when an actual
   instrumented run has occurred; none is claimed by this baseline.

### Historical evaluation and observability status

| Capability | Status | Next evidence needed |
| --- | --- | --- |
| Retrieval comparison (vector / hybrid / reranker) | Not started | Fixed evaluation set and Recall@K, Precision@K, MRR, NDCG results. |
| Answer faithfulness / relevance / citation correctness | Not started | Versioned rubric or dataset, reproducible evaluator output. |
| Agent completion, tool choice, evidence coverage, loop detection | Not started | Scenario suite with cost and latency capture. |
| LangSmith tracing | Not validated | Trace identifiers and a documented, credential-safe validation run. |
| Token usage, cost, latency, error telemetry | Not validated | Instrumented runtime evidence. |
| Rate-limit / retry / failure recovery | Not validated | Deterministic integration tests or controlled service simulation. |

### Historical Module Handoff

| Receiving module | Handoff | Quality acceptance boundary |
| --- | --- | --- |
| 03-Backend | Implement P4-001 Research Session create/read/list and Agent Server control-plane provisioning. | Provide focused fake-client tests and the real `threads.create/get` smoke with matching metadata and PostgreSQL association; do not invoke model/Search. |
| 04-Frontend | No P4-001 implementation work is requested here. Plan the next Frontend batch after the Backend slice is inspected. | Replace global discovery with Project-scoped session discovery and then run a direct `useStream` end-to-end smoke. |
| 05-Quality | Maintain this report and review resulting evidence. | Update findings, test-gap status, and metrics only from reproducible results. |
| 00-Architect | No architecture decision is requested by this scan rework. | Review only if implementation proposes a contract, data-model, ownership, or stream-boundary change. |

## Update procedure

For every future formal quality task:

1. Add or update only evidence actually produced by that task.
2. Update the relevant finding with root cause, fix, and regression test when
   resolved.
3. Change the baseline status and counts if severity changes.
4. Add a one-line history entry below, linking to the task or durable artifact.

## Historical QUALITY-SCAN-001 Completion Report

Status: DONE

Created:

- `docs/QUALITY_REPORT.md`

Key Decisions:

- Project scope is reported as create/read, not CRUD.
- P4-001 readiness is READY; its cross-service smoke is an implementation
  acceptance check, not a prerequisite for starting work.
- Frontend `useStream` end-to-end validation remains outside P4-001.

Validation:

- Alembic reports no drift; backend and agent tests: 20 passed; `pip check`:
  passed.
- TypeScript and Frontend build passed; lint reports 0 errors and 18 warnings.
- Agent Server was not running during the scan; no real model or Web Search call
  was made.

Architecture Impact: None

## History

| Record | Outcome | Durable result |
| --- | --- | --- |
| `P4-001-GATE-B` | DONE | Recorded the user's five boundary explanations and closed QF-004. |
| `QUALITY-SCAN-002` | PASS WITH FINDINGS | Established the Post-P4 current baseline; QF-002 and QF-004 are closed. |
| `P4-001` | DONE | Verified revision `20260831_0002`, 26 Backend+Agent tests, failure boundaries, real Backend↔Agent Server smoke, and PAIR learning Gate B. |
| `QUALITY-SCAN-001` | PASS WITH FINDINGS | Established the Pre-P4 validation baseline; Architect rework set P4-001 readiness to READY and findings to Low 1 / Info 2. |
| `QUALITY-REPORT-001` | DONE | Created this maintained quality-report entry point under `docs/`. |
