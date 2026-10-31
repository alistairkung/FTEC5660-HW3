# Point 4 evaluation status — 31 October 2026

The real-model public evaluation has **not run**. Preflight found configured
DeepSeek and Langfuse credentials, but this execution environment could not resolve
either `api.deepseek.com` or the configured `cloud.langfuse.com`.
Both returned `socket.gaierror: [Errno 8] nodename nor servname provided, or not known`.
No paid model call or public company interview was made by this implementation task.
No successful trace ingestion or retrieval is claimed. Shell Git access also failed
DNS resolution; GitHub connector access remained available.

| Requested live measurement | Result |
| --- | --- |
| Correct classifications out of 20 | Not measured |
| PASS recall / FAIL recall / balanced accuracy | Not measured |
| Misclassified companies | Unknown |
| Interviews per company / fallback activations | Not measured |
| Final adjudication frequency | Not measured |
| Model calls / token usage | No live model calls; usage unavailable |
| Langfuse ingestion and retrieval | Not verified |

Offline verification: `python -m unittest discover -s test -v` ran 42 tests:
41 passed and one optional paid smoke test was skipped. Tests use fake LangChain
models/tools and a mocked Langfuse backend; they are not an accuracy measurement.
They cover all workflow branches, quote/schema validation, bounded recovery,
company isolation, deadlines, cancellation, scoring and evaluation serialization.

Once shell networking is available, run:

```bash
python -m evaluation.point4 --live --data-folder public_test --output evaluation/point4-baseline.json
```

Keep that baseline file before making any prompt changes. Compare its metrics and
inspect the saved interviews, assessments, diagnostics and trace IDs. Retrieve the
traces from Langfuse to verify remote delivery, nesting, metadata and generation
usage. No prompt tuning against public companies has been performed.
