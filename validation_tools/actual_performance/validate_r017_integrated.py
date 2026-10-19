"""Real AC parity of the packaged r017 scopes against sealed r016."""
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
from v44_recovery_r016.operations import sources as baseline_sources,schema_backend_sources
from v44_recovery_r017.operations import sources
from v44_recovery_r017.current_ac_performance import current_probe_scope,ExactAuditEncoding as R017Encoding
from v44_recovery_r017.fresh_performance import live_fresh_scope as r017_fresh
from v44_recovery_r017.source_io import install as source_install
from v44_recovery_r017.source_ports import install as ports_install
from v44_recovery_r017.exact_clean import install as clean_install
from v44_recovery_r017.thread_policy import numerical_threads
from v44_recovery_r017.cpu_placement import actual_cpu_scope

original_oracle=oracle
def oracle(arm):
    if arm=='B3':return original_oracle(arm)
    return SVR12CurrentAC(arm=arm,issue_seconds=a['issue_seconds'],sites=list(map(str,arrays['sites'])),
        power_model=None,observations=obs,mess_plan=None,day_start_seconds=a['day_start_seconds'])

candidate_sources=sources()
request=read(helper.parent/'requests/2025-05-01_B3_attempt003.json')
pins=list({r['path']:r for r in request['sources']+baseline_sources()+schema_backend_sources()+candidate_sources}.values())
checks=[];measurements=[]
with native_zero() as denied,source_install(pins) as pool,ports_install(pool),clean_install(),numerical_threads(1),actual_cpu_scope():
    for arm in ('B0','B1','B3'):
        engines={mode:oracle(arm) for mode in ('r016','r017')}
        encodings={'r016':ExactAuditEncoding(),'r017':R017Encoding()}
        for label,fresh,delta in [('cold120',False,0.),('repeat120',False,.5),('independent_Fresh120',True,0.)]:
            candidate=list(rows);candidate[-1]=dict(candidate[-1],P=list(candidate[-1]['P']));candidate[-1]['P'][0]+=delta
            values={}
            for mode in (('r017','r016') if label=='repeat120' else ('r016','r017')):
                engine=oracle(arm) if fresh else engines[mode]
                engine._independent_fresh=fresh
                with scope(),patch('v44.svr11_ac.RUNTIME',out/'AC_AUDIT'):
                    if fresh:
                        adapter=r017_fresh(engine) if mode=='r017' else live_fresh_scope(engine)
                    else:
                        adapter=current_probe_scope(engine,candidate,encodings[mode]) if mode=='r017' else live_read_scope(encodings[mode],engine)
                    with adapter as stats:
                        start=time.perf_counter();cpu=time.process_time();result=engine._probe(candidate)
                        wall=time.perf_counter()-start;cpu=time.process_time()-cpu
                audit=read(result['physical_audit']['path'])
                fingerprint=dict(PASS=result['PASS'],physical_steps_sha=digest(result['physical_steps']),
                    raw_slots_SHA=record(audit['slots_receipt']['path'])['sha256'],
                    raw_events_SHA=record(audit['physical_solve_events_receipt']['path'])['sha256'],
                    native_solve_events=audit['total_physical_SolveSnap_count'])
                if fresh:
                    assert not hasattr(engine,'_prefix_history_proofs')
                    assert engine.performance['verified_history_reuses']==engine.performance['legacy_branch_measurement_reuses']==0
                values[mode]=fingerprint
                value=dict(arm=arm,label=label,mode=mode,wall_seconds=wall,CPU_seconds=cpu,
                    history_stats=stats if mode=='r017' and not fresh else {},**fingerprint)
                measurements.append(value);print(value,flush=True)
                atomic(out/'PROGRESS.json',dict(UTC=now(),checks=checks,measurements=measurements))
            assert values['r016']==values['r017'],'R017_RAW_OR_PHYSICS_MISMATCH'
            assert values['r017']['PASS'],'DIAGNOSTIC_INPUT_PHYSICAL_FAILURE'
            checks.append(dict(arm=arm,label=label,PASS=True))
verify(pins);assert not denied
atomic(out/'RESULT.json',dict(UTC=now(),PASS=True,checks=checks,measurements=measurements,sources=candidate_sources,
    validation_source=record(__file__),Native_optimizer_calls=0,production_applied=False,
    scope='Packaged r017 combined scope against sealed r016 on diagnostic120-slot inputs: cold and repeated current candidates and new independent full Fresh per arm.'))
