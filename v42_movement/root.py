from .common import *
import numpy as np
import gurobipy as gp
from v42_degen.identity import inputs,model
from v42_integrated.matrix import arrays,audit
def install(m):
    selected=read(OUT/'SELECTED_MOVEMENT_GRID_CUTS.json');vs=m.getVars();rho=vs[selected['rho_column']]
    for k,r in enumerate(selected['cuts']):
        m.addConstr(gp.LinExpr(r['coefficients'],[vs[j] for j in r['columns']])-rho<=-BASE_LB,name=f'movement_grid_epigraph[{k}]')
    m.update()
    assert m.NumVars==316743 and m.NumBinVars==208312
    assert m.NumConstrs==886017+len(selected['cuts'])
    return selected
def run():
    gate('strengthened_root')
    A,d,B,e,i,_=inputs();m,_=model(B,e,i);selected=install(m)
    after=dict(rows=m.NumConstrs,columns=m.NumVars,binaries=m.NumBinVars,nnz=m.NumNZs)
    C,f=arrays(m)
    assert (C[:B.shape[0]]!=B).nnz==0
    for key in ('rhs','sense'):assert np.array_equal(f[key][:B.shape[0]],e[key])
    for key in ('names','types','lower','upper','objective','constant'):assert np.array_equal(f[key],e[key])
    policy=dict(Threads=1,Method=2,Crossover=0,TimeLimit=300,FeasibilityTol=1e-8,OptimalityTol=1e-8,BarConvTol=1e-11,PreDual=0,Seed=20260929)
    m.setAttr('VType',m.getVars(),['C']*m.NumVars);m.update()
    for k,v in policy.items():m.setParam(k,v)
    m.Params.LogFile='docs/v42_m1_movement_grid_epigraph_strengthening/MOVEMENT_GRID_STRENGTHENED_ROOT.log'
    once('STRENGTHENED_ROOT');m.optimize()
    result=dict(status=m.Status,status_name='OPTIMAL' if m.Status==2 else str(m.Status),objective=m.ObjVal if m.SolCount else None,
                LB=None,runtime=m.Runtime,barrier_iterations=m.BarIterCount,simplex_iterations=m.IterCount,settings=policy,
                original_prefix_exact=True,no_new_binary=True,integer_feasible_set_unchanged=True,physical_authority_unchanged=True,
                rejected_strengthening_added=False,matrix=after,optimization_calls=1,added_cuts=len(selected['cuts']),added_nnz=after['nnz']-8447855)
    if m.SolCount:
        x=np.asarray(m.getAttr('X'));full=audit(A,d,x,tolerance=1e-8);extended=audit(C,f,x,tolerance=1e-8)
        result.update(original_full_row_audit=full,extended_row_audit=extended,fractional_census=census(d,x,'STRENGTHENED'))
        np.savez_compressed(OUT/'MOVEMENT_GRID_STRENGTHENED_ROOT_POINT.npz',names=d['names'],values=x)
        if m.Status==2 and full['PASS'] and extended['PASS']:result['LB']=float(m.ObjVal)
    exact=all(read(OUT/p)['PASS'] for p in ('GRID_EPIGRAPH_ROW_DECOMPOSITION.json','PCS_GRID_SUPPORT_ORACLE_PROOF.json','MOVEMENT_ARC_TRANSIT_SEMANTICS_PROOF.json','MOVEMENT_ARC_CONDITIONAL_LB_PROOF.json','MOVEMENT_ARC_CLIQUE_PROOF.json'))
    result['material_gate']=material(result['LB'],exact=exact and m.Status==2)
    write('MOVEMENT_GRID_STRENGTHENED_ROOT_RESULT.json',result);m.dispose()
    if not result['material_gate']['PASS']:
        write('MOVEMENT_GRID_MIP_CANARY_RESULT.json',dict(status='NOT_RUN',reason='MATERIAL_ROOT_GATE_FAIL',optimization_calls=0,first_nonroot=None,first_branch=None,UB=None,LB=None,gap=None,Start_attempted=False,Start_accepted=None,Start_rejected=None))
    print('ROOT_DONE',result['status_name'],result['LB'],result['material_gate'],flush=True)
if __name__=='__main__':run()
