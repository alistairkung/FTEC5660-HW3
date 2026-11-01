# Point 14 returns-disclosure evaluation — 1 November 2026

Evaluated source: `55729f0561932b592e577ce492bed0630391d447`, based on
`bfa7a06` / the unmerged two-point integration branch. This is a separate experiment;
PR #5's broader transparency pipeline is unchanged. No grading orchestration,
shared contract, protected lecturer code or other specialist changed.

The fixed rule flags a quarterly unit-return rate at least twice the preceding
four-quarter pooled rate; Python uses integer cross-products. Only flagged quarters
receive same-quarter-call acknowledgement assessments. Zero current/baseline returns
are the explicitly authorized no-anomaly exception. See the
[rule, source gates and limitations](../docs/point14-returns-disclosure.md).

## Executed offline validation

**Before paid evaluation: 108 tests, 107 passed and one opt-in live smoke skipped.** All 83 pre-existing
tests remain unchanged. Twenty-five new tests exercise the exact/pooled/zero rule,
monthly completeness and invalid counts, source attribution including indented
headings, one structured format repair, partial FAIL with unresolved neighbors,
timeouts/cancellation, worker isolation, actual mocked HTTP serialization, and
label/artifact isolation. Independent Standards and Spec reviews cleared the slice.

After the baseline, two test-only additions covered multiple clean anomalies
(all acknowledged versus one unacknowledged) and recorded Cobalt/Kestrel call sources
plus a synthetic paraphrase at the provenance-validation boundary. The final full
suite is **110 tests, 109 passed and one opt-in live smoke skipped**. These additions
are not claimed as pre-baseline checks or live paraphrase-accuracy evidence. The
application source, prompt and decision rule remain frozen at `55729f0`.

The actual financial-only run used 20 supplied SQL calls and returned 160 required
quarter totals / 80 reporting-quarter comparisons. It reproduced 12 flagged
quarters and eight no-anomaly companies, with zero documents, interviews, models
or labels. Tool/calculation wall time: 0.0160 seconds. No model-based classifier
score follows from this financial-only result.

## Gated live validation

The first serial gate evaluated Cobalt (acknowledged anomaly), Kestrel (unacknowledged
anomaly) and Aurel (no anomaly), all against the frozen source above. **3/3 grounded
correct; accuracy, balanced accuracy and both recalls 100%.** Two model calls,
2,045 input + 403 output = **2,448 tokens**, 3.840 seconds. No repairs, errors,
abstentions, fallback credits or interviews. Aurel used no document/model calls.
The orchestrator remotely retrieved all three traces: 35 observations, all closed,
complete parent links. Cobalt's exact CFO quotation was verified; Kestrel returned
NOT_ACKNOWLEDGED after full-call inspection with null quote/speaker.

## Unchanged full public baseline

The passed gate was followed by exactly one 20-company run, concurrency two, with
unchanged source/prompt/rule `55729f0`. **20/20 grounded correct; accuracy and balanced
accuracy 100%; PASS recall 14/14, FAIL recall 6/6.** No misclassified companies,
uncertain events, operational failures, repairs or hypothetical fallback credits.
All 20 shared PointResults have status complete.

| Point | Accuracy | Balanced accuracy | PASS recall | FAIL recall | Wall | Model calls | Input / output / total tokens | Failures |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 14 returns disclosure | 100% | 100% | 14/14 | 6/6 | 9.695 s | 12 | 12,221 / 2,363 / 14,584 | 0 |

Twenty SQL calls identified 12 anomalies: six acknowledged and six unacknowledged.
Only those 12 companies used document listing, one relevant full-call read and one
structured model call each. The eight no-anomaly companies used SQL only. Total:
20 SQL + 12 listings + 12 document reads; zero interviews. No fallback verdict was
needed or credited. Disclosure calls and semantic judgements were bounded as
specified, with no rubric/prompt/threshold tuning between the gate and baseline.

