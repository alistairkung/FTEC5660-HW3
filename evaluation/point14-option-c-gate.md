# Point 14 Option C — first live gate

**Decision: NOT READY; ADJUST normalization/recovery before another gate.** The
architecture's deterministic invariants pass offline, but the first live attempt
did not reach semantic verification. This is not evidence of improved accuracy.

## Measured execution

On 31 October 2026, the orchestrator evaluated one company (`cobalt_holdings`)
against frozen runtime commit `7950f3c5828cda79bd3dd3ea947d7bc2580a938c`:

| Measure | Result |
| --- | ---: |
| Grounded final classifications | 0/1 |
| Operational errors / semantic abstentions | 1 / 0 |
| Public fallback credit | 0 |
| Model calls / bounded repairs | 2 / 1 |
| Input / output / total tokens | 3,908 / 3,046 / 6,954 |
| Wall time | 10.9187 seconds |
| SQL errors / quotation rejections | 0 / 0 |

The operational result was `invalid_output` at `claim-extraction`. Both model
responses were valid JSON/schema objects with 12 claims, using 1,522 and 1,524
output tokens, below the unchanged 3,500-token cap; this was not an API or
reasoning-budget failure. No verification or final aggregation was reached.
The four remaining gate companies were cancelled before inference. No full
20-company Option C run was launched.

## Offline diagnosis of the recorded responses

Each response had seven individually invalid normalized claims:

- Four revenue propositions declared `measurement_definition="sales_revenue"`
  with `definition_quotation=null`. The first atomic-batch rejection was
  `Measurement definition needs exact source wording`.
- Three qualitative propositions put `negligible` (twice) or `low` in the numeric
  `value_text` field. They passed the string schema but failed numeric grounding.

Repair exposed only the finite generic `grounding_mismatch` code, so the second
response repeated both defects. Original quotations were source-grounded.

Disposable in-memory counterfactuals were diagnostic only: clearing unsupported
definitions alone still failed numeric grounding; clearing both unsupported
definitions and nonnumeric values allowed all 12 source quotations through the
extractor. No application changes or extra model calls were made, and this replay
does not establish correct normalization, disclosure judgement or company verdicts.

## Recommendation and evidence

Retain the proposition/disclosure separation for the next narrow experiment. A
future authorized change must address both normalized-field cases and provide
specific finite recovery feedback. A missing supported definition should remain
unknown; qualitative low/negligible should remain qualitative without an invented
number. Fabricated quotations and unsupported numeric facts must still be rejected.
Do not add judges, raise token limits or extend retry loops to address this failure.

[Retrieved trace](https://cloud.langfuse.com/project/cmvvyy2cf010pad0k901a5phs/traces/07a230a14e01746a01dc6aba8ca40553):
generations `ec603dca0aae3a85` and `cce50e598587b629`; 15 observations, all closed,
including three error observations. Local ignored evidence is
`.review/orchestrator-option-c-first.json`, its retrieved traces, and
`orchestrator-option-c-first-diagnosis.json` in the Point 14 worktree.

The earlier non-thinking baseline at `b10326b` scored 6/20 grounded correct,
45.24% balanced accuracy. It predates Option C and must be reported separately.
Option C has **no comparable live semantic score**. Its offline suite remains
77 tests: 76 passed and one opt-in live smoke skipped. Publication of this failed
gate evidence does not mark PR #5 ready or authorize integration.
