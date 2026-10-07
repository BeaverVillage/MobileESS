"""Validated integer incumbent control plus independently closed root LB."""
import gzip,pickle,traceback
from fractions import Fraction
from time import time
import numpy as np
from v42_pr134_b1.common import read,record,atomic
from v42_a_stage_practical.physical import Physical
from .policy import OUT,STATIC,POLICY
from .budget import Allocation
from .native import Native
from .execution import verify
from .queue import Queue,gap

def value(s,x):
    o=s.objectives[0];return o.constant+sum((c*Fraction(float(x[j])) for j,c in o.coefficients().items()),Fraction(0))

def run():
    verify()
    if (OUT/'INTEGER_STARTED.json').exists():raise PermissionError('INTEGER_CONTROL_ALREADY_STARTED_USE_CHECKPOINT')
    build=read(OUT/'INTEGER_BUILD_VERIFICATION.json')
    with gzip.open(build['state']['path'],'rb') as f:p=pickle.load(f)
    state,s=p['state'],p['typed'];p1=read(OUT/'P1_RESULT.json');physical=Physical(state,s)
    q=Queue();root=q.add(None);q.close_lp(root.id,Fraction(p1['exact_valid_LB']),row_closed=True,column_closed=True)
    budget=Allocation(POLICY['control_allocation_seconds']);native=Native(budget)
    native.warm_point=np.load(p1['closed_point']['path'])['expanded_X'];best=None;events=[];serial=0;last_checkpoint=time()
    folder=OUT/'M19/INTEGER/CONTROL';folder.mkdir(parents=True,exist_ok=True)
    atomic(OUT/'INTEGER_STARTED.json',dict(PASS=True,deadline=budget.record,component_deadline=budget.component_deadline,
        global_budget_resets=0,source_freeze=record(OUT/'INTEGER_SOURCE_FREEZE.json')))
    def checkpoint():
        atomic(OUT/'BNP_CHECKPOINT.json',dict(PASS=True,queue=q.document(),incumbent=best,root_LB=str(q.global_bound()),
            source_freeze=record(OUT/'INTEGER_SOURCE_FREEZE.json'),deadline=budget.record,rows=build['snapshot'],
            pricing_state=p1['closure_receipt'],checkpoint_unix=time(),generated_nodes=len(q.nodes)))
    def candidate(x,native_obj):
        nonlocal best,serial,last_checkpoint
        serial+=1;cfolder=folder/('C'+str(serial));cfolder.mkdir(parents=True,exist_ok=True)
        path=STATIC/'INTEGER_CANDIDATES'/('C'+str(serial)+'.npz');path.parent.mkdir(exist_ok=True)
        np.savez_compressed(path,X=x)
        # Raw candidate is immutable before any independent reconstruction.
        verification=physical.verify(x);U=value(s,x);L=q.global_bound();g=None
        if verification['PASS'] and L is not None and U>=L:g=gap(L,U)
        receipt=dict(PASS=verification['PASS'],raw=record(path),verification=verification,exact_UB=str(U),
            full_domain_LB=str(L),gap=None if g is None else float(g),exact_gap=None if g is None else str(g),
            native_active_ObjBound_not_used_as_full_domain_bound=True,native_objective=native_obj)
        atomic(cfolder/'FULL_ORIGINAL_A1_REPLAY.json',receipt)
        if verification['PASS'] and g is not None and (best is None or U<Fraction(best['exact_UB'])):
            best=dict(exact_UB=str(U),UB=float(U),exact_LB=str(L),LB=float(L),exact_gap=str(g),gap=float(g),
                candidate=record(path),verification=record(cfolder/'FULL_ORIGINAL_A1_REPLAY.json'))
            atomic(OUT/'VALIDATED_INTEGER_INCUMBENT.json',dict(PASS=True,**best));print('INTEGER_INCUMBENT',float(U),float(g),flush=True)
        events.append(dict(unix=time(),native_objective=native_obj,independent_PASS=verification['PASS'],valid_UB=None if best is None else best['UB'],
            valid_LB=float(L),global_gap=None if best is None else best['gap']))
        if time()-last_checkpoint>=300 or best is not None:checkpoint();last_checkpoint=time()
    native.incumbent_callback=candidate;checkpoint()
    result=dict(P1_accepted=False,classification=None,global_gap=None,global_LB=float(q.global_bound()),global_UB=None,
        BNP_generated_nodes=1,BNP_closed_LP_nodes=1,BNP_processed_children=0,control_is_not_full_domain_MIP_bound=True)
    try:
        rec,raw=native.solve(s,folder,'INTEGER_CONTROL')
        if 'X' in raw:candidate(raw['X'],rec['objective'])
        accepted=bool(best and best['gap']<=.005 and rec['status']==2)
        result.update(P1_accepted=accepted,classification='A_PRACTICAL_SOLVER_P1_GAP_LE_0P5' if accepted else 'A_ROWCOL_PHASE1_SUCCESS_BNP_PENDING',
            native_control_status=rec['status'],native_control_Nodes=rec['NodeCount'],native_control_MIPGap=rec['MIPGap'],
            incumbent=best,global_UB=None if best is None else best['UB'],global_gap=None if best is None else best['gap'],
            inherited_P1_native_OPTIMAL_required=True,full_domain_integer_gap_certificate=accepted)
        if accepted:
            atomic(OUT/'P1_FULL_DOMAIN_INTEGER_GAP_CERTIFICATE.json',dict(PASS=True,kind='OTHER_VALID_INTEGER_DOMAIN_CERTIFICATE',
                full_scientific_domain_covered=True,full_domain_root_LB_gate=record(OUT/'P1_INTEGER_ENTRY_GATE.json'),
                integer_incumbent=best,original_A1_replayed=True,root_queue= q.document(),
                generated_other_nodes=0,all_other_generated_nodes_exactly_fathomed=True,target_gap=.005,
                LP_closure_alone_not_integer_closure=True,integer_primal_plus_full_domain_LB_proves_gap=True,
                exact_global_optimum_not_claimed=True,inherited_native_P1_status_and_gap_convention_preserved=True))
    except Exception as error:result.update(classification='A_NUMERICAL_INCONCLUSIVE',stop_reason=repr(error),traceback=traceback.format_exc(),incumbent=best)
    finally:
        checkpoint();atomic(OUT/'INTEGER_INCUMBENT_TRACE.json',dict(events=events))
        result.update(native_seconds=native.native_seconds,Work=sum(c['Work'] or 0 for c in native.calls),elapsed_wall_seconds=budget.accounted(),
            peak_RSS_bytes=max((c.get('peak_RSS_bytes') or 0 for c in native.calls),default=0))
        atomic(OUT/'INTEGER_NATIVE_CALLS.json',dict(calls=native.calls));atomic(OUT/'INTEGER_RESULT.json',result)
        print('INTEGER_RESULT',result['classification'],result.get('stop_reason'),flush=True)
    return result
if __name__=='__main__':run()
