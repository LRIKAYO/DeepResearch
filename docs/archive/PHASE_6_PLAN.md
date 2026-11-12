# Phase 6 — Project-scoped Permanent Knowledge Foundation

**Status:** DONE — P6-002 implementation, validation, Quality review, Gate B,
and Gate C are complete; `QUALITY-SCAN-004` is the Post-P6 baseline.

> Engineering goal: establish the first durable, Project-scoped Knowledge
> foundation, beginning with Markdown Documents and ending later in this Phase
> with semantic retrieval.
>
> Planning scope: only the first three tasks are planned here.
>
> Learning strategy remains owned by the user / Project Mentor; the importance
> ratings below are Architect recommendations.

## Current Repository Facts

- Phase 5 is DONE and committed locally as `1054d91 phase5_finished`.
- Product Backend persists Projects and Research Sessions in PostgreSQL 18.6.
- No `Document`, `Chunk`, or permanent Knowledge model, API, package, migration,
  vector extension, embedding dependency, or retrieval implementation exists.
- The Compose fixture uses the official `postgres:18.6` image and does not
  configure a vector extension.
- P6-001 verified `pgvector/pgvector:0.8.6-pg18` (measured locally as
  PostgreSQL 18.6 with pgvector 0.8.6) and `BAAI/bge-m3` embeddings with a
  stable dimension of 1024.
- The Agent graph binds exactly one Web Search Tool. Its provisional `Evidence`
  accepts only `source`, `content`, and optional `relevance_note`.
- Product/session identifiers do not enter Agent State. Agent Server thread
  metadata is diagnostic projection, not Project-membership authority.
- SQLAlchemy's declarative `Base` currently lives in `projects.py`; adding a
  third product resource is the first concrete reason to move it to a shared
  Backend persistence location.
- `QUALITY-SCAN-003` records no Retrieval evaluation dataset or metric result.

## Engineering Phase Goal

The intended Phase-level flow is:

```text
Authenticated User ID → Project
  → durable Markdown Document
  → deterministic Chunks
  → Embeddings
  → Project-scoped vector retrieval
  → typed Knowledge Hits
```

This Phase establishes permanent Knowledge storage and retrieval. It does not
yet attach `knowledge_search` to the Agent graph. Agent integration must wait
until the retrieval output and Project-scope handoff are proven independently.

## Constraints

- A permanent Document belongs to a Project, not to one Research Session. Any
  authorized session in that Project may later retrieve it.
- Product Backend owns Document identity, Project ownership enforcement, HTTP
  validation, and product persistence.
- 02-Knowledge owns extraction/chunking/embedding/retrieval behavior. It does not
  decide Agent graph orchestration.
- Agent must not import or query a concrete vector database implementation.
- `KnowledgeHit` and Agent `Evidence` are distinct Contracts in the first
  slice. Their later adapter must preserve provenance; ToolMessage text is not
  a substitute for either.
- User and Project isolation must be enforced by the Backend/Knowledge query,
  not merely by Frontend filtering or LangGraph metadata.
- PostgreSQL/pgvector is the approved minimal persistence path. D-013 fixes the
  measured first image, model, dimension, and exact cosine semantics; it does
  not approve an approximate index.
- The first ingestion path should be synchronous and size-bounded unless the
  approved Contract or measured runtime proves a background job is necessary.
- No generic repository, vector-store interface with one implementation,
  ingestion framework, task queue, or event bus is introduced in this batch.

## Explicitly Deferred

- PDF, DOCX, HTML/Web Source saving, OCR, binary object storage, and Frontend
  upload UI.
- BM25, Hybrid Retrieval, RRF/fusion, reranking, query rewriting, and retrieval
  evaluation comparisons.
- Agent `knowledge_search`, Web + Knowledge Evidence fusion, citation rendering,
  Reviewer, Compression, and Writer changes.
- Document update/delete/versioning, duplicate detection, asynchronous ingestion
  status, retry/reconciliation, quotas, and broader multi-tenant policy.
- Product User CRUD, passwords, login, token issuance, and identity-provider
  implementation; D-014 supplies only a trusted upstream identity boundary.
- Final Evidence Schema, Report/Evidence product persistence, and research-event
  replay.

## Dependency Order

```text
P6-000 Permanent Knowledge Contract
        ↓
P6-001 pgvector + embedding feasibility spike
        ↓
mandatory Architect checkpoint
        ↓
P6-002 atomic Markdown upload-to-search vertical slice
```

