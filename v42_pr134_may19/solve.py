"""One fresh barrier LP and conditional original-setting feasibility MIP."""
import sys,pickle,gzip,time
import numpy as np,scipy.sparse as sp,gurobipy as gp
from .common import *
from v42_a_stage_domain_v2.execution import require_action_authorized,guarded_optimize,tag_model_for_day
from v42_a_stage_domain_v2.status import initial_domain_status

def materialize(folder,relaxed):
    comp=folder/'COMPACT';proof=read(comp/'COMPRESSION_VERIFICATION.json')
    if not proof['PASS'] or not read(comp/'A2SC_INDEPENDENT_VERIFICATION.json')['PASS']:raise PermissionError('EXACT_COMPACT_PROOF_REQUIRED')
    for k in ('original_matrix','original_attributes','reduced_matrix','proof','objective'):
        if sha(proof[k]['path'])!=proof[k]['sha256']:raise PermissionError('COMPACT_SHA_DRIFT')
    a=sp.load_npz(comp/'A2SC_MATRIX.npz');z=dict(np.load(comp/'A2SC_ATTRIBUTES.npz'))
    m=gp.Model('MAY19_RESCUE_'+('LP' if relaxed else 'MIP'));m.Params.OutputFlag=0
    tag_model_for_day(m,DAY)
    x=m.addMVar(a.shape[1],lb=z['lb'],ub=z['ub'],vtype='C' if relaxed else z['vtype'])
    m.addMConstr(a,x,z['sense'],z['rhs'])
    m.setObjective(0.);m.update()
    actual=m.getA();diff=actual-a;diff.eliminate_zeros();assert diff.nnz==0
    return m

def replay_point(folder,raw,relaxed):
    from v42_pr134_sc.build import replay
    from v42_pr134_b1.native import sc_namespace
    sc,*_=sc_namespace(folder/'COMPACT');mapping=sc.proof_data('A2SC')['mapping']
    a=sp.load_npz(folder/'EXPANDED_MATRIX.npz');z=dict(np.load(folder/'EXPANDED_ATTRIBUTES.npz'))
    point=np.zeros(a.shape[1]);mask=mapping>=0;point[mask]=raw[mapping[mask]]
    if relaxed:z['vtype']=np.full(a.shape[1],'C')
    z.update(rf=np.zeros(a.shape[0],dtype=np.uint8),rf_names=np.array(['ORIGINAL_FULL_CAPTURED_ROW']))
    audit=replay(a,z,point);audit.update(finite_raw_point=bool(np.isfinite(raw).all()),all_four_objectives_unchanged=True)
    audit['PASS']=bool(audit['PASS'] and audit['finite_raw_point'])
    return point,audit

def physical(folder,point,audit):
    from v42_pr134_b1.native import bind
    from v42_pr134_sc.snapshot import certify
    from v42_integrated.contract import physical_authority
    with (folder/'DATA.pkl').open('rb') as f:data=pickle.load(f)
    with gzip.open(folder/'SCIENTIFIC_INTERFACES.pkl.gz','rb') as f:descriptor=pickle.load(f)
    _,_,coeff,_,_,_=bind(data[0],PRODUCTION/'inputs'/DAY,folder/'VERIFY_NAMESPACE')
    with physical_authority():cert,selected,controls,globals=certify(descriptor,data,point,audit,coeff)
    atomic(folder/'INDEPENDENT_PHYSICAL_FEASIBILITY.json',cert)
    atomic(folder/'VERIFIED_SELECTED_JOBS.json',selected)
    return cert

