# Quality Report

> Owner: 05-Quality / Quality Evaluation Engineer  
> Current baseline: `P8-QA-001` (local browser-completion acceptance)
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
5. `docs/PHASE_1_PLAN.md` through the current Phase plan
6. `docs/tasks/`
7. Code and tests

## Current baseline — P8-QA-001

**Status:** **PASS WITH FINDINGS — LOCAL/TEST MVP ACCEPTED**

| Area | Status | Evidence / note |
| --- | --- | --- |
| Project Knowledge UI | **Validated** | Native Markdown upload/list consumes the existing Project-scoped Backend API, preserves bytes, refreshes authoritative order, rejects stale Project responses, and presents sanitized actionable errors. |
| Latest Sources UI | **Validated** | Reads only typed checkpoint `citations`, preserves order/duplicates, separates Web links from uploaded provenance, and distinguishes absent from valid empty State. |
| Browser success path | **Validated** | Real configured-provider A/B browser runs proved upload → scoped Knowledge → Report/Sources, Project isolation, selected-session reload, and in-flight rejoin. |
| Browser failure path | **Validated** | Invalid upload created no Document. A real browser-resumed `execute_tool` Knowledge failure reached Agent error and retained the prior matching Report/Citation pair. |
| Regression | **Validated** | 146 Python tests with warnings as errors, dependency/compile checks, both migration drift checks, Frontend P8 assertions/type/lint/build, and documentation diff checks passed. |
| Release boundary | **Accepted with limitation** | Local/test MVP only. Production identity, durable Agent restart recovery, claim-level Citation, and comprehensive product features are not claimed. |

P8-QA-001 cleaned only its enumerated review rows/threads and left no matching
test Project. Full evidence and commands are recorded in
`docs/tasks/P8-QA-001.md`.

Current Phase 8 findings are **Blocker 0 / High 0 / Medium 0 / Low 1 / Info 2**:
local Agent-server restart retention (QF-006), inherited Frontend lint warnings,
and the trusted identity deployment precondition. The reused development
database also emitted a non-blocking local collation-version warning; it is
maintenance evidence, not a repository-code failure.

### QF-006 — Agent-server restart retention is not durable

- Severity: **Low for local/test; blocker for a durability claim**.
- Status: accepted release limitation.
- Evidence: browser hard reload restored current runtime checkpoints, but after
  the in-memory Agent Server process exited, PostgreSQL Session/thread rows
  remained while a fresh Server did not contain their completed State.
- Current action: keep the limitation explicit. Before promising durable
  history, define checkpoint persistence and stale-session reconciliation at
  the Agent Server/Product Backend boundary; do not infer it in Frontend.

## P7 stream regression — BUG-P7-STREAM-001

**Status:** validated for the pinned D-016 tuple and all executable
current-graph browser paths.

The pinned D-016 tuple was reproduced in a real browser. The `422` was caused
by the Frontend wrapper's object spread evaluating SDK getters and adding the
unsupported `tools` mode, not by Server rejection of multi-mode arrays. The
minimal wrapper fix preserves only lazy SDK getters and overrides `submit`.

Validated evidence: actual browser Run context carries `knowledge_scope` at
top level and not Graph input; effective modes are `values`,
`messages-tuple`, and `custom`; `runs/stream` returns `200`; the Run reaches
`success`; checkpoint state includes a Report; and the UI finishes without an
error. A fresh browser Project → Session run waited for its Report, retained
the selected URL and user message across hard reload, then regenerated on the
same thread; the regenerate request also returned `200` with the approved
three modes, top-level scope, and a final Report. The pinned Python/Frontend
dependencies, 92 Python tests, Frontend typecheck, lint (0 errors; 16 existing
warnings), and production build passed.

Fresh browser evidence now covers in-flight rejoin, edit branch checkpointing,
and A/B Knowledge provenance. The latter used real indexed Markdown Documents:
each selected Project's Agent state contained only its own distinct token and
Report. The current graph has no `interrupt()` producer, so interrupt/resume
needs a separately scoped Agent scenario if that capability is introduced. No
scope authority, Agent/Backend contract, or dependency version was changed.

## Current baseline — P7-003B/C

