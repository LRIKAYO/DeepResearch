# Retrieval Evaluation — retrieval-v3

> Compatibility replay only: rankings were captured against the earlier 122-chunk retrieval-v2 corpus and reused here to verify scoring and reporting. They are not retrieval results for the expanded corpus. Run a fresh isolated live evaluation before drawing quality conclusions.

## Run metadata

| Field | Value |
| --- | --- |
| Dataset | `retrieval-v3` (schema v2) |
| Dataset SHA-256 | `aeab02b059982f21b446588644ff993fb9a22debb356afd242c28f74901a6820` |
| Mode | replay |
| API base URL | n/a (replay) |
| Run id | n/a (replay) |
| Cutoff k | 5 |
| Abstain threshold | 0.60 (cosine similarity) |
| Generated at (UTC) | 2026-11-10T16:45:33+00:00 |
| Cost per run | TODO(needs-credentials) |

> Labels: Hand-authored corpus and relevance labels for six domains, expanded with supplemental background reference documents to exceed 200 chunks per project. Every labelled passage is mechanically checked against the production chunker. Labels were AI-reviewed but have not been human-reviewed, so no release threshold is claimed.

## Headline metrics

Macro, MRR, and nDCG are computed over the 45 answerable cases. Unanswerable cases (n=5) are scored through the abstain metrics instead.

| Metric | Value | Denominator |
| --- | --- | --- |
| Macro Recall@5 | 1.000 | 45 answerable cases |
| Micro Recall@5 | 1.000 | all relevant passages |
| MRR | 0.978 | 45 answerable cases |
| nDCG@5 | 0.979 | 45 answerable cases |
| Hard-negative hit rate (lower is better) | 0.750 | 28 cases with distractors |
| Cross-lingual Recall@5 | 1.000 | 6 answerable CJK-query cases |
| Unanswerable abstain rate | 1.000 | 5 unanswerable cases |
| False-abstain rate (lower is better) | 0.089 | 45 answerable cases |
| Abstain correctness | 0.920 | all 50 cases |
| Latency p50 | n/a | n/a (replay has no network requests to time) |
| Latency p95 | n/a | n/a (replay has no network requests to time) |

## Dataset composition

| Dimension | Count |
| --- | --- |
| Projects | 6 |
| Documents | 30 |
| Chunks (re-chunked offline) | 1448 |
| Cases | 50 |
| Easy / medium / hard | 10 / 25 / 15 |
| Hard-negative cases | 28 |
| Multi-hop cases | 6 |
| Cross-lingual cases | 6 |
| Unanswerable cases | 5 |

## Per-case detail

`RR` is the reciprocal rank of the first relevant passage. `HN hit` is whether a declared distractor entered the top-k (lower is better). `Abstain` shows the policy decision and whether it was correct for the case.

