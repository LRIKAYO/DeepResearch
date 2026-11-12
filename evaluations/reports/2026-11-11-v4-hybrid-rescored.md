# Retrieval Evaluation — retrieval-v4

> Re-scored from a saved run: the stored ranking and cosine scores, re-evaluated under the current abstain policy. No new retrieval happened.

## Run metadata

| Field | Value |
| --- | --- |
| Dataset | `retrieval-v4` (schema v2) |
| Dataset SHA-256 | `f57b923b39a57809378a653c4bde652dc22337471ef544979dd493a07c659e9d` |
| Mode | replay |
| API base URL | n/a (replay) |
| Run id | n/a (replay) |
| Cutoff k | 5 |
| Abstain threshold | 0.60 (cosine similarity) |
| Generated at (UTC) | 2026-11-11T16:10:02+00:00 |
| Cost per run | TODO(needs-credentials) |

> Labels: Documents are unmodified README files of third-party open source packages installed under frontend/node_modules, compiled into six volumes per Project. Each section names its package and the licence that package declares. Relevance labels are answered only by the cited passage and are checked against the production chunker (max 2000 chars, overlap 0).

## Headline metrics

Macro, MRR, and nDCG are computed over the 45 answerable cases. Unanswerable cases (n=5) are scored through the abstain metrics instead.

| Metric | Value | Denominator |
| --- | --- | --- |
| Macro Recall@5 | 0.856 | 45 answerable cases |
| Micro Recall@5 | 0.824 | all relevant passages |
| MRR | 0.720 | 45 answerable cases |
| nDCG@5 | 0.740 | 45 answerable cases |
| Hard-negative hit rate (lower is better) | 0.265 | 49 cases with distractors |
| Cross-lingual Recall@5 | 0.833 | 6 answerable CJK-query cases |
| Unanswerable abstain rate | 0.600 | 5 unanswerable cases |
| False-abstain rate (lower is better) | 0.067 | 45 answerable cases |
| Abstain correctness | 0.900 | all 50 cases |
| Latency p50 | n/a | n/a (replay has no network requests to time) |
| Latency p95 | n/a | n/a (replay has no network requests to time) |

## Dataset composition

| Dimension | Count |
| --- | --- |
| Projects | 6 |
| Documents | 36 |
| Chunks (re-chunked offline) | 5091 |
| Cases | 50 |
| Easy / medium / hard | 12 / 24 / 14 |
| Hard-negative cases | 49 |
| Multi-hop cases | 6 |
| Cross-lingual cases | 6 |
| Unanswerable cases | 5 |

## Per-case detail

`RR` is the reciprocal rank of the first relevant passage. `HN hit` is whether a declared distractor entered the top-k (lower is better). `Abstain` shows the policy decision and whether it was correct for the case.

