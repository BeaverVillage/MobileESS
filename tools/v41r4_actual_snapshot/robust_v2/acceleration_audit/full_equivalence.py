"""Independent whole-search order/result regression plus 96-slot equivalence."""
from state_regression import *
from cached_engine import CachedPrefixEngine
import hashlib

common.OUT=PROD
import robust_search
common.OUT=HERE

def signature(r):
    h=hashlib.sha256()
    for k in ('v','ia','ipu','kva','losses'):h.update(np.asarray(r[k]).tobytes())
    h.update(str((r['taps'],r['caps'],r['converged'],feasible(r))).encode())
    return h.hexdigest()

def main():
    start=time.time();verified=verify_method();before={str(PROD/n):sha(PROD/n) for n in ('METHOD_FREEZE.json','METHOD_CODE_BINDING.json','EXECUTION_BINDING.json','robust_search.py','frozen_code/qsafe.py')}
    save(HERE/'FULL_EQUIVALENCE_PLAN.json',dict(status='FROZEN_BEFORE_EXTENDED_AUDIT',source_hashes=before,performance_engine_SHA=sha(HERE/'cached_engine.py'),cases_96=[['2025-05-01','B2'],['2025-05-12','B3']],full_search_case=['2025-05-12','B3',30],require_all_evaluated_Q_points_same_order=True,require_exact_arrays_and_accepted_Q=True,search_algorithm_modified=False))
    original_allocate=NativeAllocation.allocate;allocation_cache={}
    def allocate(self,p,q):
        key=(id(p),id(q))
        if key not in allocation_cache:allocation_cache[key]=(p,q,original_allocate(self,p,q))
        return allocation_cache[key][2]
    NativeAllocation.allocate=allocate
    trajectories=[]
    with corrected_mapping():
        for day,policy,source in [('2025-05-01','B2',PROD),('2025-05-12','B3',OLD)]:
            c=load_case(day,policy,0,source);folder=HERE/f'96_{day}_{policy}';folder.mkdir(exist_ok=True)
            engine=CachedPrefixEngine(c.context,c.voltage,c.trajectory,folder);rows=[];tic=time.perf_counter()
            for t in range(96):
                r=engine.evaluate(t,c.z['Q_EXEC'][t]);engine.accepted_taps.append(r['taps']);rows.append(r)
                for key,field in [('v','voltage_pu'),('ia','phase_current_a'),('ipu','phase_current_loading_pu'),('kva','transformer_total_kva_loading_pu')]:
                    assert np.array_equal(r[key],c.base[field][t],equal_nan=True),('SEQUENTIAL_BIT_MISMATCH',day,t,key,float(np.nanmax(np.abs(r[key]-c.base[field][t]))))
                assert r['taps']==c.base['regulator_taps'][t].tolist() and r['caps']==c.base['capacitor_states'][t].tolist()
            elapsed=time.perf_counter()-tic;result=engine.result(rows,elapsed)
            assert not engine.fallback
            trajectories.append(dict(day=day,policy=policy,slots_bit_identical=96,cached_seconds=elapsed,compiled_engines=engine.compile_count,native_solves=engine.solve_count,P_and_Q_schedule_unchanged=True))
            save(HERE/'96_SLOT_REGRESSION.json',dict(status='PASS',cases=trajectories));print('96_SLOT_PASS',day,elapsed,flush=True)
            del c,engine,rows;allocation_cache.clear();gc.collect()
        c=load_case('2025-05-12','B3',30,OLD);q0=c.z['Q_EXEC'][30];q_da=np.asarray(c.events[30]['Q_original']);full=[];atimes=[];btimes=[]
        folder=HERE/'FULL_SEARCH_CACHED';folder.mkdir(exist_ok=True);cached=CachedPrefixEngine(c.context,c.voltage,c.trajectory,folder);cached.accepted_taps=c.engine.accepted_taps.copy()
        def a_eval(q):
            tic=time.perf_counter();r=c.engine.evaluate(30,q);atimes.append(time.perf_counter()-tic);full.append((q.copy(),signature(r)))
            if len(full)%64==0:
                gc.collect();save(HERE/'FULL_SEARCH_PROGRESS.json',dict(mode='A_AUTHORITATIVE_FULL_PREFIX',trials=len(full),elapsed_seconds=time.time()-start,RSS_GB=psutil.Process().memory_info().rss/1024**3));print('AUTHORITATIVE',len(full),flush=True)
            return r
        tic=time.perf_counter();aq,ar,ae=robust_search.correct_slot(a_eval,q0,c.lower,c.upper,q_da=q_da);a_seconds=time.perf_counter()-tic
        save(HERE/'A_FULL_SEARCH.json',dict(Q=aq.tolist(),signature=signature(ar),event=ae,seconds=a_seconds,trials=len(full),candidate_seconds=atimes,trial_Q=[q.tolist() for q,s in full],trial_result_SHA=[s for q,s in full]))
        position=0
        def b_eval(q):
            nonlocal position
            assert position<len(full) and np.array_equal(q,full[position][0]),('SEARCH_ORDER_DRIFT',position)
            tic=time.perf_counter();r=cached.evaluate(30,q);btimes.append(time.perf_counter()-tic)
            assert signature(r)==full[position][1],('EXACT_TRIAL_ARRAY_DRIFT',position)
            position+=1
            if position%64==0:save(HERE/'FULL_SEARCH_PROGRESS.json',dict(mode='B_CACHED',trials=position,expected=len(full),elapsed_seconds=time.time()-start));print('CACHED',position,flush=True)
            return r
        tic=time.perf_counter();bq,br,be=robust_search.correct_slot(b_eval,q0,c.lower,c.upper,q_da=q_da);b_seconds=time.perf_counter()-tic
        assert position==len(full) and np.array_equal(aq,bq) and signature(ar)==signature(br)
        for key in ('evaluations','unique_Q_trials','phase_trial_counts','feasible_candidates_found','status','optimizer_calls','sum_squared_delta_Q'):assert ae[key]==be[key],('FROZEN_SEARCH_EVENT_DRIFT',key)
        assert not cached.fallback
        save(HERE/'B_FULL_SEARCH.json',dict(Q=bq.tolist(),signature=signature(br),event=be,seconds=b_seconds,trials=position,candidate_seconds=btimes))
        cached.odd.Basic.ClearAll();cached.odd=None
    assert all(sha(p)==h for p,h in before.items());verify_method()
    save(HERE/'FULL_EQUIVALENCE_RESULT.json',dict(status='COMPLETE',audit_status='PASS',all_Q_trials_identical_order_and_bit_identical_outputs=True,accepted_Q_bit_identical=True,full_search_trials=len(full),selected_Q=aq.tolist(),search_status=ae['status'],candidate_mean_seconds_A=float(np.mean(atimes)),candidate_mean_seconds_B=float(np.mean(btimes)),candidate_speedup=float(np.sum(atimes)/np.sum(btimes)),intervention_seconds_A=a_seconds,intervention_seconds_B=b_seconds,intervention_speedup=a_seconds/b_seconds,trajectory_regressions=trajectories,method_and_sources_unchanged=True,performance_engine_SHA=sha(HERE/'cached_engine.py'),elapsed_seconds=time.time()-start))
    print('FULL_EQUIVALENCE_PASS',a_seconds,b_seconds,a_seconds/b_seconds,flush=True)

if __name__=='__main__':
    try:main()
    except BaseException as exc:save(HERE/'FULL_EQUIVALENCE_FAILURE.json',dict(error=repr(exc),traceback=traceback.format_exc()));raise
