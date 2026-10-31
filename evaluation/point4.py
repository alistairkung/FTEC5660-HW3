"""Development-only Point 4 evaluation; leaves the three-point grader unchanged."""
import argparse
import asyncio
from dataclasses import asdict
from datetime import datetime, timezone
import json
import os
from pathlib import Path

import hw3
from fisher_agent.sales_records import SalesResult
from fisher_agent.evidence_interpreter import PROMPT_VERSION
from fisher_agent.runtime import build_sales_specialist
from observability import Tracing


def score_results(results: dict[str, SalesResult], labels: dict) -> dict:
    """Report grader-style scores AND grounded successes, never conflate them."""
    if any(name not in labels or labels[name]['points'].get('4') not in ('PASS', 'FAIL')
           for name in results):
        raise ValueError('Every evaluated company needs a valid Point 4 label')
    hits = {'PASS': [0, 0], 'FAIL': [0, 0]}
    wrong, failures = [], []
    grounded_correct = 0
    for name, result in results.items():
        expected = labels[name]['points']['4']
        correct = result.verdict == expected
        hits[expected][0] += int(correct)
        hits[expected][1] += 1
        if not correct:
            wrong.append(name)
        if result.status not in ('assessed', 'adjudicated'):
            failures.append(name)
        elif correct:
            grounded_correct += 1
    recalls = {key: hit / count if count else None for key, (hit, count) in hits.items()}
    rates = [value for value in recalls.values() if value is not None]
    usage_keys = ('input_tokens', 'output_tokens', 'total_tokens')
    return dict(total=len(results), correct=sum(hit for hit, _ in hits.values()),
                pass_recall=recalls['PASS'], fail_recall=recalls['FAIL'],
                balanced_accuracy=sum(rates) / len(rates) if rates else None,
                misclassified=wrong, successful_assessments=len(results) - len(failures),
                grounded_correct=grounded_correct, failures=failures,
                interviews_per_company={name: result.interviews_used for name, result in results.items()},
                fallback_activations=sum(result.fallback_triggered for result in results.values()),
                final_adjudications=sum(result.adjudication_used for result in results.values()),
                model_calls=sum(result.model_calls for result in results.values()),
                companies_with_usage=sum(bool(result.usage) for result in results.values()),
                usage={key: sum(result.usage.get(key, 0) for result in results.values())
                       for key in usage_keys})


async def evaluate(folder: Path, output: Path) -> dict:
    hw3.load_env_file()
    if not os.getenv('DEEPSEEK_API_KEY', '').strip():
        raise ValueError('DEEPSEEK_API_KEY is required for live evaluation')
    folders = hw3.company_folders(folder)
    if not folders:
        raise ValueError('No company folders found')
    # Evidence is accessed ONLY through the unchanged supplied factory/tools.
    companies = {path.name: hw3.make_tools(path) for path in folders}
    with Tracing() as tracing:
        specialist = build_sales_specialist(tracing)
        results = await specialist.assess_companies(companies)
    # Read labels only after prediction. The specialist never receives this mapping.
    labels = hw3.read_ground_truth(folder)
    metrics = score_results(results, labels)
    report = dict(run_at=datetime.now(timezone.utc).isoformat(), model=hw3.MODEL_NAME,
                  temperature=0, prompt_version=PROMPT_VERSION,
                  live_evaluation_complete=metrics['successful_assessments'] == len(results),
                  metrics=metrics,
                  results={name: {**asdict(result),
                                  'assessments': [item.model_dump() for item in result.assessments],
                                  'public_result': result.public_result(),
                                  'lecturer_interviews_used': hw3.INTERVIEWS_USED[name]}
                           for name, result in results.items()})
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true', required=True,
                        help='allow paid calls to the permitted DeepSeek model')
    parser.add_argument('--data-folder', type=Path, default=Path('public_test'))
    parser.add_argument('--output', type=Path, default=Path('evaluation/point4-latest.json'))
    args = parser.parse_args()
    report = asyncio.run(evaluate(args.data_folder, args.output))
    print(json.dumps(report['metrics'], indent=2))
    print(f'Results: {args.output}; live evaluation complete: {report["live_evaluation_complete"]}')
    return 0 if report['live_evaluation_complete'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
