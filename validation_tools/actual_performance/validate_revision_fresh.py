"""Full independent Fresh for B0/B1/B3, old versus r016 pure readers."""
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
from v44_recovery_r016.fresh_performance import live_fresh_scope
from v44_recovery_r016.operations import sources,schema_backend_sources
from v44_recovery_r016.source_io import install as source_install
from v44_recovery_r016.source_ports import install as ports_install
from v44_recovery_r016.exact_clean import install as clean_install
from v44_recovery_r016.thread_policy import numerical_threads
from v44_recovery_r016.cpu_placement import actual_cpu_scope
request=read(helper.parent/'requests/2025-05-01_B3_attempt003.json')
pins=list({r['path']:r for r in request['sources']+sources()+schema_backend_sources()}.values())
checks=[];measurements=[]
with native_zero() as denied,source_install(pins) as pool,ports_install(pool),clean_install(),numerical_threads(1),actual_cpu_scope():
    for index,arm in enumerate(['B0','B1','B3']):
        values={}
        for mode in (['r015','r016'] if index%2==0 else ['r016','r015']):
            engine=oracle(arm) if arm!='B0' else SVR12CurrentAC(arm=arm,issue_seconds=a['issue_seconds'],sites=list(map(str,arrays['sites'])),power_model=None,observations=obs,mess_plan=None,day_start_seconds=a['day_start_seconds'])
            original=engine._probe
            def optimized(rows):
                with live_fresh_scope(engine):return original(rows)
            adapter=patch.object(engine,'_probe',optimized) if mode=='r016' else nullcontext()
            with scope(),patch('v44.svr11_ac.RUNTIME',out/'AC_AUDIT'),adapter:
                start=time.perf_counter();cpu=time.process_time()
                value=engine.full_fresh_probe(rows)
                wall=time.perf_counter()-start;cpu=time.process_time()-cpu
            audit=read(value['physical_audit']['path'])
            assert len(value['physical_steps'])==120
            assert all(r['full_physical']['all_original_and_added_axes_checked'] for r in value['physical_steps'])
            assert engine.performance['slot_replays']==120 and engine.performance['engine_compiles']==1
            assert engine.performance['verified_history_reuses']==engine.performance['legacy_branch_measurement_reuses']==0
            fingerprint=dict(PASS=value['PASS'],physical_steps_SHA=digest(value['physical_steps']),raw_slots_SHA=record(audit['slots_receipt']['path'])['sha256'],raw_events_SHA=record(audit['physical_solve_events_receipt']['path'])['sha256'],counts=engine.performance)
            values[mode]=fingerprint
            measurements.append(dict(arm=arm,mode=mode,wall_seconds=wall,CPU_seconds=cpu,**fingerprint))
            print(measurements[-1],flush=True)
            atomic(out/'PROGRESS.json',dict(checks=checks,measurements=measurements))
        assert values['r015']==values['r016'],'INDEPENDENT_FRESH_RAW_OR_PHYSICS_MISMATCH'
        pair=[r for r in measurements if r['arm']==arm]
        times={r['mode']:r['wall_seconds'] for r in pair}
        checks.append(dict(arm=arm,PASS=True,all120slots_allnodes_allterminals_measured=True,history_reuse=0,bank_measurement_reuse=0,wall_reduction_percent=100*(1-times['r016']/times['r015'])))
verify(pins);assert not denied
atomic(out/'RESULT.json',dict(PASS=True,UTC=now(),checks=checks,measurements=measurements,sources=sources()+[record(__file__)],Native_optimizer_calls=0,scope='Fixed real120-slot independent Fresh; no whole-controller or campaign speedup claim'))
