# Hybrid retrieval — decision record

**Question.** Does adding a lexical signal to exact cosine improve retrieval on the
`retrieval-v4` corpus, and should it become the default?

**Answer.** Yes, with one correction to how abstention is scored and one real cost
(latency). R@1 is flat; do not claim an R@1 gain.

## What was built

`search_knowledge` now ranks by **Reciprocal Rank Fusion** of two rankings over the
same owner-scoped Project:

1. exact pgvector cosine (unchanged, still the source of `score`), and
2. Okapi BM25 computed in-process over the Project's chunk texts, no new
   dependency, k1=1.2, b=0.75, identifier-aware tokenizer (`baseNameMatch` splits
   into `basename` / `name` / `match`).

The SQL filter is untouched: Project and owner are applied before any row leaves
the database, and no candidate is post-filtered. Queries containing CJK skip the
lexical ranking, because BM25's Latin-only tokenisation sees only incidental
identifiers in a Chinese query and that partial signal measurably hurt
cross-lingual recall.

The HTTP contract is unchanged: same five fields, same `limit`, and `score`
remains the hit's cosine similarity — never the RRF value.

## One correction: abstention was scored against the wrong number

The abstain rule compared the threshold to **rank-1's score**. That was correct
while rank order *was* cosine order. Fusing with a lexical ranking breaks that
assumption: rank 1 can be a lexically-promoted chunk whose cosine is lower than a
passage sitting at rank 2, so an answerable question with a close-enough passage
was refused.

The threshold is a cosine similarity, so it must be compared against the **best
returned score**. `evaluations/metrics.should_abstain` now does that, and both
runs were re-scored from their stored rankings with `scripts/rescore_run.py`, so
the comparison below is apples to apples.

Left uncorrected, this would have been reported as a hybrid regression
(false-abstain 0.067 → 0.111) that does not exist.

## Comparison (both re-scored under the corrected policy)

| Metric | Cosine only | Cosine + BM25 (RRF) | Δ |
| --- | --- | --- | --- |
| Macro Recall@1 | 0.556 | 0.556 | 0.000 |
| Macro Recall@3 | 0.744 | 0.789 | **+0.045** |
| Macro Recall@5 | 0.833 | 0.856 | **+0.022** |
| MRR | 0.696 | 0.720 | **+0.024** |
| nDCG@5 | 0.713 | 0.740 | **+0.028** |
| Hard-negative hit rate (lower better) | 0.286 | 0.265 | **−0.020** |
| Distractor above every relevant | 5 | 3 | **−2** |
| Cross-lingual Recall@5 | 0.833 | 0.833 | 0.000 |
| False-abstain rate (lower better) | 0.067 | 0.067 | 0.000 |
| Latency p50 / p95 | 157 / 234 ms | 328 / 515 ms | **worse** |

Seven cases improved their reciprocal rank, one broke
(`http-openai-retry-statuses`, 1.00 → 0.25: BM25 promoted a 0.560-cosine chunk over
the 0.629-cosine relevant one), and one lost R@5 (`lint-braces-range-limit`, where
generic "range/expression/list" chunks displaced the relevant one). Net R@5: +2
cases, −1 case.

## Decision

**Hybrid is the default retrieval path.** It improves ranking quality at every
cutoff except k=1, reduces wrong-answer-wins, and leaves the HTTP contract and the
cross-lingual behaviour untouched.

Accepted costs:
- **Latency roughly doubles** in the evaluation (157 → 328 ms p50). Measured
  breakdown on the largest Project (1,521 chunks): cosine-only ~18 ms, BM25 alone
  ~71 ms, the hybrid path ~99 ms; the rest of the evaluation delta is
  embedding-provider variance.
- **R@1 does not improve.** The boundary problem the corpus exposes is not solved
  by adding a lexical signal — the same ~20 answerable cases still put the right
  passage second or later.

Deliberately not done: cosine-weighted RRF (a 1.5:1 variant scored slightly higher
in replay but is untuned), a cross-encoder reranker, and a smaller chunk size
(measured earlier and rejected: `2026-11-11-chunking-ab.md`).

## Reproduce

```powershell
py -3.12 -m scripts.rescore_run --report evaluations/reports/2026-11-11-v4-live.json `
  --out evaluations/reports/2026-11-11-v4-live-fixture.json
py -3.12 -m evaluations.run_eval --dataset evaluations/datasets/retrieval_v4.json `
  --replay evaluations/reports/2026-11-11-v4-live-fixture.json --k 5 `
  --out evaluations/reports/2026-11-11-v4-live-rescored.md
```

The same three commands with the `-hybrid` report reproduce the hybrid column.
