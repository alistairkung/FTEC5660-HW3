# Fisher Point 14 — Management transparency

PASS means management's communication is factually consistent with the financial
record and meaningfully addresses material difficulties. Falling revenue can PASS;
optimistic language alone does not establish dishonesty. Only `TRANSPARENT` maps
to PASS. `EVASIVE` maps to FAIL. `UNCERTAIN` receives one final adjudication using
exactly the same evidence, then must resolve or become an explicit operational error.

## Components and evidence

`fisher_agent.point14` is independent of Points 4/5 and does not modify `hw3.py`.

| Component | Responsibility |
| --- | --- |
| `FinancialEvidenceExtractor` | One aggregated supplied SQL call; quarterly revenue, expense components, operating costs/profit/margin, QoQ and YoY comparisons |
| `ManagementClaimExtractor` | One model extraction over the four supplied earnings-call documents; exact quotation/source/quarter validation |
| `TransparencyVerifier` | Materiality and disclosure interpretation, reference validation, and optional single adjudication |
| `TransparencySpecialist` | Company-local sequencing, deadlines, diagnostics, optional nested tracing and canonical final explanation |

The financial query aggregates orders and costs separately before joining them.
It retrieves ten quarters (2024Q1–2026Q2) for the four call periods and comparisons;
only ten SQL rows are returned. There are 84 derived metrics: seven metrics,
three views (level, QoQ, YoY), four quarters. Source amounts remain USD thousands;
margins use percent. Absolute margin changes are percentage points. Relative
change uses `difference / abs(previous) * 100`, including for negative profit.
A zero comparison denominator retains the absolute change and an explicit status.
Non-positive revenue, missing periods/months, duplicate quarters/monthly cost rows, malformed or
non-finite numbers, nonnumeric source fields, SQL failures and truncation are errors.
Every metric links to the original query and tool response. No materiality threshold
or intent judgement is made by this component.

Claims retain the exact retrieved management statement as the quotation (no separate
unchecked paraphrase). Only whitespace differences are normalized for matching;
canonical quotations are rebuilt from the transcript. Misattributed documents or
quarters, unsupported/blank quotes, headings, analyst turns, cross-speaker spans and
extra model fields are rejected. Each quote must remain within one management turn;
bare executive names are recognized by a matching titled introduction anywhere in that transcript.
At least one claim per call is required; an empty extraction is not evidence of silence.
A model can still misinterpret a speaker or the time reference within a sentence;
source grounding is not a guarantee of semantic correctness.

The verifier sees all computed metrics, validated claims and complete original
transcripts, allowing omissions to be assessed against the whole call. It returns
only supplied evidence IDs, materiality flags, classifications and finite explanation
codes. It cannot add numerical facts or free-text business events. Python rebuilds
the final explanation from original numbers and quotes; the complete comparison
list remains on the result. `ACKNOWLEDGED` needs a setback/explanation claim;
`CONTRADICTED` needs a same-quarter claim. `UNADDRESSED` references the complete
quarter transcript. `NOT_APPLICABLE` cannot assert materiality. `UNVERIFIABLE`
is distinct from contradiction. An EVASIVE assessment requires at least one material
contradiction/omission; TRANSPARENT cannot retain that finding or material UNVERIFIABLE
evidence, including after final adjudication. Every quarter
must be covered. Materiality and semantic factual consistency remain model judgements.
No labels or company-name rules enter this process.

The verifier payload adds Decimal-computed USD-million equivalents while preserving
the original thousand-denominated records and provenance. It includes an explicitly
named one-decimal displayed level, matching the supplied calls' monetary precision;
this is a presentation value, not a factual-conflict tolerance. Selecting the relevant
claim and judging materiality remain semantic tasks; no general numeric parser is added.

## Execution, failures and integration dependency

Typical use (after loading the environment):

```python
from fisher_agent.point14.runtime import build_transparency_specialist
from observability import Tracing

with Tracing() as tracing:
    specialist = build_transparency_specialist(tracing)
    result = await specialist.evaluate(company_id, supplied_tools)
    point_only_output = result.public_result()
```

Use the application's single `Tracing` lifecycle, closing after all company tasks.
If constructed without an injected or current lifecycle, call `specialist.close()`
once after the batch. Missing credentials/SDK or SDK export errors do not change
results. Model and supplied tool invocations receive native LangChain callbacks;
all manual stages nest under Point 14. Quote validation nests under extraction.
Model usage/latency, recovery counts, rejection counts, classifications, adjudication
and final verdict are recorded. A trace ID does not prove remote ingestion.

The required model is `hw3.MODEL_NAME` (`deepseek-v4-flash`), through LangChain,
with thinking explicitly disabled in the serialized request.
No SDK transport retries; each logical model stage gets at most one malformed-output
or grounding recovery. Semantic adjudication is a separate single stage. Normally
two calls; at most six, each limited to 40 seconds, with a 180-second company deadline.
The evaluator uses four concurrent companies (about 15 minutes at the company
bounds), with a 25-minute batch deadline that preserves queued-company error entries; the eventual three-point orchestrator must enforce its global 30-minute
budget and share tool instances. Point 14 spends **zero interviews**.

Exceptional results have `verdict=None`, stage/type diagnostics and an explicit
`api_error`, `retrieval_error`, `invalid_output` or `deadline` status. Cancellation
propagates. `public_result()` deliberately returns a clearly labelled FAIL fallback
so the parent can preserve company coverage; this is never an evidence-backed FAIL.
The development scorer counts unresolved errors wrong, even if fallback FAIL would
coincidentally match a label.