| Case | Project | Difficulty | Flags | Recall@5 | RR | nDCG@5 | HN hit | Abstain | Top-1 | Latency (ms) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| lab-spectrometer-calibration | lab-operations | medium | neg | 1.000 | 1.000 | 1.000 | yes | no (ok) | `lab-handbook#1` | - |
| lab-imaging-timezone | lab-operations | easy | - | 1.000 | 1.000 | 1.000 | - | no (ok) | `instrument-log#1` | - |
| lab-biohazard-autoclave | lab-operations | medium | neg | 1.000 | 1.000 | 1.000 | yes | no (ok) | `safety-and-waste#2` | - |
| lab-freezer-storage | lab-operations | medium | neg | 1.000 | 1.000 | 1.000 | no | no (ok) | `lab-handbook#4` | - |
| lab-incident-near-miss | lab-operations | hard | multi | 1.000 | 1.000 | 1.000 | - | no (ok) | `lab-handbook#5` | - |
| lab-visitor-access | lab-operations | easy | - | 1.000 | 1.000 | 1.000 | - | no (ok) | `training-matrix#4` | - |
| lab-cross-lingual-biohazard | lab-operations | medium | xling | 1.000 | 1.000 | 1.000 | - | no (ok) | `safety-and-waste#2` | - |
| lab-unanswerable-radioactive | lab-operations | hard | unans, neg | n/a | n/a | n/a | yes | yes (ok) | `safety-and-waste#2` | - |
| api-upload-limits | api-documentation | medium | neg | 1.000 | 1.000 | 1.000 | yes | no (ok) | `endpoints-documents#1` | - |
| api-key-rotation | api-documentation | easy | - | 1.000 | 1.000 | 1.000 | - | no (ok) | `authentication#1` | - |
| api-rate-limit | api-documentation | medium | neg | 1.000 | 1.000 | 1.000 | yes | no (ok) | `authentication#3` | - |
| api-soft-delete | api-documentation | hard | neg | 1.000 | 1.000 | 1.000 | yes | no (ok) | `endpoints-projects#3` | - |
| api-webhook-signature | api-documentation | hard | neg | 1.000 | 1.000 | 1.000 | yes | no (ok) | `webhooks#1` | - |
| api-cross-lingual-upload | api-documentation | medium | xling | 1.000 | 1.000 | 1.000 | - | no (ok) | `endpoints-documents#1` | - |
| api-multi-hop-key-event | api-documentation | hard | multi | 1.000 | 0.500 | 0.651 | - | no (ok) | `webhooks#0` | - |
| api-unanswerable-graphql | api-documentation | medium | unans, neg | n/a | n/a | n/a | no | yes (ok) | `endpoints-projects#0` | - |
| hr-annual-leave-carryover | hr-policy | medium | neg | 1.000 | 1.000 | 1.000 | yes | no (ok) | `leave-and-absence#1` | - |
| hr-sick-certificate | hr-policy | easy | - | 1.000 | 1.000 | 1.000 | - | no (ok) | `leave-and-absence#2` | - |
| hr-parental-leave | hr-policy | medium | - | 1.000 | 1.000 | 1.000 | - | no (ok) | `leave-and-absence#3` | - |
| hr-bonus-timing | hr-policy | easy | - | 1.000 | 1.000 | 1.000 | - | no (ok) | `compensation#2` | - |
| hr-gift-limit | hr-policy | medium | neg | 1.000 | 1.000 | 1.000 | no | no (ok) | `conduct#3` | - |
| hr-multi-hop-probation-salary | hr-policy | hard | multi | 1.000 | 1.000 | 1.000 | - | no (ok) | `compensation#1` | - |
| hr-cross-lingual-parental | hr-policy | medium | xling | 1.000 | 1.000 | 1.000 | - | no (ok) | `leave-and-absence#3` | - |
| hr-conflict-disclosure | hr-policy | medium | neg | 1.000 | 1.000 | 1.000 | no | no (ok) | `conduct#2` | - |
| clin-primary-endpoint | clinical-protocol | easy | - | 1.000 | 1.000 | 1.000 | - | no (ok) | `study-overview#4` | - |
| clin-eligibility-egfr | clinical-protocol | medium | neg | 1.000 | 1.000 | 1.000 | yes | yes (WRONG) | `study-overview#2` | - |
| clin-dose-escalation | clinical-protocol | medium | neg | 1.000 | 1.000 | 1.000 | yes | no (ok) | `dosing#1` | - |
| clin-missed-dose | clinical-protocol | easy | neg | 1.000 | 1.000 | 1.000 | yes | no (ok) | `dosing#2` | - |
| clin-renal-adjustment | clinical-protocol | hard | neg | 1.000 | 1.000 | 1.000 | yes | no (ok) | `dosing#3` | - |
| clin-sae-timeline | clinical-protocol | hard | neg | 1.000 | 1.000 | 1.000 | yes | no (ok) | `safety-reporting#2` | - |
| clin-multi-hop-egfr-monitoring | clinical-protocol | hard | multi | 1.000 | 1.000 | 0.877 | - | no (ok) | `dosing#3` | - |
| clin-cross-lingual-sae | clinical-protocol | medium | xling | 1.000 | 1.000 | 1.000 | - | no (ok) | `safety-reporting#2` | - |
| clin-unanswerable-stopping | clinical-protocol | hard | unans, neg | n/a | n/a | n/a | yes | yes (ok) | `assessments#2` | - |
| fin-purchase-threshold | finance-policy | medium | neg | 1.000 | 1.000 | 1.000 | yes | no (ok) | `procurement#1` | - |
| fin-vendor-screening | finance-policy | easy | - | 1.000 | 1.000 | 1.000 | - | no (ok) | `procurement#2` | - |
| fin-travel-class | finance-policy | medium | - | 1.000 | 1.000 | 1.000 | - | no (ok) | `expenses#1` | - |
| fin-capitalization | finance-policy | hard | neg | 1.000 | 1.000 | 1.000 | no | no (ok) | `budgeting#4` | - |
| fin-multi-hop-purchase-control | finance-policy | hard | multi | 1.000 | 1.000 | 1.000 | - | no (ok) | `procurement#1` | - |
| fin-cross-lingual-receipts | finance-policy | medium | xling | 1.000 | 0.500 | 0.631 | - | yes (WRONG) | `procurement#2` | - |
| fin-emergency-purchase | finance-policy | medium | neg | 1.000 | 1.000 | 1.000 | yes | no (ok) | `procurement#4` | - |
| fin-unanswerable-crypto | finance-policy | medium | unans, neg | n/a | n/a | n/a | yes | yes (ok) | `procurement#2` | - |
| prod-embedding-dims | product-spec | easy | - | 1.000 | 1.000 | 1.000 | - | no (ok) | `architecture#2` | - |
| prod-success-metric | product-spec | medium | neg | 1.000 | 1.000 | 1.000 | yes | no (ok) | `product-requirements#4` | - |
| prod-search-response | product-spec | medium | neg | 1.000 | 1.000 | 1.000 | yes | yes (WRONG) | `api-contract#2` | - |
| prod-chunk-cap | product-spec | hard | neg | 1.000 | 1.000 | 1.000 | yes | no (ok) | `architecture#3` | - |
| prod-no-model-training | product-spec | medium | neg | 1.000 | 1.000 | 1.000 | no | no (ok) | `product-requirements#3` | - |
| prod-multi-hop-beta | product-spec | hard | multi | 1.000 | 1.000 | 0.877 | - | no (ok) | `release-plan#2` | - |
| prod-cross-lingual-versioning | product-spec | medium | xling | 1.000 | 1.000 | 1.000 | - | yes (WRONG) | `api-contract#4` | - |
| prod-rollback | product-spec | easy | neg | 1.000 | 1.000 | 1.000 | no | no (ok) | `release-plan#3` | - |
| prod-unanswerable-onprem | product-spec | hard | unans, neg | n/a | n/a | n/a | yes | yes (ok) | `product-requirements#0` | - |

