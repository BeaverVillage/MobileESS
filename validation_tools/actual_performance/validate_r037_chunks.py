"""Differential complete Current AC and Fresh probes, isolated from campaign."""
import sys,time
from pathlib import Path
from contextlib import nullcontext,ExitStack
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import v44_recovery_r029
from v44_actual_bank_gate import install as bank_install
from v44_actual_control_key import install as control_install
from v44_actual_audit_encoding import ExactImmutableEncoding
from v44_actual_record_light import SharedControlEncoding
from v44_actual_content_store import install as content_install
from v44_audit_chunk_store import install as chunk_install,ChunkStore
import hashlib
from v44_actual_queue_light import clock_scope
from statistics import median
from v44_recovery_r029 import history
from v44_recovery_r029.current_ac_performance import live_read_scope
from v44_recovery_r029.fresh_performance import live_fresh_scope

out=Path(sys.argv[1]);out.mkdir(exist_ok=False)
helper=Path('D:/MobileESS_V44/runtime/v43_planning_svr12_actual_v1/campaign004/AUTONOMOUS_RECOVERY/validate_r009_final_repeated.py')
setup=helper.read_text(encoding='utf-8').split('import v44_recovery_r009.current_ac_performance as performance')[0]
setup=setup.replace('out=Path(sys.argv[1]);out.mkdir(exist_ok=False)','out=Path(sys.argv[1])')
exec(compile(setup,str(helper),'exec'))
from v44_recovery_r029.current_ac_performance import live_read_scope
from v44.common import digest
import v44.svr11_ac as ac
checks=[]
with native_zero() as denied:
    for arm in ('B1','B3'):
        engines={mode:oracle(arm) for mode in ('baseline','lightweight')}
        encodings={mode:SharedControlEncoding() for mode in engines}
        for step in ('initial','changed_candidate','Fresh'):
            candidate=list(rows[:32])
            if step=='changed_candidate':
                candidate[-1]=dict(candidate[-1],P=candidate[-1]['P'].copy())
                candidate[-1]['P'][0]+=.5
            values={};details={}
            for mode,e in engines.items():
                fresh=step=='Fresh';e._independent_fresh=fresh
                with ExitStack() as stack:
                    stack.enter_context(bank_install());stack.enter_context(control_install())
                    audit_root=out/('CHUNK_AUDIT' if mode=='lightweight' else 'BASELINE_AUDIT')
                    if not fresh:
                        stack.enter_context(clock_scope())
                        active_store=stack.enter_context(content_install(audit_root))
                        if mode=='lightweight':chunk_state=stack.enter_context(chunk_install(audit_root))
                    stack.enter_context(scope())
                    stack.enter_context(patch.object(ac,'RUNTIME',audit_root))
                    stack.enter_context(live_fresh_scope(e) if fresh else live_read_scope(encodings[mode],e))
                    stats=stack.enter_context(history.scope(e,candidate))
                    began=time.perf_counter();value=e._probe(candidate);elapsed=time.perf_counter()-began
                    audit=read(value['physical_audit']['path'])
                    def raw_sha(receipt):
                        if mode=='lightweight' and not fresh:
                            return hashlib.sha256(ChunkStore(audit_root).restore(receipt['path'])).hexdigest()
                        return record(receipt['path'])['sha256']
                    values[mode]=dict(PASS=value['PASS'],physical_steps_SHA=digest(value['physical_steps']),
                        raw_slots_SHA=raw_sha(audit['slots_receipt']),
                        raw_events_SHA=raw_sha(audit['physical_solve_events_receipt']),
                        native_solves=audit['total_physical_SolveSnap_count'])
                    details[mode]=dict(seconds=elapsed,stats=stats,storage_counts=dict(chunk_state[0].counts) if mode=='lightweight' and not fresh else {},
                        bank_counts=dict(getattr(e,'_r034_bank_gate_counts',{})),
                        control_counts=dict(getattr(e,'_r034_control_key_counts',{})))
            assert values['baseline']==values['lightweight'],(arm,step,values)
            assert details['lightweight']['bank_counts']['calls']>0
            check=dict(arm=arm,step=step,PASS=True,fingerprint=values['baseline'],details=details)
            checks.append(check);atomic(out/'PROGRESS.json',dict(UTC=now(),checks=checks))
            print(arm,step,'PASS',flush=True)
    assert not denied
atomic(out/'RESULT.json',dict(UTC=now(),PASS=True,checks=checks,Native_optimizer_calls=0,
    production_worker_modified=False,scope='B1/B3 32-slot actual observation probes, row chunks and trajectory factoring with byte-exact complete Raw reconstruction, changed final candidate and independent Fresh; complete Raw and native solve trace equality'))
