"""Conditional reuse of May19's original-objective cutoff architecture."""
import math
from dataclasses import replace
from fractions import Fraction
from time import time
import numpy as np
from v42_pr134_b1.common import atomic,record,sha
from v42_a_stage_compact_rowgen.budget import Budget
from v42_a_stage_bnp.budget import Allocation
from v42_a_stage_domain_v2.lexstage import LexLock,rebuild_locked_snapshot,integer_optimality_certificate
from v42_a_stage_lexrefine.partition import split
from v42_a_stage_lexfull.runner import objective_value
from v42_a_stage_phase1.core import primal_replay
from .policy import OUT,STATIC
from . import native as base

class Native(base.Native):
    def solve(self,snapshot,folder,component):
        compiler=base.materialize;self.live_model=None
        def materialize(s,day):
            model,objectives=compiler(s,day);self.live_model=model
            hints=getattr(self,'hint_point',None)
            if hints is not None and model.NumIntVars:
                if len(hints)!=model.NumVars:raise ValueError('ORIGINAL_INCUMBENT_HINT_AXES_REQUIRED')
                indices=np.flatnonzero(s.vtypes!='C');allvars=model.getVars();variables=[allvars[int(j)] for j in indices]
                values=np.rint(hints[indices]).tolist()
                if any(v<s.lower[j] or v>s.upper[j] for j,v in zip(indices,values)):raise ValueError('INDIVIDUAL_HINT_BOX_REQUIRED')
                model.setAttr('VarHintVal',variables,values);model.setAttr('VarHintPri',variables,[1]*len(values));model.update()
                if not np.array_equal(model.getAttr('VarHintVal',variables),values):raise ValueError('NATIVE_HINT_READBACK_FAILED')
                atomic(folder/'NONBINDING_INCUMBENT_HINTS.json',dict(PASS=True,columns=len(indices),source=self.hint_record,
                    heuristic_guidance_only=True,not_pruning_or_feasibility_authority=True,current_query_primal_claimed=False,
                    original_rows_boxes_types_objectives_unchanged=True,hint_priority=1))
            return model,objectives
        base.materialize=materialize
        try:return super().solve(snapshot,folder,component)
        finally:base.materialize=compiler;self.live_model=None

