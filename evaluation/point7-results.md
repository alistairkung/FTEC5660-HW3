# Point 7 public evaluation

Evaluated 1 November 2026, 08:58 HKT, from PR #6 head `bfa7a06` in
`.worktrees/point7` on `feat/fisher-point-7`. Prompt: `labour-v1`.
Required model: `deepseek-v4-flash`, explicit non-thinking mode, temperature 0.
No prompt changes or company-specific rules followed the gate.

| Measure | Four-company live gate | All 20 public companies |
| --- | ---: | ---: |
| Grounded correct | 4/4 | 20/20 |
| Grounded accuracy | 100% | 100% |
| Balanced accuracy | 100% | 100% |
| PASS recall | 2/2 | 14/14 |
| FAIL recall | 2/2 | 6/6 |
| Operational errors / insufficient evidence | 0 / 0 | 0 / 0 |
| Second interviews | 0 | 0 |
| Interviews / model calls | 4 / 4 | 20 / 20 |
| Input / output tokens | 2,628 / 523 | 13,172 / 2,679 |
| Total tokens | 3,151 | 15,851 |
| Runtime, including tracing shutdown | 3.631s | 11.332s |

Every public classification has an exact validated quotation and source. No
operational fallback receives credit. Every lecturer interview counter matches
one current-employee interview. Labels were read by the evaluator after inference;
the specialist received only its company's permitted tools and returned evidence.
Gate usage is additional to the full-run usage (24 total calls/interviews).

## Offline verification and scope review

`python -m unittest discover -s test` ran **104 tests: 103 passed, one optional paid
observability smoke skipped**. The 21 new tests cover decisive PASS/FAIL, conditional
follow-up, repeated uncertainty, exact quotes/source membership, malformed and
multiple structured responses, bounded repairs and interviews, retrieval/API
failures, company isolation, concurrency, company/batch deadlines, cancellation,
Langfuse propagation/unavailability, actual non-thinking request serialization,
shared `PointResult` mapping and development scoring.

The first specialist test failed on the absent implementation before passing.
Subsequent uncertainty/error slices likewise failed before their implementation.
A batch-deadline regression caught discarded in-flight usage counters; the fix
retains them and returns errors for queued companies after budget exhaustion.
`git diff --check` passed. Diff review confirmed only Point 7 files, tests,
documentation and ignore entries were added. `hw3.py` (including protected lecturer
code and `CHOSEN_POINTS`), shared contracts, existing specialists and dependencies
remain byte-identical to the integration base. The unchanged three-point grader
was not invoked for this independent backup: Point 7 is not wired into it.

## Remote Langfuse verification

The current observations API (`GET /api/public/v2/observations`) was queried via
`langfuse-cli` after the run. The full run has **20/20 complete traces, 260 closed
observations**, one generation and one interview tool per company, no errors,
resolved parents, isolated company/Point 7 metadata, interview answers, model
inputs/outputs and final verdicts. Token totals reconcile exactly after adding
Langfuse's separate cached-input category. Each trace has 9 LangChain chain
observations, 2 spans, 1 tool and 1 generation.

The request and LangChain `ls_model_name` record `deepseek-v4-flash`; the provider
returns the response alias `deepseek-flash`, which Langfuse uses as the generation
model field. The offline wire test verifies the requested model and disabled
thinking independently. The pinned existing Langfuse 5.1.0 integration is reused.

Representative remotely retrieved traces:

- [Bramble PASS](https://cloud.langfuse.com/project/cmvvyy2cf010pad0k901a5phs/traces/f605fdef7525726cb58598d4b5fef2d6): fair pay, retention and resolved concerns.
- [Ashgrove FAIL](https://cloud.langfuse.com/project/cmvvyy2cf010pad0k901a5phs/traces/9f1e66fa8cc14707ea1652b4ab41a4b8): constant overtime and monthly departures.

Local ignored artifacts: `point7-gate.json`, `point7-public.json`,
`point7-remote-observations.json` and `point7-trace-audit.json`. Remote records and
checked-in results provide review evidence without committing bulky SDK payloads.

## Reproduction and limitations

See [execution commands and contract](../docs/point7.md). The full-run report
records these live-evaluation SHA-256 hashes. The interpreter and records files
subsequently received whitespace-only EOF cleanup; their behaviour and prompt
are unchanged:

| File | SHA-256 |
| --- | --- |
| `hw3.py` | `50ebe4346e2c59fe4c738b2e031f14fcc60b237adb18c805166d2b25925e6a01` |
| `labour_interpreter.py` | `904650316f7daf56a01ea6340081ad8caebd000c1897f874952027d5c527a5eb` |
| `labour_records.py` | `3816549601d60b34765146df6cbe3b5c2c9b6cd8c46c30668b7a8bb0dfecae28` |
| `labour_runtime.py` | `b1999c9403092834583caddaf763b65722ca7852bcf4af8a825ec17e330f7446` |
| `labour_specialist.py` | `ce5f48e14e41311bf23f68675feb1fac7e848f04db196aeeb3893001f1027279` |

**Ready as an independently tested backup at the shared-contract boundary.**
A final 4/5/7 selection, homework wiring, report update and combined evaluation
remain a separate decision. This is one full public run after a four-company gate;
it does not establish private-set or repeat-run accuracy. Follow-up and recovery
paths were exercised offline, not triggered by these public interviews. Exact
quotation validation proves source grounding, while semantic correctness still
depends on the model. Usage is provider-reported; failed calls may have unreported
provider usage. Async timeouts cannot kill a blocked native synchronous tool
thread; the supplied in-memory interviews completed promptly in this evaluation.
