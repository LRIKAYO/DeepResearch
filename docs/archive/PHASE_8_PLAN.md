# Phase 8 — Local Browser Completion

**Status:** DONE — P8-FE-001, P8-FE-002, and P8-QA-001 passed; 00-Architect
accepted the local/test browser-completion boundary on 2026-09-15.

> Engineering goal: turn the implemented local Project-scoped research slice
> into one browser workflow that can manage Markdown Knowledge and show the
> latest completed research Sources.
>
> Release claim: local/test only.
>
> Planning scope: only the next three executable tasks are planned here.

## Current Repository Facts

- Phase 7 is DONE at the reviewed implementation baseline `3ba608b`; the
  documentation closure is commit `5d29b4a`.
- Product Backend already implements Project-scoped Markdown Document create,
  read, and list. Create is synchronous and returns `201` only after atomic
  chunk/vector indexing.
- The Frontend Backend client currently exposes only Project and Research
  Session calls. It discards the Backend response detail on errors.
- The current navigation sidebar already owns Project and Research Session
  selection. It has no permanent Knowledge list or upload action.
- The composer has an upstream PDF/image attachment control, but that content
  enters one chat message. It is not permanent Project Knowledge and must not
  be reused as though the lifecycles were the same.
- Agent output and checkpoint State already expose ordered `citations` beside
  `report`. The Frontend `StateType` currently types only `messages` and `ui`,
  and the thread renders messages, tools, and interrupts only.
- `useStream` already restores the selected LangGraph thread/checkpoint and
  preserves the latest successful Report/Citation pair when a later run is
  in-flight or fails.
- `@playwright/test` is installed, but the repository has no Playwright
  configuration, browser spec, or package script. Prior browser gates are
  recorded real-browser acceptance runs, not a committed E2E harness.

## Engineering Phase Goal

```text
Selected Project
  ├─ Product Backend → list/upload permanent Markdown Documents
  └─ Selected Research Session → LangGraph run with knowledge_scope
       → Report + citations in one successful Writer update
       → useStream latest checkpoint
       → Report messages + latest completed Sources in the browser
```

This batch consumes already implemented Contracts. It does not add a new
Product entity, Agent event, Graph node, persistence path, or API.

## Constraints

- Document management is Project-scoped and independent of the selected
  Research Session, `thread_id`, and `run_id`.
- Browser-side Project selection chooses which API path to call; Product
  Backend remains the ownership authority and repeats the User/Project filter.
- Permanent Markdown upload and transient composer attachments remain separate
  controls and separate state.
- Sources render only from typed `citations`. ToolMessage text, Tool calls,
  Report prose, and custom stream events are not Citation inputs.
- `citations` is a latest-successful source inventory, not per-message history
  and not claim-level attribution. Its `c1...` values are run-local ordinals,
  not durable IDs.
- The Frontend must use SDK checkpoint recovery. It must not add localStorage,
  a Frontend event log, or Product persistence for Report/Sources.
- A later in-flight or failed run leaves the prior successful Report/Citation
  pair intact. UI copy must make that lifecycle clear rather than presenting
  the old Sources as live progress for the new run.
- Keep the implementation inside the existing Backend client, sidebar/thread,
  and Stream provider boundaries. No new state-management, upload, query, or
  Citation library is justified.

## Explicitly Deferred

- PDF, DOCX, HTML, OCR, multi-file ingestion, Saved Web Source, delete/update,
  background ingestion, status polling, and download/preview endpoints.
- Inline claim markers, claim-to-source association, Citation correctness,
  Report/Evidence/Citation Product persistence, history, and replay.
- Research Progress events, event ordering/replay, `run_id` UI history, and a
  custom current-run status model.
- Supervisor, multi-researcher, Compression, Reviewer, BM25, hybrid/RRF,
  reranking, and retrieval changes.
- Production authentication, public deployment, and any security claim beyond
  the existing trusted local/test boundary.
- A new deterministic browser-test fixture or CI orchestration framework. The
  first gate is a recorded real-local-stack browser acceptance run.

## Dependency Order

```text
                    ┌─ P8-FE-001 Knowledge UI ─┐
P8-000 planning ────┤                          ├─ P8-QA-001 browser acceptance
                    └─ P8-FE-002 Sources UI ───┘
```

P8-FE-001 and P8-FE-002 intentionally touch different paths and may be given
to the Frontend owner in parallel. P8-QA-001 is the integration gate and may
not compensate for a defect by changing Backend, Agent, or product Contracts.

