# ResearchFlow

ResearchFlow is a local research-agent MVP that combines live Web research
with Project-scoped private Knowledge. It turns both source types into typed
Evidence, then produces a Report and an ordered Sources inventory through a
LangGraph workflow.

> **Current status:** working local/test MVP. This repository is intentionally
> not presented as a production-ready, multi-user service.

## What works today

- Minimal `Researcher → Tool → Evidence → Writer → Report/Citations` graph.
- Web search and Project-scoped permanent Knowledge search through a fixed Tool
  registry.
- Product-owned Projects and Research Sessions, with one immutable LangGraph
  `thread_id` per session.
- UTF-8 Markdown upload, structure-aware chunking, atomic Document/Chunk/vector
  persistence, and Project-filtered semantic retrieval.
- PostgreSQL 18 + pgvector 0.8.6, fixed 1024-dimensional `BAAI/bge-m3`
  embeddings, and exact cosine search.
- Typed Web and user-upload Evidence with URL or Document/Chunk provenance.
- Next.js chat UI with direct LangGraph streaming, checkpoint recovery,
  permanent Knowledge management, and latest-completed Sources rendering.
- User/Project filtering at the Product Backend boundary for the local trusted
  identity model.
- 146 Python regression tests and a versioned three-case retrieval baseline
  with measured macro Recall@5 = 1.0. This baseline is small and is not a claim
  of general answer quality.

## Architecture

```mermaid
flowchart LR
    UI[Next.js Frontend]
    BE[FastAPI Product Backend]
    LG[LangGraph Agent Server]
    DB[(PostgreSQL + pgvector)]
    WEB[Web Search]

    UI -->|Projects, Sessions, Documents| BE
    UI -->|messages + streaming| LG
    BE -->|product data + vectors| DB
    LG -->|knowledge_search HTTP| BE
    LG -->|web_search| WEB
    LG -->|Report + citations| UI
```

The two browser connections have different responsibilities:

- Product Backend owns Project membership, Research Session association,
  Document lifecycle, and scoped retrieval.
- LangGraph Agent Server owns messages, runs, checkpoints, streaming, Tool
  execution, and Agent output.
- `project_id` and local `user_id` enter Agent execution through immutable Run
  context. They are not model-generated Tool arguments or Graph State fields.
- Agent code calls Knowledge through a typed HTTP boundary and does not import
  pgvector or Product persistence.

See [Architecture](docs/ARCHITECTURE.md),
[API Contracts](docs/API_CONTRACTS.md),
[Data Model](docs/DATA_MODEL.md), and
[Decisions](docs/DECISIONS.md) for the authoritative boundaries.

## Repository layout

```text
src/researchflow/agent/       LangGraph State, nodes, Tools, Evidence, Citations
src/researchflow/backend/     FastAPI Product Backend and PostgreSQL ownership
src/researchflow/knowledge/   Chunking, embeddings, and vector retrieval
frontend/                     Next.js client derived from Agent Chat UI
tests/                        Agent, Backend, Knowledge, and contract regression
evaluations/                  Versioned logical retrieval fixture and evaluator
migrations/                   Alembic database revisions
docs/                         Architecture, Contracts, decisions, and task evidence
```

## Local development

### Prerequisites

- Python 3.12
- Node.js and pnpm 10
- Docker Desktop
- A SiliconFlow-compatible chat/embedding credential
- A Tavily credential for Web search

### Install

```powershell
py -3.12 -m pip install -e ".[backend,dev]"
Set-Location frontend
pnpm install --frozen-lockfile
Set-Location ..
```

Copy the example environment files and provide local values without committing
them:

```powershell
Copy-Item .env.example .env
Copy-Item frontend/.env.example frontend/.env.local
```

The Frontend identity value is a local development carrier, not a password or
authentication mechanism. PowerShell does not automatically export the root
`.env` values to Uvicorn; follow
[Backend local development](docs/BACKEND_LOCAL_DEV.md) for the exact process
environment and migration commands.

### Start the stack

```powershell
docker compose up -d postgres
py -3.12 -m alembic -c pyproject.toml upgrade head
```

Then start one process per terminal:

```powershell
langgraph dev --allow-blocking --no-browser
py -3.12 -m uvicorn researchflow.backend.app:app --reload --port 8000
Set-Location frontend; pnpm dev
```

Open `http://localhost:3000`, create/select a Project, upload a Markdown
Document, create a Research Session, and submit a research request.

## Validation

```powershell
$env:RESEARCHFLOW_DATABASE_URL = "postgresql+psycopg://researchflow:researchflow_dev_only@127.0.0.1:5432/researchflow"
$env:RESEARCHFLOW_TEST_DATABASE_URL = "postgresql+psycopg://researchflow:researchflow_dev_only@127.0.0.1:5432/researchflow_test"
py -3.12 -m pytest -W error -q
py -3.12 -m pip check

Set-Location frontend
pnpm exec tsc --noEmit
pnpm lint
pnpm build
```

The current lint baseline is 0 errors and 16 inherited Agent Chat UI warnings.
See [Quality Report](docs/QUALITY_REPORT.md) for what has and has not been
validated.

## Current limitations

- Knowledge ingestion accepts Markdown only; PDF, DOCX, HTML, OCR, and Saved
  Web Sources are not implemented.
- The graph has one Researcher decision and one Writer pass. Supervisor,
  multi-researcher execution, Compression, and Reviewer are deferred.
- Retrieval is exact vector search. BM25, hybrid/RRF, and reranking are not yet
  justified by the current evaluation baseline.
- Sources are a latest-successful inventory, not inline claim-level citations.
- Product Report/Evidence persistence and historical replay are not available.
- The browser-supplied local identity is not production authentication.
- The local LangGraph development runtime demonstrates checkpoint/rejoin
  behavior but is not a production retention guarantee. Restarting that
  in-memory Server may leave PostgreSQL Research Session rows whose Agent
  checkpoint State is no longer available.
- Production deployment, recovery, observability, cost/latency evaluation, and
  public security boundaries remain future work.

## Upstream acknowledgement

The Frontend is adapted from
[langchain-ai/agent-chat-ui](https://github.com/langchain-ai/agent-chat-ui),
whose MIT license remains at [frontend/LICENSE](frontend/LICENSE). The Phase 0
source review also studied
[langchain-ai/open_deep_research](https://github.com/langchain-ai/open_deep_research),
but ResearchFlow's current minimal Agent graph was reconstructed rather than
copied wholesale. The reconnaissance records are under
[docs/source-review](docs/source-review/).