P6-001 and its mandatory technical checkpoint are complete. Its measured
image/model/dimension/distance choices are approved inputs to P6-002. D-014
accepted the endpoint and identity decisions below, so P6-002 is executable.
The first implementation uses exact cosine search; P6-001's HNSW check proved
syntax compatibility only and does not authorize an approximate index.

## P6-002 Activation Decisions — ACCEPTED

### ADR-P6-A — Document endpoint scope: Option A

**Current problem:** P6-000 approved Document create/read/list plus Knowledge
search for P6-002, while the checkpoint draft narrowed implementation to create
plus search and deferred read/list. This is a material task-scope change, not a
measured conclusion from P6-001.

- **Option A — retain the accepted scope:** P6-002 implements create, read,
  list, and Knowledge search. This keeps the approved lifecycle together but
  increases the first implementation and test surface.
- **Option B — narrow the vertical slice:** P6-002 implements create and search;
  read/list move to the next rolling batch. This shortens the first path but
  requires an explicit scope amendment to P6-000's task boundary.

**Accepted on 2026-09-04:** retain create, read, list, and Knowledge search in
P6-002.

### ADR-P6-B — User isolation before multi-user use: Option A

**Current problem:** the project requirement says permanent Knowledge search
must consider both `user_id` and `project_id`, while the accepted current Data
Model/API explicitly defer User, Auth, memberships, and tenant scope. A
Project-only query is meaningful for the current local single-user MVP but is
not a production multi-user isolation boundary.

- **Option A — introduce user ownership now:** expand P6-002 to add the minimum
  User/Project ownership or membership model and an authenticated/trusted
  `user_id` request context, then enforce both identities in Document access
  and retrieval. This satisfies the stated private multi-user boundary but is
  a cross-module expansion.
- **Option B — preserve the local single-user slice:** implement Project-only
  isolation under the existing no-Auth Contract, label it non-production for
  multi-user use, and require a separate architecture task to add User/Auth and
  compound ownership filtering before any multi-user deployment.

**Accepted on 2026-09-04:** add immutable Project `owner_user_id`, obtain the
opaque UUID only from the trusted `X-ResearchFlow-User-Id` dependency, and
enforce current user plus Project at every Product/Knowledge boundary. No
password, login, token-issuing, or Product User CRUD is introduced. Existing
Project rows require explicit `RESEARCHFLOW_LEGACY_OWNER_USER_ID` migration
ownership. D-014 records the full boundary.

## P6-000 — Permanent Knowledge Boundary Contract

**Status:** DONE — D-012 and the approved-next Architecture, Data Model, and API
Contracts were accepted by the user on 2026-09-02.

**Goal**

Define the smallest stable boundary for Project-owned Documents, internal
Chunks, typed retrieval hits, ingestion failure semantics, and the future
Agent adapter before any Knowledge implementation begins.

**Why Now**

The repository currently knows only Projects, Research Sessions, Web Evidence,
and LangGraph execution identities. Creating vector tables or an upload route
first would force lifecycle, ownership, and provenance decisions into whichever
module happened to write code first.

**Scope**

- Define Document meaning, Project cardinality, ID/time authority, minimum
  fields, and create/read/list lifecycle.
- Decide the first accepted input as a bounded UTF-8 Markdown upload and define
  filename/media-type/content validation.
- Define whether normalized Markdown source is stored in PostgreSQL for the
  first slice and what is returned by Product APIs.
- Define Chunk identity, ordering, content, Document relationship, and whether
  Chunks are internal rather than general CRUD resources.
- Define a provisional `KnowledgeHit` retrieval response with stable Document
  and Chunk provenance, while keeping it distinct from Agent `Evidence`.
- Define synchronous ingestion transaction/failure semantics.
- Define the Project-scoped search boundary and result-limit rules needed by a
  later implementation task.
- Record the preferred pgvector candidate and the facts P6-001 must verify.
- Record that the future Agent Tool needs an approved Project-scope handoff that
  does not add product IDs to Agent State or trust thread metadata as authority.

**Out of Scope**

- Runtime code, migrations, dependency or Compose changes.
- Choosing final chunk sizes, embedding model, vector dimension, or similarity
  metric before the Spike measures them.