## Method and limitations

- Relevance is literal: a passage is labelled relevant only when its chunk text contains the answer. Every `(document_key, chunk_index, anchor)` tuple is checked against `researchflow.knowledge.chunking.chunk_markdown` before any request is made.
- `Recall@k`, MRR, and nDCG use binary relevance. Macro Recall is the unweighted mean over answerable cases; Micro Recall pools relevant passages.
- The hard-negative hit rate is a failure rate over cases with declared `distractor_passages`; lower is better. Unanswerable cases may also declare distractors, in which case returning one is a hard-negative hit.
- Abstention is a retrieval-side proxy: the system abstains when no returned passage scores at least the configured threshold. The default threshold is a policy choice, not a calibrated probability; calibrate it on a development split before using abstain numbers for release decisions.
- Latency percentiles use the nearest-rank method over measured search requests; replay runs have no latency and report `n/a` rather than a fabricated number.
- Citation support rate and answer quality are not measured here. They require an agent-level evaluation with generated answers and a citation verifier.
- Cost per run is not observable from the API; it is either operator-supplied or left as `TODO(needs-credentials)`.
- Live mode creates projects and documents in the target backend and cannot delete them (the Product Backend has no delete endpoint). Run it against a disposable stack. Projects are named with the dataset version and a random run id.

## Reproduction

Live (needs a running backend, embedding credentials, and a disposable database):

```powershell
py -3.12 -m evaluations.run_eval --dataset evaluations/datasets/retrieval_v3.json --api http://127.0.0.1:8000 --user-id <uuid> --k 5 --abstain-threshold 0.60 --out evaluations/reports/<date>.md
```

Replay (offline, no credentials):

```powershell
py -3.12 -m evaluations.run_eval --dataset evaluations/datasets/retrieval_v3.json --replay <ranking-fixture.json> --k 5 --abstain-threshold 0.60 --out evaluations/reports/<date>-replay.md
```