**Status:** **PASS WITH FINDINGS — ARCHITECT REVIEW REQUIRED FOR PHASE EXIT**

| Area | Status | Evidence / note |
| --- | --- | --- |
| Run-local Citation output | **Validated** | Strict two-source projection preserves order, duplicates, bounded excerpts, and JSON-safe provenance. Report, final message, and Citations update atomically. |
| Graph repeat/failure behavior | **Validated** | Fresh checkpoint tests retain the last matching successful Report/Citation pair through mapping and Writer failures; successful no-Tool runs publish `citations: []`. |
| Retrieval fixture | **Validated with limitation** | Frozen `retrieval-v1`, SHA-256 `9b42eaf6ee6c0b7f7de03c50b9520dc1ea1400c2e6ed98bb1ad13f9e2f8d7f29`; synthetic AI-reviewed, not human-reviewed. |
| Real Recall@5 baseline | **Measured** | Real `BAAI/bge-m3` ingestion and scoped pgvector API search: 3/3 cases at 1.0; macro Recall@5 = 1.0 over ten candidate chunks. No pass threshold is claimed. |
| Regression | **Validated** | Agent/Backend/Knowledge/Quality warnings-as-errors: 146 passed. Dependency check, Python compilation, both migration drift checks, Frontend type check, lint (0 errors; 16 pre-existing warnings), and production build passed. |
| Product completion | **Not claimed** | D-017 requires 00-Architect to inspect this evidence before Phase 7 exit or activation of another product batch. |

The real evaluator used Product Project creation, Markdown ingestion, and
`POST /projects/{project_id}/knowledge/search` with `limit=5`. It used no
ranking override, committed no runtime IDs, and cleaned exactly its one Project,
two Documents, and ten chunks from `researchflow_test`. The credential-safe
artifact is `docs/evaluations/retrieval-v1-baseline-2026-09-14.json`.

Open findings remain **Blocker 0 / High 0 / Medium 0 / Low 1 / Info 2**:
automated restart coverage, adopted Frontend lint warnings, and the trusted
identity deployment precondition are unchanged. Citation correctness,
answer quality, multilingual retrieval, observability, retries, and release
thresholds remain unvalidated rather than implicitly passed.

## Historical baseline — QUALITY-SCAN-004 (Post-P6)

**Status:** **PASS WITH FINDINGS**

This baseline superseded `QUALITY-SCAN-003` for the
P6 permanent-Knowledge vertical slice, user-and-Project isolation, pgvector
schema, and Gate B/C learning evidence. The Post-P5 scan remains below as a
historical record.

| Area | Status | Evidence / note |
| --- | --- | --- |
| P6-002 acceptance | **Validated** | Gate A engineering evidence, Gate B user trace, and Gate C zero-norm atomicity exercise are complete. |
| Atomic Markdown ingestion | **Validated** | Invalid vectors, provider/chunk/commit failures return sanitized errors and leave no Document/Chunk rows. |
| Scoped exact retrieval | **Validated** | Retrieval joins Chunk→Document→Project, filters owner and Project before exact cosine order/limit, and excludes closer out-of-scope rows. |
| Physical vector baseline | **Validated** | pgvector 0.8.6, `vector(1024)`, `BAAI/bge-m3`, exact cosine `<=>`, and no approximate index are recorded and tested. |
| Retrieval evaluation | Deferred / unvalidated | The deterministic retrieval fixture is not a Recall@K, MRR, NDCG, faithfulness, or citation-correctness evaluation dataset. |
| Observability and reliability | Deferred / unvalidated | No LangSmith trace, token/cost telemetry, rate-limit, retry, or recovery evaluation is claimed. |

Open finding counts at that scan: **Blocker 0 / High 0 / Medium 0 / Low 1 / Info 2**.

### Current validated evidence

