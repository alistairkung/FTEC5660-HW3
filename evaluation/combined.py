"""Paid opt-in evaluation of the two-specialist milestone, with Point 14 missing."""
import argparse
import asyncio
from dataclasses import asdict
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import subprocess
from time import monotonic

from pydantic import BaseModel

import hw3
from fisher_agent.company_analyzer import CompanyAssessment
from observability import Tracing


def score_results(results: dict[str, CompanyAssessment], labels: dict) -> dict:
    metrics = {}
    for point in (4, 5):
        counts = {'PASS': [0, 0], 'FAIL': [0, 0]}
        failures, wrong, fallback_credits = [], [], 0
        for name, company in results.items():
            expected = labels[name]['points'][str(point)]
            if expected not in counts:
                raise ValueError('Expected PASS/FAIL development labels')
            result = company.points[point]
            correct = result.status == 'complete' and result.verdict == expected
            counts[expected][0] += int(correct)
            counts[expected][1] += 1
            if not correct:
                wrong.append(name)
            if result.status != 'complete':
                failures.append(name)
                fallback_credits += int(expected == 'FAIL')
        recalls = {k: hits / total if total else None for k, (hits, total) in counts.items()}
        rates = [r for r in recalls.values() if r is not None]
        correct = sum(h for h, _ in counts.values())
        metrics[str(point)] = dict(total=len(results), grounded_correct=correct,
                                   accuracy=correct / len(results) if results else None,
                                   balanced_accuracy=sum(rates) / len(rates) if rates else None,
                                   pass_recall=recalls['PASS'], fail_recall=recalls['FAIL'],
                                   misclassified=wrong, operational_failures=failures,
                                   fallback_credits=fallback_credits)
    return metrics


def _json_default(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, BaseModel):
        return value.model_dump()
    raise TypeError(f'Cannot serialize {type(value).__name__}')


async def evaluate(folder: Path, output: Path, company_ids: list[str] | None = None) -> dict:
    if output.exists():
        raise FileExistsError('Choose a new output path; baselines must not be overwritten')
    hw3.load_env_file()
    if not os.getenv('DEEPSEEK_API_KEY', '').strip():
        raise ValueError('DEEPSEEK_API_KEY is required')
    folders = hw3.company_folders(folder)
    if company_ids:
        folders = [path for path in folders if path.name in company_ids]
        if {p.name for p in folders} != set(company_ids):
            raise ValueError('Unknown evaluation company')
    if not folders:
        raise ValueError('No company folders')
    chosen = hw3.check_chosen_points(hw3.CHOSEN_POINTS)
    companies = {path.name: hw3.make_tools(path) for path in folders}
    start = monotonic()
    run_at = datetime.now(timezone.utc).isoformat()
    with Tracing() as tracing:
        agent = hw3.build_agent()
        analysis_start = monotonic()
        results = await agent.assess_companies(companies)
        analysis_seconds = monotonic() - analysis_start
    runtime = monotonic() - start
    # Labels enter only after all classifications. Runtime never receives them.
    labels = hw3.read_ground_truth(folder)
    metrics = score_results(results, labels)
    public = {name: result.public_result() for name, result in results.items()}
    csv_path, lecturer_correct = hw3.write_results(list(companies), public, labels, chosen)
    sales = [r.sales for r in results.values() if r.sales is not None]
    usage = {key: sum(r.usage.get(key, 0) for r in sales)
             for key in ('input_tokens', 'output_tokens', 'total_tokens')}
    source_paths = [Path('hw3.py'), *sorted(Path('fisher_agent').rglob('*.py'))]
    report = dict(run_at=run_at, commit=subprocess.check_output(
        ['git', 'rev-parse', 'HEAD'], text=True).strip(),
        source_sha256={str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in source_paths},
        model=hw3.MODEL_NAME, thinking='disabled', temperature=0, company_concurrency=2,
        implemented_points=[4, 5], pending_points=[14], submission_ready=False,
        analysis_seconds=analysis_seconds, runtime_seconds=runtime, metrics=metrics,
        model_calls=sum(r.model_calls for r in sales), usage=usage,
        sql_calls=sum(len(r.margin.evidence) for r in results.values() if r.margin),
        interviews_per_company={name: hw3.INTERVIEWS_USED[name] for name in results},
        second_interviews=sum(r.interviews_used > 1 for r in sales),
        adjudications=sum(r.adjudication_used for r in sales),
        sales_diagnostics=[d for r in sales for d in r.diagnostics],
        lecturer_correct_points=lecturer_correct, lecturer_total_points=len(results) * len(chosen),
        lecturer_balanced_accuracy=hw3.balanced_point_accuracy(public, labels, list(results), chosen),
        results_csv=str(csv_path), results={name: asdict(r) for name, r in results.items()})
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, default=_json_default) + '\n')
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true', required=True, help='allow paid DeepSeek calls')
    parser.add_argument('--data-folder', type=Path, default=Path('public_test'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--company', action='append', help='development-only company subset')
    args = parser.parse_args()
    report = asyncio.run(evaluate(args.data_folder, args.output, args.company))
    print(json.dumps({key: report[key] for key in ('metrics', 'analysis_seconds', 'model_calls', 'usage')}, indent=2))
    return 2 if any(m['operational_failures'] for m in report['metrics'].values()) else 0


if __name__ == '__main__':
    raise SystemExit(main())
