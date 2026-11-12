# Retrieval Evaluation Report Template

Copy this file to `evaluations/reports/<YYYY-MM-DD>-<slug>.md` for each measured
baseline → change → result cycle. Replace every `<...>` placeholder with real values.

**Never fill a cell with an estimate.** A blank cell is honest; a guessed number is
not. Any figure that requires a live backend, embedding credits, or an agent run must
stay blank (or say `TODO(needs-credentials)`) until somebody actually measures it.

---

## 1. Run metadata

| Field | Value |
| --- | --- |
| Report date (UTC) | `<YYYY-MM-DD>` |
| Author / operator | `<name>` |
| Git commit | `<sha>` |
| Dataset | `retrieval-v2` |
| Dataset SHA-256 | `<sha256 from --validate-only>` |
| Schema version | `2` |
| Cutoff k | `5` |
| Abstain threshold | `<value>` (must be calibrated; see limitations) |
| Embedding model | `BAAI/bge-m3` |
| Backend / environment | `<local researchflow_test / staging>` |
| Run command | see §7 |

## 2. Baseline

Record the frozen reference before changing anything. Use the report produced by the
existing evaluator on the commit named above.

- Report artifact: `<evaluations/reports/...md>`
- Baseline commit: `<sha>`
- Known limitations: `<e.g. synthetic labels, one embedding model, exact cosine>`

## 3. Change under test

- Change id / PR: `<id>`
- What changed: `<one paragraph: chunking, retrieval, reranking, loop depth, verifier>`
- Expected effect: `<which metric should move, and in which direction>`
- Falsification criterion: `<e.g. Macro Recall@5 must improve by >= 0.05 while hard-negative hit rate does not increase>`

## 4. Result

- Report artifact: `<evaluations/reports/...md>`
- Raw metrics artifact: `<evaluations/reports/...json>`
- Observations: `<what moved, what did not, any regressions>`
- Per-case failures worth reading: `<case ids>`

## 5. Comparison table (ready to fill)

Fill from measured reports only. Lower is better for **hard-negative hit rate**,
**avg rounds**, **cost/run**, and **latency p50**; higher is better for the rest.
`citation support rate` and `avg rounds` are agent-level metrics and are not produced
by `evaluations/run_eval.py` (retrieval-only) — leave them `TODO(needs-credentials)`
until an agent-level harness measures them.

| System variant | Recall@5 | MRR | nDCG@5 | Hard-negative hit rate | Citation support rate | Avg rounds | Cost/run | Latency p50 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| single-round | `<...>` | `<...>` | `<...>` | `<...>` | `TODO(needs-credentials)` | `<...>` | `TODO(needs-credentials)` | `<...>` |
| 3-round loop | `<...>` | `<...>` | `<...>` | `<...>` | `TODO(needs-credentials)` | `<...>` | `TODO(needs-credentials)` | `<...>` |
| 3-round loop + citation verifier | `<...>` | `<...>` | `<...>` | `<...>` | `TODO(needs-credentials)` | `<...>` | `TODO(needs-credentials)` | `<...>` |

## 6. Decision

- Decision: `<ship / hold / revert / investigate>`
- Threshold policy: `<what evidence is required to ship>`
- Residual risk: `<what this evaluation still cannot see>`

## 7. Reproduction

Live retrieval run (needs a running Product Backend, embedding credentials, and a
disposable database — live ingestion cannot delete the Projects it creates):

```powershell
py -3.12 -m evaluations.run_eval `
  --dataset evaluations/datasets/retrieval_v2.json `
  --api http://127.0.0.1:8000 `
  --user-id <uuid> `
  --k 5 `
  --out evaluations/reports/<date>.md `
  --json-out evaluations/reports/<date>.json
```

Offline replay of a frozen ranking fixture (no network, no credentials):

```powershell
py -3.12 -m evaluations.run_eval `
  --dataset evaluations/datasets/retrieval_v2.json `
  --replay evaluations/reports/<ranking-fixture>.json `
  --k 5 `
  --out evaluations/reports/<date>-replay.md
```

Dataset validation only (offline):

```powershell
py -3.12 -m evaluations.run_eval --validate-only
```

## 8. Metric definitions and limitations

- **Recall@5** — relevant passages retrieved in the top 5 divided by all relevant
  passages for the case; macro mean over answerable cases (unanswerable cases have no
  recall).
- **MRR** — reciprocal rank of the first relevant passage, averaged over answerable cases.
- **nDCG@5** — binary-relevance nDCG, ideal ranking truncated at `min(relevant, 5)`.
- **Hard-negative hit rate** — fraction of cases with declared distractors where at
  least one distractor appears in the top 5. This is a failure rate; lower is better.
- **Citation support rate** — fraction of generated claims whose citation actually
  supports the claim. Requires an agent-level verifier; not measured by the retrieval
  runner.
- **Avg rounds** — mean agent loop iterations per question. Requires an agent-level run.
- **Cost/run** — provider spend for one full evaluation; not observable from the API.
- **Latency p50** — nearest-rank median of measured search-request latency. Replay
  reports have no latency.
- Relevance labels are literal: a passage is relevant only when its chunk contains the
  answer, and every `(document_key, chunk_index, anchor)` tuple is verified against
  `researchflow.knowledge.chunking.chunk_markdown` before a run starts.
- Abstention is a retrieval-side proxy (top score below the configured threshold), not
  a calibrated probability. Calibrate the threshold on a development split before
  quoting abstain numbers.
- The labels are AI-reviewed, not human-reviewed. No release-gate claim follows from
  this dataset alone.