| Validation | Result |
| --- | --- |
| PostgreSQL / pgvector | The local service accepted connections; the documented P6 smoke verified pgvector 0.8.6, 1024 finite/non-zero `BAAI/bge-m3` values, and exact self cosine distance 0 (`docs/tasks/P6-002.md:34-48`). |
| Alembic check | Development and test databases both report `No new upgrade operations detected.` |
| Backend + Knowledge + Agent regression | Passed: **71 passed in 2.74s**. |
| `py -3.12 -m pip check` | Passed: no broken requirements. |
| Gate B | Passed: the user explained the atomic upload and authoritative scoped retrieval flows, trusted-header limitation, and KnowledgeHit/Evidence boundary. |
| Gate C | Passed: `tests/backend/test_documents.py:224-242` supplies a 1024-dimensional zero vector and asserts sanitized `503` plus zero Document/Chunk rows; focused regression passed **16 tests**. |
| Prior P6 runtime gates | Recorded real Uvicorn upload/restart/search and real configured embedding/pgvector smokes passed (`docs/tasks/P6-002.md:44-48`). |
| Frontend gates | Recorded P6 TypeScript, lint, and production build passed with no errors; the 16 lint warnings remain pre-existing and outside P6 scope (`docs/tasks/P6-002.md:49-52`). |

### Current Contract Consistency Matrix

| Contract | Authoritative source | Observed implementation / evidence | Status |
| --- | --- | --- | --- |
| Trusted identity is required and owner scope is anti-enumerating | `docs/API_CONTRACTS.md:21-45`; `docs/DATA_MODEL.md:37-73` | `get_current_user_id` validates the header at `src/researchflow/backend/current_user.py:7-20`; Project lookup applies owner scope at `src/researchflow/backend/research_sessions.py:52-63`. | Consistent |
| Successful upload is atomic | `docs/API_CONTRACTS.md:303-339`; `docs/DATA_MODEL.md:269-276` | Upload validates/chunks/embeds before `Document` and `DocumentChunk` are committed together; errors roll back at `src/researchflow/backend/documents.py:43-111`. | Consistent |
| Vectors must be finite, dimension 1024, and non-zero | `docs/PHASE_6_PLAN.md:364-367`; `docs/DATA_MODEL.md:233-249` | Shared validation rejects count, type, dimension, non-finite, and zero-norm failures at `src/researchflow/knowledge/embeddings.py:24-52`. | Consistent |
| Exact retrieval is user-and-Project-scoped before limit | `docs/API_CONTRACTS.md:420-425`; `docs/ARCHITECTURE.md:511-533` | Query joins Chunk→Document→Project, filters both identities, then orders exact cosine distance and `chunk_id` before limiting at `src/researchflow/knowledge/retrieval.py:26-56`. | Consistent |
| Knowledge remains outside Agent Contract | `docs/DECISIONS.md:264-294`; `docs/PHASE_6_PLAN.md:395-403` | P6 code returns `KnowledgeHit`; no Agent State, Tool, Evidence, or LangGraph code is part of this slice. | Consistent |

### Current Test Gap Matrix

| Area | Current evidence | Gap / boundary | Required next action |
| --- | --- | --- | --- |
| Ingestion atomicity and vector validation | Focused PostgreSQL API tests include provider, chunking, commit, wrong-vector, and zero-norm rollback paths. | No retry/reconciliation behavior is approved. | Keep deferred until a future ingestion reliability task defines it. |
| Exact retrieval isolation | Deterministic two-user/two-Project fixture proves filtering before order/limit. | No retrieval-quality benchmark is claimed. | Freeze a versioned evaluation dataset before vector/hybrid/reranker comparisons. |
| Trusted identity boundary | Missing/invalid identity and other-user resource behavior are tested. | A trusted upstream must strip/inject the header before public deployment; this Backend does not authenticate browsers. | Treat QF-005 as a deployment precondition, not a reason to add Auth ad hoc. |
| Observability | Real provider and local runtime smokes are recorded. | No trace, latency, token, cost, or error telemetry. | Scope instrumentation separately once an approved runtime destination exists. |

### Current findings

### QF-001 — Persistence restart coverage is manual rather than automated

- Severity: **Low**
- Status: Accepted test gap; unchanged.
- Evidence: manual application-restart persistence evidence is at
  `docs/tasks/P3-001.md:240-243`; the P6 real Uvicorn restart smoke is recorded
  at `docs/tasks/P6-002.md:46-48`. Automated coverage remains in-process at
  `tests/backend/test_projects.py:9-47` and `tests/backend/test_documents.py:35-242`.
