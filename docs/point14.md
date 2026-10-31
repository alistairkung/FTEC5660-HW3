# Fisher Point 14 — Scoped transparency research

**Option C is NOT READY for grading integration.** Proposition truth and disclosure
are separate findings. Python returns `TRANSPARENT`, `EVASIVE` or
`INSUFFICIENT_EVIDENCE` only after checking their prerequisites. Unknown materiality,
measurement definitions, management knowledge or misstatement policy remain explicit.
Only TRANSPARENT produces a researched PASS. The public adapter separately labels
unresolved results as FAIL fallbacks; they are not researched investment failures.

## Current implementation

```text
supplied SQL → financial facts + quarterly returns → adverse-event candidates
supplied calls → sourced propositions → one association/disclosure model call
→ deterministic proposition gates + disclosure prerequisites → typed decision
```

| Component | Responsibility |
| --- | --- |
| `FinancialEvidenceExtractor` | One supplied SQL aggregate; financial metrics and direct returns counts/rates |
| `ManagementClaimExtractor` | One model extraction; exact source spans and normalized propositions |
| `claim_evidence_matcher` | Same-proposition compatibility and numerical/directional relations |
| `disclosure_rules` | Event preparation, communication coverage and prerequisite-gated aggregation |
| `TransparencyVerifier` | One semantic association/disclosure call, source gates and canonical summary |
| `TransparencySpecialist` | Company-local sequencing, diagnostics, deadlines and optional tracing |

Revenue, costs and returns are aggregated separately before joining ten quarters
(2024Q1–2026Q2); no rows multiply through joins. The snapshot retains 84 financial
metrics and ten quarterly returns records. Return rate is
`100 * SUM(units_returned) / SUM(units_shipped)`, with original counts and provenance.
All three total/valid/distinct monthly records are required. Missing, duplicated,
malformed, nonfinite or fractional counts are errors; a zero shipment denominator
retains an explicit unknown rate. Original amounts remain USD thousands.

Claims preserve company, document, date, speaker, exact quotation and offsets.
Named executives are recognized from a matching titled introduction anywhere in
that transcript. Blank wording, headings, analyst speech and cross-speaker spans
are rejected. Normalized propositions retain subject, metric, asserted period,
assertion type, value/unit, comparison basis/period, qualifiers, certainty and
measurement definition. Numeric values and supplied definition wording must be
copied from the quotation. Missing ambiguous definitions remain unknown rather than
invalidating otherwise sourced claims. Plain unqualified company-wide quarter
revenue has the assignment-standard definition without a fabricated definition quote;
`measurement_definition_source` distinguishes this from management-supplied wording.
A copied phrase proves grounding, not semantic normalization correctness.

The normalization repair separates numeric `value_text` from general sourced
`qualitative_text`, and distinguishes directional, event, causal, forecast and
commitment assertions. A bounded compatibility migration handles only the two
observed legacy low/negligible value strings; it does not accept arbitrary nonnumeric
values as missing numbers. Invented numbers, definitions and quotations remain errors
with finite recovery codes. An explicit qualitative assertion cannot also contain a
numeric value, even when that number occurs in the source. A numeric level missing
its value is retained as incomplete (`incomplete_numeric_level`) and cannot support
a numerical verdict; an explicit sourced qualitative field instead preserves its
qualitative family. Optional `assertion_quotation` selects an exact clause
within the already validated parent span; IDs, parent quotation, speaker and citation
remain unchanged. A subspan cannot erase qualified parent revenue context or borrow
another clause's qualifiers/definition. Causes and commitments remain unverified.

Compatibility checks precede truth comparison: wrong company, subject, metric,
period, accounting/ratio definition, unit or comparator cannot produce CONTRADICTED.
Unknown alignment remains INCONCLUSIVE; known incompatibility is UNMATCHED.
Returned-unit/shipped-unit rates cannot contradict monetary refund/revenue claims.
Python converts compatible monetary units and compares at the copied decimal
precision. Signed decreases preserve their quoted magnitude and direction;
percentage-point changes are distinct from relative percentage changes. Qualitative
low/high/stable has no invented numerical threshold. Causal and forecast claims
are not treated as measured current-period facts.

Extraction is capped at three relevant candidates per call (12 total), prioritizing
revenue, quality/returns and explicit setbacks. **It is not exhaustive.** Diagnostics
record per-call counts and cap hits. The verifier sees complete original transcripts,
but can acknowledge only validated extracted quotations; relevant unextracted
wording leaves disclosure inconclusive rather than supporting an omission claim.

## Scope and unresolved policy

Event candidates are prepared from adverse fact changes before matching; they are
not automatically material. Materiality needs a relevant source-backed qualitative
basis rather than an arbitrary percentage cutoff. `NOT_FOUND` describes a search
within the named supplied quarter call, not proof of concealment. Coverage is
explicitly limited to the four supplied earnings calls and measured financial/returns
facts; missing calls, unknown dates and undefined measurements remain gaps.

This scope currently has no independent management-knowledge basis for an absent
acknowledgement. Knowledge is established only by a dated same-event admission,
which also prevents NOT_FOUND. Therefore omission-to-EVASIVE is a policy/evidence
limitation, not a supported FAIL path. The decision records
`omission_knowledge_policy_unresolved`; it does not assume that database availability
proves management knowledge. An aligned numerical misstatement remains independent
of candid disclosure about a different event, with `misstatement_policy_unresolved`
until its Point 14 aggregation policy is agreed. Critical unknowns block PASS and
remain INSUFFICIENT_EVIDENCE. No company-specific rules or public labels enter runtime.

