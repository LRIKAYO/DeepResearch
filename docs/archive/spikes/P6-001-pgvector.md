# P6-001 — pgvector and Embedding Feasibility Spike

**Status:** DONE — database and configured embedding paths are verified; GO was
accepted by 00-Architect on 2026-09-02.

## Task

- **Goal:** verify one PostgreSQL 18-compatible pgvector path and one
  user-supplied embedding model before adopting a physical vector schema.
- **Owner:** 02-Knowledge, with 03-Backend support, 00-Architect review, and
  05-Quality reproducibility review.
- **Development Mode:** PAIR.
- **Scope guard:** this Spike changes no production Compose, migration, schema,
  API, Agent, or runtime code.

## Environment isolation

The repository's existing Compose service uses `postgres:18.6` and the named
volume `researchflow_postgres_data`. Before the Spike, that volume existed with
creation time `2026-08-30T07:23:46Z`.

The Spike container:

- had the unique name `researchflow-p6-001-pgvector`;
- published no host port;
- mounted no named or host volume;
- used a tmpfs at `/var/lib/postgresql`;
- was started with `--rm` and was absent after the SQL run.

The existing `researchflow_postgres_data` volume was never mounted by the Spike
container. A post-run volume listing still contained the pre-existing volume,
and no Spike volume remained.

## Verified image and extension

Measured locally on 2026-09-02:

| Fact | Measured value |
| --- | --- |
| Image tag | `pgvector/pgvector:0.8.6-pg18` |
| Pulled repo digest | `sha256:2ba9ca5f2e7daa0f0e7723cba1ee9167bab54efd3640516a44ac1a928dd67e7a` |
| Local image ID | `sha256:2ba9ca5f2e7daa0f0e7723cba1ee9167bab54efd3640516a44ac1a928dd67e7a` |
| Platform | `linux/amd64` |
| PostgreSQL server | `18.6 (Debian 18.6-1.pgdg12+2)` |
| `vector` extension | `0.8.6` |

The versioned image is preferred over the floating `pg18` tag for the first
implementation candidate. The official pgvector project lists PostgreSQL 18
image tags and documents the same extension/query operators:

- <https://github.com/pgvector/pgvector>
- <https://github.com/pgvector/pgvector-python>

## Reproducible database smoke

Container startup shape:

```powershell
docker run --rm -d `
  --name researchflow-p6-001-pgvector `
  --tmpfs '/var/lib/postgresql:rw,noexec,nosuid,size=256m' `
  -e POSTGRES_PASSWORD=spike_only `
  -e POSTGRES_USER=spike `
  -e POSTGRES_DB=spike `
  pgvector/pgvector:0.8.6-pg18
```

Executed SQL:

```sql
CREATE EXTENSION vector;

CREATE TABLE spike_chunks (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    project_id text NOT NULL,
    content text NOT NULL,
    embedding vector(3) NOT NULL
);

INSERT INTO spike_chunks (project_id, content, embedding) VALUES
    ('project-a', 'A closest allowed', '[0.9,0.1,0]'),
    ('project-a', 'A farther allowed', '[0,1,0]'),
    ('project-b', 'B globally closest but forbidden', '[1,0,0]');

CREATE INDEX spike_chunks_embedding_cos_idx
    ON spike_chunks USING hnsw (embedding vector_cosine_ops);

SELECT id, project_id, content,
       embedding <=> '[1,0,0]'::vector AS cosine_distance
FROM spike_chunks
WHERE project_id = 'project-a'
ORDER BY embedding <=> '[1,0,0]'::vector
LIMIT 2;
```

Measured ordered result:

| id | project_id | content | cosine distance |
| --- | --- | --- | ---: |
| 1 | `project-a` | `A closest allowed` | 0.006116 |
| 2 | `project-a` | `A farther allowed` | 1.000000 |

The globally closest row was the exact vector in `project-b`; it did not appear
because the authoritative query filtered `project_id = 'project-a'`. `LIMIT 1`
returned only row 1. Querying `project-empty` returned zero rows.

With sequential scans disabled only to inspect operator/index compatibility,
PostgreSQL produced:

```text
Limit
  ->  Index Scan using spike_chunks_embedding_cos_idx on spike_chunks
        Order By: (embedding <=> '[1,0,0]'::vector)
        Filter: (project_id = 'project-a'::text)
```

This proves that cosine distance uses `<=>`, smaller distances sort first, and
`vector_cosine_ops` is compatible with that ordering. It does not approve HNSW
for P6-002 or make a recall/performance claim. The complete isolated
startup/schema/query/cleanup command took about 2.3 seconds on this machine;
that is smoke evidence, not a benchmark.

## Verified embedding model

Measured locally through the existing SiliconFlow OpenAI-compatible base
URL/key boundary on 2026-09-02:

| Fact | Measured value |
| --- | --- |
| Model | `BAAI/bge-m3` |
| Client | existing `langchain-openai` dependency / `OpenAIEmbeddings` |
| Document/query vector dimension | `1024` for all three measured vectors |
| Numeric validity | every value finite |
| Measured L2 norm range | `1.0` to `1.0` |
| Two-document embedding call | 228.19 ms |
| Query embedding call | 103.53 ms |

The timing is one local smoke observation, not a latency or cost benchmark. No
credential or complete vector is recorded in this document.

The measured dimension was used directly to create `vector(1024)`. Two real
document embeddings and one real query embedding were inserted successfully.
An attempted two-dimensional insert was rejected by PostgreSQL with SQLSTATE
`22000`, demonstrating that the model output and fixed column dimension must
agree.

The real query vector was also stored as a Project B row to make it the global
nearest neighbor at cosine distance `0`. The Project-filtered query returned:

| rank | project_id | content | cosine distance |
| ---: | --- | --- | ---: |
| 1 | `project-a` | `A retrieval boundary` | 0.321147 |
| 2 | `project-a` | `A unrelated gardening` | 0.810154 |

Project B's closer row did not cross the SQL filter. A missing Project again
returned zero rows. Creating the HNSW index with `vector_cosine_ops` over
`vector(1024)` succeeded, so the measured dimension is compatible with the
candidate fixed column and index syntax.

## Distance recommendation

Cosine distance is recommended as the first metric because pgvector provides a
direct `<=>` operator and `vector_cosine_ops` index opclass, and the measured
model outputs were unit-normalized. P6-002 must use the same metric for SQL
ordering and any later index opclass. This does not approve an approximate
index for the first production slice.

## Minimum later implementation changes

These are findings for Architect review, not changes made by this Spike:

- replace the Compose PostgreSQL image with the approved versioned pgvector
  image while preserving the existing PostgreSQL 18 data-directory contract;
- create the `vector` extension in an Alembic migration;
- add the official Python `pgvector` package for SQLAlchemy's fixed-length
  `VECTOR(n)` type and cosine expression;
- add one embedding-model setting beside the existing provider base URL/key;
- add the P6-001-measured dimension to the Chunk column;
- join Chunk to Document and filter `documents.project_id` in the authoritative
  retrieval query.

No vector-store interface, provider registry, background job, or production
index choice is needed for the first slice.

## Reproducibility and GO matrix

| Check | Evidence | Current result |
| --- | --- | --- |
| Existing data isolated | no port/named volume; tmpfs container removed | PASS |
| PostgreSQL 18 + extension | real server/extension queries | PASS |
| Two-Project isolation | closer Project B row excluded by SQL filter | PASS |
| Distance/order | `<=>`, ascending distances | PASS |
| Limit | `LIMIT 1` returned one allowed row | PASS |
| Empty result | missing Project returned zero rows | PASS |
| Index-compatible syntax | HNSW plan used `vector_cosine_ops` + `<=>` | PASS |
| Embedding model/dimension | `BAAI/bge-m3`, three stable 1024-d vectors | PASS |
| Fixed `vector(n)` suitability | `vector(1024)` and cosine index created | PASS |
| Real embedding insert/query | real vectors produced ordered isolated hits | PASS |
| Secret hygiene | no credential value recorded | PASS |

## Recommendation

**GO recommended** for the minimal Phase 6 stack:

- PostgreSQL `18.6`;
- pgvector `0.8.6` via `pgvector/pgvector:0.8.6-pg18`;
- `BAAI/bge-m3` through the existing SiliconFlow OpenAI-compatible boundary;
- fixed `vector(1024)` storage;
- cosine distance using `<=>` with ascending order;
- authoritative Project filtering through Document membership before results
  leave the query boundary.

This recommendation approves feasibility facts only. The later Architect
checkpoint accepted the physical baseline but found two non-Spike architecture
decisions that still block P6-002 activation; HNSW remains unapproved.

## Architect checkpoint

Completed on 2026-09-02:

- local image inspection reproduced the recorded image ID/repo digest and
  linux/amd64 platform;
- a new isolated tmpfs container independently reproduced PostgreSQL 18.6,
  pgvector 0.8.6, cosine ordering, bounded limit, empty results, and rejection
  of a wrong-dimension vector;
- the verification used the planned physical relationship rather than the
  Spike's simplified single table: Chunk joined Document, and
  `documents.project_id` excluded the globally closer Project B row;
- `researchflow_postgres_data` retained the same name and creation time before
  and after the run, and the temporary container was removed;
- the current Architect shell had no SiliconFlow credential, so it did not
  claim a second live provider call. The checkpoint accepts the credential-safe
  2026-09-02 measurement of three finite 1024-dimensional `BAAI/bge-m3`
  vectors; P6-002 still requires its own real configured smoke before DONE.

The measured facts match D-012 without changing `KnowledgeHit`, Agent
`Evidence`, or the Project ownership boundary. D-013 records the accepted
physical baseline. Exact cosine search with no approximate index is ready for
P6-002, but the task remains blocked on endpoint-scope and user-isolation
decisions.