- Current action: none. Revisit only after startup cache, process-local state,
  or a more complex connection lifecycle is introduced.

### QF-003 — Frontend lint warnings remain in adopted UI code

- Severity: **Info**
- Status: Observed; non-blocking and unchanged.
- Evidence: P6 lint completed with 0 errors and 16 warnings; representative
  locations are `frontend/src/components/thread/index.tsx:58-64` and
  `frontend/src/providers/Stream.tsx:356`.
- Current action: keep outside P6; address only in a dedicated Frontend-quality
  task.

### QF-005 — Trusted identity header requires an upstream deployment boundary

- Severity: **Info**
- Status: Explicit deployment precondition, not an implementation defect.
- Evidence: the Backend consumes `X-ResearchFlow-User-Id` at
  `src/researchflow/backend/current_user.py:7-20`; the API Contract forbids
  trusting an arbitrary public browser header at `docs/API_CONTRACTS.md:25-45`.
- Current action: before public multi-user deployment, provide an upstream that
  strips untrusted identity headers and injects a verified user UUID. Do not add
  login/token/User CRUD to P6 merely to silence this finding.

### Current evaluation and observability status

| Capability | Status | Next evidence needed |
| --- | --- | --- |
| Vector-only retrieval | Functional exact-search baseline only | Versioned set with Recall@K, Precision@K, MRR, NDCG. |
| Hybrid retrieval / reranker comparison | Not started | The same fixed dataset and an approved comparison protocol. |
| Faithfulness, answer relevance, citation correctness | Not started | A later Agent-integrated evaluation fixture and rubric. |
| Agent completion, tool choice, evidence coverage, loop detection | Not started | A scoped Agent scenario suite after an approved Knowledge Tool boundary. |
| LangSmith, latency, token, cost, error telemetry | Not validated | Credential-safe instrumentation and trace evidence. |

### Current Module Handoff

| Receiving module | Handoff | Quality acceptance boundary |
| --- | --- | --- |
| 02-Knowledge | P6 exact vector baseline and deterministic fixture are accepted. | Do not claim retrieval quality or add hybrid/reranker behavior without a fixed evaluation dataset and a new task. |
| 03-Backend | Atomic Product Document APIs and scoped retrieval are accepted. | Keep the upstream identity boundary explicit; no Auth expansion or Agent stream proxy is approved. |
| 05-Quality | Maintain QF-001/QF-003/QF-005 and the P6 deterministic fixture. | Establish versioned retrieval and Agent evaluation only when explicitly scoped. |
| 00-Architect | Phase 6 is complete. | An Agent `knowledge_search` handoff or KnowledgeHit→Evidence conversion is an architecture decision, not a P6 follow-up edit. |

## QUALITY-SCAN-004 Completion Report

Status: DONE

Changed:

- Updated the maintained quality baseline to Post-P6 and recorded Gate B/C,
  atomicity, isolation, and regression evidence.

Created:

- None; this scan updates the maintained report.

Key Decisions:

- The P6 deterministic fixture proves functional exact retrieval boundaries;
  it is not presented as a retrieval-quality evaluation.
- The trusted identity header remains an explicit external deployment boundary.

Validation:

- Alembic no-drift checks, 71 Backend/Knowledge/Agent tests, dependency check,
  recorded P6 runtime smokes, Gate B, and Gate C were reviewed.

What the user should understand:

- Product-scoped Knowledge needs both atomic ingestion and an authoritative
  owner/Project retrieval predicate; Frontend filtering or thread metadata is
  not a substitute.
- A correctly sized zero vector is still invalid because cosine similarity needs
  a non-zero norm; the regression proves this failure leaves no durable rows.

Architecture Impact: None beyond accepted D-014.

Open Questions:

- Public deployment needs a verified upstream identity injector. Retrieval
  evaluation, observability, reliability, and Agent integration remain separate
  tasks.

Recommended Next Step:

- Stop Phase 6 here. Require an architecture decision before Agent Knowledge
  integration, and a versioned evaluation dataset before retrieval comparisons.

## Historical baseline — QUALITY-SCAN-003 (Post-P5)

