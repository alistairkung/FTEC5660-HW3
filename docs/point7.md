# Point 7: labour and personnel relations

Independent backup specialist based on PR #6 (`integration/points4-5`,
`bfa7a06`). It does not change homework wiring or the final three points.
The assignment PDF §3.3 identifies current/former employees as knowledgeable
about working conditions. Fisher, Part One Chapter 3, Point 7 (printed pp. 65–67)
supports considering fair treatment, retention, grievances and management's
attitude to staff together; absence of strikes alone is insufficient.

PASS requires concrete evidence of strong employee relations. FAIL requires
meaningful personnel-relations problems. Missing information is uncertainty;
retrieval, API and validation failures are operational errors.

```text
current_employee / working_conditions → structured LabourAssessment → exact quote/source check
  decisive → PointResult(7, PASS/FAIL, complete)
  UNCERTAIN → former_employee / working_conditions → reassess both → validate
    decisive → complete; still uncertain → insufficient_evidence, verdict=None
  operational failure → error, verdict=None
```

`build_labour_specialist(tracing=None)` constructs the required LangChain
`deepseek-v4-flash` model with explicit disabled thinking, temperature 0,
600 output tokens, a 20s timeout and zero SDK retries. `assess(company_id, tools)`
returns `LabourRun`; its `point_result` is the existing shared `PointResult`.
Original answers, validated assessments, usage and diagnostics remain in the run.
Only the supplied `interview` tool is invoked. Source IDs are role/topic pairs;
evidence and shared provenance also carry the company ID.

Two interviews maximum, no retrieval retries, at most one repair of malformed
model output per assessment (four model calls maximum). Only validated UNCERTAIN
can trigger the second interview. No adjudicator is needed. Tool timeout: 5s;
company deadline: 90s; batch deadline: 20 minutes; company concurrency: 2.
Cancellation propagates. Failures preserve diagnostics and available counters.
Optional tracing reuses the existing lifecycle/native callbacks and works without
Langfuse credentials or its SDK; no dependencies were added.

Future integration can consume `run.point_result` directly alongside Points 4/5.
The specialist never converts unresolved evidence to an investment FAIL. A later
homework adapter must explicitly preserve or apply the agreed public fallback
policy, since the lecturer accepts only PASS/FAIL. This PR leaves that adapter,
`CHOSEN_POINTS` and Points 4, 5 and 14 unchanged.

Offline checks and independent paid evaluation:

```bash
python -m unittest discover -s test -v
python -m evaluation.point7 --live --companies bramble_labs cobalt_holdings ashgrove_labs aurel_systems --output evaluation/point7-gate.json
python -m evaluation.point7 --live --output evaluation/point7-public.json
```

The gate names were selected in development to cover two examples of each class;
they are not runtime rules. The evaluation runner loads labels after inference,
counts errors/uncertainty as incorrect for their true class, records source hashes
and reconciles interview attempts with lecturer counters. Generated reports are
ignored. See [measured results](../evaluation/point7-results.md).
