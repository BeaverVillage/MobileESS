"""Original P2 objective over complete relevant domain; gap acceptance."""
from dataclasses import replace
from fractions import Fraction
import math
import numpy as np
from v42_pr134_b1.common import read,record,atomic,sha
from v42_a_stage_domain_v2.lexstage import LexLock,rebuild_locked_snapshot,integer_objective_proof,integer_optimality_certificate
from v42_a_stage_lexfull.runner import objective_value
from v42_a_stage_phase1.core import primal_replay
from .gap import global_gap_acceptance
from .policy import OUT,STATIC

def run(native,strong,original,warm,physical,locks,folder,names=('shift_magnitude','prestart_relocation')):
    stages=[]
    domain=read(folder/'FULL_ZERO_DOMAIN_VERIFICATION.json')
    if not domain.get('PASS') or domain['full_classes']!=len(physical.state['data'][7]['classes']):
        raise ValueError('COMPLETE_RELEVANT_INTEGER_DOMAIN_REQUIRED')
    for name in names:
        locked,lockproof=rebuild_locked_snapshot(strong,locks);obj=locked.objective(name)
        query=replace(locked,objectives=(obj,)+tuple(o for o in locked.objectives if o.name!=name))
        sf=folder/'P2'/name.upper();sf.mkdir(parents=True,exist_ok=True)
        atomic(sf/'LOCK_REBUILD.json',lockproof);integrality=integer_objective_proof(original,name)
        replay=physical.verify(warm);rows=primal_replay(locked,warm)
        if not replay['PASS'] or not rows['PASS']:raise ValueError('REPLAY_PASS_LOCKED_MIP_START_REQUIRED')
        old=float(objective_value(original,warm,name));best=[old,warm.copy()];points=[]
        def candidate(x,value):
            rp=primal_replay(query,x)
            integral=np.max(abs(x[original.vtypes!='C']-np.rint(x[original.vtypes!='C'])),initial=0)<=1e-5
            phys=dict(PASS=False,reason='CURRENT_QUERY_RAW_GATE_FAILED')
            if rp['PASS'] and integral:
                try:phys=physical.verify(x)
                except Exception as e:phys=dict(PASS=False,reason=repr(e))
            val=float(objective_value(original,x,name));good=rp['PASS'] and integral and phys['PASS']
            cf=sf/'CANDIDATES'/('C'+str(len(points)));cf.mkdir(parents=True,exist_ok=True)
            atomic(cf/'ROWS.json',rp);atomic(cf/'PHYSICAL.json',phys)
            points.append(dict(value=val,PASS=bool(good),rows=record(cf/'ROWS.json'),physical=record(cf/'PHYSICAL.json')))
            if good and val<best[0]:best[:]=[val,x.copy()]
            atomic(sf/'PRIMAL_CHECKPOINT.json',dict(prior_UB=old,validated_UB=best[0],points=points,
                old_validated_point_preserved=True,callback_bound_not_acceptance_authority=True))
        native.warm_point=warm;native.warm_basis=None;native.incumbent_callback=candidate
        native.budget=native.parent_budget
        atomic(sf/'MIP_START_REPLAY.json',dict(PASS=True,rows=rows,original_physical_PASS=True,
            original_objective_value=old,prior_incumbent_kept=True,nonbinding_native_start=True))
        try:r,raw=native.solve(query,sf/'NATIVE','P2')
        finally:native.incumbent_callback=None;native.warm_point=None
        if 'X' in raw:candidate(raw['X'],r['objective'])
        warm=best[1];final=physical.verify(warm);fr=primal_replay(locked,warm)
        atomic(sf/'FINAL_ORIGINAL_PHYSICAL_REPLAY.json',final);atomic(sf/'FINAL_LOCKED_REPLAY.json',fr)
        L=r['ObjBound'] if r['status'] in (2,9,11) and r['native_error'] is None else None
        if L is not None and math.isfinite(L):L=max(0.,L)
        else:L=None
        cert=global_gap_acceptance(name,L,best[0],full_domain_verified=True,bound_verified=L is not None,
            primal_verified=final['PASS'],locks_verified=fr['PASS'],native_status=r['status'])
        exact=integer_optimality_certificate(name,best[0],L,bound_independently_validated=L is not None,
            primal_independently_validated=final['PASS'],integrality_proven=integrality['PASS'])
        atomic(sf/'EXACT_INTEGER_OPTIMALITY_CERTIFICATE.json',exact)
        cert.update(full_domain=record(folder/'FULL_ZERO_DOMAIN_VERIFICATION.json'),
            current_actual_model=record(sf/'NATIVE/INDEPENDENT_COMPILED_MODEL_VERIFICATION.json'),
            native_bound=record(sf/'NATIVE/NATIVE_RESULT.json'),physical=record(sf/'FINAL_ORIGINAL_PHYSICAL_REPLAY.json'),
            locks=record(sf/'LOCK_REBUILD.json'),independent_rational_MIP_dual_certificate=False,
            full_current_query_covers_all_native_open_branches=True,restricted_candidate_bound_used=False)
        atomic(sf/'GLOBAL_GAP_ACCEPTANCE.json',cert)
        point=STATIC/sf.relative_to(OUT)/'VALIDATED_POINT.npz';point.parent.mkdir(parents=True,exist_ok=True)
        np.savez_compressed(point,X=warm)
        stage=dict(component=name,value=best[0],valid_LB=L,gap=cert['gap'],accepted=cert['PASS'],
            native_status=r['status'],Runtime=r['native_seconds'],Work=r['Work'],point=record(point),
            certificate=record(sf/'GLOBAL_GAP_ACCEPTANCE.json'),exact_certificate=record(sf/'EXACT_INTEGER_OPTIMALITY_CERTIFICATE.json'))
        stages.append(stage);atomic(folder/'P2_CHECKPOINT.json',dict(stages=stages,prior_incumbent_preserved=True,
            native_open_nodes_retained_in_final_bound=True,full_domain=record(folder/'FULL_ZERO_DOMAIN_VERIFICATION.json')))
        if not cert['PASS']:raise RuntimeError('FULL_DOMAIN_P2_GAP_NOT_ACCEPTED:'+name)
        locks.append(LexLock(name,Fraction(round(best[0])),True,sha(sf/'GLOBAL_GAP_ACCEPTANCE.json')))
        print('GLOBAL_GAP_STAGE_ACCEPTED',name,best[0],L,cert['gap'],flush=True)
    return stages,warm
