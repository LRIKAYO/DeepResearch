# P7 Exit and Product-Completion Decision Brief

**Status:** DONE — 00-Architect selected P7-EXIT A on 2026-09-14 after commit
`3ba608b` satisfied the final version-control delivery gate.

## Why this decision is required

P7-003B and P7-003C are implemented and validated. D-017 requires 00-Architect
to inspect that evidence before declaring the Phase 7 exit or activating a new
batch. The repository has no approved release definition beyond the rolling P7
tasks, so “the whole product is finished” cannot be inferred from test success.

This brief does not activate code work or silently expand module ownership.

## Architect Review — 2026-09-14

### Disposition

- **P7 implementation:** ACCEPTED. No blocking Citation, Agent/Knowledge,
  streaming, retrieval-evaluation, API, data-model, or module-ownership defect
  was found.
- **P7-EXIT:** Option A accepted; Phase 7 is closed. No additional product
  feature is a Phase 7 exit condition.
- **Delivery gate:** satisfied by commit `3ba608b phase6_7_finished`. The
  intended Phase 6/7 implementation, migration, tests, Contracts, task records,
  logical fixture, and baseline artifact are tracked; the worktree was clean at
  inspection.
- **Next-release direction:** Option A accepted as a local/test-only browser
  completion slice. This review records the target but does not activate or
  implement its tasks.

### Satisfied exit action

Commit `3ba608b` contains the intended Phase 6/7 code, migration, tests,
Contracts, task records, logical fixture, and credential-safe baseline
artifact. Final inspection confirmed that:

1. the fixture and baseline artifact are tracked and their recorded SHA-256
   still matches;
2. no credential, local environment file, provider response, generated UUID,
   vector, build output, or runtime log entered the commit;
3. `git status` was clean and contained no unexplained Phase 6/7 deliverable;
4. the current `146 passed` regression and documentation-only checks still
   describe the committed source.

The local `.langgraph-dev.err.log` and `.langgraph-dev.out.log` files did not
enter the commit, and `/.langgraph-dev*.log` is now ignored. No feature change
was required to satisfy this delivery-integrity gate.

### Engineering Exit Criteria

- Scoped Agent Knowledge Tool and two-Tool Graph: passed.
- Frontend Run-context transport, native multi-mode stream, recovery, and
  Project A/B isolation: passed from the recorded real browser matrix.
- Run-local Citation projection and matching Report/Citation checkpoint
  behavior: passed by inspection and independent regression.
- Versioned logical retrieval fixture and Recall@5 harness: implementation,
  artifact semantics, SHA match, and repository versioning passed.
- Python regression, dependency check, compilation, development/test migration
  drift, Frontend type check/lint/build: passed in Architect review.

### Learning-relevant Findings

- P7-001/P7-002 retain their recorded user Gate B/C evidence.
- P7-003B/P7-003C were explicitly delegated. Their engineering gates pass, but
  this review does not claim that the user personally completed their original
  learning exercises or mastered Citation/Recall semantics.
- The key distinction to retain is that `citations` is a latest-successful
  source inventory, while Recall@5 evaluates passage retrieval coverage; neither
  proves claim attribution, Writer faithfulness, or final answer quality.

### Independent validation performed

- `146 passed` with warnings treated as errors.
- `pip check` and Python compilation passed.
- Development and test databases both report migration head `20260904_0003`
  and no Alembic drift.
- Frontend type check and production build passed; lint remains 0 errors and 16
  previously recorded warnings.
- The checked-in-working-tree fixture SHA-256 matches the baseline artifact.
- The real provider baseline was not rerun because the Architect process did
  not contain SiliconFlow credentials. Its guarded code path, logical ranking,
  result artifact, and prior Quality evidence were inspected; this is not a new
  independent provider-run claim.

## Evidence available for review

- P7-003B: strict run-local Citation output, atomic Report/Citation checkpoint
  behavior, and fresh-thread failure/recovery coverage.
- P7-003C: frozen logical dataset plus real `BAAI/bge-m3` scoped API baseline;
  three cases each measured Recall@5 = 1.0 and macro Recall@5 = 1.0.
- Combined Python warnings-as-errors regression: 146 passed.
- Dependency check, compilation, two Alembic drift checks, Frontend type check,
  lint (0 errors; 16 pre-existing warnings), and production build passed.
- The evaluator cleaned exactly the rows it created in `researchflow_test` and
  did not touch development data or checkpoints.

Primary artifacts:

