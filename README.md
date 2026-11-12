# ResearchFlow

**A verifiable deep-research agent: it plans, searches in bounded rounds, and every
claim in the report points back at a passage that supports it.**

Most "RAG + agent" demos stop at *retrieval worked*. ResearchFlow also answers the
next two questions: *is the report actually grounded?* and *did the extra machinery
help?* — with a citation verifier and a reproducible evaluation instead of a vibe.

```text
START
  │
  ▼
planner ──────► research question → 2-4 searchable sub-questions
  │
  ▼
researcher ◄──────────────────────┐
  │  tool_calls                    │  tool_rounds < max_tool_rounds
  ▼                                │
execute_tool ──────────────────────┘   web_search / knowledge_search
  │  no tool calls (or budget spent)
  ▼
writer ───────► report + ordered citations [c1]..[cN]
  │
  ▼
verifier ─────► per citation: full / partial / none support
  │
  ▼
 END
```

## What actually happens in one run

1. **Plan** — the question is decomposed into 2–4 self-contained sub-questions.
2. **Research loop** — the researcher sees the plan *and the evidence collected so
   far*, then either issues a focused tool call or stops. The loop is bounded by
   `RESEARCHFLOW_MAX_TOOL_ROUNDS` (default 3), so cost cannot run away.
3. **Write** — the writer receives evidence rendered as a numbered `[c1]..[cN]` block
   and must cite the ids supporting each claim, or mark the claim unverified.
4. **Verify** — every citation is checked against the passage it points at; a source
   that is listed but never cited is reported as such rather than passed silently.

Two tools only, both scoped and typed: `knowledge_search` (the Project's private
Markdown knowledge, via the Product Backend HTTP API) and `web_search` (Tavily).
Evidence is a validated Pydantic contract, not free text — a tool result that does
not validate never reaches the writer.

## What is verified today

| Claim | Evidence |
| --- | --- |
| Graph, planner, loop budget, writer, verifier, persistence | 172 deterministic tests in `tests/agent/` (stubbed models, no network); includes a `create_runtime()` end-to-end run that proves the prompt chains and run context agree |
| Citation coverage of a real report | 4 live runs: every listed source cited in the report body (coverage 1.00, `citations → cited` 10/10, 20/20, 24/24, 25/25), 0 "listed but not cited" verdicts. Units: `tests/agent/test_citation_audit.py` |
| Citation click-through | `[cN]` in the report is rewritten to `#citation-cN` (code fences untouched) and each source row carries that id; asserted by `pnpm check:modules` |
| Report persistence | a live run writes to the `reports` table through the same HTTP API the Frontend uses; verified end-to-end (run → stored row → `GET .../reports` → identical body → project deleted). 16 backend tests, 12 agent tests |
| Citation verifier judgement | **10 / 10** on known ground truth: 5 deliberately mismatched pairs all labelled `none`, 5 supported pairs all `full` (`scripts/verifier_probe.py`) |
| Agent-level quality, 4 live questions | coverage **1.00**, support rate **0.811** (30 full / 1 partial / 6 none of 37 citations) with context windows on, versus **0.585** in the same run with them off; mean 1.25 tool rounds, p50 **67 s**. n=4 questions and the same configuration varies by ~0.09 between days, so read this as directional (`2026-11-12-context-window.md`) |
| Knowledge ingestion, chunking, embedding, hybrid retrieval | 32 tests in `tests/knowledge/`, 121 offline quality tests (dataset labels, metric math, replay, rank-sensitivity analysis, corpus guards), and 71 backend tests that need PostgreSQL |
| Frontend type + lint | `pnpm exec tsc --noEmit` clean, `pnpm lint` 0 errors, `pnpm build` compiles |
| Retrieval quality on the small corpus, live run 2026-11-10 | Recall@1 0.900 · Recall@3 0.967 · Recall@5 1.000 · MRR 0.978 — but k=5 covered 25% of a 20-chunk corpus. See `evaluations/reports/2026-11-10.md` |
| **Retrieval quality on the real corpus, hybrid retrieval, 2026-11-11** | **Recall@1 0.556 · Recall@3 0.789 · Recall@5 0.856 · MRR 0.720 · nDCG@5 0.740 · latency p50 328 ms / p95 515 ms** over 5,091 chunks, where k=5 covers ~1%. Exact cosine plus BM25 fused with RRF; both configurations re-scored under the same abstain policy (`2026-11-11-v4-hybrid-decision.md`) |

