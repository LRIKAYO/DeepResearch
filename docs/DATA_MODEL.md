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
| Document              | Implemented   | Product Backend + PostgreSQL |
| Document Chunk        | Implemented   | 02-Knowledge + PostgreSQL    |
| `KnowledgeHit`        | Implemented   | Runtime retrieval response   |
| Agent `Citation`      | Implemented   | Agent State/output only      |
| Authenticated User ID | External      | Upstream identity boundary   |

## Project

### Lifecycle

Projects support create, read, and list. A Project name has no mutation
endpoint in this slice; this does not declare the name immutable forever.
Delete/archive semantics do not exist yet.

### Logical Fields

| Field        | Type                | Required | First writer                  | Update semantics         | Purpose                                                                    |
| ------------ | ------------------- | -------- | ----------------------------- | ------------------------ | -------------------------------------------------------------------------- |
| `project_id` | UUID                | yes      | Product Backend application   | immutable                | Product-level Project identity; never replaced by `thread_id` or `run_id`. |
| `owner_user_id` | UUID             | yes      | Trusted request identity      | immutable                | Opaque upstream owner identity used with `project_id` for authorization. |
| `name`       | string, 1–120 chars | yes      | Client, normalized by Backend | no P3-001 update surface | User-recognizable Project label; duplicates allowed.                       |
| `created_at` | timezone-aware time | yes      | PostgreSQL server default     | immutable                | Authoritative creation instant, returned in UTC.                           |

`updated_at` is intentionally absent. Without an update operation it would
always duplicate `created_at` and carry no state. Add it in the same migration
that introduces the first actual Project mutation.

### Physical PostgreSQL Mapping

| Column       | PostgreSQL shape                           | Constraints                                                        |
| ------------ | ------------------------------------------ | ------------------------------------------------------------------ |
| `project_id` | `uuid`                                     | primary key, not null; value supplied by Backend-generated UUID v4 |
| `owner_user_id` | `uuid`                                  | not null; no Product User FK; indexed for owner-scoped list queries |
| `name`       | `varchar(120)`                             | not null; `char_length(name) > 0`; no unique constraint            |
| `created_at` | `timestamp with time zone` (`timestamptz`) | not null; server default `CURRENT_TIMESTAMP`                       |

The Backend trims and validates `name` before insertion. The database repeats
the durable length/non-empty boundary but does not attempt to reproduce every
Unicode whitespace rule from application validation.

P6-002 adds `owner_user_id` without a server default. On a database that
already contains Projects, the migration requires a valid
`RESEARCHFLOW_LEGACY_OWNER_USER_ID`, backfills every existing local-MVP Project,
then makes the column non-null. It fails before inventing an owner when that
value is missing or invalid. A fresh empty database does not require the legacy
setting.

### ID and Time Authority

- The Product Backend generates `project_id` with Python standard-library UUID
  v4 before insertion. The database does not generate a second competing ID.
- The upstream identity boundary owns `owner_user_id`; Product Backend never
  accepts it from a Project request body or path.
- PostgreSQL generates `created_at`. SQLAlchemy retrieves the server-generated
  value as part of the insert/refresh flow.
- Neither value enters LangGraph `AgentState`.

### Relationships

D-014 adds one external authenticated User ID to many Projects. It is an opaque
ownership value rather than a Product User row. P4-001 implements the D-010
one-to-many relationship on the child side: one Project may own many Research
Sessions, and `research_sessions.project_id` references `projects.project_id`.
No LangGraph ID is added to the Project row.

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

## Document

**Status:** Implemented by P6-002.

### Meaning and Lifecycle

A Document is one permanent source owned directly by a user-owned Project. The first
source type is a bounded UTF-8 Markdown upload. It is not owned by a Research
Session, thread, or run, so later sessions under the same Project may retrieve
it.

The first lifecycle supports atomic create, metadata read, and Project-scoped
list only. Create succeeds only after every Chunk and embedding is ready to
commit in the same database transaction. Update, delete, versioning, duplicate
detection, and asynchronous status do not exist.

### Logical Fields

| Field | Type | Required | First writer | Update semantics | Purpose |
| --- | --- | --- | --- | --- | --- |
| `document_id` | UUID | yes | Product Backend application | immutable | Product identity for one permanent source. |
| `project_id` | UUID | yes | Product Backend from parent path | immutable | Owning Project and authoritative retrieval scope. |
| `filename` | string, 1–255 chars | yes | Client, validated by Backend | immutable | User-recognizable Markdown source name; path separators are rejected. |
| `media_type` | literal `text/markdown` | yes | Product Backend after HTTP validation | immutable | Canonical first-slice source media type. |
| `content_text` | non-empty text | yes | Product Backend after strict UTF-8 decoding | immutable | Internally stored Markdown source; omitted from first API responses. |
| `created_at` | timezone-aware time | yes | PostgreSQL server default | immutable | Authoritative creation instant returned in UTC. |

