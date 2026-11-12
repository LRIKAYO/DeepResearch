# Context window — 2026-11-12

**Question.** Do answers sit just outside the retrieved chunk, and does handing the
Writer a window around each hit improve the report?

**Answer.** Yes to the first. The second depends entirely on *where the window
starts*: a window in document order made citation support collapse, a window that
leads with the matched chunk lifted it above every other configuration measured.

## 1. The ceiling, measured offline

For each answerable case, does a labelled relevant passage fall inside a window
around one of the returned hits? (`scripts/context_coverage.py`, no model, no
database — it reads a saved run and the dataset.)

| Window | k=1 | k=3 | k=5 |
| --- | --- | --- | --- |
| exact | 0.600 | 0.822 | 0.889 |
| ±1 | 0.600 | 0.822 | 0.911 |
| **±2** | **0.711** | **0.911** | **0.956** |
| ±3 | 0.711 | 0.911 | 0.956 |

±2 is the sweet spot and ±3 adds nothing. At k=5 a window covers 95.6% of
answerable cases against 88.9% for the exact hit: three cases gain the answer.

## 2. The implementation, and the bug it exposed

`GET /projects/{id}/knowledge/chunks/{chunk_id}/context?radius=N` returns the
matched chunk with its neighbours. The `knowledge_search` tool uses it when
`RESEARCHFLOW_CONTEXT_RADIUS > 0`, keeps the matched chunk's provenance, and falls
back to the bare chunk if the window cannot be fetched.

**The first version joined the window in document order.** That is the natural
choice and it was wrong, for a reason that is easy to miss: the citation excerpt
is the first 500 characters of the evidence, and the verifier reads the first
1200. A document-order window puts the matched chunk in the *middle*, so both
readers were shown the context and not the answer. Support rate fell to 0.372,
worse than not expanding at all.

The fix is to put the matched chunk first, then the chunks after it, then the ones
before it. The Writer still gets the surrounding text; the excerpt and the
verifier now start at the passage that was actually matched.

## 3. Agent-level runs

Four questions (two English, one Chinese, one unanswerable), one run per
configuration, same day, same provider:

| Run | Retrieval | Window | Citations | full | partial | none | Support rate |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-11-11 | cosine | none | 45 | 36 | 5 | 4 | 0.800 |
| A | hybrid | 0 | 53 | 31 | 1 | 21 | 0.585 |
| B | hybrid | ±2, document order | 43 | 16 | 2 | 25 | **0.372** |
| C | hybrid | ±2, matched first | 37 | 30 | 1 | 6 | **0.811** |
| D | cosine | 0 | 48 | 34 | 2 | 12 | 0.708 |

Read them in that order: B is the ordering bug, C is the fix, D isolates the
lexical signal.

What this does and does not establish:

- **The fix is real and large.** B → C is +0.439 support rate and 25 → 6 `none`
  verdicts, with retrieval held constant. This is the one claim the sample
  supports strongly.
- **The lexical signal looks harmful at the agent level** (A 0.585 vs D 0.708, and
  21 vs 12 `none` verdicts). Do not treat this as established: it is four
  questions, and the *same* cosine configuration scored 0.800 the previous day and
  0.708 today — about as large as the hybrid delta. The 50-case retrieval
  evaluation remains the trustworthy measurement, and there hybrid wins
  (`2026-11-11-v4-hybrid-decision.md`).
- **Fewer, better citations.** C cites 37 passages against A's 53 and produces
  more `full` verdicts, which is the direction a verifiable agent should move.

## Decision

- `RESEARCHFLOW_CONTEXT_RADIUS` defaults to **2**; 0 disables expansion.
- The window **always leads with the matched chunk**. This is now a documented
  property of the endpoint, not an implementation detail, because two downstream
  readers depend on prefixes.
- `RESEARCHFLOW_RETRIEVAL_MODE` (`hybrid` default, `cosine` for comparison) exists
  so this class of question can be measured without editing code.
- The agent-level sample needs to grow before any retrieval choice is justified by
  it. Until then, retrieval decisions use the 50-case evaluation and agent-level
  numbers are reported with their sample size attached.

## Reproduce

```powershell
py -3.12 -m scripts.context_coverage                     # the ceiling table
$env:RESEARCHFLOW_RETRIEVAL_MODE="hybrid"; $env:RESEARCHFLOW_CONTEXT_RADIUS="2"
py -3.12 -m scripts.agent_eval --out evaluations/reports/agent-eval-radius2-matchfirst.json
```

Artifacts: `agent-eval-radius0.json`, `agent-eval-radius2.json` (the ordering bug),
`agent-eval-radius2-matchfirst.json`, `agent-eval-cosine-radius0.json`.
