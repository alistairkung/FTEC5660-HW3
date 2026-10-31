# Point 5 strategy comparison

Evaluated 31 October 2026 against all 20 public companies (14 true PASS, 6 true FAIL).
Both rules were specified before execution. No rule changes followed label inspection.

| Strategy | Balanced accuracy | PASS recall | FAIL recall | Completed | SQL errors | SQL calls |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Industry | 100.00% | 100.00% (14/14) | 100.00% (6/6) | 20/20 | 0 | 40 |
| Historical | 52.38% | 71.43% (10/14) | 33.33% (2/6) | 20/20 | 0 | 20 |

Each company uses two SQL calls for Industry and one for Historical, with at most three
annual rows and one median row per result. No interviews, model calls or paid requests.
The lecturer tool factory and SQL tool are unchanged. This is a Point 5 development
comparison, not a run or score of the unfinished three-point grading agent.

## Disagreements

Industry matches every label. All eight disagreements are Historical versus both
Industry and the label. Margins below are percentages, rounded only for display.

| Company | Label / Industry | Historical | 2023 | 2024 | 2025 | Industry median |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| ashgrove_labs | PASS | FAIL | 16.07% | 14.50% | 13.36% | 9.40% |
| cobalt_holdings | PASS | FAIL | 15.97% | 15.12% | 14.22% | 10.30% |
| emberly_systems | PASS | FAIL | 18.09% | 16.41% | 15.38% | 12.50% |
| everline_dynamics | FAIL | PASS | 5.17% | 5.38% | 6.30% | 10.30% |
| falcrest_technologies | FAIL | PASS | 4.57% | 5.73% | 6.26% | 9.40% |
| granite_group | PASS | FAIL | 21.23% | 20.10% | 19.67% | 16.80% |
| halcyon_works | FAIL | PASS | 8.38% | 9.43% | 9.52% | 11.40% |
| ironbark_technologies | FAIL | PASS | 3.56% | 5.05% | 5.80% | 9.40% |

Four false FAILs (Ashgrove, Cobalt, Emberly, Granite) have declining margins that still
exceed their industry medians. Four false PASSes (Everline, Falcrest, Halcyon, Ironbark)
have positive, improving margins that remain below their industry medians.

## Recommendation for review

Recommend **IndustryMarginStrategy** for eventual Point 5 integration. It evaluates
whether the current margin is worthwhile relative to comparable businesses and aligns
with every public label. Historical measures profitability and direction: it can accept
a persistently weak margin while rejecting a strong but declining margin. That direction
is useful supplementary evidence, but is less direct for Point 5. This recommendation
rests on assessment meaning and measured outcomes, despite Industry needing twice the
SQL calls. Neither implementation has been selected in the grading runner.

## Evidence, reproduction and limitations

- Run `python -m evaluation.compare_point5`. The default output is
  `evaluation/point5_results.json`: all 40 typed outcomes, original queries/responses,
  parsed SQL rows, totals, calculated margins, rule summaries, labels and metrics.
- Monetary inputs are USD thousands. Operating costs include production, selling/admin
  and R&D. Margins and industry medians use percentage points, with inclusive endpoint
  comparisons and strict historical positivity. No epsilon or extra threshold is used.
- SQL aggregates each table before joining to avoid multiplying revenue or costs.
  It checks source value types/counts so SUM cannot silently mask null or text inputs.
  Twelve distinct monthly cost rows are required for each assessed year. A company
  lacking complete fiscal coverage returns an explicit error. Revenue requires at least
  one numeric order per year; there is no assumption that every month has a sale.
- The supplied tool rounds floating SQL output to two decimal places. Decimal arithmetic
  avoids further float rounding but cannot recover precision lost at that boundary.
  Exactly equal observed margins pass; private data near a boundary may be sensitive
  to source rounding. Negative industry medians remain valid under the specified rule.
- An error is not an investment FAIL. Errors count wrong in their true label class,
  remain visible separately, and produce a nonzero comparison CLI exit status.
  No public grading fallback has been selected.
- Labels are loaded only after all strategy execution and tracing finish. Runtime has
  no ground-truth/evaluation imports. Public results informed this recommendation, so
  they are development evidence, not an independent estimate of unseen accuracy.
- `--trace` emits both strategy spans via the existing best-effort Langfuse integration;
  credentials are optional. Offline span payload tests passed. Live ingestion/retrieval
  has not been verified for this experiment. No paid smoke was run.
- Point 4 and Point 14 are outside scope. The complete `hw3.py`, required model/constants
  and protected lecturer code are unchanged. Full grading and submission-layout checks
  remain for final three-point integration. The PDF describes the submitted repository,
  but does not explicitly discuss helper packages; verify the final fresh-clone layout.

## Validation

- `python -m unittest discover -s test -v`: 43 tests run, 42 passed, 1 optional paid smoke skipped.
- TDD red/green runs covered margin calculation, invalid inputs, the strategy contract,
  rules, retrieval failures, provenance and evaluation. Synthetic SQLite fixtures also
  exercise the real supplied LangChain SQL tool, including a distracting industry row,
  null order, text cost and missing middle-year cost month.
- `git diff --check` passed. `git diff --exit-code db218bc -- hw3.py requirements.txt
  observability public_test` passed: all protected and unrelated inputs remain unchanged.
- Review checked SQL aggregation/periods, evidence references, class-balanced metrics,
  error isolation, answer separation and scope. No integration blocker remains within
  this standalone experiment; final strategy selection is pending review.