### The first number that is actually informative

On the real corpus, through the Product Backend and pgvector, the same embedding
model scores **Recall@5 = 0.833** instead of 1.000. Nothing regressed — the
earlier corpus was simply too small for top-5 to be able to fail.

> Provenance: `2026-11-11-v4-live.*` is a **live** run — documents uploaded
> through the HTTP API, embedded server-side, searched in PostgreSQL. An earlier
> offline bench (`scripts/local_retrieval_bench.py`) reproduced Recall@5 exactly
> and MRR within 0.017, so the offline path is a usable fallback when no database
> is available; its artifacts were removed once the live run existed so only one
> set of numbers is in the tree.

What the failure analysis shows (`2026-11-11-v4-live-ANALYSIS.md`):

| k | Macro Recall | MRR | distractor in window |
| --- | --- | --- | --- |
| 1 | 0.556 | 0.696 | 9% |
| 3 | 0.744 | 0.696 | 14% |
| 5 | 0.833 | 0.696 | 27% |

- **9 of 45 answerable cases miss a relevant passage, and in all 9 the top-1
  lands in the same document as the answer.** The retriever finds the right
  document and the wrong chunk boundary — a chunking problem, not an embedding
  problem. That is the single most actionable result in this repository.
- 18 of 45 cases put something other than a relevant passage at rank 1, and 5
  rank a distractor above every relevant passage. With a median top-1/top-2
  margin of **0.030**, the ordering is decided by noise that small.
- Cross-lingual recall is 0.833: one of six Chinese queries misses English
  chunks that English queries find. bge-m3 is multilingual, not language-neutral.
- Abstention catches 3 of 5 unanswerable questions and falsely abstains on 3 of
  45 answerable ones; the 0.60 threshold is a policy default, not a calibration.

### One experiment, one negative result

The obvious fix for "wrong chunk boundary" is a smaller chunk. It was measured
rather than assumed — same documents, same 50 questions, same model, same
backend, only `RESEARCHFLOW_CHUNK_CHARS` changed (`2026-11-11-chunking-ab.md`):

| | 2000 chars | 1000 chars |
| --- | --- | --- |
| Macro Recall@5 | 0.833 | 0.833 |
| MRR | **0.696** | 0.635 |
| nDCG@5 | **0.713** | 0.666 |
| cases with a wrong top-1 | **18/45** | 22/45 |
| cases missing a passage | 9/45 | 9/45 |

Halving the window bought no recall and cost ranking quality, and 9 of 9 misses
are still same-document. So "just use smaller chunks" is ruled out; the useful
next levers change what a hit *means* (sentence-window or parent-document
retrieval, overlap with a group-aware metric, reranking after widening the
candidate set), not where the cut falls.

### Read the metric, not the headline

`Recall@5 = 1.000` on the old corpus was real but unflattering: each Project held
about 20 chunks, so top-5 returned a quarter of everything the system could
answer from. The real corpus removes that ceiling. Quote Recall@1, MRR and the
same-document miss count — they say where the system actually stands.

Adding BM25 to the cosine ranking moved Recall@3 by +0.045, Recall@5 by +0.022
and MRR by +0.024, and cut wrong-answer-wins from 5 cases to 3. It also roughly
doubled search latency and left Recall@1 flat: a lexical signal reorders the
window, it does not make the boundary problem disappear.

### Why `retrieval-v3` is not the default

A larger `retrieval-v3` set exists (1,448 chunks over 6 Projects), but its growth
is not documentation: 1,320 appended "background" paragraphs collapse to **six
templates**, each repeated about 220 times with an incrementing record number. A
corpus like that measures whether the retriever can ignore templated filler, not
whether it finds answers — so it stays in the repository only as a filler stress
fixture, and `tests/quality/test_dataset_v3_filler.py` pins that fact. The
default evaluation corpus is still the hand-authored `retrieval-v2` (122 chunks)
that the 2026-11-10 live run measured.

