"""Continue the same frozen64 experiment by promoting ALL remaining rows."""
import gzip,pickle,traceback
from fractions import Fraction
from time import perf_counter
import numpy as np
from v42_pr134_b1.common import read,record,atomic,table
from v42_a_stage_phase1.core import elastic_master,primal_replay,verify_sign_convention,phase_objective,verify_zero
from v42_a_stage_compact_rowgen.lift import expanded_point
from v42_a_stage_compact_rowgen.budget import Budget
from .policy import OUT,STATIC
from .native import Native
from .execution import verify

def run():
    verify();budget=Budget();budget.remaining()
    if (OUT/'FULLROW_CONTINUATION_STARTED.json').exists():raise PermissionError('CONTINUATION_ALREADY_STARTED_NO_RESET')
    previous=read(OUT/'FROZEN64_ROWGEN_SEGMENT0_RESULT.json')
    source=read(OUT/'BUILD_VERIFICATION.json');initial_phi=Fraction(source['exact_Phi_before'])
    with gzip.open(source['state']['path'],'rb') as f:state=pickle.load(f)
    s=state['compact'];master=elastic_master(s,state['grows'],weights_by_row=state['row_weights']);reference=elastic_master(state['reference'],state['grows'],weights_by_row=state['row_weights'])
    native=Native(budget);folder=OUT/'M19/FROZEN64/ALL_REMAINING_ROWS';folder.mkdir(parents=True,exist_ok=True)
    atomic(OUT/'FULLROW_CONTINUATION_STARTED.json',dict(PASS=True,same_frozen64_batch=record(OUT/'FROZEN_BATCH_IDENTITY.json'),
        source_freeze=record(OUT/'PRACTICAL_SOURCE_FREEZE.json'),deadline=budget.record,new_activation_rounds=0,previous_segment=record(OUT/'FROZEN64_ROWGEN_SEGMENT0_RESULT.json')))
    result=dict(previous,stage='A2_FROZEN64',classification=None,stop_reason=None,row_closed=False,certified_Phi_after=None,continuation=True,
        candidate_repricing_or_reselection=False,activation_rounds=1,activated_STAY=32,activated_migration=32)
    result.pop('traceback',None)
    try:
        old=primal_replay(master.snapshot,state['prior'])
        if not old['PASS'] or phase_objective(master,state['prior'])!=initial_phi:raise ValueError('PREVIOUS_FEASIBLE_POINT_NOT_PRESERVED')
        atomic(folder/'INCLUSION_WITNESS.json',dict(PASS=True,primal=old,Phi=str(initial_phi),previous_point=source['preserved_point'],raw_increase_not_real_worsening=True))
        rec,raw=native.solve(master.snapshot,folder,'PHASE_I')
        if rec['status']!=2 or not all(k in raw for k in ('X','Pi','RC')):raise RuntimeError('FULLROW_NATIVE_NOT_OPTIMAL:'+str(rec['status']))
        sign=verify_sign_convention(master.snapshot,raw['Pi'],raw['RC']);replay=primal_replay(master.snapshot,raw['X']);phi=phase_objective(master,raw['X'])
        atomic(folder/'RAW_REPLAY.json',dict(PASS=sign['PASS'] and replay['PASS'],sign=sign,primal=replay,Phi=str(phi),raw_saved_first=True))
        if not sign['PASS'] or not replay['PASS']:raise ValueError('FULLROW_RAW_REPLAY_FAIL')
        x=expanded_point(state,raw['X']);rx=np.r_[x,raw['X'][s.matrix.shape[1]:]];original=primal_replay(reference.snapshot,rx)
        same=phi==phase_objective(reference,rx)
        point=STATIC/'FROZEN64_CLOSED_POINT.npz';np.savez_compressed(point,X=raw['X'],expanded_X=rx)
        zero=verify_zero(reference,rx)
        cert=dict(PASS=original['PASS'] and same,full_compact=replay,expanded_original=original,zero=zero,
            Phi=str(phi),same_original_weighted_Phi=same,point=record(point),all_original_rows=state['reference'].matrix.shape[0],
            omitted_rows=0,all_original_rows_evaluated=True,all_original_rows_present=True)
        atomic(folder/'ROW_CLOSED_CERTIFICATE.json',cert)
        if not cert['PASS']:raise ValueError('FULL_ORIGINAL_EXPANDED_REPLAY_FAIL:'+str(original))
        result.update(row_closed=True,certified_Phi_after=float(phi),exact_Phi_after=str(phi),certified_zero=zero['PASS'],
            reduction=float((initial_phi-phi)/initial_phi),closure_certificate=record(folder/'ROW_CLOSED_CERTIFICATE.json'),
            classification='A2_ZERO_READY_A4' if zero['PASS'] else 'A2_ROW_CLOSED_READY_A3',
            closed_master_folder=str(folder),included_rows=list(range(s.matrix.shape[0])))
    except Exception as error:result.update(classification='A_NUMERICAL_INCONCLUSIVE',stop_reason=repr(error),traceback=traceback.format_exc())
    finally:
        result.update(continuation_calls=native.calls,continuation_native_seconds=native.native_seconds,
            native_seconds=previous['native_seconds']+native.native_seconds,Work=previous['Work']+sum(c['Work'] or 0 for c in native.calls),
            elapsed_wall_seconds=budget.accounted(),maximum_factor_nnz=max(previous['maximum_factor_nnz'],max((c['max_factor_nnz'] or 0 for c in native.calls),default=0)),
            maximum_factor_memory_GB=max(previous['maximum_factor_memory_GB'],max((c['max_factor_memory_GB'] or 0 for c in native.calls),default=0)),
            peak_RSS_bytes=max(previous['peak_RSS_bytes'],max((c['peak_RSS_bytes'] or 0 for c in native.calls),default=0)))
        atomic(OUT/'FROZEN64_RESULT.json',result);print('FROZEN64_CONTINUATION_RESULT',result['classification'],result.get('stop_reason'),flush=True)
    return result
if __name__=='__main__':run()
