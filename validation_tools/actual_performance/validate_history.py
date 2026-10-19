"""Alternating r016 and structural history audit reuse on real AC prefixes."""
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
from v44_recovery_r016.operations import sources,schema_backend_sources
from v44_recovery_r016.source_io import install as source_install
from v44_recovery_r016.source_ports import install as ports_install
from v44_recovery_r016.exact_clean import install as clean_install
from v44_recovery_r016.thread_policy import numerical_threads
from v44_recovery_r016.cpu_placement import actual_cpu_scope
from v44_actual_prefix.history import scope as history_scope
candidate_sources=[record(p) for p in Path('v44_actual_prefix').glob('*.py')]
request=read(helper.parent/'requests/2025-05-01_B3_attempt003.json')
pins=list({r['path']:r for r in request['sources']+sources()+schema_backend_sources()+candidate_sources}.values())
checks=[];measurements=[]
with native_zero() as denied,source_install(pins) as pool,ports_install(pool),clean_install(),numerical_threads(1),actual_cpu_scope():
    for arm in (sys.argv[2:] or ['B3','B1']):
        engines={mode:oracle(arm) for mode in ['r016','history']}
        encodings={mode:ExactAuditEncoding() for mode in engines}
        for index,delta in enumerate([0.,.5,1.,1.5]):
            values={}
            for mode in (['r016','history'] if index%2==0 else ['history','r016']):
                engine=engines[mode]
                candidate=list(rows);candidate[-1]=dict(candidate[-1],P=candidate[-1]['P'].copy());candidate[-1]['P'][0]+=delta
                with scope(),patch('v44.svr11_ac.RUNTIME',out/'AC_AUDIT'),live_read_scope(encodings[mode],engine):
                    adapter=history_scope(engine,candidate) if mode=='history' else nullcontext({})
                    with adapter as stats:
                        start=time.perf_counter();cpu=time.process_time();result=engine._probe(candidate)
                        wall=time.perf_counter()-start;cpu=time.process_time()-cpu
                audit=read(result['physical_audit']['path']);raw=read(audit['path']) if 'path' in audit else audit
                fingerprint=dict(PASS=result['PASS'],physical_steps_sha=digest(result['physical_steps']),
                    raw_slots_SHA=record(audit['slots_receipt']['path'])['sha256'],raw_events_SHA=record(audit['physical_solve_events_receipt']['path'])['sha256'],
                    native_solve_events=raw['total_physical_SolveSnap_count'])
                values[mode]=fingerprint
                value=dict(arm=arm,mode=mode,delta=delta,warmup=index==0,wall_seconds=wall,CPU_seconds=cpu,stats=stats,**fingerprint)
                measurements.append(value);print(value,flush=True)
                atomic(out/'PROGRESS.json',dict(UTC=now(),checks=checks,measurements=measurements))
            assert values['r016']==values['history'],'HISTORY_RAW_OR_PHYSICS_MISMATCH'
            checks.append(dict(arm=arm,delta=delta,PASS=True))
verify(pins);assert not denied
atomic(out/'RESULT.json',dict(UTC=now(),PASS=True,checks=checks,measurements=measurements,sources=candidate_sources,
    validation_source=record(__file__),Native_optimizer_calls=0,production_applied=False,
    scope='Real120-slot fixed physical prefix and diagnostic current-P changes; native chronological solves retained; current candidate full checks; not complete native checkpoint cloning.'))