**Status:** **PASS WITH FINDINGS**

This historical baseline supersedes `QUALITY-SCAN-002` for its original
Phase 5 browser reachability, Project-scoped session adoption, and the current
regression results. The Post-P4 record remains below as historical evidence for
the Backend vertical slice.

| Area | Status | Evidence / note |
| --- | --- | --- |
| Overall repository quality | PASS WITH FINDINGS | P5-001 and P5-002 acceptance evidence, including Quality review, is complete. The two remaining findings are non-blocking. |
| Product navigation authority | **Validated** | Browser selection uses `projectId` and optional `researchSessionId`; a selected Session derives the opaque Agent `thread_id`. |
| Browser→Backend control plane | **Validated** | Exact-origin CORS, Project/Session create-read flow, and persisted PostgreSQL association were exercised from a real browser. |
| Frontend→Agent data plane | **Validated (recorded smoke)** | The P5-002 direct-stream smoke reached Agent `runs/stream`, completed successfully, restored history, and made no Product Backend stream request. |
| Regression boundary | **Validated** | Alembic has no drift; Backend/Agent tests, TypeScript, production build, dependency check, and CORS tests passed. |
| Evaluation and observability | Deferred / unvalidated | No Retrieval/Agent evaluation suite, LangSmith trace, or runtime latency/token/cost telemetry is claimed by this scan. |

Current open finding counts: **Blocker 0 / High 0 / Medium 0 / Low 1 / Info 1**.

### Current validated evidence

| Validation | Result |
| --- | --- |
| `docker compose config --quiet` | Passed. |
| Alembic check | Development and test databases: no new upgrade operations detected. |
| `py -3.12 -m pytest tests/backend tests/agent -q` | Passed: **29 passed**. |
| `py -3.12 -m pip check` | Passed: no broken requirements. |
| `pnpm exec tsc --noEmit` | Passed. |
| `pnpm run build` | Passed. |
| `pnpm run lint` | Passed: **0 errors / 16 existing warnings**; warning cleanup is outside P5 scope. |
| CORS regression and local preflight | Focused tests cover listed and unlisted origins at `tests/backend/test_cors.py:7-41`; the recorded browser preflight allowed only the configured origin, without credentials (`docs/tasks/P5-002.md:60-62`). |
| Browser control-plane smoke | A real browser created a Project and Research Session, observed canonical product URL state with no standalone `threadId`, kept the composer disabled before provisioning, and observed no global `threads.search` request (`docs/tasks/P5-002.md:63-71`). The Quality re-review repeated the control-plane portion against real Backend, PostgreSQL, and Agent Server. |
| Browser data-plane smoke | The recorded P5-002 no-tools prompt made direct Agent history and `runs/stream` calls for the persisted thread; it returned `200`, reached `success`, and restored the expected assistant output without Product Backend message/stream traffic (`docs/tasks/P5-002.md:72-80`). |
| Current review cost boundary | The Quality re-review did not submit a model prompt or invoke Web Search. The recorded direct-stream smoke is retained as distinct earlier acceptance evidence rather than represented as a new no-cost rerun. |

### Current Contract Consistency Matrix

| Contract | Authoritative source | Observed implementation / evidence | Status |
| --- | --- | --- | --- |
| Product navigation uses Project and optional Research Session IDs | `docs/DECISIONS.md:156-178`; `docs/ARCHITECTURE.md:391-414` | Query state is `projectId` / `researchSessionId`; legacy `threadId` is cleared at `frontend/src/providers/ProjectSession.tsx:56-60,108-110`. | Consistent |
| Session membership is Project-scoped | `docs/API_CONTRACTS.md:205-231`; `docs/DATA_MODEL.md:111-128` | Sessions are requested only through `listResearchSessions(projectId)` and the visible selection is bound to the loaded Project at `frontend/src/providers/ProjectSession.tsx:149-208`. | Consistent |
| `thread_id` is derived, not navigation state | `docs/DECISIONS.md:156-178`; `docs/ARCHITECTURE.md:391-414` | `useStream` receives `selectedSession?.thread_id` at `frontend/src/providers/Stream.tsx:99-117`; browser smoke found no standalone product URL `threadId`. | Consistent |
| Product control plane and direct Agent data plane remain separate | `docs/ARCHITECTURE.md:431-444`; `docs/tasks/P5-002.md:72-80` | The recorded direct stream used Agent history and `runs/stream`, with no Product Backend message or stream request. | Consistent |
| Browser Backend reachability uses exact CORS origins without credentials | `docs/PHASE_5_PLAN.md:47-58`; `docs/API_CONTRACTS.md:7-20` | Backend builds an exact allow-list at `src/researchflow/backend/app.py:13-26`; regression tests assert allowed and unlisted-origin behavior at `tests/backend/test_cors.py:7-41`. | Consistent |

