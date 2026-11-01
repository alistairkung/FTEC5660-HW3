"""Independent Point 14 experiment; live inference requires explicit opt-in."""
import argparse
import asyncio
from contextlib import nullcontext
from dataclasses import asdict
from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
import subprocess
from time import monotonic

from fisher_agent.returns_disclosure import Point14ReturnsStrategy, build_returns_strategy
from fisher_agent.returns_disclosure.point14_returns_strategy import (PROMPT_VERSION, DISCLOSURE_PROMPT,
    COMPANY_DEADLINE_SECONDS, MODEL_TIMEOUT_SECONDS, TOOL_TIMEOUT_SECONDS, MAX_MODEL_CALLS)
from fisher_agent.returns_disclosure.records import ReturnsRun
from observability import Tracing


def json_ready(value):
    if isinstance(value,Decimal):
        return str(value)
    if isinstance(value,dict):
        return {key:json_ready(item) for key,item in value.items()}
    if isinstance(value,(list,tuple)):
        return [json_ready(item) for item in value]
    return value


def score_runs(runs: dict[str,ReturnsRun], labels: dict[str,str]) -> dict:
    if set(runs) != set(labels) or any(label not in ('PASS','FAIL') for label in labels.values()):
        raise ValueError('Predictions and valid labels must have the same companies')
    correct = sum(run.point_result.verdict == labels[company] for company,run in runs.items())
    recalls = {}
    for verdict in ('PASS','FAIL'):
        count = sum(label == verdict for label in labels.values())
        recalls[verdict] = (sum(labels[company] == verdict and run.point_result.verdict == verdict
            for company,run in runs.items())/count if count else None)
    return {'companies':len(runs),'grounded_correct':correct,'accuracy':correct/len(runs) if runs else None,
        'pass_recall':recalls['PASS'],'fail_recall':recalls['FAIL'],
        'balanced_accuracy':sum(recalls.values())/2 if all(v is not None for v in recalls.values()) else None,
        'incorrect':sorted(c for c,r in runs.items() if r.point_result.verdict != labels[c]),
        'semantic_abstentions':sorted(c for c,r in runs.items() if r.point_result.status=='insufficient_evidence'),
        'operational_failures':sorted(c for c,r in runs.items() if r.failure_status=='error'),
        'independent_verdicts_with_errors':sorted(c for c,r in runs.items()
            if r.failure_status=='error' and r.point_result.verdict is not None),
        'hypothetical_fail_fallback_credit':sum(r.point_result.verdict is None and labels[c]=='FAIL'
                                             for c,r in runs.items())}


def summarize(runs: dict[str,ReturnsRun]) -> dict:
    usage = {key:sum(r.usage.get(key,0) for r in runs.values())
             for key in ('input_tokens','output_tokens','total_tokens')}
    return {'companies':len(runs),'anomalous_quarters':sum(c.anomalous for r in runs.values() for c in r.comparisons),
        'no_anomaly_companies':sum(len(r.comparisons)==4 and not any(c.anomalous for c in r.comparisons)
                                    for r in runs.values()),
        'model_calls':sum(r.model_calls for r in runs.values()),
        'format_repairs':sum(r.format_repairs for r in runs.values()),'usage':usage,
        'tool_calls':{name:sum(r.tool_calls.get(name,0) for r in runs.values())
                      for name in ('sql_query','list_documents','read_document')},
        'statuses':{c:r.point_result.status for c,r in runs.items()}}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--financial-only',action='store_true',help='SQL calculations only; no documents/model/labels')
    mode.add_argument('--live',action='store_true',help='Opt in to paid acknowledgement calls for anomalies only')
    parser.add_argument('--data-folder',type=Path,default=Path('public_test'))
    parser.add_argument('--output',type=Path,required=True,help='New artifact path; existing files are never overwritten')
    parser.add_argument('--companies','--company',nargs='+',help='Evaluation-only folder filter')
    parser.add_argument('--concurrency',type=int,choices=(1,2),default=1)
    parser.add_argument('--trace',action='store_true',help='Use the existing optional Langfuse integration')
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Output already exists; choose a new artifact path')
    import hw3
    folders = hw3.company_folders(args.data_folder)
    if args.companies:
        selected = set(args.companies)
        if len(selected) != len(args.companies) or not selected <= {f.name for f in folders}:
            parser.error('Company filter contains duplicate or unknown folders')
        folders = [f for f in folders if f.name in selected]
    if not folders:
        parser.error('No company folders found')
    if args.live or args.trace:
        hw3.load_env_file()
    tools = {f.name:hw3.make_tools(f) for f in folders}
    lifecycle = Tracing() if args.trace else nullcontext(None)
    started = monotonic()
    with lifecycle as tracing:
        strategy = build_returns_strategy(tracing) if args.live else Point14ReturnsStrategy(tracing=tracing)
        # Each assess() owns a company root; the lifecycle is shared, context is not.
        runs = asyncio.run(strategy.assess_companies(tools,concurrency=args.concurrency,
                                                   financial_only=args.financial_only))
        summary = summarize(runs)
        summary['interview_calls'] = sum(hw3.INTERVIEWS_USED.get(name,0) for name in runs)
    wall_seconds = monotonic()-started
    # Runtime and trace lifecycle finish before evaluation labels are loaded.
    scores = None
    if args.live:
        truth = hw3.read_ground_truth(args.data_folder)
        labels = {company:truth[company]['points']['14'] for company in runs}
        scores = score_runs(runs,labels)
    config = {'commit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        'working_tree_dirty':bool(subprocess.check_output(['git','status','--porcelain'],text=True).strip()),
        'utc_time':datetime.now(timezone.utc).isoformat(),'point':14,'prompt_version':PROMPT_VERSION,
        'threshold':'current_returned*baseline_shipped >= 2*baseline_returned*current_shipped',
        'zero_zero_exception':'no anomaly','financial_only':args.financial_only,
        'companies':list(runs),'concurrency':args.concurrency,'data_folder':str(args.data_folder),
        'model':hw3.MODEL_NAME if args.live else None,'thinking':'disabled' if args.live else None,
        'temperature':0 if args.live else None,'max_tokens':600 if args.live else None}
    source_dir = Path(__file__).resolve().parents[1]/'fisher_agent'/'returns_disclosure'
    config.update(prompt_sha256=sha256(DISCLOSURE_PROMPT.encode()).hexdigest(),
        source_sha256={file.name:sha256(file.read_bytes()).hexdigest() for file in sorted(source_dir.glob('*.py'))},
        company_deadline_seconds=COMPANY_DEADLINE_SECONDS,model_timeout_seconds=MODEL_TIMEOUT_SECONDS,
        tool_timeout_seconds=TOOL_TIMEOUT_SECONDS,max_model_calls=MAX_MODEL_CALLS)
    artifact = {'configuration':config,'summary':summary,'scores':scores,'wall_seconds':wall_seconds,
                'trace_ids':{c:r.trace_id for c,r in runs.items()},'runs':{c:asdict(r) for c,r in runs.items()}}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x') as stream:
        stream.write(json.dumps(json_ready(artifact),indent=2,allow_nan=False)+'\n')
    print(json.dumps({'summary':summary,'scores':scores,'wall_seconds':wall_seconds},indent=2))
    return 1 if any(r.failure_status=='error' for r in runs.values()) else 0


if __name__ == '__main__':
    raise SystemExit(main())