## P8-FE-001 — Project Knowledge Markdown UI

**Status:** DONE — implementation, module validation, real-stack evidence, and
00-Architect review passed on 2026-09-15.

**Goal**

Let a user list and upload permanent Markdown Documents for the selected
Project from the existing browser UI, with actionable and sanitized errors.

**Why Now**

The permanent Knowledge API and retrieval path already work, but a browser user
must leave the product and call the API manually before research can consume a
Document. This is the shortest missing control-plane link.

**Scope**

- Add the implemented Document metadata type and Project-scoped list/upload
  calls to the existing Frontend Backend client.
- Send exactly one `file` part using browser `FormData`; let the browser set the
  multipart boundary. For an accepted `.md` file, normalize the part media type
  to the API-required `text/markdown` when the browser supplies an empty or
  platform-dependent type; do not rewrite the file bytes.
- Add a small Knowledge section to the existing Project sidebar/mobile sheet.
- Load Documents when the selected Project changes, discard stale async
  responses from a previous Project, and refresh the authoritative server list
  after a successful upload.
- Use a dedicated native Markdown file input. Client hints may reject obvious
  mistakes early, while Backend validation remains authoritative.
- Map the approved `401`, `404`, `413`, `415`, `422`, and `503` responses to
  actionable UI copy. Only approved sanitized Backend detail may be surfaced;
  never display raw response bodies, provider errors, or stack traces.
- Add accessible loading, empty, uploading, success, and failure states.
- Update the local Frontend runbook and produce a task Completion Report.

**Out of Scope**

- Any Backend endpoint, model, migration, Knowledge algorithm, or Agent change.
- Document read/preview/download, delete/update, duplicate handling, status,
  pagination, drag-and-drop framework, or progress percentage.
- Reusing or expanding the composer PDF/image attachment path.
- Shared server-state libraries or moving the one-consumer Document list into
  `ProjectSessionProvider` without a demonstrated second consumer.

**Owner**

04-Frontend. 03-Backend reviews API/error fidelity; 00-Architect reviews the
Project-versus-Session boundary.

**Development Mode:** DELEGATE

**Learning Importance:** LOW

This is mostly consumption of an already learned and implemented Product API.
The lifecycle distinction matters, but the UI and request boilerplate do not
justify taking time away from the user's Backend focus.

**Learning Goal**

The user should be able to explain why a permanent Document is selected by
`project_id`, why it does not depend on a Research Session, and why the
composer attachment control is a different lifecycle. AI may implement the
Frontend code; Gate A plus Architect review is sufficient.

**Deliverables**

- Frontend Document metadata/client calls.
- Project Knowledge list/upload UI in the existing navigation surface.
- Actionable sanitized error mapping and focused loading/race handling.
- Frontend runbook update.
- `docs/tasks/P8-FE-001.md` Completion Report.

**Acceptance Criteria**

- No Project selected means no Document request and a disabled/hidden upload
  action; no Research Session is required to manage Project Knowledge.
- Selecting Project A then B cannot leave A's Documents visible under B, even
  if A's response arrives late.
- A valid non-empty UTF-8 `.md` upload sends one multipart `file`, returns only
  after indexing, uses the required `text/markdown` part type even when the
  browser did not infer it, refreshes the list in server order, and is
  available to a later research run without recreating the session.
- Unsupported media, invalid/empty/non-UTF-8/oversized Markdown, unavailable
  indexing, missing identity, unavailable Project, and network failure produce
  a useful safe message and do not add a phantom Document.
- The UI does not imply support for PDF/DOCX/HTML, preview, delete, background
  progress, or durable upload jobs.
- Existing Project/Session selection and composer attachments still work.
- Type check, lint with no new errors, production build, and focused formatting
  checks pass.

## P8-FE-002 — Latest Completed Sources UI

**Status:** DONE — implementation, module validation, selected-session
recovery evidence, and 00-Architect review passed on 2026-09-15.

**Goal**

Render the selected Research Session's latest successful ordered Sources from
the Agent's implemented `citations` State/output Contract.

**Why Now**

The Agent already emits a coherent Report/Citation pair, but the browser drops
the Citation half. Rendering that existing state closes source visibility
without inventing persistence or claim-level semantics.

**Scope**

- Add a Frontend discriminated union matching the two implemented Citation
  variants and type optional `citations` in the current stream State.
