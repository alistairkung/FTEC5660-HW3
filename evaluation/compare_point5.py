"""Compare Point 5 strategies without feeding answers into strategy execution."""

from __future__ import annotations

import argparse
from contextlib import nullcontext
from dataclasses import asdict
from decimal import Decimal
import json
from pathlib import Path
from typing import Any

from fisher_agent.point5.margin_records import MarginResult, MarginStrategy, SQLTool, StrategyError
from fisher_agent.point5.historical_margin_strategy import HistoricalMarginStrategy
from fisher_agent.point5.industry_margin_strategy import IndustryMarginStrategy
from observability.tracing import Observation, Tracing


def evaluate_strategies(
    company_tools: dict[str, SQLTool], strategies: list[MarginStrategy],
    *, tracing: Tracing | None = None,
) -> dict[str, dict[str, MarginResult]]:
    """No labels accepted here. Preserve an outcome for every company/strategy."""
    results: dict[str, dict[str, MarginResult]] = {}
    for strategy in strategies:
        if strategy.name in results:
            raise ValueError('Strategy names must be unique')
        results[strategy.name] = {}
        for company_id, sql_tool in company_tools.items():
            scope = tracing.observation(
                f'point5-{strategy.name}', company_id=company_id, fisher_point=5,
                input={'strategy': strategy.name},
            ) if tracing is not None else nullcontext(Observation())
            with scope as span:
                try:
                    result = strategy.evaluate(company_id, sql_tool)
                except Exception as error:
                    result = MarginResult(
                        company_id, strategy.name, 'error', None,
                        'Unexpected strategy failure',
                        error=StrategyError('strategy_error', type(error).__name__),
                    )
                results[strategy.name][company_id] = result
                span.update(output=json_ready(asdict(result)),
                            level='ERROR' if result.error else 'DEFAULT')
    return results


def compare(
    results: dict[str, dict[str, MarginResult]], labels: dict[str, str],
) -> dict[str, Any]:
    """Missing/error verdicts count wrong in their true class, as in the harness."""
    if not labels or any(label not in ('PASS', 'FAIL') for label in labels.values()):
        raise ValueError('Need nonempty, valid Point 5 ground truth')
    metrics = {}
    for strategy, predictions in results.items():
        if set(predictions) != set(labels):
            raise ValueError('Prediction and ground truth company sets must match exactly')
        recalls = {}
        for label in ('PASS', 'FAIL'):
            total = sum(expected == label for expected in labels.values())
            correct = sum(labels[company] == label and result.verdict == label
                          for company, result in predictions.items())
            recalls[label] = correct / total if total else None
        metrics[strategy] = {
            'total': len(labels),
            'completed': sum(result.status == 'complete' for result in predictions.values()),
            'pass_recall': recalls['PASS'], 'fail_recall': recalls['FAIL'],
            'balanced_accuracy': ((recalls['PASS'] + recalls['FAIL']) / 2
                                  if all(value is not None for value in recalls.values()) else None),
            'label_disagreements': sorted(company for company, result in predictions.items()
                                          if result.verdict is not None and result.verdict != labels[company]),
            'errors': {company: asdict(result.error) for company, result in predictions.items()
                       if result.error is not None},
            'sql_errors': sorted(company for company, result in predictions.items()
                                 if result.error is not None and result.error.code == 'sql_error'),
            'sql_calls': sum(len(result.evidence) for result in predictions.values()),
        }
    return {
        'metrics': metrics,
        'strategy_disagreements': sorted(
            company for company in labels
            if len({predictions[company].verdict for predictions in results.values()
                    if predictions[company].verdict is not None}) > 1
        ),
    }


def json_ready(value: Any) -> Any:
    """Preserve Decimal precision in evidence artifacts and trace payloads."""
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {key: json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_ready(item) for item in value]
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-folder', type=Path, default=Path('public_test'))
    parser.add_argument('--output', type=Path, default=Path('evaluation/point5_results.json'))
    parser.add_argument('--trace', action='store_true', help='Opt in to optional Langfuse spans')
    args = parser.parse_args()

    # Reuse the lecturer's unchanged tool factory, never access company evidence ourselves.
    import hw3

    folders = hw3.company_folders(args.data_folder)
    tools = {folder.name: next(tool for tool in hw3.make_tools(folder) if tool.name == 'sql_query')
             for folder in folders}
    if args.trace:
        hw3.load_env_file()
    lifecycle = Tracing() if args.trace else nullcontext(None)
    with lifecycle as tracing:
        results = evaluate_strategies(
            tools, [IndustryMarginStrategy(), HistoricalMarginStrategy()], tracing=tracing,
        )
    # Answers are first read after all strategy execution and trace payloads finish.
    truth = hw3.read_ground_truth(args.data_folder)
    labels = {company: item['points']['5'] for company, item in truth.items()}
    report = compare(results, labels)
    artifact = {'point': 5, 'data_folder': str(args.data_folder),
                'report': report, 'labels': labels,
                'results': {name: {company: asdict(result) for company, result in predictions.items()}
                            for name, predictions in results.items()}}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(json_ready(artifact), indent=2, allow_nan=False) + '\n')
    print(json.dumps(report, indent=2))
    print(f'Evidence and per-company results: {args.output}')
    return 1 if any(metrics['errors'] for metrics in report['metrics'].values()) else 0


if __name__ == '__main__':
    raise SystemExit(main())
