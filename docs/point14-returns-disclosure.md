# Point 14 — Returns-disclosure experiment

This independent experiment is **READY FOR INTEGRATION EXPERIMENT within its fixed scope**. It does not
replace PR #5, select a strategy in `hw3.py`, or integrate the three specialists.
The research dataset has already been inspected: public performance is not held-out
validation or a universal test of Fisher's Point 14.

## Fixed scope and rule

For each reporting quarter 2025Q3–2026Q2, calculate returned/shipped units and compare
with pooled returned/shipped units in the preceding four quarters. Flag the quarter
when its rate is at least twice the baseline. Python compares the exact integers:

`current_returned * baseline_shipped >= 2 * baseline_returned * current_shipped`

Displayed Decimal percentages and ratios never decide the threshold. The authorized
zero-return exception treats zero current and zero baseline returns as no anomaly;
a positive current count against zero baseline returns is anomalous, with ratio
undefined (`None`). All shipped denominators must be positive. Zero shipments,
missing/duplicate months, nonintegral/negative counts, returned units exceeding
shipped units, malformed dates, SQL errors and truncated evidence remain operational
errors with no investment verdict. One SQL query aggregates only `returns`, without
joins. It retrieves the eight required quarters (2024Q3–2026Q2) and validates exactly three total,
valid and distinct monthly records per quarter. Integer totals are returned as SQL
TEXT to avoid the lecturer tool's rounding of floating outputs.

No anomaly means scoped PASS with **one SQL call and no document/model calls**.
For an anomaly, list supplied documents once, then read only its complete same-quarter
call. Validate the named quarter, date, management turns and explicit truncation
markers; the supplied `read_document` contract provides full text. A focused model
assessment asks whether management acknowledges the returns/quality setback:
ACKNOWLEDGED, NOT_ACKNOWLEDGED or UNCERTAIN. It does not verify a claimed cause,
replacement expense, economic materiality, management intent or unrelated revenue
statements. Unrelated profit/demand discussion and a future commitment alone do not
acknowledge the setback. Paraphrased admissions are eligible.

ACKNOWLEDGED requires an exact nonblank quotation contained in the relevant
management speaker turn. Speaker aliases come from titled executive introductions
in that source. Analyst statements, headings, fabricated/cross-speaker quotations
and wrong-quarter evidence are rejected. NOT_ACKNOWLEDGED and UNCERTAIN require
null quote/speaker; absence is assessed from the whole call, never a fabricated
negative quotation. `full_call_inspected` records the model's attestation, not a
mathematical proof that it understood every sentence.

All flagged events acknowledged gives PASS. Any independently validated negative
assessment gives FAIL, preserving that evidence if a different event is unresolved;
the summary and diagnostics explicitly disclose neighboring errors/uncertainty.
Otherwise uncertainty/missing evidence/errors retain `PointResult.verdict=None`.
There is no runtime FAIL fallback.

## Interface and execution bounds

`fisher_agent.returns_disclosure.Point14ReturnsStrategy` provides:

- `evaluate(company_id, tools) -> PointResult`: existing shared contract, point 14.
- `assess(...) -> ReturnsRun`: original tool evidence, company/source-linked counts
  and rate comparisons, event findings, diagnostics, model/tool counts and usage.
- `assess_companies(..., concurrency=1|2)`: isolated company workers.

`build_returns_strategy(tracing=None)` constructs the existing LangChain
`deepseek-v4-flash` model with thinking disabled, temperature 0, 600 output tokens,
SDK retries 0 and function-calling structured output. One normal assessment per
anomalous quarter permits at most one format/provenance repair over unchanged
cached evidence. No SQL/document re-fetch, reflection or extra judge is used.
Model timeout 20 seconds, tool timeout 5 seconds, company deadline 120 seconds;
four quarters imply at most eight model attempts. Cancellation propagates.

Optional Langfuse uses one lifecycle and separate company roots. Supplied tools
and LLM calls receive the existing callback config; anomaly comparisons and final
statuses/findings/usage are nested observations. Observability failures remain
optional. No secrets are stored in evidence or committed.

## Independent evaluation

```bash
.venv/bin/python -m unittest discover -s test -v
.venv/bin/python -m evaluation.returns_disclosure --financial-only \
  --data-folder public_test --output .review/returns-financial-new.json
.venv/bin/python -m evaluation.returns_disclosure --live --trace \
  --data-folder public_test --companies cobalt_holdings kestrel_technologies aurel_systems \
  --concurrency 1 --output .review/returns-three-gate-new.json
```

The last command is paid and requires explicit authorization; the orchestrator
controls the three-case gate before any full public run. Existing artifact paths
are refused before model construction. Financial-only mode reads no labels,
documents or API credentials. Live labels are loaded only after all predictions
and tracing finish. Evaluation separates grounded accuracy/recalls, semantic
abstentions, operational errors, independent verdicts with neighboring errors and
hypothetical FAIL-fallback credits. Artifacts retain source/prompt hashes, commit,
configuration, per-company traces and measured interview counters.

## Offline measurement — 1 November 2026

Current full suite: **110 tests; 109 passed and one opt-in live smoke skipped**, including
all 83 existing tests unchanged. New coverage includes exact/pooled threshold,
zero baselines, provenance, bad SQL/counts, speaker/quote gates, all assessment
states, one repair, timeouts, cancellation, concurrency/isolation, partial FAIL,
actual mocked HTTP serialization, no-overwrite and post-prediction label loading.

Actual financial-only public run: **20 SQL calls, 12 anomalous quarters, eight
no-anomaly companies; zero documents, models, interviews or labels**. Measured
calculation/tool wall time was 0.0160 seconds. The flagged quarters reproduce the
prior read-only research; no model acknowledgement performance is claimed yet.
Local ignored artifact: `.review/returns-financial-required-eight.json`.

## Live public baseline — 1 November 2026

After a successful three-case gate, one unchanged 20-company run produced **20/20
grounded correct, 100% balanced accuracy, PASS recall 14/14 and FAIL recall 6/6**.
It used 12 model calls, 12,221 input + 2,363 output = 14,584 tokens and 9.695 seconds
at concurrency two. No repairs, errors, abstentions, fallback credits or interviews.
Six anomalous quarters were acknowledged, six were not; eight companies had no
anomaly and made no document/model calls. See the [per-company results and traces](../evaluation/returns-disclosure-results.md).
All 20 traces were retrieved remotely (216 closed observations, complete parent links),
with source/quotation checks and exact usage reconciliation. These results do not
change the scope limitations below; this is not a final submission or automatic
replacement of another Fisher point. Final integration remains
separate and requires explicit instruction.

## Limits

No anomaly is not affirmative evidence of overall transparency. This rule ignores
non-returns troubles and other investor communications. A rolling baseline can be
contaminated by persistent/repeated anomalies and seasonal changes. A valid exact
quotation proves provenance, not semantic correctness; negative assessments still
need live trace review. Public call wording is strongly templated, and private or
real-world generalization is unproven. The acknowledged faulty-batch cause remains
unverified and is not needed by this deliberately narrow disclosure rule.
