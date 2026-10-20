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
        encodings={mode:(SharedControlEncoding() if mode=='lightweight' else ExactImmutableEncoding()) for mode in engines}
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
                    if mode=='lightweight' and not fresh:
                        stack.enter_context(clock_scope())
                        active_store=stack.enter_context(content_install(out/'AC_AUDIT'))
                    stack.enter_context(scope())
                    stack.enter_context(patch.object(ac,'RUNTIME',out/'AC_AUDIT'))
                    stack.enter_context(live_fresh_scope(e) if fresh else live_read_scope(encodings[mode],e))
                    stats=stack.enter_context(history.scope(e,candidate))
                    began=time.perf_counter();value=e._probe(candidate);elapsed=time.perf_counter()-began
                    audit=read(value['physical_audit']['path'])
                    values[mode]=dict(PASS=value['PASS'],physical_steps_SHA=digest(value['physical_steps']),
                        raw_slots_SHA=record(audit['slots_receipt']['path'])['sha256'],
                        raw_events_SHA=record(audit['physical_solve_events_receipt']['path'])['sha256'],
                        native_solves=audit['total_physical_SolveSnap_count'])
                    details[mode]=dict(seconds=elapsed,stats=stats,storage_counts=dict(active_store[0].counts) if mode=='lightweight' and not fresh else {},
                        bank_counts=dict(getattr(e,'_r034_bank_gate_counts',{})),
                        control_counts=dict(getattr(e,'_r034_control_key_counts',{})))
            assert values['baseline']==values['lightweight'],(arm,step,values)
            assert details['lightweight']['bank_counts']['calls']>0
            if step=='changed_candidate':
                # Real immutable/mutable object graph with its actual sharing.
                from v42_voltage_control.integration import canonical
                graph=e._scenario_audit
                times={m:[] for m in engines};sizes={}
                old_encoder,new_encoder=ExactImmutableEncoding(),SharedControlEncoding()
                for turn in range(8):
                    raw={}
                    for m,encoder in (('baseline',old_encoder),('lightweight',new_encoder)):
                        began=time.perf_counter()
                        raw[m]=(encoder.canonical_list(graph.rows,canonical),encoder.canonical_list(graph.events,canonical))
                        times[m].append(time.perf_counter()-began)
                    assert raw['baseline']==raw['lightweight']
                    sizes=dict(slots=len(raw['baseline'][0]),events=len(raw['baseline'][1]))
                details['encoding_component']=dict(medians={m:median(t[1:]) for m,t in times.items()},
                    speedup=median(times['baseline'][1:])/median(times['lightweight'][1:]),sizes=sizes,
                    shared_control_rows=new_encoder.shared_control_rows,new_identity_hits=new_encoder.identity_hits)
            check=dict(arm=arm,step=step,PASS=True,fingerprint=values['baseline'],details=details)
            checks.append(check);atomic(out/'PROGRESS.json',dict(UTC=now(),checks=checks))
            print(arm,step,'PASS',flush=True)
    assert not denied
atomic(out/'RESULT.json',dict(UTC=now(),PASS=True,checks=checks,Native_optimizer_calls=0,
    production_worker_modified=False,scope='B1/B3 32-slot actual observation probes, exact shared-file storage, changed final candidate and independent Fresh; complete Raw and native solve trace equality'))
