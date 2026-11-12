# Rank-sensitivity analysis

Source run: `evaluations/reports/2026-11-11-v4-hybrid.json`

Mode `live` · dataset `retrieval-v4` · run `8658c8c0` · 45 answerable of 50 cases

## Cutoff sensitivity

| k | Macro Recall@k | Micro Recall@k | MRR | Distractor in window | Distractor above every relevant |
| --- | --- | --- | --- | --- | --- |
| 1 | 0.556 | 0.529 | 0.720 | 2/44 (5%) | 3 |
| 3 | 0.789 | 0.765 | 0.720 | 8/44 (18%) | 3 |
| 5 | 0.856 | 0.824 | 0.720 | 11/44 (25%) | 3 |

## Corpus coverage

| Project | Chunks | Largest k as a share of the corpus |
| --- | --- | --- |
| build-and-tooling | 720 | 1% |
| data-visualisation | 359 | 1% |
| http-and-async-runtime | 604 | 1% |
| markdown-pipeline | 1521 | 0% |
| schemas-and-utilities | 1005 | 0% |
| testing-and-lint | 882 | 1% |

## Separation

- Median top-1 score: 0.676
- Median top-1 minus top-2 margin: 0.050
- Abstained rate: 16%

## Reading

- Recall@1 is 0.556: about 20 answerable case(s) put the right passage second or later, even though every one of them is recovered by k=5.