def run(native,strong,original,warm,physical,locks,folder):
    budget=Budget();native.budget=budget;stages=[]
    for name in ('shift_magnitude','prestart_relocation'):
        locked,lockproof=rebuild_locked_snapshot(strong,locks);obj=locked.objective(name)
        query=replace(locked,objectives=(obj,)+tuple(o for o in locked.objectives if o.name!=name))
        sf=folder/'P2'/name.upper();sf.mkdir(parents=True,exist_ok=True);atomic(sf/'LOCK_REBUILD.json',lockproof)
        if not physical.verify(warm)['PASS'] or not primal_replay(locked,warm)['PASS']:raise ValueError('PRIOR_LOCKED_PRIMAL_INCLUSION_REQUIRED')
        best=float(objective_value(original,warm,name));LB=0.;ledger=[];serial=0
        def checkpoint():
            atomic(sf/'CHECKPOINT.json',dict(queue=ledger,UB=best,valid_LB=LB,deadline=budget.record,unix=time(),
                source=record(OUT/'CANARY_SOURCE_FREEZE.json'),prior_incumbent_preserved=True))
        while True:
            checkpoint();cert=integer_optimality_certificate(name,best,LB,bound_independently_validated=True,
                primal_independently_validated=True,integrality_proven=True)
            if cert['PASS']:
                cp=sf/'INTEGER_CERTIFICATE.json';cert.update(scope='FULL_RELEVANT_SCIENTIFIC_INTEGER_DOMAIN_UNDER_CERTIFIED_PRIOR_LOCKS',
                    ledger=record(sf/'CHECKPOINT.json'),independent_rational_MIP_dual_certificate=False)
                atomic(cp,cert);stages.append(dict(component=name,value=cert['incumbent_integer'],valid_LB=LB,certificate=record(cp)))
                locks.append(LexLock(name,Fraction(cert['incumbent_integer']),True,sha(cp)));break
            remaining=budget.remaining()
            if remaining<=180:raise RuntimeError('IMMUTABLE_BUDGET_FINALIZATION_RESERVE')
            problem,partition=split(query,name,best);nf=sf/('N'+str(serial));serial+=1;nf.mkdir(parents=True,exist_ok=True)
            atomic(nf/'EXHAUSTIVE_OBJECTIVE_PARTITION.json',partition);node=dict(id=serial-1,status='OPEN',partition=partition,prior_LB=LB)
            ledger.append(node);checkpoint();accepted=[]
            def candidate(x,value):
                nonlocal warm,best
                rows=primal_replay(problem,x);integral=np.max(abs(x[original.vtypes!='C']-np.rint(x[original.vtypes!='C'])))<=1e-5
                p=dict(PASS=False)
                if rows['PASS'] and integral:
                    try:p=physical.verify(x)
                    except Exception as e:p=dict(PASS=False,reason=repr(e))
                good=rows['PASS'] and integral and p['PASS'];val=float(objective_value(original,x,name))
                cf=nf/'CANDIDATES'/('C'+str(len(accepted)));cf.mkdir(parents=True,exist_ok=True)
                atomic(cf/'CURRENT_QUERY_ROWS_REPLAY.json',rows);atomic(cf/'FULL_ORIGINAL_A1_REPLAY.json',p);accepted.append(bool(good))
                if good and val<best-1e-5:
                    best=val;warm=x.copy();checkpoint()
                    if math.ceil(LB-1e-6)>=round(val) and native.live_model is not None:native.live_model.terminate()
            hp=STATIC/sf.relative_to(OUT)/('HINT_'+str(serial)+'.npz');hp.parent.mkdir(parents=True,exist_ok=True);np.savez_compressed(hp,X=warm)
            native.hint_point=warm;native.hint_record=record(hp);native.warm_point=None;native.warm_basis=None
            native.incumbent_callback=candidate;native.queue_checkpoint=record(sf/'CHECKPOINT.json');native.budget=Allocation(remaining-180)
            try:r,raw=native.solve(problem,nf,'P2')
            finally:native.budget=budget;native.incumbent_callback=None;native.hint_point=None
            if 'X' in raw:candidate(raw['X'],r['objective'])
            if math.ceil(LB-1e-6)>=round(best):node['status']='CLOSED_PRIOR_BOUND_AND_NEW_PRIMAL'
            elif r['status']==3:LB=partition['right']['valid_LB'];node['status']='LEFT_INFEASIBLE_RIGHT_CLOSED'
            elif r['status'] in (2,9,11) and r['native_error'] is None and r['ObjBound'] is not None and math.isfinite(r['ObjBound']):
                LB=max(LB,min(float(r['ObjBound']),partition['right']['valid_LB']));node['status']='OPEN_CURRENT_NATIVE_BOUND'
            else:raise RuntimeError('COMPLETE_INTEGER_BOUND_NOT_VALID')
            atomic(nf/'INTEGER_BOUND_PROVENANCE.json',dict(PASS=True,native_result=record(nf/'NATIVE_RESULT.json'),
                actual_full_model=record(nf/'INDEPENDENT_COMPILED_MODEL_VERIFICATION.json'),full_domain=record(folder/'FULL_ZERO_DOMAIN_VERIFICATION.json'),
                branch=node,valid_stage_LB=LB,interrupted_is_not_infeasible=True,independent_rational_MIP_dual_certificate=False));checkpoint()
            if r['status']==2 and 'X' in raw and not any(accepted):raise RuntimeError('NATIVE_OPTIMAL_CANDIDATE_FAILS_ORIGINAL_PHYSICS')
    return stages,warm