`evaluations/reports/retrieval-v3-compat-replay.*` reuses the v2 rankings against
the v3 corpus to exercise scoring and reporting. Its header carries that caveat
from the fixture itself, so regenerating it cannot drop the disclaimer.

### The real corpus: `retrieval-v4`

`retrieval_v4.json` is built from something real and already on disk: the README
files of the packages installed under `frontend/node_modules`. Six Projects
group those packages by purpose and compile each Project into six volumes, with
the package name and declared licence recorded in every section.

| Project | Packages | Chunks | Cases |
| --- | --- | --- | --- |
| markdown-pipeline | 42 | 1,521 | 9 |
| schemas-and-utilities | 42 | 1,005 | 8 |
| testing-and-lint | 42 | 882 | 8 |
| build-and-tooling | 39 | 720 | 8 |
| http-and-async-runtime | 36 | 604 | 8 |
| data-visualisation | 18 | 359 | 9 |
| **total** | **219** | **5,091** | **50** |

Composition: 45 answerable + 5 abstain, 12 easy / 24 medium / 14 hard, 49 cases
carry a declared distractor, 6 cross-lingual (Chinese query against English
documents) and 6 multi-hop (two passages in different volumes). Every anchor is
checked against the production chunker, so a label cannot drift from its chunk.

At ~850 chunks per Project, top-5 covers about 1% of the corpus instead of 25%,
which is the whole point of growing it. Exact duplicate chunks are dropped at
build time: packages from the same family repeat each other's sections, and a
repeated passage both wastes a top-k slot and makes a search hit impossible to
map back to a single chunk index — the live runner refuses to guess, which is
how the duplicates were found in the first place.

It is reproducible and it is not hand-written:

```powershell
# needs `pnpm install` in frontend/ first; never touches the network
py -3.12 -m scripts.build_eval_corpus `
  --cases-dir evaluations/datasets/_v4_cases `
  --out evaluations/datasets/retrieval_v4.json `
  --sources-out evaluations/datasets/retrieval_v4_SOURCES.md
```

Attribution and licence inventory: `evaluations/datasets/retrieval_v4_SOURCES.md`.
The authored cases live in `evaluations/datasets/_v4_cases/` (one file per
Project) so a review can read them without the 3 MB compiled corpus.

The default dataset stays `retrieval-v2` until a live run on v4 exists — the
default is the corpus with evidence behind it, not the newest one. To produce
that evidence:

```powershell
py -3.12 -m evaluations.run_eval `
  --dataset evaluations/datasets/retrieval_v4.json `
  --api http://127.0.0.1:8000 --user-id <uuid> --k 5 `
  --out evaluations/reports/<date>-v4.md `
  --json-out evaluations/reports/<date>-v4.json
```

It creates 6 Projects and 36 Documents in the target backend and **cannot delete
them** (the Product Backend has no delete endpoint), so point it at a disposable
stack. Ingestion embeds 5,304 chunks in batches of 32.

Everything above is reproducible offline. `evaluations/analyze.py` re-reads a
saved run and reports any cutoff without touching a model or the network:

```powershell
# A run may only be paired with the dataset version it was measured against;
# a mismatch is refused instead of silently describing the wrong corpus.
py -3.12 -m evaluations.analyze --report evaluations/reports/2026-11-10.json --dataset evaluations/datasets/retrieval_v2.json --out evaluations/reports/2026-11-10-ANALYSIS.md
```

## Quickstart

Prerequisites: Docker Desktop, Python 3.12, Node 20+ with pnpm, a SiliconFlow
chat/embedding credential, a Tavily key.

```powershell
# 1. Configuration (never committed)
Copy-Item .env.example .env
Copy-Item frontend/.env.example frontend/.env.local
#    fill SILICONFLOW_API_KEY and TAVILY_API_KEY in .env

# 2. Database + backend + agent
docker compose up -d --build
py -3.12 -m pip install -e ".[backend,dev]"
$env:RESEARCHFLOW_DATABASE_URL = "postgresql+psycopg://researchflow:researchflow_dev_only@127.0.0.1:5432/researchflow"
py -3.12 -m alembic -c pyproject.toml upgrade head

# 3. Frontend
Set-Location frontend; pnpm install --frozen-lockfile; pnpm dev
```

