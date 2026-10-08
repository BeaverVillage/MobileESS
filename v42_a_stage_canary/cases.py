"""The completed May19 exact-Z case algorithm, with identical allocations."""
import math
from dataclasses import replace
from fractions import Fraction
from time import time
import numpy as np
from v42_pr134_b1.common import atomic,record,read,sha
from v42_a_stage_lexcases.definition import define,fix_case
from v42_a_stage_domain_v2.lexstage import rebuild_locked_snapshot,LexLock,integer_optimality_certificate
from v42_a_stage_lexfull.runner import objective_value
from v42_a_stage_bnp.budget import Allocation
from v42_a_stage_compact_rowgen.budget import Budget
from v42_a_stage_phase1.core import primal_replay
from .policy import OUT,STATIC,POLICY

def run(native,strong,original,warm,physical,locks,folder):
    stages=[];budget=Budget();weighted=read(OUT/'CONDITIONAL_CANARY_GATE.json')['May19_engine']=='WEIGHTED_CG'
    for name in ('shift_magnitude','prestart_relocation'):
        locked,lockproof=rebuild_locked_snapshot(strong,locks);extended,definition=define(locked,name);Z=definition['Z_column']
        obj=extended.objective(name);query=replace(extended,objectives=(obj,)+tuple(o for o in extended.objectives if o.name!=name))
        sf=folder/'P2'/name.upper();sf.mkdir(parents=True,exist_ok=True)
        atomic(sf/'LOCK_REBUILD.json',lockproof);atomic(sf/'INTEGER_OBJECTIVE_DEFINITION.json',definition)
        if not physical.verify(warm)['PASS'] or not primal_replay(locked,warm)['PASS']:raise ValueError('CANARY_PRIOR_LOCKED_POINT_INCLUSION_REQUIRED')
        best=float(objective_value(original,warm,name));LB=0.;ledger=[];whole=True;serial=0
        def checkpoint():
            atomic(sf/'CHECKPOINT.json',dict(queue=ledger,UB=best,valid_LB=LB,deadline=budget.record,unix=time(),
                source=record(OUT/'CANARY_SOURCE_FREEZE.json'),prior_incumbent_preserved=True))
        while True:
            budget.remaining();checkpoint()
            cert=integer_optimality_certificate(name,best,LB,bound_independently_validated=True,primal_independently_validated=True,integrality_proven=True)
            if cert['PASS']:
                cp=sf/'INTEGER_CERTIFICATE.json';cert.update(scope='FULL_RELEVANT_SCIENTIFIC_INTEGER_DOMAIN_UNDER_CERTIFIED_PRIOR_LOCKS',
                    integer_domain_closure_proven=True,ledger=record(sf/'CHECKPOINT.json'),independent_rational_MIP_dual_certificate=False)
                atomic(cp,cert);stages.append(dict(component=name,value=cert['incumbent_integer'],valid_LB=LB,certificate=record(cp)))
                locks.append(LexLock(name,Fraction(cert['incumbent_integer']),True,sha(cp)));break
            value=math.ceil(LB-1e-6);nf=sf/('N'+str(serial));serial+=1
            node=dict(id=serial-1,status='OPEN',restriction='WHOLE_STAGE' if whole else 'Z='+str(value),valid_LB=LB)
            if not whole:node.update(both_children_preserved=True,left=dict(restriction='Z='+str(value),status='OPEN'),right=dict(restriction='Z>='+str(value+1),valid_LB=value+1,status='OPEN'))
            ledger.append(node);checkpoint();problem=query if whole else fix_case(query,Z,value)
            if whole and weighted:
                lo=query.lower.copy();hi=query.upper.copy();lo[Z]=value;hi[Z]=round(best)-1
                problem=replace(query,lower=lo,upper=hi).require()
                node.update(both_children_preserved=True,left=dict(restriction='Z<=UB-1',status='OPEN'),right=dict(restriction='Z>=UB',valid_LB=round(best),status='PRUNED_BOUND'))
                checkpoint()
            native.warm_point=np.r_[warm,best] if whole and not weighted else None;native.warm_basis=None;native.queue_checkpoint=record(sf/'CHECKPOINT.json')
            native.budget=Allocation(POLICY['control_allocation_seconds'] if whole else POLICY['case_allocation_seconds'])
            try:r,raw=native.solve(problem,nf,'P2')
            finally:native.budget=budget
            if not read(nf/'INDEPENDENT_COMPILED_MODEL_VERIFICATION.json')['PASS']:raise ValueError('CANARY_ACTUAL_MODEL_READBACK_REQUIRED')
            primal=False
            if 'X' in raw:
                x=raw['X'];p=physical.verify(x[:Z]);rows=primal_replay(problem,x)
                atomic(nf/'FULL_ORIGINAL_A1_REPLAY.json',p);atomic(nf/'EXACT_CASE_ROWS_REPLAY.json',rows)
                primal=p['PASS'] and rows['PASS'] and np.max(abs(x[problem.vtypes!='C']-np.rint(x[problem.vtypes!='C'])))<=1e-5
                if primal:
                    val=float(objective_value(original,x[:Z],name))
                    if val<=best+1e-5:best=val;warm=x[:Z]
            if r['status']==3:
                if whole and not weighted:raise ValueError('CANARY_WHOLE_STAGE_INFEASIBLE_DESPITE_VALID_PRIMAL')
                LB=round(node['right']['valid_LB']) if whole else value+1;node['left']['status']='FATHOMED_NATIVE_FULL_INTEGER_INFEASIBILITY'
            elif r['status'] in (2,9,11) and r['native_error'] is None and r['ObjBound'] is not None and math.isfinite(r['ObjBound']):
                LB=max(LB,min(float(r['ObjBound']),node['right']['valid_LB']) if whole and weighted else float(r['ObjBound']) if whole else min(float(r['ObjBound']),value+1));node['status']='PRIMAL_FOUND' if primal else 'OPEN_BOUNDED'
            else:raise RuntimeError('CANARY_COMPLETE_INTEGER_CASE_NOT_CERTIFIABLY_BOUNDED')
            atomic(nf/'INTEGER_BOUND_PROVENANCE.json',dict(PASS=True,native_result=record(nf/'NATIVE_RESULT.json'),
                actual_full_model=record(nf/'INDEPENDENT_COMPILED_MODEL_VERIFICATION.json'),
                full_domain=record(folder/'FULL_ZERO_DOMAIN_VERIFICATION.json'),original_integer_valid_cuts=record(folder/'P2/INHERITED_INTEGER_STRENGTHENING.json'),
                objective_definition=record(sf/'INTEGER_OBJECTIVE_DEFINITION.json'),branch=node,valid_stage_LB=LB,
                interrupted_is_not_infeasible=True,independent_rational_MIP_dual_certificate=False))
            checkpoint()
            if not whole and not primal and r['status']!=3:raise RuntimeError('CANARY_EXACT_INTEGER_CASE_OPEN_AT_COMPONENT_LIMIT')
            whole=False
    return stages,warm
