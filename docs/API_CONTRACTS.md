# ResearchFlow API Contracts

This document distinguishes implemented APIs from approved-next Contracts.
An approved-next Contract is ready for implementation but is not evidence that
the endpoint already exists.

## Product Backend Conventions

**Status:** Implemented by P3-001 and verified against PostgreSQL.

- Media type: `application/json`, except the implemented Markdown upload uses
  `multipart/form-data` with one `file` part.
- `project_id` is serialized as the canonical hyphenated UUID string produced
  by Python `str(uuid.UUID(...))`.
- Datetimes are serialized as RFC 3339 timestamps with a UTC offset. Consumers
  compare parsed instants, not the textual `Z` versus `+00:00` representation.
- Request objects reject undeclared fields instead of silently ignoring them.
- Framework validation uses FastAPI's standard `422` response with a `detail`
  list. Tests may rely on the status, list shape, and error location/type; they
  must not freeze version-specific prose in `msg`.
- Every Product endpoint except `/health` requires the trusted user context
  defined below. Resource requests enforce both that identity and Project
  membership; path/body values and Frontend selection are not authorization.

### Trusted User Context

P6-002 introduces one normalized header supplied by an authenticated/trusted
upstream boundary:

```http
X-ResearchFlow-User-Id: 14d809d2-42e7-4ec0-aafd-5289e9a4ef0a
```

The value is an opaque UUID. It is not accepted in Product request bodies or
paths. Missing identity returns `401` with `{"detail":"Authentication
required"}`; a malformed value returns the standard `422` header-validation
response. The Backend does not implement password, login, or token issuing in
P6-002. A deployment must protect or inject this header; direct public trust of
an arbitrary browser value is forbidden.

For resource anti-enumeration, a missing Project and a Project owned by another
user both return the existing `404 {"detail":"Project not found"}` response.
The exact-origin CORS allow-list additionally permits
`X-ResearchFlow-User-Id`. Local Frontend development may source the non-secret
UUID from `NEXT_PUBLIC_RESEARCHFLOW_USER_ID`; this is a development transport,
not production authentication.

## Health

### `GET /health`

**Purpose:** service readiness, including the configured business database.

Successful response:

```http
200 OK
```

```json
{
  "status": "ok"
}
```

If the configured database cannot answer the readiness query:

```http
503 Service Unavailable
```

```json
{
  "detail": "Database unavailable"
}
```

The response must not expose connection strings or driver exceptions.

## Projects

### `GET /projects`

**Status:** Implemented and verified by P4-001.

Returns only Projects owned by the current user using the existing Project response shape, ordered by
`created_at` descending and then `project_id` descending for deterministic
ties.

Successful response:

```http
200 OK
```

```json
[
  {
    "project_id": "3f511e4c-10d7-4a1d-9da8-8496d5dfac72",
    "name": "Climate policy research",
    "created_at": "2026-08-30T08:00:00+00:00"
  }
]
```

An empty database returns `[]`. Pagination is deferred until a real scale or UI
requirement appears.

### `POST /projects`

Creates one Project owned by the current trusted user identity.

Request:

```json
{
  "name": "Climate policy research"
}
```

Request rules:

| Field  | Contract                                                                            |
| ------ | ----------------------------------------------------------------------------------- |
| `name` | Required JSON string; trim surrounding whitespace; 1–120 characters after trimming. |

`null`, an empty/whitespace-only name, a name longer than 120 characters, a
non-string value, or an undeclared field returns the standard `422` validation
response.

Successful response:

```http
201 Created
```

```json
{
  "project_id": "3f511e4c-10d7-4a1d-9da8-8496d5dfac72",
  "name": "Climate policy research",
  "created_at": "2026-08-30T08:00:00+00:00"
}
```

Project names are not unique in P3-001. Duplicate names create independent
Projects, so this endpoint has no approved business `409` response.

### `GET /projects/{project_id}`

Returns one Project using the same response shape as `POST /projects`.

Successful response:

```http
200 OK
```

An invalid UUID path value returns the standard `422` validation response.

A valid UUID that does not identify a Project owned by the current user returns:

```http
404 Not Found
```

```json
{
  "detail": "Project not found"
}
```

## Research Sessions

**Status:** Implemented and verified by P4-001.

