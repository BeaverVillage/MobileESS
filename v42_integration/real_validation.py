"""Run one explicitly scoped real May01 integration attempt; no dispatcher."""
import argparse
from pathlib import Path
import time
import traceback
import threading
import psutil

from .actual_validation import read,write
from .budget import IntegrationBudget
from .coordinator import run_arm
from .m_engine import file_record
from .production_case import build_integration_case


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--arm',choices=('B0','B2','B1','B3'),required=True)
    parser.add_argument('--source-freeze',type=Path,required=True)
    parser.add_argument('--strict-stats',type=Path,required=True)
    parser.add_argument('--initial-site-authority',type=Path,help='Historical option; rejected by current boundary policy')
    parser.add_argument('--planning-only',action='store_true')
    parser.add_argument('--initial-state-freeze',type=Path)
    parser.add_argument('--budget',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--a-call-cap',type=float,default=480.)
    parser.add_argument('--m-stage-cap',type=float,default=120.)
    args=parser.parse_args()
    if args.output.exists():
        raise ValueError('INTEGRATION_ATTEMPT_ALREADY_EXISTS')
    if not (0<args.a_call_cap<=5400 and 0<args.m_stage_cap<=1800):
        raise ValueError('OPERATIONAL_STAGE_CAP_MUST_BE_PRESERVED')
    args.output.mkdir(parents=True)
    began=time.perf_counter()
    measured={'peak_RSS_bytes':0};stop=threading.Event()
    def sample_rss():
        process=psutil.Process()
        while not stop.is_set():
            measured['peak_RSS_bytes']=max(measured['peak_RSS_bytes'],process.memory_info().rss)
            stop.wait(.1)
    watcher=threading.Thread(target=sample_rss,daemon=True);watcher.start()
    budget=IntegrationBudget(args.budget)
    before=budget.used()
    receipt=dict(arm=args.arm,scope='ONE_DAY_ISOLATED_VALIDATION',campaign_HOLD=True,
        campaign_started=False,source_freeze=file_record(args.source_freeze),
        initial_site_authority=None if args.initial_site_authority is None else file_record(args.initial_site_authority),
        initial_state_freeze=None if args.initial_state_freeze is None else file_record(args.initial_state_freeze),
        integration_solve_seconds_before=before)
    try:
        case=build_integration_case(source_freeze=read(args.source_freeze),strict_stats=args.strict_stats,
            output=args.output/'CASE',initial_site_authority=args.initial_site_authority,
            initial_state_freeze=args.initial_state_freeze,
            a_call_cap=args.a_call_cap,m_stage_cap=args.m_stage_cap)
        receipt.update(case_sha=case.case_sha,preparation='NATIVE0_PASS')
        write(args.output/'EXECUTION_RECEIPT.json',receipt)
        result=run_arm(args.arm,case,budget,args.output/args.arm,planning_only=args.planning_only)
        actual=result.get('actual')
        receipt.update(status='PLANNING_ONLY_EXECUTED' if actual is None else 'EXECUTED',stages=list(result['stages']),
            actual=None if actual is None else actual['receipt'],Fresh_AC=None if actual is None else actual.get('Fresh_AC'),
            actual_gate=result.get('actual_gate'),
            whole_AIDC_MESS_global_gap='NOT_CERTIFIED')
    except Exception as exc:
        receipt.update(status='FAILED',error=repr(exc),traceback=traceback.format_exc())
        raise
    finally:
        stop.set();watcher.join()
        receipt.update(wall_seconds=time.perf_counter()-began,
            measured_process_peak_RSS=measured,RSS_sample_interval_seconds=.1,
            integration_solve_seconds_after=budget.used(),
            new_solve_seconds=budget.used()-before)
        write(args.output/'EXECUTION_RECEIPT.json',receipt)


if __name__=='__main__':
    main()