**Shared-contract dependency:** no `PointResult` exists on the chosen committed
foundation (`db218bc`). Point 4's `SalesResult` and Point 5's
`MarginResult` are different specialist records. This change therefore adds only
an owned `TransparencyResult`, not a replacement shared contract or a conflicting
`fisher_agent/contracts.py`. Integration must adapt these fields to the eventual
shared contract: `point_id=14`, company, final verdict, reason, financial/transcript/
claim provenance and diagnostics. Preserve `verdict=None` and error status until
the public boundary. That adapter is intentionally deferred to the integration task.
The namespace package will coexist with Point 4's parent `fisher_agent/__init__.py`.

## Commands and measured results

From this worktree with the existing virtual environment activated:

```bash
python -m unittest discover -s test -v
python -m evaluation.point14 --financial-only --output .venv/evaluation/point14-financial-results.json
python -m evaluation.point14 --live --env-file ../../.env --concurrency 2 --output .venv/evaluation/point14-results.json
```

The live command explicitly allows paid model calls. In a fresh clone use the
normal `.env` (omit `--env-file ../../.env`). Ground truth is loaded only by
`evaluation.point14`, after all specialist decisions. Its report includes accuracy,
PASS/FAIL recall, balanced accuracy, disagreements, failures by stage, unsupported
quotation rejections, adjudications, calls, tokens, latency, trace IDs and full evidence.
The five disagreement-attribution fields are deliberately unreviewed until a human
compares financial extraction, missed statements, misattributed evidence, verification
and judgement. They are not automatically guessed from the expected label.

**Readiness: NOT READY for integration.** On 31 October 2026 the orchestrator ran
the repaired implementation against all 20 public companies, with concurrency two:

| Measure | Result |
| --- | ---: |
| Evidence-backed correct / total | 6/20 (30.00%) |
| Balanced accuracy, errors counted wrong | 45.24% |
| PASS recall / FAIL recall | 7.14% (1/14) / 83.33% (5/6) |
| Valid final assessments / operational failures | 14 / 6 |
| Runtime / model calls | 86.98 seconds / 54 |
| Input / output / total tokens | 561,290 / 38,257 / 599,547 |
| Adjudications / bounded repairs | 3 / 11 |
| Financial / claim-extraction / quotation failures | 0 / 0 / 0 |

All 54 generations returned valid JSON. Offline replay rejected 17 semantically
inconsistent proposals: 13 acknowledgements without the required claim kind, two
TRANSPARENT proposals retaining material unresolved evidence, and two EVASIVE
proposals without supporting material findings. Six companies exhausted recovery
(four during verification, two during final adjudication). Eight other companies
received valid but incorrect FAIL verdicts. Only `emberly_systems` received PASS.
Mapping all six operational errors to public FAIL would give 7/20 and 53.57%
balanced accuracy; its extra matching fallback is not evidence-backed correctness.

Before repair, the live baseline spent 515,187 tokens and 541.50 seconds on 56
calls, producing zero supported classifications because thinking exhausted the
3,500-token output allowance. Disabling thinking restored structured execution;
the current baseline exposes semantic and validation-consistency failures instead.
Prompts, domain rules, output schemas and execution bounds were preserved.

Remote Langfuse retrieval confirmed 20 traces and 317 observations, all closed and
with complete parent links. Representative workflows:
[supported PASS](https://cloud.langfuse.com/project/cmvvyy2cf010pad0k901a5phs/traces/f511864df6b0d71ce17f91f798517449),
[incorrect FAIL](https://cloud.langfuse.com/project/cmvvyy2cf010pad0k901a5phs/traces/4188339ba382c9fa411ac4a0325885be),
[rejected final adjudication](https://cloud.langfuse.com/project/cmvvyy2cf010pad0k901a5phs/traces/2e0073c85ed7d6c6b2e8cd5bab3945a4).

The evaluated source is base commit `7da41532d677196b691ebbfbd384ade83d28ea61`
plus the local repair patch; the review manifest records runtime hashes and full
configuration. The ignored review artifacts are `point14-full.json`,
`point14-full-config.json` and retrieved traces under the orchestrator's
`.review/repairs/` directory; generated evaluation outputs are not committed.

Financial extraction succeeded for 20/20 companies with 84 metrics each. The
snapshot excludes cash flow and returns, so setbacks limited to those indicators
may be missed. Unit equivalents remove scaling work but do not establish semantic
claim association or a universal materiality threshold. Further changes need an
evidence-backed semantic review; no public-company-specific rules were introduced.
Repeated execution of the same repaired configuration changed Ashgrove from an
adjudicated FAIL to an unresolved error, demonstrating workflow variability.

`python -m unittest discover -s test -v` ran **51 tests: 50 passed, one opt-in
live smoke skipped**. Regression tests cover serialized thinking configuration,
unresolved adjudication, speaker/heading provenance and invalid duplicate costs.
Protected `hw3.py`, requirements, public data and observability remain unchanged.
The standalone optional observability smoke retains its foundation configuration;
the Point 4 repair supplies its non-thinking configuration when those PRs are
eventually reconciled. This Point 14 specialist uses its own repaired runtime.
Shared-result adaptation and full three-point orchestration remain separate work.