A Research Session is addressed under its owning Project. Its response shape
is:

```json
{
  "research_session_id": "a7f5482a-782a-4cac-a813-e6e650f4fd39",
  "project_id": "3f511e4c-10d7-4a1d-9da8-8496d5dfac72",
  "thread_id": "6f0a8481-0c53-4a2d-9771-c999144f6f9b",
  "created_at": "2026-08-30T08:05:00+00:00"
}
```

`thread_id` is serialized as the opaque non-empty string returned by LangGraph
Agent Server. The API does not promise that it is a Product UUID even if the
current Server happens to generate UUID-shaped values.

### `POST /projects/{project_id}/research-sessions`

Creates one Research Session and provisions its LangGraph thread. The request
has no JSON body.

Successful response:

```http
201 Created
```

The response is the complete Research Session shape above. Before returning,
Product Backend must have both a persisted row and a thread returned by Agent
Server.

An invalid Project UUID returns the standard `422` validation response. An
unknown or other-user Project UUID returns the existing Project `404` response.

If Agent Server cannot create the thread, return:

```http
503 Service Unavailable
```

```json
{
  "detail": "Agent service unavailable"
}
```

Do not expose Agent Server URLs, SDK exceptions, response bodies, or
credentials. No Research Session row is created on this path.

If database persistence fails after thread creation, Product Backend makes one
best-effort thread deletion attempt and preserves the original database failure
as the request failure. This is compensation, not a distributed transaction or
a guarantee that no infrastructure orphan can exist.

### `GET /projects/{project_id}/research-sessions`

Returns Research Sessions owned by the current user's Project, ordered by `created_at`
descending and then `research_session_id` descending for deterministic ties.
The response is a JSON array of the complete Research Session shape. A Project
with no sessions returns `[]`. An unknown Project returns the existing Project
`404` response.

Pagination is deferred for the first local MVP slice.

### `GET /projects/{project_id}/research-sessions/{research_session_id}`

Returns one complete Research Session only when it belongs to the Project in
the path.

- Invalid UUID path values return the standard `422` validation response.
- An unknown Project returns the existing Project `404` response.
- A missing Research Session, including a session owned by another Project,
  returns:

```http
404 Not Found
```

```json
{
  "detail": "Research session not found"
}
```

## Documents

**Status:** Implemented by P6-002. Create/read/list are all in scope.

A Document is addressed under its owning Project. The first response shape is
metadata only:

```json
{
  "document_id": "f7691f75-40ad-4ef7-8d97-1ce995a4e67e",
  "project_id": "3f511e4c-10d7-4a1d-9da8-8496d5dfac72",
  "filename": "policy-notes.md",
  "media_type": "text/markdown",
  "created_at": "2026-09-02T08:00:00+00:00"
}
```

The validated Markdown source is stored internally but is not returned by the
first create/read/list responses. Chunk and embedding records have no Product
CRUD endpoint.

### `POST /projects/{project_id}/documents`

Creates and fully indexes one Markdown Document. The request uses
`multipart/form-data` with exactly one required `file` part; undeclared form
parts are rejected.

File rules:

