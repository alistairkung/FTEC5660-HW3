"""Development-only Point 14 evaluation. Labels never enter specialist inputs."""
import argparse
import asyncio
from dataclasses import asdict
import json
from pathlib import Path
from time import monotonic

import hw3
from fisher_agent.point14.financial_evidence_extractor import FinancialEvidenceExtractor
from fisher_agent.point14.records import TransparencyResult
from fisher_agent.point14.runtime import build_transparency_specialist
from observability import Tracing

REVIEW_CATEGORIES = ('incorrect_financial_extraction', 'missed_management_statement',
                     'unsupported_or_misattributed_evidence', 'incorrect_claim_verification',
                     'incorrect_transparency_judgement')
BATCH_DEADLINE_SECONDS = 25 * 60


def score_results(results: list[TransparencyResult], expected: dict) -> dict:
    labelled = [(result, expected[result.company_id]['points']['14']) for result in results
                if result.company_id in expected]
    recalls = {}
    for verdict in ('PASS', 'FAIL'):
        group = [(result, label) for result, label in labelled if label == verdict]
        recalls[verdict] = sum(result.verdict == label for result, label in group) / len(group) if group else None
    disagreements = [(result, label) for result, label in labelled if result.verdict != label]
    return {
        'companies': len(results), 'labelled_companies': len(labelled),
        'total_correct': sum(result.verdict == label for result, label in labelled),
        'grounded_correct': sum(result.verdict == label for result, label in labelled),
        'public_adapter_correct': sum(result.public_result()['points'][14] == label for result, label in labelled),
        'public_fallback_credit': sum(result.verdict is None and label == 'FAIL' for result, label in labelled),
        'pass_recall': recalls['PASS'], 'fail_recall': recalls['FAIL'],
        'balanced_accuracy': (sum(recalls.values()) / 2 if None not in recalls.values() else None),
        'incorrect_companies': [result.company_id for result, _ in disagreements],
        'disagreements': [{'company': result.company_id, 'predicted': result.verdict, 'expected': label,
                          'stage': result.error_stage, 'status': result.status,
                          'attribution': {category: None for category in REVIEW_CATEGORIES},
                          'review_status': 'requires evidence review'} for result, label in disagreements],
        # Compatibility field: all unresolved verdicts, including semantic abstention.
        'failures': [{'company': result.company_id, 'stage': result.error_stage,
                      'status': result.status, 'error_type': result.error_type}
                     for result in results if result.verdict is None],
        'semantic_abstentions': [result.company_id for result in results if result.status == 'insufficient_evidence'],
        'operational_failures': [{'company': result.company_id, 'stage': result.error_stage,
                      'status': result.status, 'error_type': result.error_type}
                     for result in results if result.verdict is None and result.status != 'insufficient_evidence'],
        'sql_failures': sum(r.verdict is None and r.error_stage == 'financial-extraction' for r in results),
        'extraction_failures': sum(r.verdict is None and r.error_stage in
                                   ('document-retrieval', 'claim-extraction') for r in results),
        'unsupported_quotation_rejections': sum(r.diagnostics.quotation_rejections for r in results),
        'final_adjudications': sum(r.diagnostics.adjudications for r in results),
        'model_calls': sum(r.diagnostics.model_calls for r in results),
        'parsing_retries': sum(r.diagnostics.parsing_retries for r in results),
        'model_latency_seconds': sum(r.diagnostics.model_latency_seconds for r in results),
        'usage': {key: sum(r.diagnostics.usage.get(key, 0) for r in results)
                  for key in {key for r in results for key in r.diagnostics.usage}},
        'trace_ids': {r.company_id: r.trace_id for r in results if r.trace_id},
    }


async def evaluate(folder: Path, *, financial_only: bool, concurrency: int) -> dict:
    start = monotonic()
    semaphore = asyncio.Semaphore(concurrency)
    folders = hw3.company_folders(folder)
    completed = {}
    with Tracing() as tracing:
        specialist = None if financial_only else build_transparency_specialist(tracing)

        async def run(company: Path):
            async with semaphore:
                try:
                    tools = hw3.make_tools(company)
                    if specialist:
                        return await specialist.evaluate(company.name, tools)
                    financial = await FinancialEvidenceExtractor().extract(company.name, tools[2])
                    return {'company': company.name, 'status': 'complete', 'metrics': len(financial.metrics)}
                except Exception as exc:
                    if specialist:
                        return TransparencyResult(company.name, status='retrieval_error',
                            error_stage='tool-setup', error_type=type(exc).__name__)
                    return {'company': company.name, 'status': 'error', 'error_type': type(exc).__name__}

        async def record(company: Path):
            completed[company.name] = await run(company)

        try:
            await asyncio.wait_for(asyncio.gather(*(record(company) for company in folders)),
                                   BATCH_DEADLINE_SECONDS)
        except TimeoutError:
            pass  # wait_for cancels and awaits pending tasks; preserve completed work.
        results = [completed.get(company.name) or (
            {'company': company.name, 'status': 'error', 'error_type': 'BatchDeadline'}
            if financial_only else TransparencyResult(company.name, status='deadline',
                error_stage='batch-deadline', error_type='BatchDeadline')) for company in folders]
    if financial_only:
        return {'mode': 'financial_only', 'companies': len(results),
                'complete': sum(result['status'] == 'complete' for result in results),
                'results': results, 'wall_seconds': monotonic() - start,
                'transparency_accuracy': 'not measured; no LLM calls or labels loaded'}
    # Ground truth is accessed only after all specialist decisions are complete.
    report = score_results(results, hw3.read_ground_truth(folder))
    report['wall_seconds'] = monotonic() - start
    report['results'] = [asdict(result) for result in results]
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-folder', type=Path, default=Path('public_test'))
    parser.add_argument('--env-file', type=Path, default=Path('.env'))
    parser.add_argument('--output', type=Path, default=Path('evaluation/point14-results.json'))
    parser.add_argument('--concurrency', type=int, choices=range(1, 5), default=4)
    parser.add_argument('--financial-only', action='store_true', help='No model calls; do not read labels')
    parser.add_argument('--live', action='store_true', help='Allow paid DeepSeek analysis')
    args = parser.parse_args()
    if not args.financial_only and not args.live:
        parser.error('Choose --financial-only or --live (paid model evaluation)')
    hw3.load_env_file(args.env_file)
    report = asyncio.run(evaluate(args.data_folder, financial_only=args.financial_only,
                                  concurrency=args.concurrency))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, default=str, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({key:value for key,value in report.items() if key not in ('results', 'trace_ids')}, indent=2))


if __name__ == '__main__':
    main()
