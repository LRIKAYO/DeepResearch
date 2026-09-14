# Retrieval baseline (P7-003C)

`evaluations/retrieval_v1.json` is a small synthetic dataset: two Markdown
Documents, ten heading-based passages in one Project, and three queries,
including one query requiring two passages. All queries have more than five
candidate passages; selecting every candidate cannot trivially yield Recall@5.

Labels are **synthetic AI-reviewed, not human-reviewed**. The user delegated the
remaining implementation and personal review exercises on 2026-09-14. Labels
were written before the first ranking run, with a rationale for each case.
Keep this distinction in every result and do not relabel after observing ranks
to inflate the baseline. A later independently reviewed dataset should receive
a new version; do not silently replace this one.

The manifest uses `(project_key, document_key, chunk_index)` references.
Ingestion generates new IDs on every run. The evaluation harness resolves
logical references using the committed chunks' deterministic zero-based index
and verifies their text against the existing Markdown chunker. No IDs or
vectors are written into the dataset or report. An intentional chunking change
requires a corresponding reviewed dataset version.

## Run

From the repository root, install the existing Backend/dev extras and migrate
`researchflow_test` as documented in `docs/BACKEND_LOCAL_DEV.md`. Run the baseline
in a fresh process, separately from Backend tests: those tests truncate the
test database and must not run concurrently with evaluation.

```powershell
py -3.12 -m pytest tests/quality -q
py -3.12 -m evaluations.retrieval --validate-only
$env:RESEARCHFLOW_TEST_DATABASE_URL = "postgresql+psycopg://researchflow:researchflow_dev_only@127.0.0.1:5432/researchflow_test"
$env:SILICONFLOW_EMBEDDING_MODEL = "BAAI/bge-m3"
# SILICONFLOW_API_KEY and SILICONFLOW_BASE_URL must already be configured.
py -3.12 -m evaluations.retrieval
```

The validation-only command prints the dataset SHA-256 before any ranking.
The actual command prints one credential-safe JSON result to stdout, including
that hash, model, K, logical ranked passages, per-case and macro Recall@5, run
time and cleanup counts. Save the result as a reviewed artifact in this folder.
Provider calls incur the configured embedding service's normal usage.

The frozen first-run artifact is
`retrieval-v1-baseline-2026-09-14.json`. Its dataset SHA-256 is
`9b42eaf6ee6c0b7f7de03c50b9520dc1ea1400c2e6ed98bb1ad13f9e2f8d7f29`;
all three cases and the macro result measured Recall@5 = 1.0. This is a
baseline observation, not a release threshold.

The harness refuses a non-local database, any database name except the exact
`researchflow_test`, URL connection options, and an already imported Backend.
This guard runs before any Backend/database import. It then checks PostgreSQL's
actual `current_database()` before writes. It uses a fresh FastAPI TestClient
and real configured embeddings: Project creation and Markdown ingestion use
the Product APIs, and ranking uses `POST /projects/{project_id}/knowledge/search`
with the generated user header and `limit=5`. No retrieval dependency overrides
or direct ranking calls are used.

Cleanup runs in `finally` and checks the exact newly created Project IDs and
owners before deleting their chunks, Documents and Projects. It does not
truncate tables, change existing test Projects, or access development data or
LangGraph checkpoints. Run failures do not yield a partial baseline. The CLI
prints only the exception type on failure to avoid leaking provider details.

## Meaning and limitations

For each case, Recall@5 is the number of relevant passage IDs in the first five
results divided by the number of relevant passage IDs. Repeated hits do not
increase recall. Macro Recall@5 gives each case equal weight regardless of the
number of relevant passages. Tests cover exact, partial, zero-hit and top-K
boundary cases, logical resolution after new ingestion, fixture validation and
the database guard.

A poor numeric baseline is a valid result. There is no pass/fail quality
threshold, retrieval optimization, or embedding-model change in this task.
This tiny English synthetic set does not establish production retrieval
quality, multilingual coverage, answer quality, source attribution or citation
correctness. Exact-distance ties may change order with newly generated chunk
IDs; the report records the logical ranking observed in that run.
