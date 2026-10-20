"""Alternating baseline/candidate AC probes with exact Raw comparisons."""
import sys
import time
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,'D:/v44_may01_07_prepare_20261016')
out=Path(sys.argv[1]);out.mkdir(exist_ok=False)
helper=Path('D:/MobileESS_V44/runtime/v43_planning_svr12_actual_v1/campaign004/AUTONOMOUS_RECOVERY/validate_r009_final_repeated.py')
setup=helper.read_text(encoding='utf8').split('import v44_recovery_r009.current_ac_performance as performance')[0]
setup=setup.replace('out=Path(sys.argv[1]);out.mkdir(exist_ok=False)','out=Path(sys.argv[1])')
exec(compile(setup,str(helper),'exec'))
from v44.common import digest
from v44_recovery_r015.current_ac_performance import live_read_scope,ExactAuditEncoding
from v44_recovery_r015.operations import sources,schema_backend_sources
from v44_recovery_r015.source_io import install as source_install
from v44_recovery_r015.source_ports import install as ports_install
from v44_recovery_r015.exact_clean import install as clean_install
from v44_recovery_r015.cpu_placement import actual_cpu_scope
from v44_recovery_r015.thread_policy import numerical_threads
from v44_actual_performance.current_ac import scope as candidate_scope
request=read(helper.parent/'requests/2025-05-01_B3_attempt003.json')
pins=list({r['path']:r for r in request['sources']+sources()+schema_backend_sources()}.values())
measurements=[];checks=[]
with native_zero() as denied,source_install(pins) as pool,ports_install(pool),clean_install(),numerical_threads(1),actual_cpu_scope() as placement:
    for arm in (sys.argv[2:] or ['B3','B1']):
        engines={mode:oracle(arm) for mode in ['r015','candidate']}
        encodings={mode:ExactAuditEncoding() for mode in engines}
        for index,delta in enumerate([0.,.5,1.,1.5]):
            values={}
            for mode in (['r015','candidate'] if index%2==0 else ['candidate','r015']):
                engine=engines[mode]
                candidate=list(rows);candidate[-1]=dict(candidate[-1],P=candidate[-1]['P'].copy())
                candidate[-1]['P'][0]+=delta
                adapter=live_read_scope if mode=='r015' else candidate_scope
                with scope(),patch('v44.svr11_ac.RUNTIME',out/'AC_AUDIT'),adapter(encodings[mode],engine):
                    cpu=time.process_time();start=time.perf_counter()
                    result=engine._probe(candidate)
                    elapsed=time.perf_counter()-start;cpu=time.process_time()-cpu
                    audit=read(result['physical_audit']['path'])
                    fingerprint=dict(PASS=result['PASS'],physical_steps_sha=digest(result['physical_steps']),raw_slots_SHA=record(audit['slots_receipt']['path'])['sha256'],raw_events_SHA=record(audit['physical_solve_events_receipt']['path'])['sha256'])
                    value=dict(arm=arm,mode=mode,delta=delta,warmup=index==0,wall_seconds=elapsed,CPU_seconds=cpu,**fingerprint)
                    values[mode]=fingerprint;measurements.append(value)
                    print(value,flush=True)
                    atomic(out/'PROGRESS.json',dict(measurements=measurements,checks=checks))
            assert values['r015']==values['candidate'], 'PHYSICAL_OR_RAW_MISMATCH'
            checks.append(dict(arm=arm,delta=delta,PASS=True))
assert not denied
atomic(out/'RESULT.json',dict(PASS=True,measurements=measurements,checks=checks,Native_optimizer_calls=0,baseline_sources=pins,candidate_sources=[record(p) for p in Path('v44_actual_performance').glob('*.py')],scope='Real 120-slot PCC diagnostic perturbations; no whole-event service equivalence claim'))
