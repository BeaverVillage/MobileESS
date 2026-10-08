"""Exhaustive exact integer objective cases on the complete relevant domain."""
import gzip,pickle,math,traceback
from dataclasses import replace
from fractions import Fraction
from time import time
import numpy as np
from v42_pr134_b1.common import read,record,atomic,sha
from v42_a_stage_domain_v2.lexstage import LexLock,rebuild_locked_snapshot,integer_optimality_certificate
from v42_a_stage_phase1.core import primal_replay
from v42_a_stage_practical.physical import Physical
from v42_a_stage_compact_rowgen.budget import Budget
from v42_a_stage_bnp.budget import Allocation
from v42_a_stage_lexfull.runner import objective_value
from .policy import OUT,POLICY
from .native import Native
from .execution import verify
from v42_a_stage_lexcases.definition import define,fix_case

def run():
    verify()
    if (OUT/'P2_CG_STARTED.json').exists():raise PermissionError('INTEGER_CASES_ALREADY_STARTED')
    build=read(OUT/'LEX_FULL_BUILD_VERIFICATION.json')
    with gzip.open(build['state']['path'],'rb') as f:p=pickle.load(f)
    original=p['snapshot'];physical=Physical(p['state'],original)
    cg=read(OUT/'WEIGHTED_CG_BUILD_VERIFICATION.json')
    if record(cg['snapshot']['path'])!=cg['snapshot']:raise ValueError('QUALIFIED_WEIGHTED_CG_SNAPSHOT_DRIFT')
    with gzip.open(cg['snapshot']['path'],'rb') as f:s=pickle.load(f)
    previous=read(OUT/'P2_CASE_CHECKPOINT.json');bestpoint=previous['incumbent']['point']
    if record(bestpoint['path'])!=bestpoint:raise ValueError('PREVIOUS_CASE_INCUMBENT_BYTE_DRIFT')
    warm=np.load(bestpoint['path'])['X']
    physics=physical.verify(warm)
    if not physics['PASS']:raise ValueError('PRIOR_PHYSICAL_INTEGER_INCUMBENT_REQUIRED')
    atomic(OUT/'P2_CG_PRIOR_INCUMBENT_REPLAY.json',physics)
    p1=read(OUT/'VALIDATED_INTEGER_INCUMBENT.json');migration=read(OUT/'P2_MIGRATION_PROBE_RESULT.json')
    locks=[LexLock('rho',Fraction(p1['exact_UB']),True,sha(OUT/'P1_FULL_DOMAIN_INTEGER_GAP_CERTIFICATE.json'),Fraction(1e-7)),
        LexLock('migration_count',Fraction(0),True,migration['certificate']['sha256'])]
    inherited=read(OUT/'P2_CASE_RESULT.json')['stages']
    for stage in inherited:
        cp=stage['certificate']
        if record(cp['path'])!=cp or not read(cp['path'])['PASS']:raise ValueError('PREVIOUS_CERTIFIED_STAGE_DRIFT')
        locks.append(LexLock(stage['component'],Fraction(stage['value']),True,cp['sha256']))
    budget=Budget();native=Native(budget);stages=list(inherited);ledger=[];events=[];currentLB=None;best=None
    result=dict(A1_accepted=False,classification='A_PRACTICAL_SOLVER_P1_GAP_LE_0P5',stages=stages)
    atomic(OUT/'P2_CG_STARTED.json',dict(PASS=True,deadline=budget.record,source=record(OUT/'CG_SOURCE_FREEZE.json'),
        previous_queue_preserved=record(OUT/'P2_CASE_CHECKPOINT.json'),prior_incumbent=bestpoint,
        weighted_CG_application=True,source_weighted_CG=record(OUT/'WEIGHTED_CG_BUILD_VERIFICATION.json')))
    def checkpoint():
        atomic(OUT/'P2_CG_CHECKPOINT.json',dict(stages=stages,queue=ledger,events=events,valid_global_LB=currentLB,
            incumbent=best,unix=time(),deadline=budget.record,source=record(OUT/'CG_SOURCE_FREEZE.json')))
    try:
        for name in ('shift_magnitude','prestart_relocation'):
            if any(t['component']==name for t in inherited):continue
            locked,lockproof=rebuild_locked_snapshot(s,locks);extended,definition=define(locked,name);Z=definition['Z_column']
            obj=extended.objective(name);query=replace(extended,objectives=(obj,)+tuple(o for o in extended.objectives if o.name!=name))
            folder=OUT/'M19/P2/WEIGHTED_CG'/name.upper();folder.mkdir(parents=True,exist_ok=True)
            atomic(folder/'LOCK_REBUILD.json',lockproof);atomic(folder/'INTEGER_OBJECTIVE_DEFINITION.json',definition)
            best=dict(value=float(objective_value(original,warm,name)),point=bestpoint)
            if not primal_replay(locked,warm)['PASS']:raise ValueError('PRIOR_LOCK_INCLUSION_FAILED')
            prior_events=previous.get('events',[])
            same_stage=prior_events and prior_events[-1]['component']==name
            currentLB=previous['valid_global_LB'] if same_stage else read(OUT/'INTERRUPTED_BOUND_RECOVERY.json')['valid_full_domain_LB'] if name=='shift_magnitude' else 0.
            serial=0;whole=True;bounded=False
            while True:
                budget.remaining();value=math.ceil(currentLB-1e-6)
                certificate=integer_optimality_certificate(name,best['value'],currentLB,bound_independently_validated=True,
                    primal_independently_validated=True,integrality_proven=True)
                if certificate['PASS']:
                    certpath=folder/'INTEGER_CERTIFICATE.json';certificate.update(scope='FULL_SCIENTIFIC_RELEVANT_INTEGER_DOMAIN_UNDER_CERTIFIED_PRIOR_LOCKS',
                        source=record(OUT/'CG_SOURCE_FREEZE.json'),bound_ledger=record(OUT/'P2_CG_CHECKPOINT.json'),
                        independent_rational_MIP_dual_certificate=False)
                    atomic(certpath,certificate);stages.append(dict(component=name,value=certificate['incumbent_integer'],valid_LB=currentLB,
                        certificate=record(certpath),point=best['point']))
                    locks.append(LexLock(name,Fraction(certificate['incumbent_integer']),True,sha(certpath)))
                    bestpoint=best['point'];print('P2_CASE_EXACT_ACCEPTED',name,best['value'],currentLB,flush=True);break
                cfolder=folder/('N'+str(serial));serial+=1
                node=dict(component=name,id=serial-1,status='OPEN',restriction='WHOLE_STAGE' if whole else 'Z='+str(value),
                    valid_LB=currentLB,incumbent=best)
                interval=whole and not bounded
                if interval:
                    node.update(both_children_preserved=True,left=dict(restriction='Z<=UB-1',status='OPEN'),
                        right=dict(restriction='Z>=UB',status='PRUNED_BOUND',valid_LB=round(best['value'])),
                        valid_prior_lower_bound=currentLB,scientific_domain_deletion=False)
                if not whole:
                    node.update(both_children_preserved=True,left=dict(restriction='Z='+str(value),status='OPEN'),
                        right=dict(restriction='Z>='+str(value+1),status='OPEN',valid_LB=value+1),
                        excluded_lower_integers='ONLY_PRIOR_PROVEN_FULL_DOMAIN_BOUND_OR_INFEASIBLE_CASES')
                ledger.append(node);checkpoint();problem=query if whole else fix_case(query,Z,value)
                if interval:
                    lo=query.lower.copy();hi=query.upper.copy();lo[Z]=value;hi[Z]=round(best['value'])-1
                    problem=replace(query,lower=lo,upper=hi).require()
                # Previous point remains the stage UB even when outside a fixed-value child.
                native.warm_point=None
                native.warm_basis=None;native.queue_checkpoint=record(OUT/'P2_CG_CHECKPOINT.json')
                native.budget=Allocation(POLICY['control_allocation_seconds'] if whole else POLICY['case_allocation_seconds'])
                try:rec,raw=native.solve(problem,cfolder,'P2')
                finally:native.budget=budget
                if not read(cfolder/'INDEPENDENT_COMPILED_MODEL_VERIFICATION.json')['PASS']:raise ValueError('ACTUAL_CURRENT_MODEL_REQUIRED')
                primal=False
                if 'X' in raw:
                    lifted=raw['X'];x=lifted[:Z];rows=primal_replay(problem,lifted);phys=physical.verify(x)
                    integer=np.max(abs(lifted[problem.vtypes!='C']-np.rint(lifted[problem.vtypes!='C'])))<=1e-5
                    atomic(cfolder/'FULL_ORIGINAL_A1_REPLAY.json',phys);atomic(cfolder/'EXACT_CASE_ROWS_REPLAY.json',rows)
                    primal=rows['PASS'] and phys['PASS'] and integer
                    if primal:
                        objective=float(objective_value(original,x,name))
                        if objective<=best['value']+1e-5:
                            # Store original-width point separately; later stage definitions are rebuilt fresh.
                            from .policy import STATIC
                            path=STATIC/cfolder.relative_to(OUT)/'ORIGINAL_WIDTH_INCUMBENT.npz';np.savez_compressed(path,X=x)
                            best=dict(value=objective,point=record(path));warm=x
                if rec['status']==3:
                    currentLB=round(node['incumbent']['value']) if interval else value+1
                    node['left']['status']='FATHOMED_NATIVE_FULL_INTEGER_INFEASIBILITY'
                    node['status']='LEFT_FATHOMED_RIGHT_OPEN'
                elif rec['status'] in (2,9,11) and rec['native_error'] is None and rec['ObjBound'] is not None and math.isfinite(rec['ObjBound']):
                    nodeLB=float(rec['ObjBound']);currentLB=max(currentLB,min(nodeLB,round(node['incumbent']['value'])) if interval else min(nodeLB,value+1))
                    node['status']='PRIMAL_FOUND' if primal else 'OPEN_BOUNDED'
                else:raise RuntimeError('CURRENT_COMPLETE_INTEGER_CASE_NOT_CERTIFIABLY_BOUNDED')
                provenance=dict(PASS=True,native_current_result=record(cfolder/'NATIVE_RESULT.json'),
                    actual_model=record(cfolder/'INDEPENDENT_COMPILED_MODEL_VERIFICATION.json'),
                    full_relevant_domain=record(OUT/'LEX_FULL_BUILD_VERIFICATION.json'),integer_equivalence=record(OUT/'WEIGHTED_CG_BUILD_VERIFICATION.json'),
                    objective_definition=record(folder/'INTEGER_OBJECTIVE_DEFINITION.json'),branch=node,valid_stage_LB=currentLB,
                    authority='CURRENT_NATIVE_FULL_RELEVANT_INTEGER_MODEL_AND_EXHAUSTIVE_INTEGER_CASES',
                    independent_rational_MIP_dual_certificate=False,interrupted_is_not_infeasible=True)
                atomic(cfolder/'INTEGER_BOUND_PROVENANCE.json',provenance)
                events.append(dict(component=name,node=serial-1,LB=currentLB,UB=best['value'],status=rec['status'],unix=time()))
                checkpoint()
                certificate_now=integer_optimality_certificate(name,best['value'],currentLB,bound_independently_validated=True,
                    primal_independently_validated=True,integrality_proven=True)
                if not whole and not primal and rec['status']!=3 and not certificate_now['PASS']:raise RuntimeError('EXACT_INTEGER_CASE_OPEN_AT_COMPONENT_LIMIT')
                whole=False;bounded=True
        result.update(A1_accepted=True,classification='A_PRACTICAL_SOLVER_A1_ACCEPTED',migration_count=0,
            shift_magnitude=stages[0]['value'],prestart_relocation=stages[1]['value'])
    except Exception as e:result.update(stop_reason=repr(e),traceback=traceback.format_exc())
    finally:
        checkpoint();result.update(native_seconds=native.native_seconds,Work=sum(c['Work'] or 0 for c in native.calls),
            elapsed_wall_seconds=budget.accounted(),peak_RSS_bytes=max((c.get('peak_RSS_bytes') or 0 for c in native.calls),default=0))
        atomic(OUT/'P2_CG_NATIVE_CALLS.json',dict(calls=native.calls));atomic(OUT/'P2_CG_RESULT.json',result)
        print('P2_CG_RESULT',result['classification'],result.get('stop_reason'),flush=True)
    return result
if __name__=='__main__':run()
