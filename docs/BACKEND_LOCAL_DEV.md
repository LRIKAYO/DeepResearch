# Backend local development

Run these commands from the repository root in PowerShell. The PostgreSQL
initialization script runs only when the `postgres_data` volume is empty.
Deleting that volume deletes local databases, so do not use `docker compose down
-v` unless a destructive reset is explicitly intended.

## Start PostgreSQL

```powershell
docker version
docker compose config
docker compose up -d postgres
docker compose ps
docker compose exec postgres pg_isready -U researchflow -d researchflow
```

## Install and configure

```powershell
py -3.12 -m pip install -e ".[backend,dev]"
$env:RESEARCHFLOW_DATABASE_URL = "postgresql+psycopg://researchflow:researchflow_dev_only@127.0.0.1:5432/researchflow"
$env:RESEARCHFLOW_TEST_DATABASE_URL = "postgresql+psycopg://researchflow:researchflow_dev_only@127.0.0.1:5432/researchflow_test"
$env:RESEARCHFLOW_LANGGRAPH_URL = "http://127.0.0.1:2024"
$env:RESEARCHFLOW_GRAPH_ID = "researchflow"
$env:RESEARCHFLOW_BACKEND_URL = "http://127.0.0.1:8000"
$env:RESEARCHFLOW_CORS_ORIGINS = "http://localhost:3000,http://127.0.0.1:3000"
$env:SILICONFLOW_BASE_URL = "https://api.siliconflow.cn/v1"
$env:SILICONFLOW_EMBEDDING_MODEL = "BAAI/bge-m3"
$env:SILICONFLOW_API_KEY = "<configured secret>"
$env:RESEARCHFLOW_USER_ID = "<local opaque UUID>"
```

These set process-local values and do not create or overwrite a `.env` file.
The runtime URL targets `researchflow`; tests use `researchflow_test` and refuse
to truncate any other database.

`RESEARCHFLOW_CORS_ORIGINS` is an optional comma-separated allow-list for
browser Product Backend requests. Each value must be an exact origin; leaving
it unset adds no CORS middleware. Credentials are not enabled.

Every Product request requires `X-ResearchFlow-User-Id`. The local UUID is an
opaque stand-in supplied by a trusted request boundary; it is not a password or
authentication token. The browser may use the same value through
`NEXT_PUBLIC_RESEARCHFLOW_USER_ID`, which is development-only public
configuration.

## Migrate and test

```powershell
py -3.12 -m alembic -c pyproject.toml upgrade head
$env:RESEARCHFLOW_DATABASE_URL = $env:RESEARCHFLOW_TEST_DATABASE_URL
py -3.12 -m alembic -c pyproject.toml upgrade head
$env:RESEARCHFLOW_DATABASE_URL = "postgresql+psycopg://researchflow:researchflow_dev_only@127.0.0.1:5432/researchflow"
py -3.12 -m pytest tests/backend tests/agent
```

If the development database already contains Projects from before P6-002, set
`RESEARCHFLOW_LEGACY_OWNER_USER_ID` to the intended local owner UUID before the
first development-database migration. The migration deliberately fails instead
of inventing an owner. Empty databases do not require this setting; unset it
again after migration.

## Run and smoke test

Start the Agent Server in one PowerShell after setting its provider credentials:

```powershell
langgraph dev --allow-blocking --no-browser
```

Start Product Backend in another PowerShell with the configuration above:

```powershell
py -3.12 -m uvicorn researchflow.backend.app:app --reload --port 8000
Invoke-RestMethod http://127.0.0.1:8000/health
$headers = @{ "X-ResearchFlow-User-Id" = $env:RESEARCHFLOW_USER_ID }
$project = Invoke-RestMethod http://127.0.0.1:8000/projects -Method Post -Headers $headers -ContentType "application/json" -Body '{"name":"Climate policy research"}'
Invoke-RestMethod "http://127.0.0.1:8000/projects/$($project.project_id)" -Headers $headers
$session = Invoke-RestMethod "http://127.0.0.1:8000/projects/$($project.project_id)/research-sessions" -Method Post -Headers $headers
$threadId = $session.thread_id
py -3.12 -c "from researchflow.backend.agent_server import get_agent_server; print(get_agent_server().get_thread('$threadId'))"
docker compose exec postgres psql -U researchflow -d researchflow -c "SELECT research_session_id, project_id, thread_id FROM research_sessions WHERE thread_id = '$threadId';"
```

For the permanent-Knowledge path, upload one UTF-8 Markdown file as the single
`file` multipart part, then search it with the same user header:

```powershell
$document = Invoke-RestMethod "http://127.0.0.1:8000/projects/$($project.project_id)/documents" -Method Post -Headers $headers -Form @{ file = Get-Item ".\notes.md" }
$searchBody = '{"query":"What does the document say?","limit":5}'
Invoke-RestMethod "http://127.0.0.1:8000/projects/$($project.project_id)/knowledge/search" -Method Post -Headers $headers -ContentType "application/json" -Body $searchBody
```

A successful upload is synchronous and atomic: `201` means the Document and
all of its Chunks/vectors are committed. Only Markdown up to 1,048,576 raw
bytes is accepted. Search uses exact cosine distance and is filtered by both
the current user and Project before its limit is applied.

Stop PostgreSQL without removing its data volume:

```powershell
docker compose stop postgres
```
