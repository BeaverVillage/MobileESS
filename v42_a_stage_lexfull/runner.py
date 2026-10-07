"""Inherited P2 on the proved complete relevant domain, with independent LB."""
import gzip,pickle,traceback
from dataclasses import replace
from fractions import Fraction
from time import time
import numpy as np
from v42_pr134_b1.common import read,record,atomic,sha
from v42_a_stage_domain_v2.lexstage import LexLock,rebuild_locked_snapshot,integer_objective_proof,integer_optimality_certificate
from v42_a_stage_phase1.backend import project_local_point
from v42_a_stage_phase1.core import primal_replay,interval_box_bound,verify_sign_convention
from v42_a_stage_practical.physical import Physical
from v42_a_stage_practical.global_bounds import implied_upper
from v42_a_stage_compact_rowgen.budget import Budget
from v42_a_stage_bnp.budget import Allocation
from .policy import OUT,STATIC,POLICY
from .native import Native
from .execution import verify

def objective_value(s,x,name):
    o=s.objective(name)
    return o.constant+sum((c*Fraction(float(x[j])) for j,c in o.coefficients().items()),Fraction(0))

def warm_reindex(oldstate,newstate,x,n):
    out=np.zeros(newstate['reference'].matrix.shape[1]);out[:n]=x[:n]
    for key in oldstate['data'][7]['classes']:
        old=[u for u in oldstate['reference_descriptor']['units'] if u['class_key']==key]
        new=[u for u in newstate['reference_descriptor']['units'] if u['class_key']==key]
        part=project_local_point(old,x,new,len(out));out+=part
    return out

def bound(s,raw,upper):
    pi=raw['Pi'].copy();pi[(s.senses=='<')&(pi>0)]=0;pi[(s.senses=='>')&(pi<0)]=0
    c=np.zeros(s.matrix.shape[1])
    for j,v in s.objectives[0].coefficients().items():c[j]=float(v)
    return interval_box_bound(s.matrix,c,pi,s.lower,upper,s.rhs,float(s.objectives[0].constant))