- `docs/tasks/P7-003B.md`
- `docs/tasks/P7-003C.md`
- `docs/evaluations/retrieval-v1-baseline-2026-09-14.json`
- `docs/QUALITY_REPORT.md`

## ADR-P7-EXIT — Phase 7 disposition

### Option A — Close Phase 7 (recommended)

Accept the implemented Knowledge Tool, two-Tool graph, scoped Frontend stream,
run-local Citation output, and first retrieval baseline as the P7 boundary.
Known future product capabilities remain explicit new work.

### Option B — Keep Phase 7 open

Require one additional, explicitly named acceptance condition before exit. The
Architect must state that condition; Citation UI, Saved Web, parsers, Auth, and
Report persistence are not automatically part of D-017.

## ARCHITECTURE DECISION REQUIRED — next release target

### Current problem

The tested system is a strong local vertical slice, but several capabilities
commonly implied by a complete ResearchFlow product have no approved Contract
or lifecycle. Implementing them together would alter the Product data model,
security boundary, Evidence provenance, Frontend surface, and Agent graph.

### Option A — Local daily-use release first (recommended)

Activate the smallest user-visible completion batch:

1. Project Knowledge UI for Markdown upload, document list, and actionable
   ingestion errors using existing Backend APIs.
2. Sources inventory UI rendered from the implemented latest-run `citations`;
   no inline claim markers or new persistence.
3. Browser E2E for upload → scoped research → Report/Sources, Project isolation,
   reload, and failure display.

This option largely consumes approved Contracts and gives the current backend a
complete browser workflow. It makes a local/test product claim only.

### Option B — Comprehensive release scope

Before calling the product complete, define and implement all of the following
as separate tasks:

1. domain-neutral PDF, DOCX, and HTML parsers with structural/page metadata;
2. explicit Saved Web Source save/delete/re-index lifecycle in permanent
   Project Knowledge, without embedding ordinary temporary research;
3. Product Report/Evidence/Source persistence and historical replay identity;
4. claim-level Citation semantics and evaluation, if required by the UX;
5. iterative Deep Research graph behavior beyond the current single Researcher
   decision and Writer pass;
6. production authentication/scope injection, retention, deployment,
   observability, recovery, and release thresholds.

This option requires multiple ADRs; it should not be implemented as one
unreviewable task.

## Affected modules

- 00-Architect: release definition, lifecycle and security decisions.
- 01-Agent: research loop, durable output identity, claim attribution.
- 02-Knowledge: multi-format normalization and Saved Web ingestion lifecycle.
- 03-Backend: source/report resources, mutation semantics, authentication edge.
- 04-Frontend: Knowledge management and Sources/report experience.
- 05-Quality: release scenarios, larger ground truth, quality/reliability gates.

## Recommendation

Select `P7-EXIT: A` and `NEXT-RELEASE: A`. Ship the local daily-use browser
closure as the next bounded batch, then decide Saved Web/multi-format and public
deployment independently. BM25, RRF, and reranking should remain evidence-led:
the first baseline does not justify adding them.

## Architect Decision

```text
P7-EXIT: A
NEXT-RELEASE: A
Security claim: local/test only
Activated task(s): none in this review
```

## P7 Exit Review Completion Report

**Status:** DONE

**Changed:**

- Accepted P7-EXIT A after the engineering, architecture, and repository
  delivery gates passed.
- Accepted the local/test browser-completion direction without activating its
  implementation tasks.

**Created:**

- None.

**Key Decisions:**

- Phase 7 ends at the implemented scoped research, Citation, and Recall@5
  boundary; deferred product features are not retroactive exit requirements.
- Commit `3ba608b` is the reviewed Phase 6/7 implementation baseline.

**Validation:**

- Commit contents, clean worktree, ignore rules, credential/runtime-artifact
  exclusions, fixture tracking, and fixture/result SHA match passed.
- The prior Architect run passed 146 Python tests, dependency/compile checks,
  both Alembic drift checks, and Frontend type/lint/build gates.

**What the user should understand:**

- Phase completion proves this bounded local engineering slice. It does not
  prove production security, claim-level citation correctness, answer quality,
  or mastery of the delegated P7-003B/C learning goals.

**Architecture Impact:**

- D-018 records the Phase 7 boundary and next local/test release direction.

**Open Questions:**

- The next batch still needs its own rolling task plan. Comprehensive release
  capabilities remain separately decided work.

**Recommended Next Step:**

- Commit this documentation-only closure, then plan only the first 2–4 tasks of
  the local browser-completion batch.
