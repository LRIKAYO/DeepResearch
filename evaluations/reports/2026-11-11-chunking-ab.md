# Chunking A/B — does a smaller fixed window help?

**Question.** On `retrieval-v4`, 9 of 45 answerable cases miss a relevant passage
while their top-1 lands in the right document. That is a chunk-boundary failure,
not an embedding failure. Does halving the chunk size fix it?

**Setup.** Identical documents, identical 50 questions, identical model
(`BAAI/bge-m3`), identical exact-cosine search, identical Product Backend and
PostgreSQL. The only variable is `RESEARCHFLOW_CHUNK_CHARS`:

| Arm | Chunk size | Overlap | Chunks | Corpus sha256 |
| --- | --- | --- | --- | --- |
| A | 2000 | 0 | 5,091 | `f57b923b…` |
| B | 1000 | 0 | 6,157 | `10035b55…` |

Labels were re-pointed from their anchor text after each rebuild
(`scripts/repair_case_anchors.py`), so a case is always labelled against the
chunk that actually contains its answer.

**Result.**

| Metric | A (2000) | B (1000) | Δ |
| --- | --- | --- | --- |
| Macro Recall@5 | 0.833 | 0.833 | 0.000 |
| Micro Recall@5 | 0.804 | 0.804 | 0.000 |
| MRR | **0.696** | 0.635 | **−0.061** |
| nDCG@5 | **0.713** | 0.666 | −0.047 |
| Distractor hit rate | 0.286 | 0.306 | +0.020 (worse) |
| Cases with a wrong top-1 | **18/45** | 22/45 | +4 (worse) |
| Cases missing a passage | 9/45 | 9/45 | 0 |
| …of those, top-1 in the right document | 9 | 9 | — |
| Cross-lingual Recall@5 | 0.833 | 0.833 | 0.000 |
| Latency p50 / p95 | 157 / **234** ms | 156 / 297 ms | p95 worse |

**Reading.** Smaller chunks did not buy any recall at k=5 and cost ranking
quality: the rank of the first relevant chunk dropped, four more cases put a
non-relevant chunk at rank 1, and the p95 latency rose because the corpus grew.

Nothing about the boundary problem changed: 9 of 9 misses are still
"right document, wrong chunk". Halving the window moves the boundary; it does
not make the answer span the boundary.

**What this rules out.** "Just use smaller chunks" is not the fix. The plausible
remaining levers are the ones that change what a hit *means* rather than where
the cut falls:

- sentence-window or parent-document retrieval (retrieve the chunk, answer from
  the section around it);
- overlap with a group-aware metric — an answer repeated in two adjacent chunks
  must count as one hit, otherwise overlap is penalised by the metric itself;
- reranking, which the A-arm's 0.030 median top-1/top-2 margin says has little
  signal to work with unless the candidate set is widened first.

**Caveats.**

- Three anchors occur in more than one chunk of their volume (identical bullets
  in sibling package docs). The repair resolved them to the first occurrence in
  both arms, so those cases carry the same ambiguity in each arm.
- One distractor was dropped in both arms: its text only ever occurred inside a
  chunk already used as the relevant passage.

**Reproduce.**

```powershell
$env:RESEARCHFLOW_CHUNK_CHARS = "1000"; $env:RESEARCHFLOW_CHUNK_OVERLAP = "0"
py -3.12 -m scripts.build_eval_corpus --cases-dir evaluations/datasets/_v4_cases `
  --out evaluations/datasets/retrieval_v4.json
py -3.12 -m scripts.repair_case_anchors --dataset evaluations/datasets/retrieval_v4.json `
  --cases-dir evaluations/datasets/_v4_cases --write
# rebuild once more so the fragment indices land in the dataset
py -3.12 -m scripts.build_eval_corpus --cases-dir evaluations/datasets/_v4_cases `
  --out evaluations/datasets/retrieval_v4.json
# then start the backend with the same env and run evaluations.run_eval --api ...
```

The dataset is checked against the chunking that produced it: loading a
1000-char dataset under a 2000-char process fails with an explicit message, not
a mysterious anchor error.
