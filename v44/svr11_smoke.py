"""Short physical driver checks after the seven Forecast workers release locks.

This directly probes issue-only observed GPU occupancy under actual exogenous
observations. Holding issue occupancy is a disclosed diagnostic load fixture,
not a job-event simulation or a 96-slot campaign result.
"""
from pathlib import Path
import argparse
import time
import traceback
import numpy as np

from .common import ROOT,DOC,RUNTIME,read,record,verify,atomic,now
from .config import DAYS,ARMS,axis
from .locks import coordinator,process_identity
from .svr11_hardware import HARDWARE

OUT=RUNTIME/'svr11_revision01/PHYSICAL_DRIVER_SHORT_PREFIX001'


def sources():
    return [record(ROOT/'v44'/name) for name in ('svr11_smoke.py','svr11_ac.py','svr11_actual.py',
        'svr11_grid.py','daily.py','initial_states.py')]


def observed_issue_rows(day,count=25):
    from .daily import day_inputs
    from v43_actual.case import power_model
    from v43_actual.observations import load_observations
    row=day_inputs(day);a=axis(day);native=read(row['files']['native']['path'])
    policy=read(row['files']['initial_running_authority']['path'])
    sites=sorted(native['capacities']);gpu=np.zeros(len(sites))
    for job in native['known_population']:
        if job['state']=='RUNNING':gpu[sites.index(policy['mapping'][job['job_uid']])]+=job['GPU_gang']
    if any(gpu[j]>native['capacities'][s] for j,s in enumerate(sites)):
        raise ValueError('SMOKE_ISSUE_GPU_CAPACITY_DRIFT')
    model,power_sources=power_model(read(row['files']['power_authority']['path']),native['capacities'])
    observation=load_observations(begin=a['issue_seconds'],end=a['issue_seconds']+count*900,bundle=Path(row['actual_bundle']))
    rows=[]
    for t in range(count):
        start=a['issue_seconds']+t*900;seen=observation.at(start,observed_now=start)
        physical=model.recompute(gpu[None,:],sites,[seen['weather']['values']])
        rows.append(dict(slot=t,start_seconds=start,end_seconds=start+900,GPU=gpu.tolist(),
            P=physical['PCC_P_kw'][0].tolist(),Q=physical['PCC_Q_kvar'][0].tolist(),observations=seen))
    return rows,sites,model,observation,dict(day=day,initialization=row['files']['initial_running_authority'],
        power_sources=power_sources,private_job_runtime_or_completion_reads=0,
        occupancy='ISSUE_OBSERVED_RUNNING_GPU_HELD_FIXED_FOR_DIAGNOSTIC_ONLY',future_actual_for_Planning_reads=0)


