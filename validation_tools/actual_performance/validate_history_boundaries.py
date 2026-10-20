"""All-arm and causal-boundary validation of the isolated structural adapter."""
import sys,time
from pathlib import Path
from unittest.mock import patch
from contextlib import nullcontext
sys.path.insert(0,'D:/v44_may01_07_prepare_20261016')
out=Path(sys.argv[1]);out.mkdir(exist_ok=False)
helper=Path('D:/MobileESS_V44/runtime/v43_planning_svr12_actual_v1/campaign004/AUTONOMOUS_RECOVERY/validate_r009_final_repeated.py')
setup=helper.read_text(encoding='utf8').split('import v44_recovery_r009.current_ac_performance as performance')[0]
setup=setup.replace('out=Path(sys.argv[1]);out.mkdir(exist_ok=False)','out=Path(sys.argv[1])')
exec(compile(setup,str(helper),'exec'))
from v44.common import digest,verify
from v44_recovery_r016.current_ac_performance import live_read_scope,ExactAuditEncoding
from v44_recovery_r016.fresh_performance import live_fresh_scope
from v44_recovery_r016.operations import sources,schema_backend_sources
from v44_recovery_r016.source_io import install as source_install
from v44_recovery_r016.source_ports import install as ports_install
from v44_recovery_r016.exact_clean import install as clean_install
from v44_recovery_r016.thread_policy import numerical_threads
from v44_recovery_r016.cpu_placement import actual_cpu_scope
from v44_actual_prefix.history import scope as history_scope

# B0 and B1 have no MESS injection. The helper's B3 plan is retained for B3.
original_oracle=oracle
def oracle(arm):
    if arm=='B3':return original_oracle(arm)
    return SVR12CurrentAC(arm=arm,issue_seconds=a['issue_seconds'],sites=list(map(str,arrays['sites'])),
        power_model=None,observations=obs,mess_plan=None,day_start_seconds=a['day_start_seconds'])

candidate_sources=[record(p) for p in sorted(Path('v44_actual_prefix').glob('*.py'))]
request=read(helper.parent/'requests/2025-05-01_B3_attempt003.json')
pins=list({r['path']:r for r in request['sources']+sources()+schema_backend_sources()+candidate_sources}.values())
checks=[];measurements=[]

def run_pair(arm,label,candidate,engines,encodings,*,fresh=False,order=('r016','history')):
    values={}
    for mode in order:
        engine=engines[mode]
        engine._independent_fresh=fresh
        before=dict(engine.performance)
        with scope(),patch('v44.svr11_ac.RUNTIME',out/'AC_AUDIT'):
            reader=live_fresh_scope(engine) if fresh else live_read_scope(encodings[mode],engine)
            with reader:
                with history_scope(engine,candidate) if mode=='history' else nullcontext({}) as stats:
                    start=time.perf_counter();cpu=time.process_time();result=engine._probe(candidate)
                    wall=time.perf_counter()-start;cpu=time.process_time()-cpu
        audit=read(result['physical_audit']['path'])
        fingerprint=dict(PASS=result['PASS'],physical_steps_sha=digest(result['physical_steps']),
            raw_slots_SHA=record(audit['slots_receipt']['path'])['sha256'],
            raw_events_SHA=record(audit['physical_solve_events_receipt']['path'])['sha256'],
            native_solve_events=audit['total_physical_SolveSnap_count'])
        if fresh:
            assert not hasattr(engine,'_prefix_history_proofs'),'FRESH_PROOF_CACHE_CREATED'
            for key in ('verified_history_reuses','legacy_branch_measurement_reuses'):
                assert engine.performance[key]==before[key],'FRESH_MEASUREMENT_REUSED'
        values[mode]=fingerprint
        value=dict(arm=arm,label=label,slots=len(candidate),mode=mode,independent_Fresh=fresh,
            wall_seconds=wall,CPU_seconds=cpu,stats=stats,**fingerprint)
        measurements.append(value);print(value,flush=True)
        atomic(out/'PROGRESS.json',dict(UTC=now(),checks=checks,measurements=measurements))
    assert values['r016']==values['history'],'HISTORY_RAW_OR_PHYSICS_MISMATCH'
    checks.append(dict(arm=arm,label=label,PASS=True,physical_PASS=values['r016']['PASS']))

def engines_for(arm):
    return ({mode:oracle(arm) for mode in ('r016','history')},
        {mode:ExactAuditEncoding() for mode in ('r016','history')})

with native_zero() as denied,source_install(pins) as pool,ports_install(pool),clean_install(),numerical_threads(1),actual_cpu_scope():
    engines,encodings=engines_for('B0')
    for index,delta in enumerate([0.,.5,1.,1.5]):
        candidate=list(rows);candidate[-1]=dict(candidate[-1],P=list(candidate[-1]['P']))
        candidate[-1]['P'][0]+=delta
        run_pair('B0','fixed120_delta_'+str(delta),candidate,engines,encodings,
            order=('history','r016') if index%2 else ('r016','history'))

    # A proposed current action is not the finalized observed past in the next
    # call. The changed row must invalidate that prefix and all its suffixes.
    for arm in ('B1','B3'):
        engines,encodings=engines_for(arm)
        for size in (25,26,27):
            candidate=list(rows[:size]);candidate[-1]=dict(candidate[-1],P=list(candidate[-1]['P']))
            candidate[-1]['P'][0]+=.5
            run_pair(arm,'advance_'+str(size),candidate,engines,encodings)
        candidate=list(rows[:27]);candidate[24]=dict(candidate[24],P=list(candidate[24]['P']))
        candidate[24]['P'][0]+=.25
        run_pair(arm,'changed_observed_past',candidate,engines,encodings,order=('history','r016'))

    for arm in ('B0','B1','B3'):
        engines,encodings=engines_for(arm)
        run_pair(arm,'independent_Fresh120',rows,engines,encodings,fresh=True)

verify(pins);assert not denied
atomic(out/'RESULT.json',dict(UTC=now(),PASS=True,checks=checks,measurements=measurements,sources=candidate_sources,
    validation_source=record(__file__),Native_optimizer_calls=0,production_applied=False,
    scope='All-arm diagnostic120-slot inputs; causal advancing prefixes and changed observed past; independent full120-slot Fresh; exact Raw and physics equality, including any physical rejection.'))
