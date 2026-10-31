# Points 4 and 5 integration validation

31 October 2026. **Validated two-specialist milestone; not submission-ready.**
Point 14 remains missing, and PR #5 has not been merged.

## Configuration and reproduction

Evaluated runtime commit: `ee0f821e6b51e1d34668b421658204033b98c601`, based on
main `6d49b9c` after PR #2 (`8a23e46`) and PR #3 (`6d49b9c`) merged.
Point 4 retains `deepseek-v4-flash`, temperature 0, disabled thinking, its original
prompts/schema/routing and zero SDK retries. Point 5 selects IndustryMarginStrategy;
its financial rules, SQL and Decimal arithmetic are unchanged. Company concurrency
is two, company deadline 95 seconds, analysis batch deadline 1,200 seconds, and
synchronous SQL deadline 10 seconds with at most two physical workers.

Fresh environment: Python 3.13.9, installed `requirements-observability.txt` using
`uv venv .venv` and `uv pip install --python .venv/bin/python -r requirements-observability.txt`.
The local environment freeze records LangChain 1.4.7, langchain-core 1.7.3,
langchain-deepseek 1.1.1, OpenAI 3.42.0 and Langfuse 5.1.0.

```bash
python -m unittest discover -s test -v
python -m evaluation.compare_point5 --output .review/point5-comparison.json
python -m evaluation.combined --live --data-folder public_test --output .review/combined-full.json
```

Load configured `.env` before live execution. The one-company live smoke used the
actual `observability.run` → `hw3.main` → unchanged lecturer runner over a local
one-company fixture linked to public data. It produced `4:FAIL 5:PASS 14:missing`,
one customer interview and two SQL queries; one model call, 790 tokens, 4.286 seconds
including initialization, tracing and flush. The full evaluation followed only after
this gate passed; paid runs did not overlap.

## Measured results

| Point | Grounded correct | Balanced accuracy | PASS recall | FAIL recall | Operational failures | Fallback credits |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 4 | 20/20 | 100% | 100% | 100% | 0 | 0 |
| 5 — Industry | 20/20 | 100% | 100% | 100% | 0 | 0 |

Combined analysis took **12.849 seconds**; **13.552 seconds** including model setup
and tracing flush. There were 20 model calls, 13,294 input + 2,523 output =
**15,817 tokens**, 40 SQL queries and one customer/sales_team interview per company.
There were no competitor interviews, adjudications, invalid-output diagnostics or
API failures. All 40 implemented-point predictions were grounded correct; no
operational FAIL fallback contributed a correct label.

The unchanged lecturer output reports **40/60**, **66.67% balanced accuracy** because
all 20 Point 14 entries are missing. A perfect score on the two implemented points
does not satisfy the exactly-three-point assignment contract. No three-point result
or private-grader stability claim is made.

The preserved deterministic experiment independently reproduced Industry 20/20,
100% balanced accuracy and Historical 12/20, 52.38% balanced accuracy (PASS recall
71.43%, FAIL recall 33.33%). Historical remains experimental only.

## Offline and trace verification

- Full suite: **83 tests run, 82 passed, one optional paid smoke skipped**.
- Contract/adapters distinguish operational errors from supported FAIL; orchestration
  tests cover company/batch deadlines, queued error entries, partial result preservation,
  cancellation and company isolation. SQL tests exercise stalled calls and physical
  worker bounds. An offline end-to-end test exercises real lecturer normalization/CSV.
- Protected `hw3.py` suffix and constants match starter `5fa8c37` byte-for-byte;
  requirements and public data are unchanged. Margin records moved without changing
  their definitions; no specialist decision rules or prompts changed.
- Independent Standards and Spec reviews found no remaining blockers for this milestone.
- Fresh Langfuse CLI retrieval confirmed **20 traces / 340 observations**: 80 spans,
  180 native chains, 60 tools and 20 generations. All observations closed, all parents
  resolved, no error observations. Every SQL input/output and interview answer matches
  the retained specialist evidence. Remote generation usage reconciles to local totals,
  including cached input tokens. Generation latency: 0.861–1.511 seconds, median 1.283.

Representative remotely retrieved workflows:

- [Ashgrove: supported sales FAIL and margin PASS](https://cloud.langfuse.com/project/cmvvyy2cf010pad0k901a5phs/traces/f7c02f36aa5cb5f296cddfd3e2792a10).
- [Bramble: both supported PASS](https://cloud.langfuse.com/project/cmvvyy2cf010pad0k901a5phs/traces/9ee5a3d22ce71f07deb02812f25226c1).
- [Actual homework-entry smoke](https://cloud.langfuse.com/project/cmvvyy2cf010pad0k901a5phs/traces/3495a25056d9e34dc569b473d66ab8d3).

Local ignored artifacts under `.review/`: `combined-full.json` (per-company original
evidence, diagnostics, source hashes, usage and trace IDs), `combined-full-results.csv`,
`combined-full-traces.json`, `combined-trace-audit.json`, `combined-smoke-run.json`,
`combined-smoke-results.csv`, `combined-smoke-traces.json`, and `environment.txt`.
Generated artifacts are not committed. JSON evaluation refuses to overwrite a baseline.

## Remaining boundary

Point 14 must pass its evidence-level and operational gates, gain an explicit shared
result adapter, and undergo complete three-point validation before submission. The
integration PR is a separately reviewable milestone. A timed-out SQL thread cannot
be forcibly killed; its bounded daemon worker retains capacity until return and can
outlive a native tool observation. Normal live observations were all confirmed closed.