def main(shell):
    require_action_authorized(DAY,'FEASIBILITY_LP')
    folder=CASE/shell
    if any((folder/n).exists() for n in ('SOLVE_START.json','RESULT.json','LP_RAW_POINT.npz','MIP_RAW_POINT.npz')):raise PermissionError('NO_DUPLICATE_OR_PARTIAL_NATIVE_SOLVE')
    other_heavy();static=read(folder/'STATIC_ONLY.json')
    for k in ('selected','matrix','attributes','descriptor'):
        if sha(static[k]['path'])!=static[k]['sha256']:raise PermissionError('STATIC_SHA_DRIFT')
    atomic(folder/'SOLVE_START.json',dict(started_UTC=now(),process=process(),LP_SETTINGS=LP_SETTINGS,MIP_SETTINGS=MIP_SETTINGS,
           original_clock_loaded=False,previous_point_or_basis_loaded=False,normal_objective=False,base=BASE))
    r=dict(day=DAY,shell=shell,classification='UNRESOLVED',domain_status=initial_domain_status(),LP=None,MIP=None,integer_witness_PASS=False,original_full_replay_PASS=False)
    for relaxed in (True,False):
        prefix='LP' if relaxed else 'MIP';m=materialize(folder,relaxed);settings=LP_SETTINGS if relaxed else MIP_SETTINGS
        for k,v in settings.items():m.setParam(k,v)
        m.Params.OutputFlag=1;m.Params.LogToConsole=0;m.Params.LogFile=str(folder/(prefix+'_NATIVE.log'))
        atomic(folder/(prefix+'_START.json'),dict(started=now(),process=process(),settings=settings))
        last=[0.]
        def callback(model,where):
            if where==gp.GRB.Callback.POLLING:return
            elapsed=model.cbGet(gp.GRB.Callback.RUNTIME)
            if elapsed-last[0]<2:return
            last[0]=elapsed;v=dict(shell=shell,phase=prefix,native_runtime=elapsed,report_UTC=now(),callback=where)
            if where==gp.GRB.Callback.BARRIER:
                v.update(iterations=model.cbGet(gp.GRB.Callback.BARRIER_ITRCNT),primal_infeasibility=model.cbGet(gp.GRB.Callback.BARRIER_PRIMINF),dual_infeasibility=model.cbGet(gp.GRB.Callback.BARRIER_DUALINF))
            if where==gp.GRB.Callback.MIP:
                v.update(nodes=model.cbGet(gp.GRB.Callback.MIP_NODCNT),incumbent=model.cbGet(gp.GRB.Callback.MIP_OBJBST),bound=model.cbGet(gp.GRB.Callback.MIP_OBJBND))
            atomic(CASE/'PROGRESS.json',v)
        guarded_optimize(m,DAY,callback)
        def attr(name):
            try:return float(getattr(m,name))
            except (AttributeError,gp.GurobiError):return None
        status=dict(status=m.Status,native_runtime=m.Runtime,Work=m.Work,solutions=m.SolCount,iterations=m.IterCount,
            barrier_iterations=attr('BarIterCount'),nodes=attr('NodeCount'),objective=attr('ObjVal'),bound=attr('ObjBound'),
            ConstrVio=attr('ConstrVio'),BoundVio=attr('BoundVio'),IntVio=attr('IntVio'),settings=settings,valid_primal=False,
            TIME_LIMIT_is_not_infeasibility=m.Status==gp.GRB.TIME_LIMIT)
        try:raw=np.array(m.getAttr('X'))
        except (AttributeError,gp.GurobiError):raw=None
        if raw is not None and np.isfinite(raw).all():
            np.savez_compressed(folder/(prefix+'_RAW_POINT.npz'),values=raw)
            point,audit=replay_point(folder,raw,relaxed);atomic(folder/(prefix+'_ORIGINAL_FULL_REPLAY.json'),audit)
            status['valid_primal']=audit['PASS'];status['original_full_replay']=audit
            if not relaxed and audit['PASS']:
                cert=physical(folder,point,audit);status['physical']=cert
                if cert['PASS']:
                    np.savez_compressed(folder/'VERIFIED_INTEGER_ORIGINAL_POINT.npz',values=point)
                    r.update(integer_witness_PASS=True,original_full_replay_PASS=True,classification='FIRST_FEASIBLE_TESTED_SHELL')
        if relaxed and m.Status==gp.GRB.INFEASIBLE:
            # Barrier may expose no FarkasDual without crossover. Do not change
            # method or manufacture a certificate from numerical status.
            try:
                ray=np.array(m.getAttr('FarkasDual'));np.savez_compressed(folder/'LP_NATIVE_FARKAS.npz',ray=ray)
                status['native_ray']=record(folder/'LP_NATIVE_FARKAS.npz')
            except (AttributeError,gp.GurobiError):status['native_ray']=None
            status['independent_infeasibility_proven']=False
        r[prefix]=status;atomic(folder/'RESULT.json',r);m.dispose()
        if relaxed and not status['valid_primal']:break
    print('SHELL_RESULT',shell,r['classification'],r['LP']['status'],None if r['MIP'] is None else r['MIP']['status'],flush=True)
    return r
if __name__=='__main__':main(sys.argv[1])