## Execution and evaluation

Two normal model calls are retained; no extra judge or adjudication loop is used.
Each stage permits one bounded schema/grounding repair. The existing six-call hard
cap, 40-second attempt timeout and 180-second company deadline remain unchanged.
Runtime uses LangChain `deepseek-v4-flash`, thinking explicitly disabled,
`temperature=0`, `max_tokens=3500`, and no SDK transport retries. Point 14 uses zero
interviews. Cancellation propagates; errors retain stage/type diagnostics.

Use one injected `Tracing` lifecycle for the batch; it nests source tools, model
calls, proposal validation and final diagnostics. If the specialist created its own
lifecycle, close it once after all companies finish. Optional tracing failures do
not alter results. Printed IDs alone do not prove remote ingestion.

```bash
python -m unittest discover -s test -v
python -m evaluation.point14 --financial-only --output .venv/evaluation/point14-financial.json
python -m evaluation.point14 --live --env-file ../../.env --concurrency 2 --output .venv/evaluation/point14-live.json
```

The last command explicitly permits paid calls; a full rerun is not authorized by
these instructions. In a fresh clone omit `--env-file ../../.env` to use `.env`.
Labels are loaded only after decisions. Evaluation reports semantic abstentions,
operational failures, grounded correctness and public fallback credit separately;
legacy `failures` means all unresolved verdicts, including abstentions.

Offline Option C validation after normalization repair: **87 tests, 86 passed and
one live smoke skipped**. Both archived first-gate responses are immutable hashed
fixtures; replay now retains all 12 claims with unchanged IDs/quotes/spans on one
mock invocation, preserving qualitative values as nonnumeric and distinguishing
known standard revenue definitions from unknown definitions. This offline recovery
does not establish a new live score.
Source-only retrospective fixtures cover Cobalt's incompatible profit/returns
comparison, Kestrel's direct 378/7,432 ratio, Dunmore's independent misstatement and
admission, Ashgrove uncertainty, and Aurel's unsupported omission inference. Original
source text, SQL responses and trace IDs are retained; expected labels are omitted.
All five returns fixtures exactly match the recorded feasibility-review tool outputs.

A local `cl100k_base` approximation found 12-claim sample outputs of 1,383–1,402
tokens and 21–26-event responses of 1,199–1,425 tokens. Full verification inputs
were approximately 16,105–16,455 tokens, extraction inputs 1,599–1,626. These are
examples, not DeepSeek tokenizer measurements or worst-case guarantees. The
3,500-token output allowance is unchanged.

The first evidence-focused live gate at `7950f3c` **failed** claim extraction after
two calls: 3,908 input + 3,046 output = 6,954 tokens, 10.9187 seconds, zero supported
finals, one operational failure, zero semantic abstentions and zero fallback credit.
Both responses were valid 12-claim JSON, but four revenue definitions lacked quoted
definition wording and three qualitative claims put "negligible"/"low" in the numeric
value field. Verification was never reached. The remaining four companies were
cancelled; no 20-company Option C evaluation ran. The recommendation is **ADJUST
the normalizer and finite recovery feedback**, without adding calls or weakening
source validation. No live semantic improvement has been demonstrated. See the
[gate diagnosis](../evaluation/point14-option-c-gate.md); application code remains frozen.

## Historical baselines and integration boundary

These measurements precede Option C and do not establish its accuracy:

| Version | Supported finals | Grounded correct | Balanced accuracy | Calls / tokens / seconds |
| --- | ---: | ---: | ---: | --- |
| Original thinking runtime | 0/20 | 0/20 | 0% | 56 / 515,187 / 541.50 |
| Non-thinking repaired baseline (`b10326b`) | 14/20 | 6/20 | 45.24% | 54 / 599,547 / 86.98 |

The repaired baseline had PASS recall 1/14 (7.14%), FAIL recall 5/6 (83.33%), six
validation failures, three adjudications and eleven repairs. Public FAIL fallback
credit would increase accuracy to 7/20 and balanced accuracy to 53.57%; it does not
improve grounded correctness. All 54 generations were JSON, while 17 proposals
failed semantic-consistency checks. Repeated Ashgrove execution changed an
adjudicated FAIL to an unresolved error, demonstrating workflow variability.
Remote retrieval confirmed 20 traces / 317 closed observations with complete parents:
[supported PASS](https://cloud.langfuse.com/project/cmvvyy2cf010pad0k901a5phs/traces/f511864df6b0d71ce17f91f798517449),
[incorrect FAIL](https://cloud.langfuse.com/project/cmvvyy2cf010pad0k901a5phs/traces/4188339ba382c9fa411ac4a0325885be),
[validation failure](https://cloud.langfuse.com/project/cmvvyy2cf010pad0k901a5phs/traces/2e0073c85ed7d6c6b2e8cd5bab3945a4).

Point 14 owns `TransparencyResult`; it does not define a competing shared contract.
A future adapter must retain company, point 14, optional verdict, reason, source
provenance, matching/disclosure findings and diagnostics. Preserve None until the
explicit public fallback boundary. `hw3.py`, other specialists, dependencies and the
shared observability foundation remain unchanged. Cash flow and outside-call
communications remain outside this evidence slice. Final orchestration and any
unresolved policy decision require separate agreement.