- Agent Tool integration, final Evidence conversion, Writer changes, and UI.
- Every capability listed under Explicitly Deferred.

**Owner**

00-Architect with 02-Knowledge and 03-Backend boundary review.

**Development Mode**

PAIR

**Learning Importance**

HIGH. This is the first boundary between durable product Knowledge, retrieval
infrastructure, and the Agent's temporary research Evidence.

**Learning Goal**

The user should be able to explain:

1. Why a permanent Document belongs to Project rather than Research Session.
2. Why Document, Chunk, `KnowledgeHit`, and Agent `Evidence` are four different
   responsibilities.
3. Why the Agent must not query pgvector directly.
4. What remains persisted or rolled back if extraction/embedding fails.
5. Where Project isolation is enforced and why thread metadata is insufficient.
6. Why synchronous Markdown ingestion is acceptable only with an explicit size
   ceiling.

**Deliverables**

- D-012 in `docs/DECISIONS.md`.
- Permanent Knowledge boundary in `docs/ARCHITECTURE.md`.
- Approved-next Document and Chunk definitions in `docs/DATA_MODEL.md`.
- Approved-next Document/search HTTP Contracts in `docs/API_CONTRACTS.md`.
- Updated status and decisions in this rolling plan.

**Acceptance Criteria**

- Product, Knowledge, Agent, and infrastructure ownership are explicit.
- Document and Chunk cardinality does not involve `research_session_id`,
  `thread_id`, or `run_id`.
- Project isolation and failure/transaction behavior are testable.
- `KnowledgeHit` includes durable provenance without prematurely becoming the
  final Evidence or Citation Schema.
- The Spike has concrete pass/fail questions rather than a broad vector-database
  comparison.
- No speculative status table, job queue, generic vector abstraction, or Agent
  graph change is approved.

## P6-001 — pgvector and Embedding Feasibility Spike

**Status:** DONE — GO accepted by 00-Architect on 2026-09-02.

**Goal**

Verify, against the real local environment, that the preferred PostgreSQL
vector path and one configured embedding model can support the next retrieval
slice with known dimensions and query semantics.

**Why Now**

The current database image has no configured vector extension, and the current
chat model configuration is not evidence that an embedding endpoint/model is
available. Schema or Compose changes must use measured facts instead of guessed
extension support or vector dimensions.

**Scope**

- Use an isolated, non-destructive Docker/database setup; do not alter or remove
  the existing `postgres_data` volume.
- Verify one PostgreSQL 18-compatible pgvector image/extension candidate and
  record its exact image tag/digest and extension version.
- Execute extension creation, vector insert, Project-filtered nearest-neighbor
  query, and index-compatible distance syntax on representative rows.
- Validate one user-supplied embedding model through the existing provider
  boundary, recording model name and returned vector dimension without secrets.
- Recommend the first distance metric and whether the measured dimension is
  suitable for a fixed `vector(n)` column.
- Identify the minimum Compose, dependency, environment, and migration changes
  a later implementation would require.
- Record measured latency only as smoke evidence, not as a benchmark claim.

**Out of Scope**

- Production schema, API, Agent, Compose, or runtime implementation changes.
- Broad comparison of pgvector, Qdrant, Pinecone, Chroma, or other products.
- Chunking-quality experiments, retrieval evaluation, BM25/hybrid, reranking,
  scale/load testing, and cost optimization.

**Owner**

02-Knowledge; 03-Backend supports PostgreSQL/Compose boundaries; 00-Architect
reviews the decision evidence; 05-Quality reviews reproducibility.

**Development Mode**

PAIR

**Learning Importance**

HIGH. Vector dimension, distance semantics, Project filters, and extension
availability directly constrain the durable retrieval implementation.

**Learning Goal**

The user should personally trace one text → embedding vector → PostgreSQL row →
Project-filtered nearest-neighbor result and explain why model dimension and
database column dimension must agree. AI may prepare isolated Docker and SQL
boilerplate.

**Deliverables**

- `docs/spikes/P6-001-pgvector.md` containing reproducible, credential-safe
  evidence and a GO/NO-GO recommendation.
- No production code artifact unless a separately approved correction is needed
  to make the Spike reproducible.

**Acceptance Criteria**

- Existing development/test data and volumes are untouched.
- Extension/image and embedding model/dimension are recorded from real output,
  not documentation assumptions.
- At least two Projects prove that the SQL query cannot return another
  Project's rows.