`filename` must end in `.md` case-insensitively. The Backend rejects `/`, `\`,
NUL, empty/whitespace-only names, and names longer than 255 characters rather
than treating a client filename as a filesystem path.

`content_text` preserves the strictly decoded source text. The Backend uses
whitespace trimming only to decide whether content is empty; it does not rewrite
line endings or silently repair invalid UTF-8.

### Approved Physical Mapping

| Column | PostgreSQL shape | Constraints |
| --- | --- | --- |
| `document_id` | `uuid` | primary key, not null; Backend-generated UUID v4 |
| `project_id` | `uuid` | not null; foreign key to `projects.project_id`; indexed for Project-scoped lists |
| `filename` | `varchar(255)` | not null; durable non-empty/length constraint; no uniqueness constraint |
| `media_type` | `varchar(32)` | not null; constrained to `text/markdown` |
| `content_text` | `text` | not null; durable non-empty constraint |
| `created_at` | `timestamptz` | not null; server default `CURRENT_TIMESTAMP` |

The Product API does not expose `content_text` in the first slice. Keeping the
validated source internally supports deterministic re-indexing later without
creating a binary object-storage Contract.

### Cardinality and Authority

```text
Project 1 ─── 0..N Documents
Document 1 ─── 1..N Document Chunks after successful creation
```

Product Backend generates `document_id`; PostgreSQL generates `created_at`.
Neither Document IDs nor source text enter LangGraph Agent State or thread
metadata. Document access derives `owner_user_id` by joining its Project; the
Document does not duplicate that identity.

## Document Chunk

**Status:** Implemented by P6-002 from the P6-000 logical Contract and P6-001
physical vector baseline.

A Chunk is an internal retrieval record created deterministically from one
Document. It has no general create/read/update/delete API and is committed only
as part of successful Document ingestion.

### Logical Fields

| Field | Type | Required | First writer | Update semantics | Purpose |
| --- | --- | --- | --- | --- | --- |
| `chunk_id` | UUID | yes | Knowledge ingestion application | immutable | Stable provenance for one indexed passage. |
| `document_id` | UUID | yes | Knowledge ingestion from parent | immutable | Owning Document; Project scope is derived through this relationship. |
| `chunk_index` | non-negative integer | yes | Deterministic chunker | immutable | Zero-based source order, unique within a Document. |
| `content` | non-empty text | yes | Deterministic chunker | immutable | Passage returned by retrieval and later Evidence conversion. |
| `embedding` | fixed-length vector | yes | Configured embedding model | immutable in first slice | Semantic retrieval representation; fixed at 1024 dimensions for the accepted first model. |

The future table must enforce a unique `(document_id, chunk_index)` pair. It
does not duplicate `project_id` or `user_id`; the authoritative retrieval query
joins through Document and Project, then filters `documents.project_id` and
`projects.owner_user_id`. Approximate-index denormalization is deferred until
measured scale requires it.

### Approved First Physical Mapping

| Column | PostgreSQL shape | Constraints |
| --- | --- | --- |
| `chunk_id` | `uuid` | primary key, not null; application-generated UUID v4 |
| `document_id` | `uuid` | not null; foreign key to `documents.document_id`; indexed for the retrieval join |
| `chunk_index` | `integer` | not null; `chunk_index >= 0`; unique with `document_id` |
| `content` | `text` | not null; durable non-empty constraint |
| `embedding` | `vector(1024)` | not null; dimension fixed by the accepted `BAAI/bge-m3` model |

P6-002 uses exact cosine ordering and creates no HNSW/IVFFlat index. Project
and User scope are derived through the Document and Project joins. The first chunker follows
Markdown heading hierarchy and paragraph boundaries. Normal blocks are packed
up to 2,000 Python characters; only an overlong structural block uses
2,000-character windows with 200-character overlap. Emitted non-empty chunks
are numbered consecutively from zero. Changing the embedding dimension or
persisted chunking rules later requires an explicit re-indexing decision.

## KnowledgeHit

**Status:** Implemented runtime Contract; not persisted as a Product entity.

One Project-scoped semantic search returns an ordered list of:

| Field | Type | Purpose |
| --- | --- | --- |
| `document_id` | UUID | Durable source provenance. |
| `chunk_id` | UUID | Durable passage provenance. |
| `filename` | string | Human-readable source label from Document. |
| `content` | string | Retrieved Chunk content. |
| `score` | number | `1 - cosine_distance`; provisional higher-is-better retrieval diagnostic, not a calibrated probability or final relevance/citation promise. |

`KnowledgeHit` is not Agent `Evidence`, a citation, or a stored search-result
row. A later Tool adapter must explicitly map it without losing Document/Chunk
provenance.

## Agent Citation

**Status:** Implemented by P7-003B; not a persisted Product entity.

One successful Agent run exposes an ordered Citation list beside its
Report. Each Citation is a bounded projection of one validated Evidence item:
run-local ordinal `citation_id`, source discriminator and label, excerpt, and
the matching Web URL or Project Document/Chunk provenance. Citation preserves
Evidence order and duplicates but excludes retrieval score and relevance note.

`citation_id` restarts at `c1` per successful run. It is not a UUID, database
key, `run_id`, `evidence_id`, or stable cross-run reference. The first
implementation remains in checkpointed Agent State/output only; no PostgreSQL
table, ownership relationship, Report foreign key, or historical replay
semantics are approved. Without inline Report markers, this list records
available source provenance but not claim-level citation correctness.

## Document Ingestion Atomicity

- Validate Project and the multipart file before durable writes.
- Strictly decode and chunk source text, then obtain all embeddings before the
  database write transaction begins.
- Insert one Document and all Chunks/vectors in one transaction.
- Any validation, chunking, embedding, or commit failure creates no Document or
  Chunk row.
- A successful `201` means the Document is fully searchable; no `pending`,
  `failed`, or partially indexed status exists in the first slice.

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
