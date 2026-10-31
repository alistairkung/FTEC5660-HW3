# Point 4 evaluation status — 31 October 2026

Independent live validation of the configuration repair completed successfully.
The required `deepseek-v4-flash` model now explicitly disables thinking through
`extra_body={'thinking': {'type': 'disabled'}}`, allowing the existing named
`SalesAssessment` tool choice. Prompts, schema, interview routing and budgets are
unchanged. Before this repair, all 20 requests were rejected with HTTP 400 because
thinking mode does not support the forced tool choice.

One company passed the initial live gate, followed by three additional positive/
negative examples. The table reports the subsequent full 20-company baseline only:

| Measurement | Result |
| --- | --- |
| Grounded correct classifications | 20/20 (100%) |
| PASS recall / FAIL recall / balanced accuracy | 100% / 100% / 100% |
| Misclassified companies | None |
| Interviews per company | One customer interview on `sales_team` |
| Conditional competitor interviews / final adjudications | 0 / 0 |
| Invalid outputs / parsing repairs / operational fallbacks | 0 / 0 / 0 |
| Model calls | 20 |
| Input / output / total tokens | 13,294 / 2,536 / 15,830 |
| Wall runtime, concurrency two | 13.77685 seconds |
| Langfuse ingestion and retrieval | Independently confirmed; observations closed |

All correct verdicts were evidence-backed; no score came from fallback FAILs.
Offline verification: `python -m unittest discover -s test -v` ran 44 tests:
43 passed and one optional paid smoke test was skipped. The new regression exercises
real LangChain/SDK serialization through an offline HTTP transport, checking disabled
thinking and the named tool choice together. Existing tests cover workflow branches,
quote/schema validation, bounded recovery, company isolation, deadlines, cancellation
and evaluation serialization. Protected lecturer code and public data are unchanged.

Reproduce from the repository root with dependencies and `.env` configured:

```bash
python -m evaluation.point4 --live --data-folder public_test --output .venv/point4-baseline.json
```

Keep generated results local and ignored. The output retains original interviews,
validated assessments, diagnostics, usage and trace IDs. Ground truth is read only
after predictions. This is one full baseline, preceded by small execution gates;
it does not establish private-company accuracy or run-to-run variance. No rubric,
threshold or prompt tuning against the public results was performed.