Open `http://localhost:3000`, create a Project, upload a Markdown document, create a
research session, and ask something that needs both the document and the web.

[`VERIFY.md`](VERIFY.md) is the ten-minute checklist: what to click, what each step
should produce, and what a failure would look like. `py -3.12 -m scripts.e2e_smoke`
checks the three services agree, without a browser.
[`ACCEPTANCE.md`](ACCEPTANCE.md) records the manual browser pass, including the
defect it found and the fix.

`langgraph.json` declares `env: .env`, so the agent server loads that file directly —
no manual `$env:` exports needed for the agent. The backend reads the same file when
run through compose; run locally, it needs the variables exported in its shell.

## Configuration

| Variable | Used by | Meaning |
| --- | --- | --- |
| `SILICONFLOW_API_KEY` / `_BASE_URL` / `_MODEL` | agent, backend | chat model for planner/researcher/writer/verifier |
| `SILICONFLOW_EMBEDDING_MODEL` | backend | must be `BAAI/bge-m3` (1024-d, enforced) |
| `TAVILY_API_KEY` | agent | web search |
| `RESEARCHFLOW_MAX_TOOL_ROUNDS` | agent | upper bound on research rounds (1–10, default 3) |
| `RESEARCHFLOW_DATABASE_URL` | backend | PostgreSQL + pgvector DSN |
| `RESEARCHFLOW_BACKEND_URL` | agent | where `knowledge_search` calls the backend |
| `RESEARCHFLOW_LANGGRAPH_URL` / `_GRAPH_ID` | backend | where sessions create threads |
| `RESEARCHFLOW_CORS_ORIGINS` | backend | exact origin allow-list (empty = no CORS) |
| `NEXT_PUBLIC_BACKEND_URL` / `NEXT_PUBLIC_RESEARCHFLOW_USER_ID` | frontend | Product Backend URL and the local identity header |

## Repository layout

```text
src/researchflow/agent/       planner, researcher, tools, writer, verifier, graph
src/researchflow/backend/     FastAPI Product Backend (Projects, Sessions, Documents)
src/researchflow/knowledge/   Markdown chunking, embeddings, pgvector retrieval
frontend/                     Next.js client (adapted from Agent Chat UI)
evaluations/                  dataset, runner and reports
tests/                        agent / backend / knowledge / quality regression
docs/                         current contracts (architecture, API, data model, decisions)
docs/archive/                 phase 1-8 process archive, kept for traceability only
migrations/                   Alembic revisions
```

## Design boundaries worth knowing

- **Scope is data, not model output.** `user_id` and `project_id` travel through
  immutable run context; the model cannot choose them and they never enter Graph
  State, so a prompt injection cannot widen retrieval scope.
- **Evidence is a contract.** Web and uploaded evidence are two discriminated
  Pydantic models with provenance; citations are derived from validated evidence only.
- **A failed run must not erase a good report.** Only a successful writer/verifier
  pass replaces `report`/`citations`/`verification`; each new run resets only its
  search slice (`evidence`, `tool_rounds`).

## Known limitations

- Knowledge ingestion is Markdown only; PDF/DOCX/HTML/OCR are not implemented.
- Reports **are** persisted (`reports` table, append-only) and the run writes one
  after the verifier. What is still missing is the UI surface for reading older
  reports: the API is there, the panel is a follow-up. A run started before a
  restart, and never finished, still has no report row.
- Retrieval is exact cosine search with no ANN index, no BM25 and no reranking.
- Sources are a run-scoped inventory. Each `[cN]` in the report links to its
  source row, and the Verifier scores the pair, but attribution is per source,
  not per clause: a sentence citing two sources is not split into which source
  supports which half.
- The pipeline never refuses a question the corpus cannot answer. The unanswerable
  probe question produced a well-cited "no such pricing is documented" report, and
  the verifier correctly called those citations `full` — so the support rate says
  "the citations are real", not "the answer is true".
