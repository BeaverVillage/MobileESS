"""Frozen64 experiment: complete row closure before any pricing or materiality."""
import gzip,pickle,traceback
from time import perf_counter
from fractions import Fraction
import numpy as np
from v42_pr134_b1.common import atomic,read,record,table
from v42_a_stage_phase1.core import elastic_master,primal_replay,verify_sign_convention,phase_objective,verify_zero
from .policy import OUT,STATIC,POLICY
from .execution import verify
from .budget import Budget
from .native import Native
from .rowgen import restricted,certified_separate
from .lift import expanded_point,full_artificial_point

def run():
    verify();budget=Budget();budget.remaining()
    if (OUT/'RUN_STARTED.json').exists():raise PermissionError('FROZEN64_EXPERIMENT_ALREADY_STARTED')
    build=read(OUT/'BUILD_VERIFICATION.json')
    if record(build['state']['path'])!=build['state']:raise PermissionError('STATIC_STATE_DRIFT')
    with gzip.open(build['state']['path'],'rb') as f:state=pickle.load(f)
    s=state['compact'];included=set(state['initial_rows']);grows=state['grows'];weights=state['row_weights']
    full=elastic_master(s,grows,weights_by_row=weights)
    reference=elastic_master(state['reference'],grows,weights_by_row=weights)
    native=Native(budget);traces=[];solves=0
    result=dict(stage='A2_FROZEN64',row_closed=False,certified_Phi_after=None,classification=None,
        activation_rounds=1,activated_STAY=32,activated_migration=32,Phi_before=float(Fraction(build['exact_Phi_before'])),
        pricing_calls=0,P1_LP_closure=False,integer_BNP_nodes=0,valid_LB=None,valid_UB=None,certified_gap=None)
    atomic(OUT/'RUN_STARTED.json',dict(PASS=True,deadline=budget.record,source_freeze=record(OUT/'SOURCE_FREEZE.json'),budget_resets=0))
    try:
        for iteration in range(1000000):
            budget.remaining();folder=OUT/'M19/FROZEN64'/('S'+str(iteration));folder.mkdir(parents=True,exist_ok=True)
            rows=tuple(sorted(included));r=restricted(s,rows)
            localg=tuple(j for j,i in enumerate(rows) if i<len(grows))
            master=elastic_master(r,localg,weights_by_row={j:weights[i] for j,i in enumerate(rows) if i<len(grows)})
            rec,raw=native.solve(master.snapshot,folder,'PHASE_I');solves+=1
            if rec['status']!=2 or not all(k in raw for k in ('X','Pi','RC')):raise ValueError('NATIVE_MASTER_NOT_CERTIFIED_OPTIMAL:'+str(rec['status']))
            sign=verify_sign_convention(master.snapshot,raw['Pi'],raw['RC']);replay=primal_replay(master.snapshot,raw['X']);phi=phase_objective(master,raw['X'])
            atomic(folder/'RAW_REPLAY.json',dict(PASS=sign['PASS'] and replay['PASS'],sign=sign,primal=replay,Phi=str(phi)))
            if not sign['PASS'] or not replay['PASS']:raise ValueError('NATIVE_RAW_REPLAY_FAIL')
            # Retain the independent old feasible point and its original Phi.
            old=primal_replay(full.snapshot,state['prior'])
            atomic(folder/'INCLUSION_WITNESS.json',dict(PASS=old['PASS'],full_compact_replay=old,Phi=str(phase_objective(full,state['prior'])),
                previous_point=build['preserved_point'],raw_new_Phi_not_replaced=True,raw_increase_is_not_real_worsening=old['PASS']))
            if not old['PASS']:raise ValueError('PRIOR_INCLUSION_WITNESS_FAIL')
            start=perf_counter();sep=certified_separate(s,raw['X'][:s.matrix.shape[1]],included);sep['seconds']=perf_counter()-start
            atomic(folder/'ROW_SEPARATION.json',sep)
            traces.append(dict(solve=iteration,Phi=float(phi),exact_Phi=str(phi),row_closed=sep['PASS'],rows=master.snapshot.matrix.shape[0],
                cols=master.snapshot.matrix.shape[1],nnz=master.snapshot.matrix.nnz,added_rows=len(sep['violated_rows']),
                Runtime=rec['native_seconds'],Work=rec['Work'],factor_nnz=rec['max_factor_nnz'],factor_memory_GB=rec['max_factor_memory_GB'],
                separation_seconds=sep['seconds'],elapsed_wall=budget.accounted()))
            table(OUT/'PHASE1_ITERATION_TRACE.csv',traces,list(traces[0]));print('ROWGEN',iteration,float(phi),len(sep['violated_rows']),flush=True)
            if (rec['max_factor_nnz'] or 0)>POLICY['factor_limit_nnz'] or (rec['max_factor_memory_GB'] or 0)>POLICY['factor_limit_GB']:raise RuntimeError('MEASURED_FACTOR_TRACTABILITY_LIMIT')
            if not sep['PASS']:included.update(sep['violated_rows']);continue
            fx=full_artificial_point(full,master,rows,raw['X'],s.matrix.shape[1]);fullreplay=primal_replay(full.snapshot,fx)
            lifted=expanded_point(state,fx);rx=np.r_[lifted,fx[s.matrix.shape[1]:]];replay_reference=primal_replay(reference.snapshot,rx)
            same=phase_objective(full,fx)==phi==phase_objective(reference,rx)
            point=STATIC/'FROZEN64_CLOSED_POINT.npz';np.savez_compressed(point,X=fx,expanded_X=rx)
            cert=dict(PASS=fullreplay['PASS'] and replay_reference['PASS'] and same,all_original_rows=state['reference'].matrix.shape[0],
                full_compact=fullreplay,expanded_original=replay_reference,Phi=str(phi),same_original_weighted_Phi=same,point=record(point),
                row_separation=record(folder/'ROW_SEPARATION.json'),zero=verify_zero(reference,rx))
            atomic(folder/'ROW_CLOSED_CERTIFICATE.json',cert)
            if not cert['PASS']:raise ValueError('FULL_ORIGINAL_EXPANDED_REPLAY_FAIL')
            reduction=float((Fraction(build['exact_Phi_before'])-phi)/Fraction(build['exact_Phi_before']))
            result.update(row_closed=True,certified_Phi_after=float(phi),exact_Phi_after=str(phi),reduction=reduction,
                certified_zero=cert['zero']['PASS'],closure_certificate=record(folder/'ROW_CLOSED_CERTIFICATE.json'),
                classification='A2_ZERO_READY_A4' if cert['zero']['PASS'] else 'A2_ROW_CLOSED_READY_A3',
                closed_master_folder=str(folder),included_rows=list(rows))
            break
    except Exception as error:
        result.update(classification='A_NUMERICAL_INCONCLUSIVE',stop_reason=repr(error),traceback=traceback.format_exc())
    finally:
        result.update(master_solves=solves,Phi_trajectory=[t['Phi'] for t in traces],native_seconds=native.native_seconds,
            Work=sum(c['Work'] or 0 for c in native.calls),elapsed_wall_seconds=budget.accounted(),
            peak_RSS_bytes=max((c.get('peak_RSS_bytes') or 0 for c in native.calls),default=0),
            maximum_factor_nnz=max((c.get('max_factor_nnz') or 0 for c in native.calls),default=0),
            maximum_factor_memory_GB=max((c.get('max_factor_memory_GB') or 0 for c in native.calls),default=0))
        atomic(OUT/'NATIVE_CALLS.json',dict(calls=native.calls));atomic(OUT/'FROZEN64_RESULT.json',result)
        print('FROZEN64_RESULT',result['classification'],result.get('stop_reason'),flush=True)
    return result
if __name__=='__main__':run()