- Add one session-level **Latest completed research sources** component near
  the thread output, separate from individual message rendering.
- Render entries in supplied order and preserve duplicates.
- Render temporary Web provenance as an external HTTP(S) link with safe new-tab
  attributes. Render user-upload provenance as Document/section metadata only;
  do not invent a content/download link.
- Treat absent `citations` as no completed Citation state yet. Treat a present
  empty list as a valid latest successful run that used no Sources.
- Keep the prior successful Sources visible and clearly labelled while a later
  run is in-flight or after it fails, matching the checkpoint State Contract.
- Verify selected-session reload through the existing SDK recovery path.
- Produce a task Completion Report.

**Out of Scope**

- Parsing ToolMessage/tool-call text, Report prose, or custom events.
- Attaching Citations to historical message rows without a stable association
  Contract; comparing message text to `report` is not an accepted association.
- Inline markers, deduplication, scoring, source saving, Document preview,
  Product persistence, `run_id`, events, or replay.
- Agent State/schema, Writer, Backend, or database changes.

**Owner**

04-Frontend. 01-Agent reviews exact Citation shape; 00-Architect reviews the
latest-successful lifecycle and non-claim-level wording.

**Development Mode:** DELEGATE

**Learning Importance:** MEDIUM

The rendering code is small, but the difference between latest checkpoint
State, message history, live run state, and durable product history is a core
cross-module boundary. The user should review it but need not hand-write it.

**Learning Goal**

The user should be able to explain why Sources come from `stream.citations`
rather than ToolMessage text, why they are shown as session-level latest
successful output rather than per-message history, and what reload recovers.

**Deliverables**

- Frontend Citation types matching current Agent output.
- Typed Stream State and latest Sources renderer.
- Empty/absent, Web, user-upload, reload, in-flight, and failure behavior.
- `docs/tasks/P8-FE-002.md` Completion Report.

**Acceptance Criteria**

- Rendering consumes only typed `citations`; it never infers a Source from a
  Tool call, Tool result, message, or Report string.
- Citation order and duplicate entries are preserved; `c1...` is not presented
  as a Product ID or proof that a Report claim is attributed.
- Web Sources link only to their validated provenance URL. User uploads show
  filename and available section/page metadata without a fake link.
- Undefined Citation State renders no Sources panel. A present empty list
  renders an explicit no-Sources result for the latest completed research.
- A successful run shows its Sources; reload of the same selected session
  restores them through checkpoint/useStream State.
- Starting or failing a later run does not synthesize a new Citation list or
  mismatch prior Sources with a new Report. Copy remains explicit that the
  panel represents the latest completed research.
- Switching Research Sessions shows only the selected thread's recovered
  latest Citation State.
- No new event, persistence, SDK fork, state library, Backend API, or Agent
  change appears.
- Type check, lint with no new errors, production build, and focused formatting
  checks pass.

## P8-QA-001 — Local Browser Completion Acceptance

**Status:** DONE — real browser success/failure evidence, independent review,
full regression, and test-data cleanup passed on 2026-09-15.

**Goal**

Verify one real local browser path from permanent Markdown upload through
Project-scoped research to Report/Sources, including isolation, reload, and
controlled failure behavior.

**Why Now**

Module checks cannot prove that the two direct browser planes—Product Backend
control/Knowledge calls and LangGraph streaming—work together under the same
selected Project and Research Session.

**Scope**

- Run the real local PostgreSQL/pgvector, Product Backend, LangGraph Server,
  and Frontend with test-only identity and configured providers.
- Use two Projects with unique source tokens and upload one Markdown Document
  to each through the browser UI.
- Verify each selected Project lists only its own Document and a research run
  returns a Report plus ordered Sources containing only that Project's token
  and provenance.
- Reload a completed selected session and verify messages/Report/Sources recover
  from the existing Product selection plus LangGraph checkpoint path.
- Exercise one controlled upload validation failure and one controlled Agent
  Knowledge failure. Confirm actionable UI errors, no phantom Document, and no
  replacement/mismatch of the prior successful Sources.
- Re-run existing Python regression and Frontend type/lint/build gates.
- Record reproducible, credential-safe evidence in the Quality report and task
  Completion Report; clean only test data created by the acceptance run.

**Out of Scope**

- Changing architecture or weakening isolation to make the acceptance pass.
- A new mocked LangGraph protocol, generalized E2E fixture framework, CI
  orchestration, or production reliability claim.
