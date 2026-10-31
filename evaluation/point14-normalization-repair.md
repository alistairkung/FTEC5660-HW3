# Point 14 normalization-contract repair

**Status: extraction repair validated; NOT READY overall.** The
evaluated repair source is `81b794de110ca6b1e754de8e6f7d19981b079161`. No aggregation
policy, model, token limit, retry allowance, execution bound or model stage was added.

## Recorded failure and cause classes

The original Option C gate used runtime `7950f3c`, producing two valid 12-claim JSON
responses but no accepted extraction or semantic verification. Immutable response
fixtures retain observations `ec603dca0aae3a85` and `cce50e598587b629` from
[trace 07a230a14e01746a01dc6aba8ca40553](https://cloud.langfuse.com/project/cmvvyy2cf010pad0k901a5phs/traces/07a230a14e01746a01dc6aba8ca40553).
Each response had the same seven individually rejected normalized claims:

| Period | Original source quotation | Model representation | Original rejection / cause class |
| --- | --- | --- | --- |
| 2025Q3 | Revenue for the quarter was USD 215.6 million. | `sales_revenue`, definition quote null | Missing definition wording; redundant standard-definition contract |
| 2025Q4 | Revenue for the quarter was USD 192.6 million. | `sales_revenue`, definition quote null | Same contract mismatch |
| 2026Q1 | Revenue for the quarter was USD 201.1 million. | `sales_revenue`, definition quote null | Same contract mismatch |
| 2026Q2 | Revenue for the quarter was USD 227.7 million. | `sales_revenue`, definition quote null | Same contract mismatch |
| 2025Q4 | Product quality remained excellent and returns were negligible. | numeric `value_text="negligible"`, direction low | Numeric grounding; qualitative representation in numeric field |
| 2026Q1 | Product quality remained excellent and returns were negligible. | numeric `value_text="negligible"`, direction low | Same model/schema representation mismatch |
| 2026Q2 | Returns stayed low and product quality was steady. | numeric `value_text="low"`, direction low | Same model/schema representation mismatch |

The first atomic rejection masked the other six. Generic `grounding_mismatch`
feedback repeated both defects. Quotations themselves were source-grounded;
neither generation exhausted the output allowance. The source-only fixture is
[`point14_cobalt_normalization.json`](../test/fixtures/point14_cobalt_normalization.json);
its decoded response strings have hashes
`9705c1c72bb5881bb434d5cea4e4cbad1f1f6e4a2b260126ac836d68856afe54` and
`06b60d1a62ee6e0285d3f69096174e0798d19ee1f368d4c82cc415ff82e4f3a5`.

## Repaired contract

Numeric level/change claims retain strict copied-number/unit checks. Explicit
qualitative assertions use sourced `qualitative_text` and cannot carry a numeric
value, even when that number occurs in the source. Only the two observed legacy
low/negligible representations receive a bounded compatibility migration; arbitrary
nonnumeric `value_text` remains invalid. Missing numeric levels retain no fabricated
number, record `incomplete_numeric_level`, and remain inconclusive.

Plain unqualified company-wide quarter revenue can use the assignment-standard
definition without inventing a management definition quotation. Its runtime
provenance is explicit. Gross/net/product/division contexts do not receive this
fallback. Missing ambiguous definitions stay unknown; fabricated supplied wording
is rejected. Optional assertion clauses remain inside their validated parent quote,
retain the original ID/speaker/citation, and cannot borrow another clause's
qualifiers or definition. Causal, forecast and commitment assertions remain
unverified; directional claims deliberately use the existing comparison gate.
Specific finite error codes guide the same single bounded recovery.

## Executed offline evidence

The raw-response regression first reproduced the definition rejection in both
attempts. Repairing only that boundary exposed the independent numeric-field
failure. Repairing both now replays each unchanged response into all 12 sourced
claims on one mock invocation, with unchanged IDs, parent quotations and spans.
Focused red/green checks also cover incompatible qualitative/numeric fields,
missing numeric levels, source scope, repeated clauses, fabricated values and
definitions, unit matching and finite recovery feedback.

`python -m unittest discover -s test -v`: **87 tests; 86 passed, one opt-in live smoke
skipped**. The five earlier evidence-level retrospective cases also pass. These
mocked/offline checks are not a live company accuracy result.

## One-company live result

The orchestrator ran one Cobalt gate against frozen source `81b794d`; no other
companies ran. All 12 claims passed extraction on its first call, with zero
extraction repairs or quotation rejections. Source membership was verified. The
typed assertions were four numeric revenue levels, one change, one commitment and
six qualitative claims. Ten quarters of direct returns evidence were retained.

| Measure | Original gate (`7950f3c`) | Repaired gate (`81b794d`) |
| --- | ---: | ---: |
| Accepted extracted claims | 0 | 12 |
| Verification reached | No | Yes |
| Operational failures / semantic abstentions | 1 / 0 | 0 / 1 |
| Grounded PASS/FAIL verdicts / public fallback credit | 0 / 0 | 0 / 0 |
| Extraction calls / extraction tokens | 2 / 6,954 | 1 / 3,825 |
| Total calls / repairs | 2 / 1 | 3 / 1 |
| Total input / output tokens | 3,908 / 3,046 | 43,889 / 5,144 |
| Total tokens / wall seconds | 6,954 / 10.9187 | 49,033 / 17.5086 |

Extraction used 2,133 input + 1,692 output tokens. Overall cost increased because
verification now ran: its two attempts consumed 45,208 tokens. The first proposed
23 events, including unrequested `event:2026Q1:return_rate` and
`event:2026Q2:return_rate`; `incomplete_event_coverage` triggered the existing one
repair. The second covered exactly the 21 prepared events. No limits or loops were
extended to obtain this result.

Python retained four SUPPORTED, four INCONCLUSIVE and four UNMATCHED claim/fact
relations, with no contradictions. The final result was valid
`INSUFFICIENT_EVIDENCE`, not an operational failure. In particular, the verifier
combined the Q3 returns admission with a commitment/wrong-metric claim in its
acknowledgement references; the source gates left that disclosure INCONCLUSIVE.
This is a remaining downstream association issue, not a normalization failure.
The causal clause remains in the original quotation and was not separately extracted
or verified. Three candidates per call are still non-exhaustive.

[Retrieved repaired trace](https://cloud.langfuse.com/project/cmvvyy2cf010pad0k901a5phs/traces/74b534cbee1aefd186c38f13529b60b4):
16 observations, all closed, no missing parent links. Generations were
`dcaf794cf3efae1b` (extraction), `f2ecf10b79c8d3f9` and `8434eeae54ca00b5`
(verification and bounded repair). The ignored local gate/audit artifacts are
`.review/normalization-cobalt-gate.json` and `.review/normalization-cobalt-audit.json`.

The gate demonstrates restored live extraction and an honest semantic-abstention
path, not improved company accuracy. No additional cases or full public baseline
were run. Scope, knowledge, materiality, qualitative criteria and misstatement-policy
limitations remain unchanged. PR #5 stays draft and NOT READY; no aggregation rule
or further source change was made after the gate.