| Case | Project | Difficulty | Flags | Recall@5 | RR | nDCG@5 | HN hit | Abstain | Top-1 | Latency (ms) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| build-detect-libc-off-linux | build-and-tooling | easy | neg | 1.000 | 0.250 | 0.431 | no | no (ok) | `build-and-tooling-volume-1#21` | - |
| build-espree-default-ecma-version | build-and-tooling | easy | neg | 0.000 | 0.000 | 0.000 | yes | no (ok) | `build-and-tooling-volume-2#9` | - |
| build-enhanced-resolve-lower-level-factory | build-and-tooling | medium | neg | 1.000 | 0.333 | 0.500 | no | no (ok) | `build-and-tooling-volume-1#65` | - |
| build-tapable-withoptions-tap-order | build-and-tooling | medium | neg | 1.000 | 0.500 | 0.631 | yes | no (ok) | `build-and-tooling-volume-3#104` | - |
| build-cssesc-global-default-options | build-and-tooling | medium | xling, neg | 1.000 | 1.000 | 1.000 | yes | no (ok) | `build-and-tooling-volume-3#19` | - |
| build-semver-coerce-rtl-tuple | build-and-tooling | hard | neg | 1.000 | 1.000 | 1.000 | no | no (ok) | `build-and-tooling-volume-4#73` | - |
| build-napi-postinstall-unrs-bridge | build-and-tooling | hard | multi, neg | 0.500 | 0.500 | 0.387 | yes | no (ok) | `build-and-tooling-volume-3#66` | - |
| build-sharp-commercial-licence-price | build-and-tooling | medium | unans, neg | n/a | n/a | n/a | no | yes (ok) | `build-and-tooling-volume-2#81` | - |
| dv-arc-default-digits | data-visualisation | easy | neg | 1.000 | 1.000 | 1.000 | no | no (ok) | `data-visualisation-volume-1#11` | - |
| dv-fraction-default-epsilon | data-visualisation | easy | neg | 1.000 | 1.000 | 1.000 | no | no (ok) | `data-visualisation-volume-1#98` | - |
| dv-format-round-precision | data-visualisation | medium | neg | 1.000 | 1.000 | 1.000 | yes | no (ok) | `data-visualisation-volume-2#10` | - |
| dv-symlog-constant | data-visualisation | medium | neg | 1.000 | 1.000 | 1.000 | no | no (ok) | `data-visualisation-volume-2#33` | - |
| dv-array-natural-sort | data-visualisation | medium | neg | 1.000 | 1.000 | 1.000 | no | no (ok) | `data-visualisation-volume-3#20` | - |
| dv-time-format-month-name | data-visualisation | medium | xling, neg | 1.000 | 0.250 | 0.431 | no | yes (WRONG) | `data-visualisation-volume-4#29` | - |
| dv-quantize-sample-domain | data-visualisation | hard | multi, neg | 0.500 | 1.000 | 0.613 | no | no (ok) | `data-visualisation-volume-5#11` | - |
| dv-ease-back-overshoot | data-visualisation | hard | neg | 1.000 | 1.000 | 1.000 | no | no (ok) | `data-visualisation-volume-6#10` | - |
| dv-recharts-pricing-roadmap | data-visualisation | hard | unans, neg | n/a | n/a | n/a | yes | no (WRONG) | `data-visualisation-volume-2#73` | - |
| http-pqueue-strict-burst | http-and-async-runtime | medium | xling, neg | 1.000 | 0.500 | 0.631 | no | no (ok) | `http-and-async-runtime-volume-6#64` | - |
| http-pqueue-timeout-clock | http-and-async-runtime | medium | neg | 1.000 | 1.000 | 1.000 | yes | no (ok) | `http-and-async-runtime-volume-1#46` | - |
| http-ptimeout-fake-timers | http-and-async-runtime | easy | neg | 1.000 | 1.000 | 1.000 | yes | no (ok) | `http-and-async-runtime-volume-1#141` | - |
| http-nodefetch-agent-capabilities | http-and-async-runtime | medium | neg | 1.000 | 1.000 | 1.000 | yes | no (ok) | `http-and-async-runtime-volume-3#74` | - |
| http-openai-retry-statuses | http-and-async-runtime | easy | neg | 1.000 | 0.250 | 0.431 | no | no (ok) | `http-and-async-runtime-volume-4#48` | - |
| http-agentkeepalive-reused-socket | http-and-async-runtime | medium | neg | 1.000 | 1.000 | 1.000 | no | no (ok) | `http-and-async-runtime-volume-6#17` | - |
| http-multihop-timeout-retry-clock | http-and-async-runtime | hard | multi | 1.000 | 1.000 | 1.000 | - | no (ok) | `http-and-async-runtime-volume-4#37` | - |
| http-openai-data-residency | http-and-async-runtime | hard | unans, neg | n/a | n/a | n/a | no | yes (ok) | `http-and-async-runtime-volume-5#52` | - |
| md-hastscript-injected-node | markdown-pipeline | easy | neg | 1.000 | 1.000 | 1.000 | no | no (ok) | `markdown-pipeline-volume-1#57` | - |
| md-mdx-jsx-tight-selfclosing | markdown-pipeline | easy | xling, neg | 0.000 | 0.000 | 0.000 | no | no (ok) | `markdown-pipeline-volume-6#39` | - |
| md-micromark-virtual-line-endings | markdown-pipeline | medium | neg | 1.000 | 1.000 | 1.000 | yes | no (ok) | `markdown-pipeline-volume-4#93` | - |
| md-tojsx-solid-name-case | markdown-pipeline | medium | neg | 1.000 | 0.500 | 0.631 | no | no (ok) | `markdown-pipeline-volume-5#55` | - |
| md-html-safe-url-protocols | markdown-pipeline | medium | neg | 1.000 | 1.000 | 1.000 | no | no (ok) | `markdown-pipeline-volume-6#121` | - |
| md-rehype-katex-release-date | markdown-pipeline | medium | unans, neg | n/a | n/a | n/a | yes | no (WRONG) | `markdown-pipeline-volume-6#214` | - |
| md-remark-gfm-parse-pairing | markdown-pipeline | hard | neg | 1.000 | 1.000 | 1.000 | yes | no (ok) | `markdown-pipeline-volume-3#195` | - |
| md-async-highlighter-deferred-refractor | markdown-pipeline | hard | multi, neg | 0.500 | 1.000 | 0.613 | no | no (ok) | `markdown-pipeline-volume-3#167` | - |
| md-highlightjs-v10-upgrade-reading | markdown-pipeline | hard | neg | 1.000 | 1.000 | 1.000 | no | no (ok) | `markdown-pipeline-volume-5#111` | - |
| util-uuid-v8-helpers | schemas-and-utilities | easy | neg | 1.000 | 1.000 | 1.000 | no | no (ok) | `schemas-and-utilities-volume-3#113` | - |
| util-commander-required-flag | schemas-and-utilities | easy | neg | 1.000 | 0.500 | 0.631 | no | no (ok) | `schemas-and-utilities-volume-2#63` | - |
| util-ajv-format-compare | schemas-and-utilities | medium | neg | 1.000 | 1.000 | 1.000 | no | no (ok) | `schemas-and-utilities-volume-1#76` | - |
| util-nuqs-default-value | schemas-and-utilities | medium | xling, neg | 1.000 | 1.000 | 1.000 | no | no (ok) | `schemas-and-utilities-volume-4#73` | - |
| util-dotenv-override-order | schemas-and-utilities | medium | neg | 1.000 | 1.000 | 1.000 | no | no (ok) | `schemas-and-utilities-volume-6#65` | - |
| util-fast-equals-strict-symbols | schemas-and-utilities | medium | neg | 1.000 | 0.333 | 0.500 | no | yes (WRONG) | `schemas-and-utilities-volume-5#71` | - |
| util-zod-json-schema-to-ajv | schemas-and-utilities | hard | multi, neg | 1.000 | 1.000 | 1.000 | no | no (ok) | `schemas-and-utilities-volume-3#140` | - |
| util-lru-cache-stale-entry | schemas-and-utilities | hard | neg | 1.000 | 0.500 | 0.631 | yes | no (ok) | `schemas-and-utilities-volume-6#145` | - |
| lint-axe-core-ie11 | testing-and-lint | easy | neg | 1.000 | 1.000 | 1.000 | no | no (ok) | `testing-and-lint-volume-1#44` | - |
| lint-glob-parent-non-glob | testing-and-lint | easy | neg | 1.000 | 0.500 | 0.631 | no | no (ok) | `testing-and-lint-volume-6#88` | - |
| lint-humanfs-node-emfile-budget | testing-and-lint | medium | neg | 0.000 | 0.000 | 0.000 | no | yes (WRONG) | `testing-and-lint-volume-2#3` | - |
| lint-minimatch-platform-default | testing-and-lint | medium | neg | 1.000 | 0.500 | 0.631 | no | no (ok) | `testing-and-lint-volume-1#147` | - |
| lint-braces-range-limit | testing-and-lint | medium | neg | 0.000 | 0.000 | 0.000 | no | no (ok) | `testing-and-lint-volume-1#76` | - |
| lint-ignore-allow-relative-paths | testing-and-lint | medium | xling, neg | 1.000 | 1.000 | 1.000 | no | no (ok) | `testing-and-lint-volume-6#117` | - |
| lint-basename-match-minimatch-vs-fastglob | testing-and-lint | hard | multi, neg | 0.000 | 0.000 | 0.000 | no | no (ok) | `testing-and-lint-volume-2#148` | - |
| lint-paid-support-sla | testing-and-lint | hard | unans, neg | n/a | n/a | n/a | no | yes (ok) | `testing-and-lint-volume-4#52` | - |

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
py -3.12 -m evaluations.run_eval --dataset evaluations/datasets/retrieval_v4.json --api http://127.0.0.1:8000 --user-id <uuid> --k 5 --abstain-threshold 0.60 --out evaluations/reports/<date>.md
```

Replay (offline, no credentials):

```powershell
py -3.12 -m evaluations.run_eval --dataset evaluations/datasets/retrieval_v4.json --replay <ranking-fixture.json> --k 5 --abstain-threshold 0.60 --out evaluations/reports/<date>-replay.md
```