- Quality evaluation of Writer faithfulness, claim attribution, retrieval
  thresholds, latency, load, or provider uptime.
- Any deferred Phase 8 feature.

**Owner**

05-Quality coordinates. 04-Frontend fixes Frontend-local defects; 03-Backend,
01-Agent, and 02-Knowledge only receive defects proven inside their boundary;
00-Architect reviews cross-module findings.

**Development Mode:** DELEGATE

**Learning Importance:** MEDIUM

The user does not need to operate the browser tooling, but should review where
control-plane selection becomes Agent Run context and where recovered Citation
State becomes UI.

**Learning Goal**

The user should be able to trace one browser action across Frontend → Product
Backend → PostgreSQL/Knowledge and one research action across Frontend → Agent
Server → Backend Knowledge → checkpoint → Frontend, and identify which owner
receives a failure at each edge.

**Deliverables**

- Recorded real-browser acceptance matrix with non-secret request/state facts.
- Updated `docs/QUALITY_REPORT.md`.
- `docs/tasks/P8-QA-001.md` Completion Report.
- Focused regression only if a discovered defect warrants one; no speculative
  test framework.

**Acceptance Criteria**

- Browser upload → indexed Document list → scoped research → Report → Sources
  passes on the real local stack.
- Project A/B Document lists, Agent Evidence, Reports, and Sources remain
  isolated using distinct tokens.
- Reload of a completed session restores the correct Report/Sources without
  Frontend-local persistence or ToolMessage parsing.
- Upload validation failure is actionable and creates no visible/persisted
  phantom Document.
- Controlled Knowledge/run failure is visible, does not become an empty-success
  result, and leaves the previous matching completed Report/Sources intact.
- All recorded evidence excludes credentials, full provider payloads, vectors,
  local environment files, and unrelated development data.
- Backend/Agent tests, dependency/compile checks, migration drift checks,
  Frontend type/lint/build, and `git diff --check` pass with no new regression.

## Batch Stop / Review Gate

00-Architect review accepted the local/test browser-completion Phase on
2026-09-15. Phase 8 is closed. This acceptance does not activate multi-format
parsing, Saved Web, Product Report persistence, claim-level Citation, deeper
research orchestration, production Auth, or deployment work. QF-006 records
that Agent-server process restart retention needs a future persistence and
stale-session reconciliation decision before any durability claim.

## P8-000 Completion Report

**Status:** DONE

**Changed:**

- Activated only the first local/test browser-completion batch selected by
  D-018.
- Defined the Project Knowledge UI and latest Sources UI as independent
  Frontend tasks followed by one Quality integration gate.
- Recorded the browser projection boundary in Architecture and D-019.

**Created:**

- `docs/PHASE_8_PLAN.md`.

**Key Decisions:**

- P8-FE-001 and P8-FE-002 may run in parallel and require no Backend or Agent
  implementation change.
- Permanent upload remains Project-scoped and separate from transient composer
  attachments.
- Latest Sources comes only from typed checkpoint `citations` and is not
  historical or claim-level Citation UI.
- The first Quality gate is a recorded real-local-stack browser acceptance,
  not a new generalized E2E/CI framework.

**Validation:**

- Inspected the current Frontend Backend client, Project/Session provider,
  Stream provider, thread/history render path, package scripts, implemented
  Backend Document routes, Agent State/Citation models, and accepted Contracts.
- Confirmed there is no existing Knowledge/Citation UI or committed browser
  test harness and that the planned slice needs no API/data-model change.
- Documentation whitespace and tracked diff checks passed. No runtime test was
  required because P8-000 changes planning documents only.

**What the user should understand:**

- This batch closes a browser usability gap over already working Backend and
  Agent paths. It does not expand research depth or production readiness.
- The user can delegate both Frontend implementations. The important review is
  whether they preserve Project ownership and latest-checkpoint Citation
  semantics.

**Architecture Impact:**

- D-019 adds the Phase 8 local browser projection boundary; existing API,
  State, persistence, identity, and module-ownership Contracts do not change.

**Open Questions:**

- A deterministic committed browser/CI fixture remains undecided and is not a
  blocker for this local acceptance batch.
- Comprehensive product features remain outside this Phase 8 batch and require
  later rolling decisions.

**Recommended Next Step:**

- Give P8-FE-001 and P8-FE-002 to 04-Frontend in parallel. Start P8-QA-001 only
  after both Completion Reports pass Architect review.
