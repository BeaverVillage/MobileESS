"""User-approved reduced gate: cached search once, old engine at selected 96 Qs."""
from state_regression import *
from cached_engine import CachedPrefixEngine
import hashlib
common.OUT=PROD
import robust_search
common.OUT=HERE
FOLDER=HERE/'selected_q_gate/2025-05-12/B3'

def signature(r):
    h=hashlib.sha256()
    for k in ('v','ia','ipu','kva','losses'):h.update(np.asarray(r[k]).tobytes())
    h.update(str((r['taps'],r['caps'],r['converged'],feasible(r))).encode())
    return h.hexdigest()

def main():
    verify_method();wall=time.perf_counter();day='2025-05-12';policy='B3';source=OLD
    FOLDER.mkdir(parents=True,exist_ok=True)
    assert not (FOLDER/'RESULT.json').exists(),'DO_NOT_OVERWRITE_COMPLETED_GATE'
    files=[source/'replays'/day/policy/stage/name for stage,name in [('ETA95_ACTUAL','EXECUTION.npz'),('ETA95_ACTUAL','ACTUATOR.json'),('ETA95_QSAFE_ACTUAL','EXECUTION.npz'),('ETA95_QSAFE_ACTUAL','ACTUATOR.json'),('ETA95_QSAFE_ACTUAL','Q_CONTROL_EVENTS.json'),('ETA95_QSAFE_ACTUAL','OPENDSS_PHASE_ARRAYS.npz')]]
    files+=[ROOT/'frozen_artifacts/v41r4_may/audit'/day/'inputs/ORIGINAL_ACTUAL_BACKGROUND.npz',HERE/'cached_engine.py',PROD/'robust_search.py',PROD/'METHOD_FREEZE.json']
    hashes={str(p):sha(p) for p in files};save(FOLDER/'INPUT_HASHES.json',hashes)
    c=load_case(day,policy,0,source);baseline=arrays(source/'replays'/day/policy/'ETA95_ACTUAL/EXECUTION.npz')
    assert all(np.array_equal(v,c.z[k]) for k,v in baseline.items() if k!='Q_EXEC')
    q0=baseline['Q_EXEC'].copy();c.trajectory.mess_q_kvar[:]=q0
    fixedP=c.trajectory.mess_p_kw.copy();locations=c.trajectory.mess_locations_96x4.copy();aidc=c.trajectory.pcc_p_kw.copy()
    raw=read(source/'replays'/day/policy/'ETA95_ACTUAL/ACTUATOR.json')['trajectory'];by={(r['slot'],r['mess_id']):r for r in raw};ids=c.trajectory.mess_ids
    q_da=np.array([[by[t,m]['Q_CMD'] for m in ids] for t in range(96)])
    connected=np.array([[by[t,m]['connected'] for m in ids] for t in range(96)])
    allocate_original=NativeAllocation.allocate;allocation_cache={}
    def allocate(self,p,q):
        key=(id(p),id(q))
        if key not in allocation_cache:allocation_cache[key]=(p,q,allocate_original(self,p,q))
        return allocation_cache[key][2]
    NativeAllocation.allocate=allocate
    folder=FOLDER/'LIGHTWEIGHT';folder.mkdir(exist_ok=True)
    engine=CachedPrefixEngine(c.context,c.voltage,c.trajectory,folder)
    rows=[];events=[];times=[];candidate_times=[];starts=[];peak=0.;search_begin=time.perf_counter()
    with corrected_mapping():
        for t in range(96):
            lo,hi=q_bounds(fixedP[t],connected[t],NS(pcs_kva=400.,pcs_polygon_faces=16,active_power_limit_kw=300.))
            trials=[];slot_begin=time.perf_counter()
            def evaluate(q):
                nonlocal peak
                tic=time.perf_counter();r=engine.evaluate(t,q);candidate_times.append(time.perf_counter()-tic)
                assert not engine.fallback,'ACCELERATION_FALLBACK_REJECTED'
                trials.append(dict(Q=np.asarray(q).tolist(),signature=signature(r),feasible=feasible(r)))
                mem=psutil.Process().memory_info();peak=max(peak,getattr(mem,'peak_wset',mem.rss)/1024**3)
                if len(trials)%128==1:
                    save(FOLDER/'PROGRESS.json',dict(status='RUNNING',phase='LIGHTWEIGHT_ROBUST_SEARCH',slot=t,slots_complete=t,trial=len(trials),elapsed_seconds=time.perf_counter()-wall,peak_RAM_GB=peak))
                    print('LIGHTWEIGHT_SLOT',t,'TRIAL',len(trials),flush=True)
                return r
            q,r,event=robust_search.correct_slot(evaluate,q0[t],lo,hi,q_da=q_da[t]);elapsed=time.perf_counter()-slot_begin
            c.trajectory.mess_q_kvar[t]=q;engine.accepted_taps.append(r['taps']);rows.append(r);events.append(event);times.append(elapsed);starts.append(engine.start['taps'])
            save(folder/f'SLOT_{t:02}.json',dict(slot=t,selected_Q=q.tolist(),selected_signature=signature(r),event=event,seconds=elapsed,trials=trials,start_taps=starts[-1],final_taps=r['taps']))
            save(FOLDER/'PROGRESS.json',dict(status='RUNNING',phase='LIGHTWEIGHT_ROBUST_SEARCH',slots_complete=t+1,interventions=sum(e['status']=='Q_CORRECTED' for e in events),elapsed_seconds=time.perf_counter()-wall,peak_RAM_GB=peak))
        search_seconds=time.perf_counter()-search_begin
        engine.result(rows,search_seconds).write(folder)
        save(folder/'Q_CONTROL_EVENTS.json',events)
        execution={**baseline,'Q_EXEC':c.trajectory.mess_q_kvar.copy()}
        np.savez_compressed(folder/'EXECUTION.npz',**execution)
        assert all(np.array_equal(execution[k],baseline[k]) for k in baseline if k!='Q_EXEC')
        assert np.array_equal(fixedP,c.trajectory.mess_p_kw) and np.array_equal(locations,c.trajectory.mess_locations_96x4) and np.array_equal(aidc,c.trajectory.pcc_p_kw)
        # Exactly 96 old-engine evaluations; no old robust search is run.
        oldfolder=FOLDER/'OLD_SELECTED_Q_ONLY';oldfolder.mkdir(exist_ok=True)
        reference=PrefixEngine(c.context,c.voltage,c.trajectory,oldfolder);oldrows=[];oldseconds=[];validation_begin=time.perf_counter()
        for t in range(96):
            tic=time.perf_counter();r=reference.evaluate(t,execution['Q_EXEC'][t]);oldseconds.append(time.perf_counter()-tic)
            assert signature(r)==signature(rows[t]),('SELECTED_Q_EXACT_ARRAY_DRIFT',t)
            assert reference.trace[-1]['start_taps']==starts[t]
            assert reference.trace[-1]['final_taps']==rows[t]['taps']
            reference.accepted_taps.append(r['taps']);oldrows.append(r)
            save(FOLDER/'PROGRESS.json',dict(status='RUNNING',phase='OLD_ENGINE_SELECTED_96_Q_ONLY',slots_complete=t+1,elapsed_seconds=time.perf_counter()-wall))
        validation_seconds=time.perf_counter()-validation_begin
        reference.result(oldrows,validation_seconds).write(oldfolder)
        save(oldfolder/'SELECTED_TRIALS.json',reference.trace)
        a=arrays(oldfolder/'OPENDSS_PHASE_ARRAYS.npz');b=arrays(folder/'OPENDSS_PHASE_ARRAYS.npz')
        assert set(a)==set(b) and all(np.array_equal(a[k],b[k],equal_nan=True) if a[k].dtype.kind not in 'US' else np.array_equal(a[k],b[k]) for k in a)
    assert all(sha(p)==h for p,h in hashes.items());verify_method()
    result=dict(status='COMPLETE',audit_status='PASS',day=day,policy=policy,slots=96,gate_scope='LIGHTWEIGHT_SEARCH_ONCE_PLUS_OLD_ENGINE_AT_SELECTED_96_Q',old_full_day_search_selection_equivalence_not_claimed=True,scientific_search_unchanged=True,all_selected_Q_voltage_current_transformer_arrays_bit_identical=True,regulator_start_final_taps_bit_identical=True,P_EXEC_SoC_energy_identical=True,no_future_actual_applied=True,full_prefix_fallback=False,lightweight_robust_search_seconds=search_seconds,lightweight_seconds_per_candidate=float(np.mean(candidate_times)),lightweight_seconds_per_intervention_slot=float(np.mean([v for v,e in zip(times,events) if e['status']=='Q_CORRECTED'])) if any(e['status']=='Q_CORRECTED' for e in events) else 0.,candidate_count=len(candidate_times),old_selected_Q_evaluations=96,old_selected_Q_validation_seconds=validation_seconds,old_selected_Q_seconds_per_candidate=float(np.mean(oldseconds)),lightweight_peak_working_set_GB=peak,total_elapsed_seconds=time.perf_counter()-wall,intervention_slots=[t for t,e in enumerate(events) if e['status']=='Q_CORRECTED'],unresolved_slots=[t for t,e in enumerate(events) if e['status']=='ROBUST_Q_ONLY_UNRESOLVED'],performance_engine_SHA=sha(HERE/'cached_engine.py'),scientific_method_SHA=sha(PROD/'METHOD_FREEZE.json'))
    save(FOLDER/'RESULT.json',result);print('SELECTED_96_Q_GATE_PASS',flush=True)

if __name__=='__main__':
    try:main()
    except BaseException as exc:
        save(FOLDER/'FAILURE.json',dict(error=repr(exc),traceback=traceback.format_exc()));raise
