"""Independent, development-only Point 7 evaluation; never changes CHOSEN_POINTS."""
import argparse
import asyncio
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from time import monotonic

import hw3
from fisher_agent.labour_interpreter import PROMPT_VERSION
from fisher_agent.labour_records import LabourRun
from fisher_agent.labour_runtime import build_labour_specialist
from observability import Tracing


def score_results(results: dict[str, LabourRun], labels: dict) -> dict:
    """Errors/uncertainty count as wrong for their true class, with no fallback credit."""
    if any(name not in labels or labels[name]['points'].get('7') not in ('PASS', 'FAIL')
           for name in results):
        raise ValueError('Every evaluated company needs a valid Point 7 label')
    hits = {'PASS': [0, 0], 'FAIL': [0, 0]}
    wrong, errors, insufficient = [], [], []
    for name, run in results.items():
        result = run.point_result
        expected = labels[name]['points']['7']
        grounded_correct = result.status == 'complete' and result.verdict == expected
        hits[expected][0] += int(grounded_correct)
        hits[expected][1] += 1
        if not grounded_correct:
            wrong.append(name)
        if result.status == 'error':
            errors.append(name)
        elif result.status != 'complete':
            insufficient.append(name)
    recalls = {key: hit / count if count else None for key, (hit, count) in hits.items()}
    rates = [v for v in recalls.values() if v is not None]
    correct = sum(hit for hit, _ in hits.values())
    second = sum(run.interviews_used == 2 for run in results.values())
    return dict(total=len(results), grounded_correct=correct,
                grounded_accuracy=correct / len(results) if results else None,
                pass_recall=recalls['PASS'], fail_recall=recalls['FAIL'],
                balanced_accuracy=sum(rates) / len(rates) if rates else None,
                misclassified=wrong, operational_errors=errors, insufficient_evidence=insufficient,
                successful_assessments=sum(r.point_result.status == 'complete' for r in results.values()),
                second_interviews=second, second_interview_frequency=second / len(results) if results else 0,
                interviews=sum(r.interviews_used for r in results.values()),
                model_calls=sum(r.model_calls for r in results.values()),
                companies_with_usage=sum(bool(r.usage) for r in results.values()),
                usage={key: sum(r.usage.get(key, 0) for r in results.values())
                       for key in ('input_tokens', 'output_tokens', 'total_tokens')},
                trace_ids_recorded=sum(bool(r.trace_id) for r in results.values()),
                remote_trace_completeness=None)


async def evaluate(folder: Path, output: Path, *, company_ids: list[str] | None = None) -> dict:
    hw3.load_env_file()
    if not os.getenv('DEEPSEEK_API_KEY', '').strip():
        raise ValueError('DEEPSEEK_API_KEY is required for live evaluation')
    folders = hw3.company_folders(folder)
    if company_ids is not None:
        available = {p.name: p for p in folders}
        if not company_ids or len(set(company_ids)) != len(company_ids) or set(company_ids) - available.keys():
            raise ValueError('Company selection must contain unique existing company folders')
        folders = [available[name] for name in company_ids]
    if not folders:
        raise ValueError('No company folders found')
    # Evidence access stays inside the unchanged lecturer factory and supplied tools.
    companies = {p.name: hw3.make_tools(p) for p in folders}
    started = monotonic()
    with Tracing() as tracing:
        results = await build_labour_specialist(tracing).assess_companies(companies)
    runtime = round(monotonic() - started, 6)
    # Labels are loaded AFTER inference and never passed into the specialist or tracing.
    metrics = score_results(results, hw3.read_ground_truth(folder))
    metrics['runtime_seconds_including_tracing_shutdown'] = runtime
    source_paths = [Path('hw3.py'), *sorted(Path('fisher_agent').glob('labour_*.py'))]
    report = dict(run_at=datetime.now(timezone.utc).isoformat(), model=hw3.MODEL_NAME,
                  temperature=0, thinking='disabled', prompt_version=PROMPT_VERSION,
                  source_sha256={str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in source_paths},
                  live_evaluation_complete=metrics['successful_assessments'] == len(results),
                  metrics=metrics,
                  results={name: {**asdict(run),
                                  'assessments': [a.model_dump() for a in run.assessments],
                                  'lecturer_interviews_used': hw3.INTERVIEWS_USED[name]}
                           for name, run in results.items()})
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true', required=True, help='allow paid DeepSeek calls')
    parser.add_argument('--data-folder', type=Path, default=Path('public_test'))
    parser.add_argument('--output', type=Path, default=Path('evaluation/point7-latest.json'))
    parser.add_argument('--companies', nargs='+', help='optional small live gate selection')
    args = parser.parse_args()
    report = asyncio.run(evaluate(args.data_folder, args.output, company_ids=args.companies))
    print(json.dumps(report['metrics'], indent=2))
    print(f'Results: {args.output}')
    return 0 if report['live_evaluation_complete'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
