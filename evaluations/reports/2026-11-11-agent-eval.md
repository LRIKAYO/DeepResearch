# Agent-level evaluation — 2026-11-11

The retrieval evaluation scores chunks. This one scores the **agent**: rounds
spent, citation coverage of the report it writes, what the verifier says about
each citation, and wall-clock latency. Two measurements live here:

1. `scripts/verifier_probe.py` — does the verifier's judgement work at all?
2. `scripts/agent_eval.py` — what does a real 4-question run look like?

Both need a running Product Backend and provider credentials, so they are scripts
with recorded output rather than tests.

## 1. Verifier against known ground truth

Ten pairs: five genuinely supported, five deliberately mismatched (the passage is
about something else). Ground truth is known by construction, so this measures
judgement, not plumbing.

| | result |
| --- | --- |
| Correct | **10 / 10** |
| Injected mismatches labelled `none` | **5 / 5** |
| Supported pairs labelled `full` | **5 / 5** |

The mismatches included a real near-miss: "p-queue timeouts only start counting
once the task leaves the backlog" against a passage that says the opposite in
almost the same words. It was labelled `none`.

Raw verdicts, including the verifier's one-sentence reason per pair:
`evaluations/reports/verifier-probe.json`.

## 2. Four-question agent run

Project: three volumes of the `data-visualisation` corpus (d3-shape, d3-array,
fractions). Questions: two English, one Chinese, one deliberately unanswerable
(a commercial licence price the corpus cannot contain).

| Case | Rounds | Citations | Coverage | Verdicts | Latency |
| --- | --- | --- | --- | --- | --- |
| arc-default-digits (en) | 1 | 10 | 1.00 | 10 full | 47.8 s |
| d3-natural-sort (en) | 2 | 16 | 1.00 | 15 full, 1 none | 82.1 s |
| d3-array-zip (zh) | 1 | 8 | 1.00 | 5 full, 3 none | 49.9 s |
| unsupported-pricing (en) | 2 | 11 | 1.00 | 6 full, 5 partial | 99.3 s |
| **total** | **6** | **45** | **1.00** | 36 full / 5 partial / 4 none | p50 82.1 s |

**Support rate 0.80** (36 of 45 citations judged `full`). Mean rounds 1.5. No run
failed.

### What the numbers mean, and what they hide

- **Coverage 1.00 on every run** confirms the Writer audit: no source is listed
  without being cited.
- **Support rate 0.80 is the honest number.** A citation that is present can still
  be `partial` or `none`; the verifier reported 9 such verdicts.
- **The unanswerable question was answered, not refused.** The report says
  "no official commercial pricing was found" and cites the passages it inspected.
  The verifier calls those citations `full`, because the passages really do
  support "the documentation does not mention pricing". That is correct
  citation-support judgement and *wrong* abstention behaviour: nothing in the
  pipeline refuses a question the corpus cannot answer. Treat the support rate as
  "are the citations real", not "is the answer true".
- **Latency is 48–99 s per question** with 1–2 rounds. This is a demo-grade
  number: no caching, no streaming-level optimisation, and the planner +
  researcher + writer + verifier each cost a model call.

## Reproduce

```powershell
# backend must be running, .env must hold the provider keys
py -3.12 -m scripts.verifier_probe --out evaluations/reports/verifier-probe.json
py -3.12 -m scripts.agent_eval --out evaluations/reports/agent-eval.json
```

Both scripts create their own Project through the Product Backend. `agent_eval`
leaves it behind: delete it with `DELETE /projects/{project_id}` once the run is
done (the endpoint exists for exactly this reason).