| Property | Contract |
| --- | --- |
| Filename | Trimmed 1–255 character basename ending in `.md` case-insensitively; reject `/`, `\`, NUL, empty/whitespace-only values, and longer names. |
| Part media type | Exactly `text/markdown`. |
| Raw size | 1–1,048,576 bytes. The implementation must stop reading after limit + 1 rather than buffering an unbounded request. |
| Encoding | Strict UTF-8. Do not silently replace undecodable bytes. |
| Text | Must contain at least one non-whitespace character; store decoded text without rewriting line endings. |

Successful response:

```http
201 Created
```

The response is the complete Document metadata shape above. Before returning,
the database must contain one Document and all of its deterministic Chunks and
embeddings in one committed transaction. The Document is then eligible for
Knowledge search.

Project errors follow existing conventions: an invalid UUID returns the
standard `422`; an unknown or other-user Project returns `404 Project not
found` and does not invoke chunking or embeddings.

Upload errors are sanitized as follows:

| Condition | Status | Response detail |
| --- | --- | --- |
| Missing `file` part or undeclared form part | `422 Unprocessable Entity` | Standard validation response. |
| Invalid filename | `422 Unprocessable Entity` | `Invalid Markdown filename` |
| Empty decoded text | `422 Unprocessable Entity` | `Markdown document cannot be empty` |
| Invalid UTF-8 | `422 Unprocessable Entity` | `Markdown document must be UTF-8` |
| Media type other than `text/markdown` | `415 Unsupported Media Type` | `Only text/markdown is supported` |
| More than 1,048,576 raw bytes | `413 Content Too Large` | `Markdown document exceeds the 1048576-byte limit` |

If chunking, embedding/vector validation, or the atomic database write fails,
return:

```http
503 Service Unavailable
```

```json
{
  "detail": "Knowledge indexing unavailable"
}
```

Do not expose provider URLs, model responses, credentials, source text, or
driver exceptions. No Document or Chunk row exists on any failed create path.
A failed database commit also rolls back both resources; there is no external
durable embedding resource to compensate.

Duplicate filename or content is allowed in this slice and creates an
independent Document. There is no business `409` response.

### `GET /projects/{project_id}/documents`

Returns Document metadata owned by the current user's Project, ordered by `created_at`
descending and then `document_id` descending. An empty Project returns `[]`;
an unknown Project returns the existing Project `404`. Pagination is deferred.

### `GET /projects/{project_id}/documents/{document_id}`

Returns one metadata response only when the Document belongs to the current
user's Project in the path.

- Invalid UUID values return the standard `422` validation response.
- Unknown Project returns the existing Project `404`.
- Missing Document, including a Document owned by another Project, returns:

```http
404 Not Found
```

```json
{
  "detail": "Document not found"
}
```

## Knowledge Search

**Status:** Implemented by P6-002; physical vector baseline
approved by P6-001.

### `POST /projects/{project_id}/knowledge/search`

Request:

```json
{
  "query": "What emissions target does the policy set?",
  "limit": 5
}
```

Request rules:

| Field | Contract |
| --- | --- |
| `query` | Required string, trimmed, 1–2,000 characters. |
| `limit` | Optional strict integer, default `5`, minimum `1`, maximum `20`. |

Undeclared fields, booleans/numbers used as strings, or a boolean used as
`limit` return the standard `422` validation response.

Successful response:

```http
200 OK
```

```json
[
  {
    "document_id": "f7691f75-40ad-4ef7-8d97-1ce995a4e67e",
    "chunk_id": "49700d21-4175-4dbc-a496-ab9f55d6b44f",
    "filename": "policy-notes.md",
    "content": "The policy sets a 2030 emissions target...",
    "score": 0.82
  }
]
```

Results are ordered by decreasing `score`; an eligible Project with no Chunks
returns `[]`. In the first physical slice, `score = 1 - cosine_distance`, where
PostgreSQL computes cosine distance with `<=>` and orders distance ascending.
`score` remains a provisional higher-is-better retrieval diagnostic and does
not promise a universal threshold, calibrated probability, final relevance
model, or citation correctness.

The authoritative retrieval query must join Chunk to Document to Project,
filter both the path `project_id` and current `owner_user_id`, order by cosine
distance ascending with `chunk_id` ascending as a deterministic tie-break, and
only then apply the bounded limit. It must never return a Chunk owned by another
Project or user, even if that Chunk is globally closer to the query vector.
P6-002 uses exact search and adds no approximate vector index.

An invalid, unknown, or other-user Project follows existing `422`/`404`
behavior. Query
embedding, vector validation, or retrieval database failure returns sanitized
`503` with `{"detail":"Knowledge search unavailable"}`. No provider or
database error body is exposed.

There is no Document filter, pagination cursor, threshold, BM25/hybrid mode,
reranker option, Agent-specific payload, or persisted search-result resource in
this Contract.

## Agent Knowledge Tool Contract

**Status:** Implemented by P7-001 and bound into the Agent Graph by P7-002.

`knowledge_search` exposes only:

```json
{
  "query": "What emissions target does the uploaded policy set?",
  "limit": 5
}
```

`query` is trimmed and must contain 1–2,000 characters. `limit` is a strict
integer from 1–20 and defaults to `5`. The model cannot supply `user_id` or
`project_id`; frozen `KnowledgeScope` is captured outside Tool arguments.

The typed Agent client calls the existing Project Knowledge HTTP endpoint with
the scope Project in the path and scope user in `X-ResearchFlow-User-Id`. It has
a 10-second timeout and performs no retry. Only a valid `200` hit list succeeds;
a valid empty list maps to empty Evidence. Status, timeout, transport, JSON, and
response-schema failures raise `Knowledge search unavailable` without exposing
Backend/provider details.

Each hit maps to `user_upload` Evidence containing source label, content,
retrieval score, and provenance with `document_id`, `chunk_id`, and filename.
The existing Web Tool emits the sibling `temporary_research` variant with URL
provenance. One shared Pydantic discriminator validates both variants before a
JSON-safe payload enters Agent State.

P7-002 reads a frozen `knowledge_scope` from LangGraph Run context and builds an
explicit registry ordered as `web_search`, then `knowledge_search`. The model
sees both schemas with parallel Tool calls disabled. Before execution, Agent
validates every requested name; valid calls then run sequentially in model-call
order, repeated calls are allowed, and any failure prevents a node State update
and Writer execution. `RESEARCHFLOW_BACKEND_URL` configures the internal Product
Backend base URL. The local Run-context carrier remains non-authoritative and
is not approved as a production authentication boundary.

P7-FE-001 centralizes Frontend `submit` wrapping: the current local user UUID
and selected Product Project UUID are written to the SDK run option
`context.knowledge_scope`. Lower-level message, regenerate, branch, and resume
callers cannot override it because the wrapper replaces any caller-supplied Run
context. The unrelated optional artifact `context` remains in Graph input and
does not carry access scope.

## Agent Citation Output Contract

**Status:** Implemented by P7-003B.

After a successful Writer update, Agent output adds `citations` beside
`messages` and `report`. `citations` is an ordered list with the same order and
duplicates as validated Evidence. IDs restart at `c1` for each successful run
and have no meaning outside that run.

Temporary Web Citation:

```json
{
  "citation_id": "c1",
  "source_type": "temporary_research",
  "source_label": "Example source",
  "excerpt": "A bounded excerpt from the collected evidence.",
  "provenance": {
    "url": "https://example.com/source",
    "captured_at": "2026-09-13T10:00:00+00:00"
  }
}
```

Project Document Citation:

```json
{
  "citation_id": "c2",
  "source_type": "user_upload",
  "source_label": "policy.md",
  "excerpt": "A bounded excerpt from the retrieved passage.",
  "provenance": {
    "document_id": "f70cc785-0df3-4dd7-a98d-f25b2f06e09e",
    "chunk_id": "49700d21-4175-4dbc-a496-ab9f55d6b44f",
    "filename": "policy.md",
    "page_number": 3,
    "section_path": ["Targets", "2030"]
  }
}
```

Optional provenance fields are omitted when unknown. `excerpt` strips leading
and trailing whitespace and is limited to 500 Unicode code points; truncation
uses the first 499 plus `…`. Retrieval score and relevance note are excluded.
A successful no-Tool run returns `citations: []`.

Writer returns `report` and `citations` in the same Graph State update. The
mapper reads validated Evidence only; ToolMessage/report parsing is forbidden.
This Contract is a latest-run source inventory, not inline claim attribution,
citation correctness, a PostgreSQL entity, a replay API, or a durable identity
scheme. P7-003B acceptance used fresh checkpointed threads and adds no
checkpoint migration.

## Explicitly Deferred API Surface

- Project update and delete.
- Product User CRUD, passwords, login, token issuing, and identity-provider
  implementation. The trusted user context and Project ownership enforcement
  are part of P6-002.
- Research Session title, status, update, delete, archive, and run history.
- Persisted Report/Evidence/Citation/Source resources, Citation UI or inline
  claim markers, saved Web Source, non-Markdown Document, Document
  mutation/download, and Agent-specific Knowledge endpoints.
- Agent streaming proxy endpoints and historical event replay.

## References

- [FastAPI request bodies](https://fastapi.tiangolo.com/tutorial/body/)
- [FastAPI response models](https://fastapi.tiangolo.com/tutorial/response-model/)
- [FastAPI response status codes](https://fastapi.tiangolo.com/tutorial/response-status-code/)
- [FastAPI error handling](https://fastapi.tiangolo.com/tutorial/handling-errors/)
