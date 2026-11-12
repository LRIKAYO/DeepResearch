# Verify it yourself

Ten minutes, no code. Everything below was run in a working state before this
file was written; if something fails, the failure is real.

## Start it

```powershell
cd ResearchFlow

# 1. Database + backend + agent (three containers, one command)
docker compose up -d --build

# 2. Frontend
cd frontend; pnpm install --frozen-lockfile; pnpm dev   # http://127.0.0.1:3000
```

Then confirm the three services agree with each other:

```powershell
py -3.12 -m scripts.e2e_smoke
```

It creates a Project, provisions a real thread, uploads two documents, runs the
agent through the Agent Server, and checks that the persisted report matches the
thread state. `PASS` means the stack works end to end.

**No registry access?** `docker compose up -d --build` cannot pull
`python:3.12-slim`. Run the database as a container and the two Python services as
local processes instead — same code, same environment:

```powershell
docker compose up -d postgres
py -3.12 -m scripts.run_local_stack backend     # http://127.0.0.1:8000
py -3.12 -m scripts.run_local_stack agent       # http://127.0.0.1:2024
```

**Port 2024 already in use, and the agent seems to forget threads?** A stale local
`langgraph dev` can hold `127.0.0.1:2024` while Docker publishes `0.0.0.0:2024`.
Windows prefers the more specific binding, so the host would talk to the old
process while the containers talk to the container. Stop every local agent before
`docker compose up` (`Get-NetTCPConnection -LocalPort 2024 -State Listen`).

## The checklist

1. **Create a Project.** Name it anything. It appears in the sidebar.
2. **Upload a document.** Use a README from `frontend/node_modules` — a real one,
   several thousand words. Wait for it to finish indexing.
3. **Create a research session.** The message box becomes enabled.
4. **Ask something the document answers.**
   Example: `What does arc.digits() return by default, and which option changes it?`
   Expected: a report whose factual sentences each carry `[c1]`-style markers, and
   a source list at the bottom.
5. **Click a `[cN]` marker.** The page scrolls to that source row and highlights
   it. `[cN]` inside a code block stays literal text and is not a link.
6. **Check "Saved reports".** The section under the sources lists the run you just
   made with its time, tool rounds and citation count. Expand it: the same report
   renders with its own sources.
7. **Reload the page.** The saved report is still there — it is in PostgreSQL, not
   in the Agent's memory.
8. **Ask something the document cannot answer**, for example a price or a person.
   Expected: a report that says it is not documented and cites what it inspected.
   It must not invent a number. If the retrieval was weak, the evidence was
   labelled as such, so the report should qualify rather than assert.
9. **Ask a Chinese question.** The report comes back in Chinese; an English
   question comes back in English.

## What a failure would look like

- **"Research session" creation returns 503.** The Agent Server is not reachable
  from the Backend. Check `docker compose logs agent` and the
  `RESEARCHFLOW_LANGGRAPH_URL` the Backend sees.
- **A thread exists on one side but not the other.** Two agent servers are
  running; see the port note above.


- No `[cN]` markers at all → the Writer audit did not run.
- Markers that do not scroll → the citation anchor rewrite or the source ids.
- "Saved reports" empty after a finished run → the run context lost
  `research_session_id`, so nothing was persisted.
- A report that restates the question without citing anything → retrieval
  returned nothing and the model filled the gap; that is the failure mode this
  project exists to prevent.

## Reproduce the numbers

```powershell
py -3.12 -m pytest tests -q -W error                       # 431 tests
py -3.12 -m evaluations.run_eval --validate-only           # dataset loads
py -3.12 -m scripts.context_coverage                       # the window ceiling
py -3.12 -m scripts.agent_eval --out evaluations/reports/agent-eval.json
```

The evaluation reports live in `evaluations/reports/`; the two that matter most
are `2026-11-11-v4-hybrid-decision.md` (retrieval) and
`2026-11-12-context-window.md` (agent-level, including the ordering bug).
