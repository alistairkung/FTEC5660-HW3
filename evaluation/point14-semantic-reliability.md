# Point 14 semantic-reliability gate — 1 November 2026

**Readiness: NOT READY. Stop further live expansion.** Evaluated runtime:
`21d8ac161e623a59278d3b11cba1711898b46f21`. This slice changes verification
validation and evidence reporting, not aggregation thresholds, knowledge assumptions,
model stages, token limits or execution budgets.

## Repairs and offline evidence

The saved Cobalt verification responses were replayed without a new model call.
The first response proposed two unprepared return-event IDs. The second mixed a
valid returns admission (`claim:2025Q3:2`) with an adjacent commitment/wrong-metric
claim (`claim:2025Q3:3`). Previously the latter invalidated the independent admission.

The per-company Pydantic schema now enumerates only prepared event IDs, and the
payload/instructions distinguish them from fact IDs and period patterns. Unknown,
duplicate and missing event references have separate finite rejection codes. The
same single bounded recovery remains available. A valid admission survives mixed
references; rejected known IDs and `non_acknowledging_reference` are retained.
Fabricated claim IDs still reject the proposal. No wrong-period, wrong-metric,
causal-only or commitment reference becomes an acknowledgement.

A corroborated numeric/directional proposition does not verify its causal context.
Existing qualifiers remain explicit `unverified_qualifiers`; summaries label
proposition-only support. Original quotations, claims and speaker provenance remain
unchanged. The operational policy in [the specialist documentation](../docs/point14.md#scope-and-operational-policy)
separates numerical misrepresentation from selective nondisclosure. Fisher does not
require proven fraud intent. This calls-only implementation still cannot establish
knowledge of an omitted event independently of acknowledgement; no database-to-knowledge
assumption, materiality cutoff or forced FAIL was introduced.

TDD reproduced the generic event error, discarded valid admission and absent causal
context boundary before repair. Eight new offline tests now pass, including both
immutable archived responses, exact allowed-ID recovery, missing/duplicate/fabricated
references, wrong periods/metrics, causal references and an empty-event boundary.
The fixture contains sourced financial/claim records and exact response strings,
without expected company verdicts or request headers.

`python -m unittest discover -s test -v`: **95 tests, 94 passed and one opt-in live
smoke skipped**. All five existing source-only retrospective cases pass. Independent
Standards/Spec reviews, protected-file audit and `git diff --check` passed. These
checks are offline; they do not establish live semantic accuracy.

## Four-company live gate

The orchestrator ran exactly four companies serially against the frozen runtime;
no Cobalt rerun or full 20-company evaluation occurred. All four financial/returns
extractions succeeded, retaining ten quarters of returns per company. All claim
extractions succeeded; no quotation rejections occurred.

| Company | Final state | Grounded verdict | Calls / repairs | Input / output tokens | Wall seconds |
| --- | --- | --- | ---: | ---: | ---: |
| Ashgrove | Operational `invalid_output` | None | 3 / 1 | 45,985 / 5,225 | 17.679 |
| Aurel | Semantic `INSUFFICIENT_EVIDENCE` | None | 2 / 0 | 23,618 / 3,459 | 11.919 |
| Dunmore | Semantic `INSUFFICIENT_EVIDENCE` | None | 3 / 1 | 45,521 / 5,372 | 17.100 |
| Kestrel | Semantic `INSUFFICIENT_EVIDENCE` | None | 3 / 1 | 26,082 / 5,513 | 20.921 |

Total: **11 calls, 141,206 input + 19,569 output = 160,775 tokens; 68.043 seconds**.
Three repairs, no adjudications. Grounded public accuracy and balanced accuracy
are 0%; PASS recall 0/3 and FAIL recall 0/1. All four predictions were unresolved,
so these are strict abstention/error-inclusive scores, not accuracy among supported
binary classifications. The public FAIL adapter coincidentally matches Kestrel's
label: **one fallback credit, zero grounded correct classifications**.

Ashgrove failed verification after `incomplete_claim_matching` on both bounded
attempts. Both omitted the same four extracted claims (`claim:2025Q3:2`,
`claim:2025Q4:2`, `claim:2026Q1:3`, `claim:2026Q2:2`): three quality claims and a replacement commitment.
Its 26 prepared events were covered, but no complete claim analysis was accepted.
Dunmore repaired that code successfully; Kestrel repaired an `unsupported_qualifier`
during extraction. None of the six verification attempts invented an event ID,
supporting the prepared-ID constraint in this gate. Aurel needed no repair. These
observations do not establish
that the event-ID constraint will always succeed.

Dunmore preserves an independently corroborated 2026Q1 revenue contradiction and
an ACKNOWLEDGED 2025Q3 returns admission. Its materiality and separate misstatement
communication significance remain unresolved. Kestrel's direct 2026Q1 returns are
378 / 7,432 = 5.0861%; the measurement is available, but does not independently
settle qualitative criteria, materiality or management knowledge. Aurel's scoped
NOT_FOUND and rejected non-admission references do not establish concealment.
Its four revenue claims are SUPPORTED, four qualitative returns claims INCONCLUSIVE
and four demand claims UNMATCHED. Measured return rates around 2.30–2.42% do not
contradict "low" or "negligible" without a justified criterion. All 23 prepared
adverse candidates have unknown knowledge/materiality (15 NOT_FOUND, eight
INCONCLUSIVE).

Ashgrove retains a genuine 2026Q1 returns admission, corroborating a rate rise
from about 2.07% to 5.59%; its claimed faulty-batch cause remains unverified. Both
verification attempts cover only eight of twelve claims, so no final semantic
decision is accepted. This is a completeness failure, not missing data, API failure
or token exhaustion.

The three valid decisions all retain unresolved matching, materiality and knowledge;
two also retain unresolved disclosure. This is a systematic evidence/policy gap,
not a reason to infer dishonest intent or turn abstentions into investment FAILs.
These missing impact/knowledge premises are genuine gaps in the selected evidence;
in addition, the chosen aggregation profile vetoes PASS for every unmatched demand
claim and unresolved candidate, including small measured movements. Fisher does
not require this universal veto. Its conservatism and the corpus limits must not
be confused with proof that the companies lack transparency.

Three-of-four abstentions trigger the agreed stop condition. **Do not run all 20,
merge Point 14 or start another automatic repair/inference cycle.** Further
classifier investment under this corpus and strict policy is not justified
by the measured gate. This does not disprove Fisher Point 14 generally. The existing
source-grounded acknowledgement/contradiction findings may remain useful as
diagnostics, without treating them as grading verdicts. A broader policy/evidence
decision requires a separate scope choice; the current specialist is not ready for
grading integration.

## Retrieved traces and remaining findings

The orchestrator retrieved all four traces remotely: **64 observations** (29 spans,
11 generations, 24 tools), all closed, no missing parent links. All 11 generations
contained valid JSON; token totals reconcile exactly to the table. Maximum output
was 2,037 tokens, below the unchanged 3,500 allowance: the verification failure was
not output exhaustion. All 47 accepted source quotations/spans/company identifiers
were independently verified (12 / 12 / 11 / 12 claims).

- [Ashgrove: operational failure](https://cloud.langfuse.com/project/cmvvyy2cf010pad0k901a5phs/traces/03eb3b37c0cd5a493782edabd6b37dc2):
  generations `6072478ff19d145f` and `9e0b0657290e2295` repeat incomplete coverage.
- [Aurel: scoped abstention](https://cloud.langfuse.com/project/cmvvyy2cf010pad0k901a5phs/traces/a094cafb275202a75535ee78b7b9b2de).
- [Dunmore: mixed independent findings](https://cloud.langfuse.com/project/cmvvyy2cf010pad0k901a5phs/traces/dc143bfa64422c8814c3b2908652d087):
  measured 248.068 million versus quoted 265.7 million remains CONTRADICTED, alongside
  the valid returns admission. Neither cancels the other.
- [Kestrel: direct returns, unresolved disclosure](https://cloud.langfuse.com/project/cmvvyy2cf010pad0k901a5phs/traces/fbcc7485e460505e1c4e2e21e34c6f74).

Only the three accepted decisions contribute semantic counts: 35 matches comprise
11 SUPPORTED, 12 INCONCLUSIVE, 11 UNMATCHED and one CONTRADICTED. Their 72 disclosures
comprise 59 NOT_FOUND, 12 INCONCLUSIVE and one ACKNOWLEDGED. NOT_FOUND is not a
validated omission; there were zero proven omission FAILs. Ashgrove has no accepted
semantic decision and is excluded from these counts.

**High:** systematic unresolved materiality/knowledge/matching prevents supported
binary classifications; complete claim matching also fails despite bounded repair.
**Medium:** non-exhaustive extraction and uncertain qualitative criteria limit
coverage; causal context is sourced but not independently verified. Kestrel's
rejected extraction used qualifier `order books` against source `Order books are
in line with our plan.` in all four calls. This was a case-only metadata mismatch
under the exact contract, not a hallucinated quotation or demonstrated semantic
falsehood. Its repair exposes validation brittleness; no further fix was made
after the stop condition. These are reported limitations, not authorizations to weaken gates or add another judge.

The historical repaired baseline used 14 calls and 174,588 tokens for these same
four names, versus 11 and 160,775 now (7.9% fewer total tokens). New output-token
consumption roughly doubled. Prior per-company durations sum to 43.64 seconds;
that is not a controlled wall-time comparison with this serial run. This gate does
not demonstrate improved binary accuracy or stable results across repeated runs.

Ignored reproducibility records: `.review/semantic-four-gate.json`,
`.review/semantic-four-launch.json`, `.review/semantic-four-audit.json` and the
retrieved trace artifacts. No generated live artifacts are committed.
