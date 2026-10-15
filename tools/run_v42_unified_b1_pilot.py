"""May01 B1 only: one new Known A1, followed by separately gated Actual."""
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
    parser.add_argument('--output',type=Path,default=REPORT/'B1_NEW_A1_ATTEMPT01')
    parser.add_argument('--run',action='store_true')
    parser.add_argument('--a-seconds',type=float,default=75.)
    parser.add_argument('--assembly-wall-seconds',type=float,default=360.)
    parser.add_argument('--canary-slots',type=int,default=1)
    parser.add_argument('--actual-wall-seconds',type=float,default=180.)
    parser.add_argument('--cc4-headroom-pairs',type=int,default=0)
    parser.add_argument('--diagnose-seed-only',action='store_true')
    parser.add_argument('--iis-seconds',type=float,default=15.)
    args=parser.parse_args()
    if not args.run:raise SystemExit('Use --run for the explicitly costed May01 B1 pilot.')
    # The current user scope holds construction as well as optimization.
    from v42_integration.unified_resource import require_heavy_scope
    require_heavy_scope('A1',dict(stage='A1',arm='B1',day='2025-05-01'))
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    budget=UnifiedResearchBudget()
    _write(out/'RESOURCE_ADMISSION.json',budget.preflight())
    if args.a_seconds>budget.remaining():raise RuntimeError('A1_CAP_EXCEEDS_REMAINING_BUDGET')
    from v42_integration.aidc_sensitivity_runtime import (build_new_unified_case,run_b1_prefix_canary,
        select_cc4_headroom_seed_choices)
    from v42_integration.coordinator import run_arm
    common=load_contracts();root=REPORT.parents[1]
    names=('v42_integration/coordinator.py','v42_integration/a_engine.py','v42_integration/a_seed.py',
        'v42_integration/aidc_sensitivity_runtime.py','v42_integration/unified_contract.py',
        'v42_integration/unified_resource.py','v42_a_stage_domain_v2/domain.py',
        'v42_a_stage_phase1/producer.py','v42_boundary/generator.py','tools/run_v42_unified_b1_pilot.py')
    sources=[file_record(root/n) for n in names]
    _write(out/'ATTEMPT_FREEZE.json',dict(bindings=common['bindings'],executed_sources=sources,
        arm='B1',day='2025-05-01',a_stage_seconds=args.a_seconds,Threads=1,Heavy_workers=1,
        assembly_watchdog_seconds=args.assembly_wall_seconds,minimum_available_RAM_bytes=4*1024**3,
        old_point_UB_LB_transferred=False,auto_retry=False,B3='HEAVY_HOLD',other_May_days='NOT_RUN',
        Full96_Planning=True,Full96_Actual='NOT_RUN',Fresh_AC='NOT_RUN'))
    started=perf_counter()
    import psutil
    initial_calls=len(budget.document['calls'])
    phase=dict(name='PLANNING',began=started)
    stop=threading.Event();memory=[]
    def monitor():
        process=psutil.Process()
        while not stop.is_set():
            row=process.memory_info();vm=psutil.virtual_memory()
            memory.append(dict(elapsed_seconds=perf_counter()-started,RSS_bytes=row.rss,
                private_bytes=getattr(row,'private',row.rss),available_RAM_bytes=vm.available))
            if len(memory)%5==0:_write(out/'RESOURCE_MEMORY_LATEST.json',memory[-1])
            state=json.loads(budget.path.read_text(encoding='utf8'))
            native_wall=sum(r.get('wall_seconds',0.) for r in state['calls'][initial_calls:])
            outside_native=state.get('inflight') is None
            clock_excess=(phase['name']=='PLANNING' and outside_native and
                perf_counter()-started-native_wall>args.assembly_wall_seconds) or (
                phase['name']=='ACTUAL_CANARY' and perf_counter()-phase['began']>args.actual_wall_seconds)
            if vm.available<4*1024**3 or clock_excess:
                _write(out/'WATCHDOG_STOP.json',dict(reason='RAM_OR_ASSEMBLY_PILOT_CEILING',
                    memory=memory[-1],assembly_watchdog_seconds=args.assembly_wall_seconds,
                    measured_completed_native_wall_seconds=native_wall,native_inflight=state.get('inflight')))
                import _thread
                _thread.interrupt_main()
                return
            stop.wait(2.)
    thread=threading.Thread(target=monitor,daemon=True);thread.start()
    result=None;failure=None;canary=None
    try:
        case=build_new_unified_case(out/'PREPARATION',shared_manifest=common,a_call_cap=args.a_seconds)
        if any(v!=0. for field in ('P_by_site','Q_by_site') for row in case.initial_mess[field].values() for v in row):
            raise ValueError('B1_SOURCE_MESS_OFF_REQUIRED')
        case.input_receipts.extend(sources)
        original=case.make_a_case
        def make_a(arm,stage,mess,folder):
            if (arm,stage)!=('B1','A1'):raise ValueError('B1_A1_ONLY')
            _write(out/'A1_BUILD_ADMISSION.json',budget.preflight())
            value=original(arm,stage,mess,folder)
            budget.stage_context=dict(bindings=case.unified_bindings,stage=stage,arm=arm,day=value.data[0]['day'],
                native_case_sha=value.case_sha,input_mess_anchor=mess['plan_sha'],
                executed_source_sha=digest(sources),bound_scope='FIXED_ZERO_MESS_CURRENT_A_ONLY')
            value.progress=lambda receipt:_write(out/'A1_BUILD_PROGRESS.json',dict(receipt,
                elapsed_seconds=perf_counter()-started))
            if args.cc4_headroom_pairs:
                selected=select_cc4_headroom_seed_choices(value,
                    issue_seconds=case.planning_slot_zero_seconds,pairs=args.cc4_headroom_pairs,
                    output=out/'AUTHORIZED_CC4_HEADROOM_SEED_CHOICES.json')
                if not selected['all_necessary_CDF_capacity_PASS']:
                    raise ValueError('SEED_CHOICES_NATIVE_CAPACITY_CDF_NECESSARY_CHECK_FAILED')
                value.known_seed_choices=selected['override_plans']
            if args.diagnose_seed_only:
                value.seed_diagnostic_only=True;value.seed_iis_cap=args.iis_seconds
            print('May01 B1 A1 BUILD_ADMITTED',flush=True)
            return value
        case.make_a_case=make_a
        result=run_arm('B1',case,budget,out/'B1',planning_only=True)
        if args.canary_slots:
            phase.update(name='ACTUAL_CANARY',began=perf_counter())
            canary=run_b1_prefix_canary(case,result['stages']['A1'],slots=args.canary_slots,
                output=out/'PREFIX_CANARY',profile=True)
            _write(REPORT/'AIDC_B1_VALIDATION_RESULT.json',dict(canary['receipt'],
                attempt_path=str(out),A1_result=file_record(out/'B1/A1/A_RESULT.json')))
    except BaseException as error:
        failure=dict(type=type(error).__name__,reason=str(error))
        import traceback
        (out/'FAILURE_TRACEBACK.txt').write_text(traceback.format_exc(),encoding='utf8')
    finally:
        stop.set();thread.join(timeout=5.)
        _write(out/'RESOURCE_MEMORY_SAMPLES.json',memory)
        _write(out/'RESOURCE_MEMORY_SUMMARY.json',dict(samples=len(memory),wall_seconds=perf_counter()-started,
            peak_RSS_bytes=max((r['RSS_bytes'] for r in memory),default=None),
            peak_private_bytes=max((r['private_bytes'] for r in memory),default=None),
            minimum_available_RAM_bytes=min((r['available_RAM_bytes'] for r in memory),default=None)))
    path=out/'B1'/'A1'/'A_RESULT.json'
    a={} if not path.exists() else json.loads(path.read_text(encoding='utf8'))
    full=a.get('FULL_feasible') is True and a.get('FULL_point_replay',{}).get('PASS') is True
    policy=out/'B1'/'OPTIMIZED_CONDITIONAL_CONTROL_POLICY.json'
    audit=dict(status='KNOWN_A1_FULL_FEASIBLE_POLICY_FROZEN' if full and result and failure is None else 'NOT_CERTIFIED',
        bindings=common['bindings'],arm='B1',day='2025-05-01',failure=failure,
        A1_FULL_feasible=full,A1_result=file_record(path) if path.exists() else None,
        policy=file_record(policy) if policy.exists() else None,AIDC_anchor=a.get('aidc_anchor'),
        Known_Planning_Actual='NOT_RUN',Allocation_performance='NOT_RUN',Actual='NOT_RUN',Fresh_AC='NOT_RUN',
        B3='HEAVY_HOLD',other_May_days='NOT_RUN',wall_seconds=perf_counter()-started,
        canonical_ledger=file_record(budget.path),executed_sources=sources,attempt_path=str(out))
    if canary:
        audit.update(Known_Planning_Actual=canary['receipt']['status'],
            Allocation_performance=canary['receipt']['status'],Actual='PREFIX_EXECUTED',canary=canary['receipt'])
    _write(out/'B1_NEW_A1_RESULT.json',audit);_write(REPORT/'B1_NEW_A1_RESULT.json',audit)
    print(json.dumps({k:audit[k] for k in ('status','failure','A1_FULL_feasible','wall_seconds')},indent=2))
    if failure:raise SystemExit(1)


if __name__=='__main__':main()
