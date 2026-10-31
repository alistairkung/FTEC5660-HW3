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
Non-positive revenue, missing periods/months, duplicate quarters, malformed or
non-finite numbers, nonnumeric source fields, SQL failures and truncation are errors.
Every metric links to the original query and tool response. No materiality threshold
or intent judgement is made by this component.

Claims retain the exact retrieved management statement as the quotation (no separate
unchecked paraphrase). Only whitespace differences are normalized for matching;
canonical quotations are rebuilt from the transcript. Misattributed documents or
quarters, unsupported quotes, analyst-turn quotes and extra model fields are rejected.
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
contradiction/omission; TRANSPARENT cannot contradict that finding. Every quarter
must be covered. Materiality and semantic factual consistency remain model judgements.
No labels or company-name rules enter this process.

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

The required model is `hw3.MODEL_NAME` (`deepseek-v4-flash`), through LangChain.
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
python -m evaluation.point14 --financial-only --output evaluation/point14-financial-results.json
python -m evaluation.point14 --live --env-file ../../.env --output evaluation/point14-results.json
```

The live command explicitly allows paid model calls. In a fresh clone use the
normal `.env` (omit `--env-file ../../.env`). Ground truth is loaded only by
`evaluation.point14`, after all specialist decisions. Its report includes accuracy,
PASS/FAIL recall, balanced accuracy, disagreements, failures by stage, unsupported
quotation rejections, adjudications, calls, tokens, latency, trace IDs and full evidence.
The five disagreement-attribution fields are deliberately unreviewed until a human
compares financial extraction, missed statements, misattributed evidence, verification
and judgement. They are not automatically guessed from the expected label.

The financial-only run completed **20/20 companies**, 84 metrics each, without SQL
errors, model calls or labels. See `evaluation/point14-financial-results.json`.
This is not a transparency verdict score. DeepSeek, Langfuse and GitHub hostnames
failed local DNS resolution in this sandbox. No paid evaluation was attempted;
Point 14 accuracy, model latency/token consumption and remote Langfuse ingestion
remain **unverified**. Offline tests validate control flow and evidence contracts,
not the model's semantic accuracy. Financial evidence does not currently include
cash flow or returns; setbacks limited to those indicators may be missed.

The branch was created from the committed optional-observability foundation while
main was still the starter. Foundation PR #1 merged during this work. The Point 14
PR now has exactly 16 additive files against main and GitHub reports a clean merge.
There are no edits to shared package infrastructure, README, `hw3.py`, Points 4/5,
requirements or observability. The integration task must wire the shared result
adapter and homework runner, evaluate the complete submission and finish the report.

Validation on this branch: `python -m unittest discover -s test -v` ran 42 tests:
**41 passed, one opt-in live smoke skipped**, including 24 Point 14 tests.
Compilation passed. Diff review confirmed the entire `hw3.py` and existing shared
foundation files remain unchanged.