### Current Test Gap Matrix

| Area | Current evidence | Gap / boundary | Required next action |
| --- | --- | --- | --- |
| Project persistence across restart | Real PostgreSQL create/read plus manual restart smoke and in-process regression coverage. | No subprocess/restart automation. | Accepted Low gap (QF-001); revisit only after startup cache, process-local state, or complex connection lifecycle is introduced. |
| Project-scoped browser path | Recorded real-browser control-plane and direct-stream smokes; static and Backend/Agent regression checks pass. | Browser coverage is a recorded smoke, not a committed browser-test harness. | Preserve the recorded smoke as P5 acceptance evidence; introduce a deterministic browser regression only when a dedicated Frontend-quality task scopes its runtime fixture. |
| CORS allow-list | Focused allowed/unlisted-origin tests plus real preflight result. | No Auth/cookie/deployment-origin scenario is approved. | Keep deferred until Auth and deployment origins are designed. |
| Retrieval, answer, citation evaluation | Not started. | No fixed evaluation dataset or Recall@K, Precision@K, MRR, NDCG, faithfulness, relevance, or citation-correctness result. | Establish a versioned evaluation dataset before comparing retrieval approaches. |
| Agent evaluation and observability | Direct-stream acceptance is recorded. | No scenario suite, LangSmith traces, latency, token, cost, error, retry, or rate-limit evidence. | Scope an instrumented evaluation task when runtime instrumentation exists. |

### Current findings

### QF-001 — Persistence restart coverage is manual rather than automated

- Severity: **Low**
- Status: Accepted test gap; unchanged.
- Evidence: PostgreSQL Project persistence through a manual application restart
  is an explicit P3 acceptance result (`docs/tasks/P3-001.md:240-243`). The
  automated Project API coverage remains in-process (`tests/backend/test_projects.py:9-47`).
- Current action: none. Revisit only if Backend adds startup cache,
  process-local state, or a more complex connection lifecycle.

### QF-003 — Frontend lint warnings remain in adopted UI code

- Severity: **Info**
- Status: Observed; non-blocking and unchanged in intent.
- Evidence: the Post-P5 lint run completed with 0 errors and 16 warnings.
  Representative adopted-UI locations include render-time ref access at
  `frontend/src/components/thread/index.tsx:58-64` and the Fast Refresh warning
  at `frontend/src/providers/Stream.tsx:356`.
- Current action: no cleanup in P5; address only in a dedicated
  Frontend-quality task.

### Current evaluation and observability status

| Capability | Status | Next evidence needed |
| --- | --- | --- |
| Retrieval comparison (vector / hybrid / reranker) | Not started | Fixed, versioned evaluation set and Recall@K, Precision@K, MRR, NDCG results. |
| Answer faithfulness / relevance / citation correctness | Not started | Versioned rubric or dataset and reproducible evaluator output. |
| Agent completion, tool choice, evidence coverage, loop detection | Not started | Scenario suite with completion, evidence, latency, and cost assertions. |
| LangSmith tracing | Not validated | Trace identifiers and a credential-safe validation run. |
| Token usage, cost, latency, and error telemetry | Not validated | Instrumented runtime evidence. |
| Rate limit, retry, and failure recovery | Not validated | Deterministic controlled-service tests after those behaviors exist. |

### Current Module Handoff

