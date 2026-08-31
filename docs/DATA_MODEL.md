# ResearchFlow Data Model

This document records product-owned data only when its lifecycle is approved.
LangGraph execution resources and provisional Agent working state are listed as
external/internal boundaries, not silently promoted into business entities.

## Status Legend

- **Implemented:** exists in current code and persistence.
- **Approved-next:** Contract is approved for the next implementation task.
- **Deferred:** name is known, but lifecycle/relationships are not approved.

## Resource Inventory

| Resource              | Status        | Authority                    |
| --------------------- | ------------- | ---------------------------- |
| Project               | Implemented   | Product Backend + PostgreSQL |
| LangGraph thread/run  | Implemented   | LangGraph Agent Server       |
| Agent `Evidence`      | Implemented   | Internal Graph State only    |
| Research Session      | Implemented   | Product Backend + PostgreSQL |
| Report product entity | Deferred      | Not decided                  |
| Document/Knowledge    | Deferred      | Not decided                  |
| User                  | Deferred      | Not decided                  |

## Project

### Lifecycle

Projects support create, read, and list. A Project name has no mutation
endpoint in this slice; this does not declare the name immutable forever.
Delete/archive semantics do not exist yet.

### Logical Fields

| Field        | Type                | Required | First writer                  | Update semantics         | Purpose                                                                    |
| ------------ | ------------------- | -------- | ----------------------------- | ------------------------ | -------------------------------------------------------------------------- |
| `project_id` | UUID                | yes      | Product Backend application   | immutable                | Product-level Project identity; never replaced by `thread_id` or `run_id`. |
| `name`       | string, 1–120 chars | yes      | Client, normalized by Backend | no P3-001 update surface | User-recognizable Project label; duplicates allowed.                       |
| `created_at` | timezone-aware time | yes      | PostgreSQL server default     | immutable                | Authoritative creation instant, returned in UTC.                           |

`updated_at` is intentionally absent. Without an update operation it would
always duplicate `created_at` and carry no state. Add it in the same migration
that introduces the first actual Project mutation.

### Physical PostgreSQL Mapping

| Column       | PostgreSQL shape                           | Constraints                                                        |
| ------------ | ------------------------------------------ | ------------------------------------------------------------------ |
| `project_id` | `uuid`                                     | primary key, not null; value supplied by Backend-generated UUID v4 |
| `name`       | `varchar(120)`                             | not null; `char_length(name) > 0`; no unique constraint            |
| `created_at` | `timestamp with time zone` (`timestamptz`) | not null; server default `CURRENT_TIMESTAMP`                       |

The Backend trims and validates `name` before insertion. The database repeats
the durable length/non-empty boundary but does not attempt to reproduce every
Unicode whitespace rule from application validation.

### ID and Time Authority

- The Product Backend generates `project_id` with Python standard-library UUID
  v4 before insertion. The database does not generate a second competing ID.
- PostgreSQL generates `created_at`. SQLAlchemy retrieves the server-generated
  value as part of the insert/refresh flow.
- Neither value enters LangGraph `AgentState`.

### Relationships

P4-001 implements the D-010 one-to-many relationship on the child side: one
Project may own many Research Sessions, and `research_sessions.project_id`
references `projects.project_id`. No LangGraph ID is added to the Project row.

## Research Session

**Status:** Implemented and verified by P4-001.

### Meaning and Lifecycle

A Research Session is the product-owned identity for one interactive research
conversation inside one Project. P4-001 supports create, read, and list only.
It has no title, mutable status, update, delete, or archive lifecycle yet.

Creating a Research Session also provisions exactly one LangGraph thread. The
thread association is immutable in this Phase. The thread may have no run yet,
and later submissions, retries, regenerations, or interrupt resumes may create
several Agent Server runs under the same thread/session.

### Logical Fields

| Field | Type | Required | First writer | Update semantics | Purpose |
| --- | --- | --- | --- | --- | --- |
| `research_session_id` | UUID | yes | Product Backend application | immutable | Product identity for one Project-scoped research conversation. |
| `project_id` | UUID | yes | Product Backend from the parent resource | immutable | Owning Project; foreign key to `projects.project_id`. |
| `thread_id` | opaque string | yes | LangGraph Agent Server | immutable | Checkpointed conversation identity used by `useStream`; unique across Research Sessions. |
| `created_at` | timezone-aware time | yes | PostgreSQL server default | immutable | Authoritative session creation instant, returned in UTC. |

`run_id` is intentionally absent. A run is an Agent Server execution resource,
and one session/thread can produce several runs. Session status, latest run,
and aggregate execution state are not inferred into this table.

### Physical PostgreSQL Mapping

| Column | PostgreSQL shape | Constraints |
| --- | --- | --- |
| `research_session_id` | `uuid` | primary key, not null; Backend-generated UUID v4 |
| `project_id` | `uuid` | not null; foreign key to `projects.project_id`; indexed for Project-scoped lists |
| `thread_id` | `text` | not null; unique; treated as an opaque external identifier |
| `created_at` | `timestamp with time zone` (`timestamptz`) | not null; server default `CURRENT_TIMESTAMP` |

Project deletion does not exist, so no cascade behavior is approved. Add it
only with a real Project deletion/archive lifecycle.

### Identity Authority and Projection

- Product Backend generates `research_session_id` before asking Agent Server to
  create a thread.
- LangGraph Agent Server generates `thread_id`; Product Backend persists the
  returned opaque string but does not reinterpret or regenerate it.
- Product Backend passes `project_id` and `research_session_id` into LangGraph
  thread metadata for diagnostics and search. PostgreSQL remains authoritative
  if that projection is absent or disagrees.
- Agent Server generates each `run_id`. Runs are neither children in the
  current business database nor fields in Agent Graph State.

### Cardinality

```text
Project 1 ─── 0..N Research Sessions
Research Session 1 ─── 1 LangGraph thread
LangGraph thread 1 ─── 0..N LangGraph runs
```

## Deferred Relationship Questions

- Whether Report and Evidence become Product Backend entities.
- How Project ownership changes once Auth/User is introduced.
- Whether a later product workflow needs more than one thread per Research
  Session. P4 fixes the simpler one-to-one association until such a caller
  exists.

These questions must be answered from the first real consuming use case, not by
adding nullable foreign keys in advance.

## References

- [SQLAlchemy UUID and timezone type guidance](https://docs.sqlalchemy.org/en/20/core/custom_types.html)
- [SQLAlchemy server-generated defaults](https://docs.sqlalchemy.org/en/20/orm/persistence_techniques.html)
