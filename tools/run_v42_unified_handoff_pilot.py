"""Supervisor-only real A1/M1/A2/M2 pilot, one durable budget and source freeze."""
from pathlib import Path
from time import perf_counter
import argparse
import json
import sys
import threading
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from v42_integration.unified_contract import REPORT,load_contracts,digest
from v42_integration.unified_resource import UnifiedResearchBudget
from v42_integration.m_engine import _write,file_record


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=REPORT/'REAL_HANDOFF_ATTEMPT01')
    parser.add_argument('--run',action='store_true')
    parser.add_argument('--a-seconds',type=float,default=75.)
    parser.add_argument('--m-seconds',type=float,default=30.)
    args=parser.parse_args()
    if not args.run:raise SystemExit('Use --run for the explicitly costed native pilot.')
    interface=json.loads((REPORT/'UNIFIED_INTERFACE_CONTRACT.json').read_text(encoding='utf8'))
    if interface.get('four_stage_Heavy_authorized') is not True:
        raise SystemExit('FOUR_STAGE_HEAVY_HOLD_USER_PRIORITY_STANDALONE_B1_AND_S1')
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    budget=UnifiedResearchBudget()
    admission=budget.preflight()
    _write(out/'RESOURCE_ADMISSION.json',admission)
    if 2*(args.a_seconds+args.m_seconds)>budget.remaining():
        raise RuntimeError('UNIFIED_FOUR_STAGE_CAP_EXCEEDS_REMAINING_BUDGET')
    from v42_integration.aidc_sensitivity_runtime import build_new_unified_case
    from v42_integration.mess_scaling import full_stay_handoff,install_scaled_m_adapter
    from v42_integration.coordinator import run_arm
    common=load_contracts()
    root=REPORT.parents[1]
    names=('v42_integration/coordinator.py','v42_integration/a_engine.py',
        'v42_integration/a_seed.py','v42_integration/aidc_sensitivity_runtime.py',
        'v42_integration/mess_scaling.py','v42_integration/unified_contract.py',
        'v42_integration/unified_resource.py','tools/run_v42_unified_handoff_pilot.py')
    sources=[file_record(root/n) for n in names]
    started=perf_counter()
    _write(out/'ATTEMPT_FREEZE.json',dict(bindings=common['bindings'],executed_sources=sources,
        a_stage_seconds=args.a_seconds,m_stage_seconds=args.m_seconds,Threads=1,
        Heavy_workers=1,old_UB_LB_transferred=False,auto_retry=False,
        MESS_scope='S1_TWO_ACTIVE_FIVE_SITES_PLUS_TWO_ORIGINAL_INACTIVE',
        Full96_planning=True,Full96_Actual='NOT_RUN',integrated_PASS_requires_four_real_stages=True))
    import psutil
    stop=threading.Event();memory=[]
    def monitor():
        process=psutil.Process()
        while not stop.is_set():
            row=process.memory_info();vm=psutil.virtual_memory()
            memory.append(dict(elapsed_seconds=perf_counter()-started,RSS_bytes=row.rss,
                private_bytes=getattr(row,'private',row.rss),available_RAM_bytes=vm.available))
            if len(memory)%5==0:_write(out/'RESOURCE_MEMORY_LATEST.json',memory[-1])
            stop.wait(2.)
    thread=threading.Thread(target=monitor,daemon=True);thread.start()
    stage_receipts=[]
    result=None;failure=None
    try:
        case=build_new_unified_case(out/'PREPARATION',shared_manifest=common,
            a_call_cap=args.a_seconds,m_stage_cap=args.m_seconds)
        case.initial_mess=full_stay_handoff()
        case.unified_bindings=dict(common['bindings'],aidc_anchor=case.reference_aidc['aidc_anchor'],
            mess_anchor=case.initial_mess['plan_sha'])
        case.input_receipts.extend(sources)
        install_scaled_m_adapter(case,m1_seconds=args.m_seconds,m2_seconds=args.m_seconds)
        make_a=case.make_a_case;make_m=case.make_m_case
        def begin(stage,aidc,mess):
            pre=budget.preflight()
            row=dict(stage=stage,elapsed_seconds=perf_counter()-started,resource_admission=pre,
                input_aidc_anchor=aidc,input_mess_anchor=mess)
            stage_receipts.append(row);_write(out/'STAGE_ADMISSIONS.json',stage_receipts)
            print(json.dumps(dict(stage=stage,event='BUILD_ADMITTED',remaining=budget.remaining())),flush=True)
        def make_a_record(arm,stage,mess,folder):
            begin(stage,case.reference_aidc['aidc_anchor'] if stage=='A1' else None,mess['plan_sha'])
            value=make_a(arm,stage,mess,folder)
            def progress(receipt):
                _write(out/(stage+'_BUILD_PROGRESS.json'),dict(receipt,
                    elapsed_seconds=perf_counter()-started))
            value.progress=progress
            budget.stage_context=dict(bindings=case.unified_bindings,stage=stage,
                native_case_sha=value.case_sha,input_mess_anchor=mess['plan_sha'],
                executed_source_sha=digest(sources),bound_scope='FIXED_MESS_CURRENT_A_ONLY')
            return value
        def make_m_record(arm,stage,aidc,folder):
            begin(stage,aidc['aidc_anchor'],None)
            return make_m(arm,stage,aidc,folder)
        case.make_a_case=make_a_record;case.make_m_case=make_m_record
        result=run_arm('B3',case,budget,out/'B3',planning_only=True)
    except BaseException as error:
        failure=dict(type=type(error).__name__,reason=str(error))
        import traceback
        (out/'FAILURE_TRACEBACK.txt').write_text(traceback.format_exc(),encoding='utf8')
    finally:
        stop.set();thread.join(timeout=5.)
        _write(out/'RESOURCE_MEMORY_SAMPLES.json',memory)
        _write(out/'RESOURCE_MEMORY_SUMMARY.json',dict(samples=len(memory),
            wall_seconds=perf_counter()-started,peak_RSS_bytes=max((r['RSS_bytes'] for r in memory),default=None),
            peak_private_bytes=max((r['private_bytes'] for r in memory),default=None),
            minimum_available_RAM_bytes=min((r['available_RAM_bytes'] for r in memory),default=None)))
    stages={} if result is None else result['stages']
    if not stages:
        for stage in ('A1','M1','A2','M2'):
            path=out/'B3'/stage/('A_RESULT.json' if stage.startswith('A') else 'M_STAGE_RESULT.json')
            if path.exists():stages[stage]=json.loads(path.read_text(encoding='utf8'))
    complete=all(s in stages and stages[s].get('FULL_feasible' if s.startswith('A') else 'FULL_validated')
        for s in ('A1','M1','A2','M2'))
    handoff=out/'B3'/'UNIFIED_HANDOFF_VALIDATION.json'
    audit=dict(status='PASS' if complete and handoff.exists() and failure is None else 'NOT_CERTIFIED',
        bindings=common['bindings'],failure=failure,stages={s:dict(
            status='FULL_PASS' if v.get('FULL_feasible' if s.startswith('A') else 'FULL_validated') else 'NO_FULL_POINT',
            native_case_sha=v.get('case_sha'),Native_call=v.get('Native_call'),
            AIDC_anchor=v.get('aidc_anchor'),MESS_anchor=v.get('mess',{}).get('plan_sha')) for s,v in stages.items()},
        handoff_validation=file_record(handoff) if handoff.exists() else None,
        Actual='NOT_RUN',Fresh_AC='NOT_RUN',original4x24_global_certified=False,
        all_four_stages_executed=complete,wall_seconds=perf_counter()-started,
        canonical_ledger=file_record(budget.path),executed_sources=sources)
    _write(out/'REAL_UNIFIED_HANDOFF_RESULT.json',audit)
    _write(REPORT/'REAL_UNIFIED_HANDOFF_RESULT.json',dict(audit,attempt_path=str(out)))
    print(json.dumps({k:audit[k] for k in ('status','failure','all_four_stages_executed','wall_seconds')},indent=2))
    if failure:raise SystemExit(1)


if __name__=='__main__':main()