| Receiving module | Handoff | Quality acceptance boundary |
| --- | --- | --- |
| 04-Frontend | P5-002 Quality review is passed; no P5 lint cleanup is requested. | Preserve the Project → Session → derived-thread boundary. Any UI/runtime regression work needs its own task and reproducible browser fixture. |
| 03-Backend | P5-001 CORS boundary is accepted. | Keep Product Backend to control-plane requests; do not proxy Agent messages or streams without an approved Contract change. |
| 05-Quality | Maintain P5 smoke evidence and current non-blocking findings. | Add evaluation, observability, or reliability evidence only from explicitly scoped, reproducible work. |
| 00-Architect | No decision is requested by this scan. | Review only a proposed change to identity authority, Product/Agent transport, data model, or module ownership. |

## QUALITY-SCAN-003 Completion Report

Status: DONE

Changed:

- Updated the maintained quality baseline to Post-P5 and recorded the accepted
  browser/control-plane/data-plane evidence.

Created:

- None; this scan updates the existing maintained report.

Key Decisions:

- The recorded real direct-stream smoke and the independently re-run no-cost
  control-plane smoke are reported separately.
- Existing non-blocking lint warnings remain outside P5 scope.

Validation:

- Alembic no-drift checks, 29 Backend/Agent tests, dependency check,
  TypeScript, production build, lint, CORS evidence, and P5 browser smoke
  records were reviewed.

What the user should understand:

- Product navigation is authoritative through Project and Research Session IDs;
  `thread_id` is derived only after Product Backend returns the persisted
  association.
- The Product Backend provisions and discovers associations, while direct
  Frontend ↔ Agent Server stream traffic remains the data plane.

Architecture Impact: None.

Open Questions:

- None for P5 acceptance. Retrieval evaluation, observability, and reliability
  work remain separate, unstarted tasks.

Recommended Next Step:

- Stop the P5 batch here. Scope the next product or evaluation task before
  implementing Report persistence, Knowledge/RAG, or additional infrastructure.

## Historical baseline — QUALITY-SCAN-002 (Post-P4-001)

This historical baseline supersedes `QUALITY-SCAN-001` for its original
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

Historical P4 open finding counts: **Blocker 0 / High 0 / Medium 0 / Low 1 / Info 1**.
QF-002 and QF-004 are closed and are not included in the open count.

### Historical P4 validated evidence

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
project_id          <runtime project UUID redacted>
research_session_id <runtime research-session UUID redacted>
thread_id           <runtime Agent-thread UUID redacted>
graph_id            researchflow
```

### Historical P4 findings

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
| `P7-003B/C` | PASS WITH FINDINGS | Validated run-local Citation output and established the frozen real Recall@5 baseline; Architect phase-exit review is pending. |
| `QUALITY-SCAN-004` | PASS WITH FINDINGS | Established the Post-P6 current baseline; P6-002 Gate B/C passed with Low 1 / Info 2 remaining. |
| `P6-002` | DONE | Recorded the accepted atomic Markdown-to-search slice, user trace, and zero-norm atomicity regression. |
| `BUG-P7-STREAM-001` | REVIEW | Reproduced and fixed the getter-enumeration `tools` mode 422; targeted browser Report E2E passed, extended browser matrix remains. |
| `QUALITY-SCAN-003` | PASS WITH FINDINGS | Established the Post-P5 current baseline; P5-002 Quality review passed with Low 1 / Info 1 remaining. |
| `P5-002` | DONE | Recorded the Quality-reviewed Project-scoped browser control-plane and direct Agent stream acceptance evidence. |
| `P4-001-GATE-B` | DONE | Recorded the user's five boundary explanations and closed QF-004. |
| `QUALITY-SCAN-002` | PASS WITH FINDINGS | Established the Post-P4 current baseline; QF-002 and QF-004 are closed. |
| `P4-001` | DONE | Verified revision `20260831_0002`, 26 Backend+Agent tests, failure boundaries, real Backend↔Agent Server smoke, and PAIR learning Gate B. |
| `QUALITY-SCAN-001` | PASS WITH FINDINGS | Established the Pre-P4 validation baseline; Architect rework set P4-001 readiness to READY and findings to Low 1 / Info 2. |
| `QUALITY-REPORT-001` | DONE | Created this maintained quality-report entry point under `docs/`. |
