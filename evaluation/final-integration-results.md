# Final Point 4/5/14 integration validation

Measured 1 November 2026. Evaluated application commit:
`2c80293a46a67941701c727953d6a355cb8a50aa`.
Subsequent release changes are documentation and merge ancestry only; application
bytes must match the recorded source hashes before release.

## Actual lecturer entry points

| Check | Command | Environment | Process time | Exit / CSV |
| --- | --- | --- | ---: | --- |
| Fresh GitHub checkout | `python hw3.py --data-folder public_test` | Python 3.14.0; only `pip install -r requirements.txt`; only DeepSeek API credential; no `.env`, optional Langfuse SDK or neighbouring artifacts | 18.217 s | 0; 20 rows, exactly 4/5/14 |
| Optional traced integration | `python -m observability.run --data-folder public_test` | Python 3.13.9; optional SDK 5.1.0; existing tracing project | 15.977 s including flush/shutdown | 0; same 60 verdicts |

The optional launcher calls the real unchanged `hw3.main()`, rather than the
independent specialist evaluators. Calls were sequential between runs, with at most
two active companies in each. No additional paid smoke or scoring-tuning calls were
made. Both runs used the existing `deepseek-v4-flash`, temperature 0, thinking
disabled, SDK retries 0 and unchanged specialist prompts/rules.

Independent post-run CSV scoring reproduced the lecturer's output:

| Point / selection | Correct | Accuracy | Balanced accuracy | PASS recall | FAIL recall | Operational fallbacks |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 4 — existing sales workflow | 20/20 | 100% | 100% | 14/14 | 6/6 | 0 |
| 5 — IndustryMarginStrategy | 20/20 | 100% | 100% | 14/14 | 6/6 | 0 |
| 14 — returns-disclosure-v1 | 20/20 | 100% | 100% | 14/14 | 6/6 | 0 |
| Total | 60/60 | 100% | 100% | 42/42 | 18/18 | 0 |

No disagreements, invalid or missing verdicts. Every CSV `points_correct` is `3/3`
and every `point_errors` is empty. Predictions agree across the two executions;
this is not a statistically sufficient estimate of private-set or three-run variance.
The traced run additionally confirms all 60 internal statuses are `complete`, with
company-scoped provenance; none is an operational FAIL credit.

## Usage and evidence audit

The figures below are measured from the remotely retrieved traced integration.
The key-only run did not export token usage, so its paid tokens are not included.

| Point | Models | Input tokens, including cache reads | Output tokens | SQL | Interviews | Document tools |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 4 | 20 | 13,294 | 2,527 | 0 | 20 | 0 |
| 5 | 0 | 0 | 0 | 40 | 0 | 0 |
| 14 | 12 | 12,221 | 2,368 | 20 | 0 | 24 |
| Total | 32 | 25,515 | 4,895 | 60 | 20 | 24 |

Total tokens: **30,410**. Document tools comprise 12 listings and 12 complete
same-quarter call reads. All sales interviews were customer / `sales_team`;
zero competitor interviews, adjudications, invalid outputs, repairs, operational
failures or abstentions. Model latency: 0.811–1.619 s, median 1.299 s, nearest-rank
95th percentile 1.607 s. Longest company workflow: 1.630 s.

Point 14 reproduced eight SQL-only PASS defaults, six validated acknowledgements
and six complete-call non-acknowledgements. Pure Python replay of all 20 SQL outputs
confirmed eight complete historical quarters and four reporting-quarter comparisons
per company. Acknowledgement proposals were revalidated against exact management
turns, document identity and period; negative proposals inspected the complete call
and contained null quotations/speakers. No added cause/intent conclusion was used.
All 20 Point 4 outputs were revalidated against their supplied interview quotation;
all 40 margin SQL input/output pairs match retained provenance.

## Remote Langfuse ingestion