def run():
    verify()
    if (OUT/'P2_FULL_STARTED.json').exists():raise PermissionError('FULL_P2_ALREADY_STARTED_USE_CHECKPOINT')
    build=read(OUT/'LEX_FULL_BUILD_VERIFICATION.json')
    with gzip.open(build['state']['path'],'rb') as f:p=pickle.load(f)
    state,s=p['state'],p['snapshot'];physical=Physical(state,s)
    old=read(OUT/'INTEGER_BUILD_VERIFICATION.json')
    with gzip.open(old['state']['path'],'rb') as f:oldstate=pickle.load(f)['state']
    migration=read(OUT/'P2_MIGRATION_PROBE_RESULT.json');x=np.load(migration['validated_point']['path'])['X']
    warm=warm_reindex(oldstate,state,x,state['n'])
    inc=read(OUT/'VALIDATED_INTEGER_INCUMBENT.json')
    locks=[LexLock('rho',Fraction(inc['exact_UB']),True,sha(OUT/'P1_FULL_DOMAIN_INTEGER_GAP_CERTIFICATE.json'),Fraction(1e-7)),
        LexLock('migration_count',Fraction(0),True,migration['certificate']['sha256'])]
    budget=Budget();native=Native(budget);results=[]
    atomic(OUT/'P2_FULL_STARTED.json',dict(PASS=True,source=record(OUT/'LEX_FULL_SOURCE_FREEZE.json'),deadline=budget.record))
    result=dict(A1_accepted=False,classification='A_PRACTICAL_SOLVER_P1_GAP_LE_0P5',stages=results)
    try:
        upper=None
        for name in ('shift_magnitude','prestart_relocation'):
            stage,lockproof=rebuild_locked_snapshot(s,locks);o=stage.objective(name)
            query=replace(stage,objectives=(o,)+tuple(o for o in stage.objectives if o.name!=name))
            folder=OUT/'M19/P2'/name.upper();folder.mkdir(parents=True,exist_ok=True)
            atomic(folder/'LOCK_REBUILD.json',lockproof);integer_objective_proof(stage,name)
            if upper is None:
                upper,ubproof=implied_upper(stage,tuple(range(len(state['grows'])))+(lockproof['lock_rows']['rho'],),
                    state['n'],tuple(state['axes'].values()))
                atomic(OUT/'P2_IMPLIED_GLOBAL_BOX_CERTIFICATE.json',ubproof)
            native.warm_point=warm;native.warm_basis=None
            native.budget=Allocation(POLICY['control_allocation_seconds'])
            try:rec,raw=native.solve(query,folder/'CONTROL','P2')
            finally:native.budget=budget
            candidate=None
            if 'X' in raw:
                x=raw['X'];physical_receipt=physical.verify(x);replay=primal_replay(stage,x)
                atomic(folder/'ORIGINAL_FULL_PHYSICAL_REPLAY.json',physical_receipt);atomic(folder/'LOCKED_ROW_REPLAY.json',replay)
                if physical_receipt['PASS'] and replay['PASS']:
                    candidate=dict(value=float(objective_value(s,x,name)),point=rec['raw_attributes']);warm=x
            # A separate full-domain root LP supplies an independently replayed
            # interval Lagrangian bound, rather than trusting the MILP bound.
            lp=replace(query,vtypes=np.full(query.matrix.shape[1],'C'));native.warm_point=None
            lprec,lpraw=native.solve(lp,folder/'ROOT_LP','NODE_LP')
            L=None
            if lprec['status']==2 and all(a in lpraw for a in ('X','Pi','RC')):
                rp=primal_replay(lp,lpraw['X']);sign=verify_sign_convention(lp,lpraw['Pi'],lpraw['RC'])
                certificate_upper=np.r_[upper,stage.upper[state['n']:]]
                L=bound(lp,lpraw,certificate_upper) if rp['PASS'] and sign['PASS'] else None
                atomic(folder/'INDEPENDENT_LP_BOUND.json',dict(PASS=L is not None,valid_LB=L,replay=rp,sign=sign,
                    full_relevant_domain=record(OUT/'LEX_FULL_BUILD_VERIFICATION.json'),all_rows_present=True,
                    no_omitted_relevant_columns=True,implied_boxes_used_only_in_certificate=True))
            cert=integer_optimality_certificate(name,None if candidate is None else candidate['value'],L,
                bound_independently_validated=L is not None,primal_independently_validated=candidate is not None,integrality_proven=True)
            # If the root LP does not close the integer objective, the exact
            # finite-domain best-bound engine continues with BOTH children.
            if not cert['PASS'] and candidate is not None and L is not None:
                from .tree import continue_tree
                tree=continue_tree(native,lp,lpraw,L,candidate,warm,physical,certificate_upper,folder,s,name)
                candidate,warm,L=tree['candidate'],tree['point'],tree['valid_LB']
                cert=integer_optimality_certificate(name,candidate['value'],L,bound_independently_validated=L is not None,
                    primal_independently_validated=True,integrality_proven=True)
            cert.update(scope='FULL_SCIENTIFIC_RELEVANT_DOMAIN_UNDER_CERTIFIED_PRIOR_LOCKS',integer_domain_closure_proven=cert['PASS'],
                all_original_migration_options_excluded_only_by_exact_global_zero_lock=True,active_MIP_bound_not_used=True)
            atomic(folder/'INTEGER_CERTIFICATE.json',cert)
            stage_result=dict(name=name,accepted=cert['PASS'],incumbent=candidate,valid_LB=L,native_control=rec,
                certificate=record(folder/'INTEGER_CERTIFICATE.json'))
            results.append(stage_result);atomic(OUT/'P2_FULL_CHECKPOINT.json',dict(stages=results,locks=[l.component for l in locks],deadline=budget.record))
            if not cert['PASS']:raise RuntimeError('P2_INTEGER_BOUND_NOT_CLOSED:'+name)
            locks.append(LexLock(name,Fraction(cert['incumbent_integer']),True,sha(folder/'INTEGER_CERTIFICATE.json')))
            point=STATIC/('P2_'+name.upper()+'_VALIDATED_POINT.npz');np.savez_compressed(point,X=warm)
            stage_result['validated_point']=record(point)
            print('P2_FULL_ACCEPTED',name,cert['incumbent_integer'],L,flush=True)
        result.update(A1_accepted=True,classification='A_PRACTICAL_SOLVER_A1_ACCEPTED',migration_count=0,
            shift_magnitude=results[0]['incumbent']['value'],prestart_relocation=results[1]['incumbent']['value'])
    except Exception as e:result.update(stop_reason=repr(e),traceback=traceback.format_exc())
    result.update(native_seconds=native.native_seconds,Work=sum(c['Work'] or 0 for c in native.calls),elapsed_wall_seconds=budget.accounted(),
        peak_RSS_bytes=max((c.get('peak_RSS_bytes') or 0 for c in native.calls),default=0))
    atomic(OUT/'P2_FULL_NATIVE_CALLS.json',dict(calls=native.calls));atomic(OUT/'P2_FULL_RESULT.json',result)
    print('P2_FULL_RESULT',result['classification'],result.get('stop_reason'),flush=True)
    return result
if __name__=='__main__':run()
