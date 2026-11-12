# Acceptance record — 2026-11-12

A manual pass through the product in a browser, performed by the project owner
against the containerised stack. This file records what was verified, what the
pass found, and what it did not cover. `VERIFY.md` is the script that was
followed.

## Environment

| Piece | How it ran |
| --- | --- |
| PostgreSQL 18 + pgvector 0.8.6 | `docker compose up -d postgres` |
| Product Backend (FastAPI) | container, `researchflow:local`, port 8000 |
| Agent Server (`langgraph dev`) | container, `--no-reload`, port 2024 |
| Frontend (Next.js 15) | `pnpm dev`, port 3000 |

## Result

| # | Check | Result |
| --- | --- | --- |
| 1 | Create a Project from the sidebar | pass |
| 2 | Upload a real Markdown document (embedding + chunking) | pass |
| 3 | Create a research session (provisions a LangGraph thread) | pass |
| 4 | Ask a question the document answers; report arrives | pass |
| 5 | Every factual sentence carries a `[cN]` marker | pass |
| 6 | Clicking `[cN]` scrolls to that source row and highlights it | pass |
| 7 | "Saved reports" lists the finished run with time, rounds, citations | pass |
| 8 | Reload keeps the report (it lives in PostgreSQL) | pass |
| 9 | A Chinese question returns a Chinese report | pass |
| 10 | Error state: agent stopped, then create a session | **failed, then fixed** |

## What the pass found

Step 10 exposed a defect that no test had caught: with the Agent Server stopped,
creating a session left the UI on "creating" for **31–35 seconds** before any
error appeared.

Cause: Docker keeps a stopped container's published port accepting connections, so
the request hung instead of being refused. The LangGraph SDK builds its own
transport with `retries=5`, which multiplies its per-attempt timeout into roughly
31 seconds of silence.

Fix (`1c66d9b`, `fix(backend): bound agent calls so a dead server fails in 12s,
not 31`): `AgentServerClient` now enforces a call-level deadline independent of the
SDK's retry budget. Measured after the fix:

| Scenario | Before | After |
| --- | --- | --- |
| Agent down, create session | 503 after ~31 s | 503 after **12.0 s** |
| Agent up, create session | 201 in 0.01 s | 201 in **0.01 s** |

Re-verified: the error is readable and the action can be retried.

Both the healthy path and the failure path had unit tests before this pass. The
combination nobody had tested — *a container that is stopped but still holds its
port* — is exactly the class of problem a manual pass exists to find.

## Not covered

- **No browser automation.** The click-through and scroll-to-source were observed
  by a human, not asserted by a program. `pnpm check:modules` asserts the citation
  rewrite; it cannot assert scrolling or highlighting.
- **One run per check.** No concurrency (two sessions at once), no very large
  document, no mobile layout, no cross-browser.
- **Quality numbers are out of scope here.** They come from the evaluation
  reports, at their own sample sizes.

## Reproduce

```powershell
cd ResearchFlow
docker compose up -d --build
cd frontend; pnpm dev

# in another shell, after the UI checks:
py -3.12 -m scripts.e2e_smoke
```

`e2e_smoke` covers steps 1–4 and 7–8 without a browser; steps 5, 6 and 9 need the
human pass described in `VERIFY.md`.