[Actual integrated batch trace](https://cloud.langfuse.com/project/cmvvyy2cf010pad0k901a5phs/traces/73e903338788c3efbfdbea071aa3a0fa)
contains 20 company workflows and all three specialists under each company:
**557 observations = 288 chains + 32 generations + 133 spans + 104 tools**.
All observations are closed, every parent resolves, and no ERROR observations exist.
Company/Fisher-point metadata and native token totals reconcile with company outputs.
The request metadata names `deepseek-v4-flash`; the provider response alias displayed
by Langfuse is `deepseek-flash`.

Representative observations in this common trace:

| Company / path | Company observation | Point 14 observation |
| --- | --- | --- |
| Cobalt — acknowledged setback, PASS | `d623ab123bb78690` | `fdc2c47c39432f3d` |
| Kestrel — unacknowledged setback, FAIL | `7b3acda722d2bb88` | `a466afbf2349ad94` |
| Aurel — no anomaly, PASS without documents/model | `65e675e54d0b9065` | `df741ed3b9089156` |

This is confirmed remote retrieval through the observations API, not merely local
trace creation. Eight no-anomaly Point 14 subtrees contain exactly one SQL tool and
zero document/model observations. Observability failures remain non-fatal by design
and are covered offline.

## Offline, fresh environment and source checks

`python -m unittest discover -s test -v`: **116 run, 115 passed, one opt-in paid smoke
skipped**, independently reproduced in both Python environments. Integration tests
exercise actual simplified Point 14 ACK/NOT_ACK paths with distinct company tools,
SQL-only routing, selected margin strategy, shared-result aggregation, deadlines,
batch queue expiry, cancellation, errors/uncertainty, tracing off and lecturer CSV.
Independent Standards and Spec reviews found no application blockers.

Fresh setup used a new clone of the published integration branch, a new virtualenv
and only the required requirements file. `langfuse` was not installed, `.env` and
`.review` did not exist, and the application received only `DEEPSEEK_API_KEY` as a
service credential. It exited normally and left no tracked modifications. Installed
versions included LangChain 1.4.7, core 1.7.3, DeepSeek adapter 1.1.1, OpenAI 3.42.0,
Pydantic 2.14.2 and python-dotenv 1.2.4. No dependency changes were introduced.

The entire protected `hw3.py` suffix matches lecturer starter `5fa8c37` byte-for-byte:
SHA-256 `745394065cca0d406516957b736cd99fa6c435f6122f00db04bb45040c008211`.
Provided constants/helpers above the student selection are also identical.
Points 4/5/14 specialist files and shared contracts/adapters match PR #8 head
`10217de`; only orchestration, student dependency wiring, tests and README changed.
Application-source audit found no direct company DB/interview-file access, labels,
public-company exceptions or hard-coded local paths. Public data and previous
baselines remain unchanged; tracked credential scan passed.

Ignored local evidence lives under the final worktree's `.review/release/`:
`traced-entrypoint/` and `clean-entrypoint/` contain CSV, stdout and immutable launch
manifests; `traced-entrypoint/observations.json`, `trace-audit.json` and
`trace-audit.txt` retain remote evidence. `final-offline.txt`, `source-audit.json`
and the independent audit scripts preserve reproducibility. Generated artifacts
are not part of the submission.

## Remaining limits and submission

Point 14 is a scoped returns/quality disclosure assessment, not a finding of intent
or comprehensive integrity. Its fixed 2x trailing pooled baseline may miss other
troubles or be affected by persistent anomalies/seasonality. Exact quotations prove
provenance, while semantic interpretation still depends on the model. The public
corpus informed development and is templated. Python cannot forcibly terminate a
blocked native tool thread; bounded waits isolate points, and margin daemon workers
cannot hold process exit indefinitely. Unresolved public FAIL fallbacks remain an
honest error policy, not grounded investment findings.

The authoritative PDF requires a public GitHub repository named `FTEC5660-HW3`,
`hw3.py`, `requirements.txt` and the README report; supporting modules are included.
Task 2 reflection is included in the README and labelled AI-assisted, as permitted.
Enter `https://github.com/alistairkung/FTEC5660-HW3` in the course submission form
before **16 November, 23:59 HKT**. No separate archive is specified. Keep the repo
public and omit API keys; graders use their own key and average three private runs,
each of which must produce `results.csv` within 30 minutes.
