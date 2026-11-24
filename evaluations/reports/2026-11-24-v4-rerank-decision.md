# Cross-encoder reranking (`BAAI/bge-reranker-v2-m3`) — evaluation record

**Question.** Does adding an optional cross-encoder reranker (`BAAI/bge-reranker-v2-m3` over RRF top-20) solve the Recall@1 plateau noted in `2026-11-11-v4-hybrid-decision.md` while keeping the `0.60` cosine abstention policy calibrated?

**Answer.** Yes: Macro Recall@1 rises from `0.556` to `0.622` (+6.6 pp), Recall@3 from `0.789` to `0.844` (+5.5 pp), MRR from `0.720` to `0.760` (+4.0 pp), and nDCG@5 from `0.740` to `0.779` (+3.9 pp), with zero regression on cross-lingual Recall@5 (`0.833`) or false-abstain rate (`0.067`).

## Comparison on `retrieval-v4` (45 answerable + 5 unanswerable cases, 5,091 chunks)

| Metric | Cosine only | Cosine + BM25 (RRF) | Hybrid RRF (top-20) + `bge-reranker-v2-m3` | Δ vs Hybrid |
| --- | --- | --- | --- | --- |
| Macro Recall@1 | 0.556 | 0.556 | **0.622** | **+0.066** |
| Macro Recall@3 | 0.744 | 0.789 | **0.844** | **+0.055** |
| Macro Recall@5 | 0.833 | 0.856 | **0.867** | **+0.011** |
| MRR | 0.696 | 0.720 | **0.760** | **+0.040** |
| nDCG@5 | 0.713 | 0.740 | **0.779** | **+0.039** |
| Distractor above every relevant (lower better) | 5 | 3 | **2** | **−1** |
| Hard-negative hit rate @ 5 (lower better) | 0.286 | 0.265 | 0.347 | +0.082 (trade-off) |
| Cross-lingual Recall@5 (6 CJK cases) | 0.833 | 0.833 | **0.833** | 0.000 |
| Unanswerable abstain rate | 0.800 | 0.800 | **0.800** | 0.000 |
| False-abstain rate (lower better) | 0.067 | 0.067 | **0.067** | 0.000 |
| Abstain correctness | 0.920 | 0.920 | **0.920** | 0.000 |

## Key observations

1. **R@1 plateau broken.** Hybrid RRF alone improved R@3/R@5/MRR but left R@1 flat at `0.556` (and regressed `http-openai-retry-statuses` from RR `1.00` to `0.25`). Reordering the top-20 RRF pool with `BAAI/bge-reranker-v2-m3` recovers `http-openai-retry-statuses` to RR `1.000` and lifts overall R@1 to `0.622`.
2. **Trade-off at k=5 distractors.** Pulling from a 20-chunk candidate pool surfaces more neighbouring sections from the same package into ranks 2–5 (`HN@5` `0.265 -> 0.347`), while *fewer* distractors outrank every relevant passage (`3 -> 2`, and only `2/44` cases place a distractor at rank 1).
3. **Cosine abstention invariant holds.** Because `KnowledgeHit.score` retains the chunk's `bge-m3` cosine similarity rather than the cross-encoder relevance logit, `DEFAULT_ABSTAIN_THRESHOLD = 0.60` keeps identical unanswerable (`0.800`) and false-abstain (`0.067`) rates without recalibration.
4. **Cross-lingual CJK safeguard.** `retrieval-v4` contains 6 Chinese queries over English npm READMEs (3 of which include stray badges like `[简体中文]` or author handles). Requiring actual CJK token overlap between query and corpus before enabling BM25 preserves cross-lingual Recall@5 at `0.833` (with all 5 retrieved CJK cases at RR `1.000`) while enabling full CJK-bigram + Latin-identifier BM25 on Chinese and bilingual projects.

## Reproduce

```powershell
py -3.12 -m scripts.rerank_eval_bench `
  --dataset evaluations/datasets/retrieval_v4.json `
  --out evaluations/reports/2026-11-24-v4-rerank-fixture.json
py -3.12 -m evaluations.run_eval `
  --dataset evaluations/datasets/retrieval_v4.json `
  --replay evaluations/reports/2026-11-24-v4-rerank-fixture.json --k 5 `
  --out evaluations/reports/2026-11-24-v4-rerank.md `
  --json-out evaluations/reports/2026-11-24-v4-rerank.json
py -3.12 -m evaluations.analyze `
  --report evaluations/reports/2026-11-24-v4-rerank.json `
  --dataset evaluations/datasets/retrieval_v4.json --ks 1,3,5
```