- The Writer's citation coverage is enforced by prompt plus one repair pass, not
  by a deterministic guarantee. Four live runs reached 100% coverage; a run that
  still leaves ids uncited publishes them with an explicit "listed but not
  cited" verdict rather than inventing a marker.
- The browser-supplied `X-ResearchFlow-User-Id` header is a local trusted-identity
  stand-in, not authentication.
- CI covers the deterministic checks only; live model and retrieval evaluation stay manual.

## Environment knobs

| Variable | Default | Effect |
| --- | --- | --- |
| `RESEARCHFLOW_CHUNK_CHARS` | 2000 | Chunk size at ingestion; the committed corpora are built at 2000 and record it. |
| `RESEARCHFLOW_CHUNK_OVERLAP` | 0 | Chunk overlap at ingestion. |
| `RESEARCHFLOW_MAX_TOOL_ROUNDS` | 3 | Research rounds before the Writer runs (1–10). |
| `RESEARCHFLOW_CONTEXT_RADIUS` | 2 | Chunks added on each side of a retrieved hit (0–3); 0 disables expansion. |
| `RESEARCHFLOW_RETRIEVAL_MODE` | hybrid | `hybrid` (cosine + BM25 via RRF) or `cosine` for comparison. |
| `NO_PROXY` | — | Must include the domestic provider host when a system proxy is configured but cannot reach it. |

## Validation

```powershell
py -3.12 -m pytest tests/agent tests/knowledge tests/quality -q   # no database required
py -3.12 -m pip check

$env:RESEARCHFLOW_DATABASE_URL = "postgresql+psycopg://researchflow:researchflow_dev_only@127.0.0.1:5432/researchflow"
$env:RESEARCHFLOW_TEST_DATABASE_URL = "postgresql+psycopg://researchflow:researchflow_dev_only@127.0.0.1:5432/researchflow_test"
py -3.12 -m alembic -c pyproject.toml upgrade head
py -3.12 -m alembic -c pyproject.toml check          # both databases must report no drift
py -3.12 -m pytest -q                                 # 394 tests including the backend

Set-Location frontend
pnpm exec tsc --noEmit
pnpm lint                                              # 0 errors, 6 warnings
pnpm check:modules                                     # offline component-contract assertions
pnpm build
```

### Manual, credentialed runs

These need a running backend, provider keys and a disposable database. They are
scripts, not tests, and their recorded output lives in `evaluations/reports/`:

```powershell
# retrieval quality on the evaluation corpus (creates Projects; delete them after)
py -3.12 -m evaluations.run_eval --dataset evaluations/datasets/retrieval_v4.json `
  --api http://127.0.0.1:8000 --user-id <uuid> --k 5 --out evaluations/reports/<date>.md

# re-score a saved run under the current policy, without re-running retrieval
py -3.12 -m scripts.rescore_run --report <run>.json --out <fixture>.json

# agent-level quality: rounds, citation coverage, verifier verdicts, latency
py -3.12 -m scripts.agent_eval --out evaluations/reports/agent-eval.json

# verifier judgement against known ground truth
py -3.12 -m scripts.verifier_probe --out evaluations/reports/verifier-probe.json
```

## Continuous integration

Every push and pull request runs `.github/workflows/ci.yml` on GitHub-hosted Ubuntu:

- **Python** — PostgreSQL 18 + pgvector 0.8.6, both databases migrated with Alembic, then
  `pytest tests -q -W error` and `pip check`.
- **Evaluation** — `run_eval --validate-only` and `pytest tests/quality -q`, offline.
- **Frontend** — Node 20, `tsc --noEmit`, `lint`, `check:modules`, `build` with pnpm 10.5.1.

No model calls and no live evaluation run in CI: those need `SILICONFLOW_API_KEY` and
`TAVILY_API_KEY`, so they stay a manual, documented step.

## Upstream acknowledgement

The frontend is adapted from [langchain-ai/agent-chat-ui](https://github.com/langchain-ai/agent-chat-ui)
(MIT, see `frontend/LICENSE`). The Phase 0 source review of
[langchain-ai/open_deep_research](https://github.com/langchain-ai/open_deep_research)
is kept in `docs/archive/source-review/`. The current graph is a deliberately small
reconstruction, not a copy.
