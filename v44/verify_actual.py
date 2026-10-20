"""Small real SVR12 cache/Fresh check and one Native0 B1 prefix canary."""
from pathlib import Path
from time import perf_counter
import traceback
import numpy as np
from .common import ROOT,DOC,RUNTIME,read,record,verify,atomic,digest,now
from .locks import coordinator,worker_slot,process_identity
from .svr12 import HARDWARE,DIRECTORY,ORIGIN,SVR12CurrentAC
from .config import axis

OUT=RUNTIME/'v43_planning_svr12_actual_v1/ACTUAL_SHORT_CANARY003'

def run():
    from v42_may_campaign_native90.preflight import native_zero
    from v43_actual.observations import load_observations
    from .daily import day_inputs,export_a
    from .planning import golden
    from .execution import short_validation
    from .worker import actual
    if OUT.exists():raise FileExistsError('NEW_SHORT_VALIDATION_ROOT_REQUIRED')
    OUT.mkdir(parents=True);a=axis('2025-05-01');day=day_inputs('2025-05-01')
    sources=[record(ROOT/'v44'/n) for n in ('svr12.py','svr12_policy.py','svr11_ac.py',
        'svr11_actual.py','worker.py','daily.py','execution.py','actual_policy.py')]
    sources+=list(day['files'].values())+[record(HARDWARE/'HARDWARE.json')]
    atomic(OUT/'START.json',dict(process_identity(),UTC=now(),sources=sources))
    with coordinator(OUT/'LEASE') as lease,native_zero() as denied:
        old=read(ORIGIN/'RESULT.json');path=old['sources'][1]['path']
        with np.load(path,allow_pickle=False) as z:arrays={k:z[k].copy() for k in z.files}
        obs=load_observations(begin=a['issue_seconds'],end=a['end_seconds'],bundle=Path(day['actual_bundle']))
        rows=[]
        for t in range(25):
            when=a['issue_seconds']+900*t
            rows.append(dict(slot=t,start_seconds=when,end_seconds=when+900,GPU=arrays['GPU'][t].tolist(),
                P=arrays['PCC_P_kw'][t].tolist(),Q=arrays['PCC_Q_kvar'][t].tolist(),
                observations=obs.at(when,observed_now=when)))
        oracle=SVR12CurrentAC(arm='B1',issue_seconds=a['issue_seconds'],sites=list(map(str,arrays['sites'])),
            power_model=None,observations=obs,mess_plan=None,day_start_seconds=a['day_start_seconds'])
        first=oracle._probe(rows);cached=oracle._probe(rows);fresh=oracle.full_fresh_probe(rows)
        pair=dict(PASS=first['physical_steps']==cached['physical_steps']==fresh['physical_steps'],
            hardware=record(HARDWARE/'HARDWARE.json'),RegControl_count=fresh['RegControl_count'],
            midnight_continuity=fresh['midnight_continuity'],historical_reuses=oracle.performance['verified_history_reuses'],
            Fresh_native_state_reused=False,full_96_execution_claimed=False,Native_calls=0)
        atomic(OUT/'CURRENT_FRESH_PAIR.json',pair)
        if not pair['PASS'] or pair['RegControl_count']!=43 or not pair['midnight_continuity']['PASS']:
            raise ValueError('SVR12_CURRENT_FRESH_NATIVE_TIME_PAIR_FAILED')
        certificate=dict(PASS=True,RegControl_count=43,SVR_count=12,hardware=record(HARDWARE/'HARDWARE.json'),
            sources=sources,real_prefix_evidence=record(OUT/'CURRENT_FRESH_PAIR.json'),
            successful_full_fixed_plan_raw=record(DIRECTORY/'REFERENCE_C_RAW_REPLAY.json'),
            old_7reg_or_SVR11_certificate_reused=False,Native_TIME_prefix_verified=True,
            scope='ACTUAL_ONLY_SOURCE_EXACT_CACHE_AND_NATIVE_TIME_PREFIX',UTC=now())
        atomic(DIRECTORY/'CURRENT_AC_CERTIFICATION.json',certificate)
        request=dict(day='2025-05-01',arm='B1',stage='ACTUAL',worker_slot=1,
            campaign_root=str(OUT/'LEASE'),case_root=str(OUT/'CASE'),output=str(OUT/'ACTUAL'),
            root=str(OUT/'ACTUAL'),sources=sources,source_sha=digest(sources),validation_control_slots=1)
        g=golden(dict(day='2025-05-01',arm='B1',stage='A1'))
        g.update(finished_UTC=now());folder=export_a(g,dict(day='2025-05-01',arm='B1',
            input_folder=day['native_folder'],sources=sources,source_sha=digest(sources)),OUT/'AIDC','A1')
        atomic(OUT/'LEASE/PHASE.json',dict(lane='MAIN'))
        # The legacy physical bootstrap installs its own solver method guards
        # on first import. Rebind Native0 after that initialization, directly
        # around the real entry point, so no solver call can be admitted.
        with native_zero() as entry_denied,worker_slot('2025-05-01','B1',1,root=OUT/'LEASE',lease=lease) as who,short_validation(request,lease,who):
            result=actual(request,folder,None)
        verify(sources)
        outcome=dict(PASS=bool(result['PASS']) and not denied and not entry_denied,UTC=now(),pair=record(OUT/'CURRENT_FRESH_PAIR.json'),
            B1_canary=record(OUT/'ACTUAL/RESULT.json'),Native_calls=0,control_slots=1,
            independent_Current_Fresh_prefix_slots=25,
            Actual96_runs=0,Fresh96_runs=0,all_arm_routing='LIGHTWEIGHT_TESTS',sources=sources)
        atomic(OUT/'RESULT.json',outcome);atomic(DIRECTORY/'ACTUAL_ENTRYPOINT_CERTIFICATION.json',outcome)
        print(outcome,flush=True)
    return outcome

if __name__=='__main__':
    try:run()
    except BaseException as error:
        atomic(OUT/'FAILURE.json',dict(error=repr(error),traceback=traceback.format_exc(),UTC=now()));raise
