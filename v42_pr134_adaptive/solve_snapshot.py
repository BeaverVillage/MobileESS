"""Fresh native LP then MIP over exact captured matrix, no incumbent/basis resume."""
import sys,gzip,pickle,time
import numpy as np,scipy.sparse as sp
import gurobipy as gp,psutil
from .common import *
from v42_a_stage_domain_v2.execution import require_action_authorized,guarded_optimize
from v42_a_stage_domain_v2.status import initial_domain_status
def main(day,tag):
    require_action_authorized(day,'FEASIBILITY_LP')
    folder=CASE/day/tag
    if any((folder/name).exists() for name in ('RESULT.json','SOLVE_START.json','LP_RAW_POINT.npz','MIP_RAW_POINT.npz','RAW_FARKAS.npz')):raise PermissionError('NO_DUPLICATE_OR_PARTIAL_NATIVE_TEST; use fresh identity/static clone only')
    static=read(folder/'STATIC_ONLY.json')
    for k in ('matrix','attributes','descriptor','selected'):
        if sha(static[k]['path'])!=static[k]['sha256']:raise PermissionError('FROZEN_STATIC_SHA_DRIFT')
    for p in psutil.process_iter(['pid','name','cmdline']):
        if p.pid==psutil.Process().pid or not str(p.info['name']).lower().startswith('python'):continue
        cmd=' '.join(p.info['cmdline'] or [])
        if any(x in cmd for x in ('v42_pr134_adaptive.capacity_master','v42_pr134_adaptive.minimum_probe','v42_pr134_adaptive.restricted','v42_pr134_adaptive.solve_snapshot','v42_pr134_b1.worker')):raise PermissionError('OTHER_HEAVY_OPTIMIZER:'+str(p.pid))
    atomic(folder/'SOLVE_START.json',dict(started=now(),matrix=static['matrix'],solver=SETTINGS,native_limit_each=600,objective='ZERO_FEASIBILITY',
        partial_checkpoint_loaded=False,incumbent_loaded=False,basis_loaded=False,old_native_clock_loaded=False))
    a=sp.load_npz(folder/'EXPANDED_MATRIX.npz');z=dict(np.load(folder/'EXPANDED_ATTRIBUTES.npz'))
    result=dict(day=day,tag=tag,LP_status=None,MIP_status=None,classification='UNRESOLVED',domain_status=initial_domain_status(),selected=read(folder/'DOMAIN_AUTHORITY_AUDIT.json')['selected'],census=read(folder/'CENSUS.json'))
    for relaxed in (True,False):
        prefix='LP' if relaxed else 'MIP';m=gp.Model('FRESH_CAPTURED_A1_'+prefix);m.Params.OutputFlag=0
        x=m.addMVar(a.shape[1],lb=z['lb'],ub=z['ub'],vtype='C' if relaxed else z['vtype']);m.addMConstr(a,x,z['sense'],z['rhs']);m.setObjective(0.);m.update()
        for key,value in SETTINGS.items():m.setParam(key,value)
        m.Params.TimeLimit=600.;m.Params.OutputFlag=1;m.Params.LogFile=str(folder/(prefix+'_NATIVE.log'))
        if relaxed:m.Params.InfUnbdInfo=1;m.Params.DualReductions=0
        guarded_optimize(m,day);result.update({prefix+'_status':m.Status,prefix+'_runtime':m.Runtime,prefix+'_Work':m.Work,prefix+'_solutions':m.SolCount,
                                   prefix+'_iterations':m.IterCount,prefix+'_nodes':m.NodeCount})
        if m.SolCount:
            raw=np.array(m.getAttr('X'));np.savez_compressed(folder/(prefix+'_RAW_POINT.npz'),values=raw)
            from v42_pr134_sc.build import replay
            replay_z=dict(z,vtype=np.full(len(z['vtype']),'C')) if relaxed else dict(z)
            replay_z.update(rf=np.zeros(a.shape[0],dtype=np.uint8),rf_names=np.array(['CAPTURED_FULL_ROW_AXIS']))
            audit=replay(a,replay_z,raw);atomic(folder/(prefix+'_ALL_ROWS_REPLAY.json'),audit)
            if not audit['PASS']:raise ValueError('RAW_NATIVE_POINT_NOT_AUTHORIZED')
            if not relaxed:
                from v42_pr134_b1.native import bind
                from v42_pr134_sc.snapshot import certify
                from v42_integrated.contract import physical_authority
                with (folder/'DATA.pkl').open('rb') as f:data=pickle.load(f)
                with gzip.open(folder/'SCIENTIFIC_INTERFACES.pkl.gz','rb') as f:desc=pickle.load(f)
                dm,native,coeff,power,idle,swing=bind(data[0],PRODUCTION/'inputs'/day,folder)
                with physical_authority():cert,selected,controls,globals=certify(desc,data,raw,audit,coeff)
                atomic(folder/'FULL_PHYSICAL_FEASIBILITY_VERIFICATION.json',cert)
                atomic(folder/'SELECTED_PHYSICAL_OPTIONS.json',selected)
                if not cert['PASS']:raise ValueError('FULL_PHYSICAL_POINT_VERIFICATION_FAILED')
                result['classification']='FULL_INTEGER_FEASIBLE_MINIMALITY_STILL_REQUIRED';result['physical_PASS']=True
        if m.Status==gp.GRB.INFEASIBLE:
            result['classification']='RESTRICTED_'+prefix+'_INFEASIBLE'
            if relaxed:np.savez_compressed(folder/'RAW_FARKAS.npz',ray=np.array(m.getAttr('FarkasDual')),rows=np.arange(m.NumConstrs),columns=np.arange(m.NumVars))
        atomic(folder/'RESULT.json',result);m.dispose()
        if relaxed and result['LP_status']!=gp.GRB.OPTIMAL:break
    print('FRESH_RESTRICTED_RESULT',result['classification'],result.get('LP_runtime'),result.get('MIP_runtime'),flush=True)
if __name__=='__main__':main(*sys.argv[1:])