- Distance operator, ordering direction, limit behavior, and empty-result
  behavior are demonstrated.
- Failure to create the extension or obtain valid embeddings produces NO-GO
  with the exact blocker; it is not hidden by switching products mid-task.
- No secret value, full credential, or local `.env` content is recorded.

## P6-002 — Atomic Markdown Upload-to-Search Vertical Slice

**Status:** DONE — implementation, Architecture/Quality review, automated/real
runtime validation, Gate B user trace, and Gate C zero-norm regression exercise
passed on 2026-09-05.

**Goal**

Implement the first complete bounded Markdown path from a user-owned Project
upload to atomic Document/Chunk/vector persistence and user-and-Project-scoped
Knowledge search.

**Why Now**

The approved Contract forbids a successful Document that is only partly
indexed. P6-001 has now supplied the physical facts needed to build that path:
pgvector 0.8.6 on PostgreSQL 18, `BAAI/bge-m3`, `vector(1024)`, and cosine
distance with ascending `<=>` ordering.

**Scope**

- Move SQLAlchemy `Base` from `projects.py` to a minimal shared
  `backend/models.py`; update model/Alembic imports without introducing a
  repository or model-registry framework.
- Change Compose to the versioned `pgvector/pgvector:0.8.6-pg18` tag. Keep the
  measured digest in Spike evidence rather than pinning one platform digest in
  portable Compose.
- Add only the required Backend dependencies (`pgvector` for SQLAlchemy and
  `python-multipart` for upload parsing) and the required
  `SILICONFLOW_EMBEDDING_MODEL=BAAI/bge-m3` environment setting. Reuse the
  existing SiliconFlow base URL/key boundary and `langchain-openai` package.
- Add one Alembic revision that creates the `vector` extension and the approved
  Document/Chunk tables. Store embeddings as fixed `vector(1024)`; add ordinary
  Project-membership/join indexes, but no HNSW or IVFFlat index.
- Add the approved Document and internal Chunk ORM models.
- Implement a deterministic, domain-independent Markdown chunker under
  `src/researchflow/knowledge/`. Prefer heading hierarchy and paragraph
  boundaries; pack normal blocks up to 2,000 Python characters and use
  2,000-character windows with 200-character overlap only for an overlong
  structural block. Preserve stable source order, omit empty chunks, and number
  emitted chunks consecutively from zero.
- Implement the verified `OpenAIEmbeddings` adapter under
  `src/researchflow/knowledge/`. Validate that every returned value is finite,
  each vector has exactly 1024 values and non-zero L2 norm, and the result count
  matches the input count before any durable write.
- Implement Project-scoped Markdown create/read/list and Knowledge search.
- Add immutable Project `owner_user_id`; obtain the current opaque UUID through
  the trusted identity dependency and scope all Project/nested-resource APIs.
  Missing identity returns 401; unknown and other-user Projects share the
  Project 404 response.
- Accept only the approved bounded UTF-8 Markdown form; validate filename,
  media type, empty content, decoding, and size at the HTTP trust boundary.
- Verify Project existence before contacting the embedding provider. Close the
  read transaction, obtain all chunk embeddings, then use one database
  transaction to insert the Document and every Chunk/vector; any failure leaves
  neither resource and returns only the approved sanitized error.
- Implement the authoritative retrieval query by joining Chunks to Documents
  to Projects, filtering `documents.project_id` and `projects.owner_user_id`,
  then ordering exactly by cosine distance
  ascending (`embedding <=> query_vector`) with `chunk_id` ascending as a
  deterministic tie-break before applying the bounded limit. Return
  `score = 1 - cosine_distance`, so API order is score descending.
- Return typed `KnowledgeHit` values without converting them to Agent Evidence.
- Preserve and regression-test existing exact-origin CORS behavior; no CORS
  architecture change is part of this task.
- Use dependency-injected/fake embeddings for deterministic tests plus one real
  local provider and pgvector smoke; do not put credentials in test fixtures.
- Add focused PostgreSQL tests for validation, atomic rollback, ordering,
  Project isolation, retrieval limit/empty results, and persistence.
- Run the existing Backend, Agent, migration, dependency, and Frontend
  regression gates.

**Out of Scope**

- Agent tools, Agent State, Evidence conversion/fusion, reports, citations, or
  LangGraph changes.
