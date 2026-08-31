# ResearchFlow API Contracts

This document distinguishes implemented APIs from approved-next Contracts.
An approved-next Contract is ready for implementation but is not evidence that
the endpoint already exists.

## Product Backend Conventions

**Status:** Implemented by P3-001 and verified against PostgreSQL.

- Media type: `application/json`.
- `project_id` is serialized as the canonical hyphenated UUID string produced
  by Python `str(uuid.UUID(...))`.
- Datetimes are serialized as RFC 3339 timestamps with a UTC offset. Consumers
  compare parsed instants, not the textual `Z` versus `+00:00` representation.
- Request objects reject undeclared fields instead of silently ignoring them.
- Framework validation uses FastAPI's standard `422` response with a `detail`
  list. Tests may rely on the status, list shape, and error location/type; they
  must not freeze version-specific prose in `msg`.
- There is no Auth or tenant scope yet. These endpoints are a local MVP
  Contract and must not be presented as a production multi-user boundary.

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

Returns all Projects using the existing Project response shape, ordered by
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

Creates one Project.

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

A valid UUID that does not identify a Project returns:

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
unknown valid Project UUID returns the existing Project `404` response.

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

Returns Research Sessions owned by the Project, ordered by `created_at`
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

## Explicitly Deferred API Surface

- Project update and delete.
- Users, memberships, Auth, and tenant scoping.
- Research Session title, status, update, delete, archive, and run history.
- Report, Evidence, Source, Document, and Knowledge endpoints.
- Agent streaming proxy endpoints and historical event replay.

## References

- [FastAPI request bodies](https://fastapi.tiangolo.com/tutorial/body/)
- [FastAPI response models](https://fastapi.tiangolo.com/tutorial/response-model/)
- [FastAPI response status codes](https://fastapi.tiangolo.com/tutorial/response-status-code/)
- [FastAPI error handling](https://fastapi.tiangolo.com/tutorial/handling-errors/)