| Company | Flagged quarter | Assessment | Verdict | LLM calls | Tokens |
| --- | --- | --- | --- | ---: | ---: |
| ashgrove_labs | 2026Q1 | ACKNOWLEDGED | PASS | 1 | 1,233 |
| aurel_systems | None | No anomaly | PASS | 0 | 0 |
| bramble_labs | 2025Q3 | NOT_ACKNOWLEDGED | FAIL | 1 | 1,191 |
| cobalt_holdings | 2025Q3 | ACKNOWLEDGED | PASS | 1 | 1,242 |
| copperfield_technologies | None | No anomaly | PASS | 0 | 0 |
| driftwood_systems | None | No anomaly | PASS | 0 | 0 |
| dunmore_holdings | 2025Q3 | ACKNOWLEDGED | PASS | 1 | 1,224 |
| elmstead_technologies | None | No anomaly | PASS | 0 | 0 |
| emberly_systems | 2025Q4 | ACKNOWLEDGED | PASS | 1 | 1,236 |
| everline_dynamics | 2025Q4 | ACKNOWLEDGED | PASS | 1 | 1,235 |
| falcrest_technologies | 2026Q2 | NOT_ACKNOWLEDGED | FAIL | 1 | 1,199 |
| fernhill_group | None | No anomaly | PASS | 0 | 0 |
| granite_group | None | No anomaly | PASS | 0 | 0 |
| halcyon_works | None | No anomaly | PASS | 0 | 0 |
| hollins_group | None | No anomaly | PASS | 0 | 0 |
| ironbark_technologies | 2026Q1 | NOT_ACKNOWLEDGED | FAIL | 1 | 1,202 |
| juniper_industries | 2026Q1 | NOT_ACKNOWLEDGED | FAIL | 1 | 1,200 |
| kestrel_technologies | 2026Q1 | NOT_ACKNOWLEDGED | FAIL | 1 | 1,203 |
| lindale_holdings | 2026Q2 | NOT_ACKNOWLEDGED | FAIL | 1 | 1,193 |
| northwind_group | 2025Q3 | ACKNOWLEDGED | PASS | 1 | 1,226 |

Cobalt and Ashgrove acknowledge the actual returns setback. Kestrel's relevant call
reassures investors that returns were low without acknowledging the measured spike,
so it fails this fixed rule. Dunmore passes because it candidly acknowledges the
returns event; its separate revenue discrepancy is outside this chosen disclosure
criterion. An admitted faulty-batch cause is not independently established here.

## Langfuse and independent source audit

All **20 traces were retrieved remotely**. Their 216 observations comprise 108
chains, 12 generations, 52 spans and 44 tools; every observation is closed and every
parent link resolves. Usage reconciles exactly to 12,221 input / 2,363 output tokens.
All 44 native tool inputs/outputs match retained source evidence. Every positive
quotation is exact and management-owned in the full same-quarter call. All six
negative assessments attest full-call inspection with null quote/speaker. Every
flagged period and acknowledgement agrees with the prior source-reviewed research.
The eight no-anomaly traces contain SQL and no generations/documents. Source hashes
match frozen `55729f0`.

Representative retrieved workflows:

- [Cobalt: acknowledged returns setback, PASS](https://cloud.langfuse.com/project/cmvvyy2cf010pad0k901a5phs/traces/361f5711bf4b7b89bbf234f6a8c50b83).
- [Kestrel: unacknowledged setback, supported scoped FAIL](https://cloud.langfuse.com/project/cmvvyy2cf010pad0k901a5phs/traces/36f0b6c311e03350d1ee7486513883c4).
- [Aurel: no anomaly, SQL-only PASS](https://cloud.langfuse.com/project/cmvvyy2cf010pad0k901a5phs/traces/785b4ee005fe3e1676e41f0b4c0250f7).

No live operational failure occurred in this experiment; Kestrel's FAIL is an
investment-rule classification, not an error or fallback. Those failure branches
were tested offline. Remote retrieval, not trace-ID creation alone, confirms ingestion.

## Readiness and next step

**READY FOR INTEGRATION EXPERIMENT**, within the fixed returns-disclosure scope;
not a final submission and not an automatic replacement of another Fisher point.
No critical/high implementation blocker remains in the reviewed slice. Remaining
risks are limited scope, public wording/generalization and unmeasured full-run
variance; these do not authorize silent threshold/prompt changes.

The measured public baseline supports this **narrow returns-disclosure candidate**,
not universal management transparency. Eight correct default PASS outcomes do not
test disclosure of bad news. The public dataset was previously inspected and uses
strongly templated language; private/generalization performance remains unknown.
Cobalt, Kestrel and Aurel have consistent verdicts across the small gate and full
run; this is limited overlap evidence, not three complete stochastic repetitions.
No further paid repetitions or optimization are needed to complete this baseline.

Review this separate PR against `integration/points4-5` (stacked on unmerged PR #6).
The existing PointResult is used directly; specialist records stay owned by the new
namespace. Do not merge, alter PR #5 or wire the grading runner without explicit
instruction. A future integration can inject `build_returns_strategy()` and await
`evaluate(company_id, tools)` without changing its decision rule.

Reproducibility: `.review/returns-gate.json`, `.review/returns-full.json`, associated
launch/remote-trace audits (including `.review/returns-full-audit.json`) and `.review/returns-financial-required-eight.json` remain
local and ignored. Evaluations retain prompt/source hashes, commit, configuration,
evidence and token counts. Only this concise report is committed, not raw outputs.