def run(root=OUT):
    from .svr11_ac import SVR11CurrentAC
    from v42_may_campaign_native90.preflight import native_zero
    root=Path(root)
    if (root/'RESULT.json').exists():raise FileExistsError('SHORT_PHYSICAL_RESULT_NEVER_OVERWRITTEN')
    root.mkdir(parents=True,exist_ok=True);frozen=sources();hardware=record(HARDWARE/'HARDWARE.json')
    atomic(root/'START.json',dict(process_identity(),UTC=now(),sources=frozen,hardware=hardware,
        scope='SHORT_DRIVER_DIAGNOSTIC_ONLY_NO_ACTUAL96_NO_GUROBI'))
    results=[]
    with native_zero() as denied:
        for day in DAYS:
            rows,sites,model,observations,inputs=observed_issue_rows(day)
            for arm in ARMS if day==DAYS[0] else ('B2',):
                verify(frozen+[hardware]);a=axis(day)
                oracle=SVR11CurrentAC(arm=arm,issue_seconds=a['issue_seconds'],sites=sites,power_model=model,
                    observations=observations,mess_plan=None,day_start_seconds=a['day_start_seconds'])
                probe=oracle.full_fresh_probe(rows)
                continuity=probe['midnight_continuity']['PASS']
                structural=(len(probe['physical_steps'])==25 and probe['RegControl_count']==40
                    and probe['Source_Initial_State_independent'] and continuity and probe['Native_TIME_queue_processed'])
                paired=None
                if day==DAYS[0] and arm=='B1':
                    first=oracle._probe(rows[:3]);cached=oracle._probe(rows[:3]);independent=oracle.full_fresh_probe(rows[:3])
                    paired=dict(PASS=first['physical_steps']==cached['physical_steps']==independent['physical_steps'],
                        exact_measurement_and_native_state_equality=True,
                        historical_measurement_reuses=oracle.performance['verified_history_reuses'],
                        native_TIME_solves_reused=0,Fresh_measurements_reused=0)
                    structural=structural and paired['PASS']
                result=dict(day=day,arm=arm,driver_contract_PASS=structural,
                    physical_test_PASS=all(r['PASS'] for r in probe['physical_steps']),
                    midnight_continuity=probe['midnight_continuity'],inputs=inputs,
                    SVR_banks=11,RegControl_count=40,Native_TIME_prefix_verified=True,
                    paired_Current_and_independent_Fresh=paired,
                    physical_probe=probe,Actual96_executed=False,Fresh96_executed=False,Native_optimize_calls=0,
                    full_campaign_security_certified=False)
                path=root/day/arm/'RESULT.json';atomic(path,result)
                results.append(dict(day=day,arm=arm,driver_contract_PASS=structural,
                    physical_test_PASS=result['physical_test_PASS'],result=record(path)))
                atomic(root/'PROGRESS.json',dict(UTC=now(),completed=results,Native_calls=0,Actual96_runs=0,Fresh96_runs=0))
    if denied:raise ValueError('SHORT_DRIVER_NATIVE_OPTIMIZE_FORBIDDEN')
    verify(frozen+[hardware])
    result=dict(PASS=all(r['driver_contract_PASS'] for r in results),
        physical_test_PASS=all(r['physical_test_PASS'] for r in results),days=list(DAYS),cases=results,
        sources=frozen,hardware=hardware,scope='SHORT_PREFIX_25_SOURCE_INITIAL_WITH_ISSUE_GPU_DIAGNOSTIC_FIXTURE',
        Native_calls=0,Actual96_runs=0,Fresh96_runs=0,full_7day_campaign_executed=False,UTC=now())
    atomic(root/'RESULT.json',result)
    atomic(DOC/'V44_PHYSICAL_DRIVER_CERTIFICATION.json',dict(result,real_prefix_evidence=record(root/'RESULT.json'),
        full_96_slot_security='NOT_CERTIFIED',job_event_driver='NOT_EXECUTED_BY_THIS_DIAGNOSTIC'))
    if result['PASS']:
        atomic(DOC/'svr11_revision01/CURRENT_AC_CERTIFICATION.json',dict(PASS=True,sources=frozen,hardware=hardware,
            real_prefix_evidence=record(root/'RESULT.json'),source_7reg_certificate_reused=False,RegControl_count=40,
            Native_TIME_prefix_verified=True,full_96_slot_security='NOT_CERTIFIED',scope=result['scope']))
    return result


def wait_and_run(root=OUT):
    from v42_may_campaign.common import LockBusy
    from .svr11_forecast_parallel import GROUP,ACTIVE
    root=Path(root);root.mkdir(parents=True,exist_ok=True);frozen=sources()
    atomic(root/'WAITING.json',dict(process_identity(),UTC=now(),status='WAITING_FORECAST_COHORT_AND_EXTERNAL_LOCKS',sources=frozen))
    while True:
        verify(frozen)
        active=read(ACTIVE) if ACTIVE.exists() else {}
        group=Path(active.get('group',str(GROUP)));result_path=group/'RESULT.json'
        if result_path.exists() and not read(result_path)['PASS']:
            raise RuntimeError('FORECAST_COHORT_FAILED_NO_AUTOMATIC_PHYSICAL_FOLLOWUP')
        if result_path.exists():
            try:
                with coordinator(root/'LEASE'):return run(root)
            except LockBusy:pass
        time.sleep(.5)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--wait-for-forecast',action='store_true');args=parser.parse_args()
    try:
        result=wait_and_run() if args.wait_for_forecast else None
        if result is None:raise PermissionError('SHORT_CHECK_REQUIRES_OWNED_EXTERNAL_LEASE;USE_WAIT_FOR_FORECAST')
        print(dict(PASS=result['PASS'],physical_test_PASS=result['physical_test_PASS']),flush=True)
    except BaseException as error:
        atomic(OUT/'FAILURE.json',dict(PASS=False,error=repr(error),traceback=traceback.format_exc(),UTC=now()))
        raise
