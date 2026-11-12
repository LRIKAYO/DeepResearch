# Rank-sensitivity analysis

Source run: `evaluations/reports/2026-11-11-v4-live.json`

Mode `live` · dataset `retrieval-v4` · run `bccbdac2` · 45 answerable of 50 cases

## Cutoff sensitivity

| k | Macro Recall@k | Micro Recall@k | MRR | Distractor in window | Distractor above every relevant |
| --- | --- | --- | --- | --- | --- |
| 1 | 0.556 | 0.529 | 0.696 | 4/44 (9%) | 5 |
| 3 | 0.744 | 0.725 | 0.696 | 6/44 (14%) | 5 |
| 5 | 0.833 | 0.804 | 0.696 | 12/44 (27%) | 5 |

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
- Median top-1 minus top-2 margin: 0.030
- Abstained rate: 12%

## Reading

- Recall@1 is 0.556: about 20 answerable case(s) put the right passage second or later, even though every one of them is recovered by k=5.