- PDF/DOCX/HTML, object storage, download endpoints, delete/update/versioning,
  duplicate detection, statuses, background jobs, retries, or UI changes.
- BM25, hybrid/fusion, reranking, query rewriting, approximate-index tuning,
  benchmarks, or generalized vector-store abstractions.
- General repository/service abstractions or a generic file-ingestion framework.

**Owner**

03-Backend is the implementation coordinator and owns Product models,
transaction/API wiring, Compose, and migrations. 02-Knowledge owns and must
review chunk/embed/retrieval behavior. 00-Architect reviews the boundary;
05-Quality reviews isolation and reproducibility evidence.

**Development Mode**

PAIR

**Learning Importance**

HIGH. This is the first permanent Knowledge retrieval path and the first real
Project filter over vector results.

**Learning Goal**

The user should personally implement or trace the exact vector query and its
Document join/Project filter, then follow one Markdown source through chunking,
embedding validation, atomic commit, and `KnowledgeHit`. AI may assist with
migration/API boilerplate, multipart validation, and repetitive tests. For the
Gate C exercise, the user should make the fake embedder return one wrong-sized
vector and add/adjust the test proving a sanitized failure and zero persisted
Document/Chunk rows.

**Deliverables**

- Shared declarative Base location and updated model imports.
- Verified pgvector runtime configuration and Document/Chunk migration.
- Minimal Knowledge chunking, embedding, and retrieval modules.
- Document create/read/list and user-and-Project-scoped Knowledge search API.
- Focused deterministic tests and real local ingestion/search smoke.
- Updated Backend runbook and `docs/tasks/P6-002.md` Completion Report.

**Acceptance Criteria**

- The approved migration upgrades development/test databases and Alembic
  reports no drift.
- The migration and ORM both use `vector(1024)`; a wrong vector count,
  non-finite value, zero vector, or wrong dimension is rejected before
  persistence.
- A valid Markdown upload returns `201` only after every Chunk/vector is
  committed; its rows remain present and searchable after a process restart.
- Missing Project returns `404` and creates no Document.
- Invalid filename/media type, empty or non-UTF-8 content, and over-limit input
  return only the approved sanitized validation errors and create no row.
- Controlled chunking, embedding, and commit failures create no Document or
  Chunk row and expose no provider/database details.
- Search returns ordered, bounded `KnowledgeHit` values and cannot return a
  closer Chunk from another Project. The test must use the real
  Document-to-Chunk join rather than a synthetic `project_id` column on Chunk.
  Empty Project results return `[]`.
- One real configured embedding + pgvector smoke proves the measured dimension
  and verified distance path; deterministic tests do not require credentials.
- No approximate vector index is created or required for correctness in this
  slice.
- No Agent State, Research Session, LangGraph metadata, Tool, Evidence, BM25,
  hybrid, or reranker change appears in this task.
- Document list/read are user-and-Project-scoped; a cross-Project or cross-user
  read returns the approved not-found response.
- Every Project and nested operation derives identity from the trusted request
  dependency, while the retrieval SQL independently filters both owner and
  Project before ordering and limit.
- Existing Backend/Agent tests, Frontend typecheck/lint/build, `pip check`, and
  `git diff --check` pass with no new error-level finding.

## Phase Exit Criteria

### Engineering Exit Criteria

- A bounded Markdown source is durably owned by a Project and survives restart.
- The selected vector/embedding stack is verified against the real local
  environment before schema adoption.
- P6-002 implements deterministic Chunks and user-and-Project-scoped semantic
  retrieval returning typed `KnowledgeHit` values.
- Cross-user and cross-Project retrieval are impossible at the authoritative
  query boundary.
- Quality has a reproducible retrieval fixture before any vector/hybrid/reranker
  comparison is claimed.

### Learning-relevant Findings

- The Project → Document → Chunk → KnowledgeHit path and its separation from
  Agent Evidence are core learning points worth tracing.
- The exact vector SQL and User/Project filters are higher learning value than
  upload form boilerplate.
- No Knowledge or vector-search mastery is claimed by task completion. Later
  explanation and a small filter/change challenge must provide that evidence.

## Batch Stop

The P6-001 technical stop gate, D-014 activation gate, and P6-002 user review
are closed. Phase 6 is complete. Do not start Frontend upload UI, Agent
`knowledge_search`, hybrid search, or a later Phase without a newly scoped
task; Agent integration requires its own architecture decision.
