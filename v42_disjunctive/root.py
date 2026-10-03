from .common import *
from .resources import gate
from .cuts import build,install
from v42_degen.identity import inputs,model,signature
from v42_integrated.matrix import arrays,audit
from v42_strengthening.analysis import graph_inputs
import numpy as np

def statistics(d,x):
    names=list(map(str,d['names'])); index={n:i for i,n in enumerate(names)}
    sites,initial,arcs,_,_=graph_inputs()
    stay=[i for i,n in enumerate(names) if n.startswith('arc[') and int(n.rsplit(',',1)[1][:-1])<len(sites)*96]
    binary=d['types']!='C';bv=x[binary];sv=x[stay]
    split=0;maximum=0
    for u in initial:
        for t in range(96):
            values=[float(x[index[f'arc[{u},{s*96+t}]']]) if f'arc[{u},{s*96+t}]' in index else 0. for s in range(len(sites))]
            positive=sum(v>1e-6 for v in values);split+=positive>1;maximum=max(maximum,positive)
    return dict(fractional_binary_count=int(((bv>1e-6)&(bv<1-1e-6)).sum()),
                fractional_binary_mass=float(np.minimum(bv,1-bv).sum()),
                location_fractional_mass=float(np.minimum(sv,1-sv).sum()),location_split_count=split,max_simultaneous_sites=maximum)

def run():
    gate('root_before_setup')
    build()
    A,d,B,e,identity,_=inputs();m,receipt=model(B,e,identity)
    try:
        growth=install(m);C,f=arrays(m)
        assert m.NumVars==316743 and m.NumBinVars==208312
        base=C[:B.shape[0]]
        check=dict(f,rhs=f['rhs'][:B.shape[0]],sense=f['sense'][:B.shape[0]],row_names=f['row_names'][:B.shape[0]],lower=d['lower'],upper=d['upper'])
        assert signature(base,check)==signature(B,e)
        allowed={c['column'] for c in read(OUT/'CONDITIONAL_INFEASIBLE_STATE_PROOF.json')['proven_fixings']}
        changed=set(np.flatnonzero((f['lower']!=d['lower'])|(f['upper']!=d['upper'])))
        assert changed==allowed
        matrix=dict(rows=m.NumConstrs,columns=m.NumVars,binaries=m.NumBinVars,nnz=m.NumNZs,
                    added_rows=m.NumConstrs-886017,added_columns=0,added_binaries=0,added_nnz=m.NumNZs-8447855,**growth)
        write('STRENGTHENED_MATRIX_IDENTITY.json',dict(PASS=True,original_rows_coefficients_RHS_senses_names_exact=True,
              original_objective_columns_types_exact=True,bounds_changed_only_for_proven_infeasible_states=sorted(allowed),matrix=matrix))
        m.setAttr('VType',m.getVars(),['C']*m.NumVars);m.update()
        for key,value in dict(Threads=1,Method=2,Crossover=0,TimeLimit=300,FeasibilityTol=1e-8,OptimalityTol=1e-8,BarConvTol=1e-11,PreDual=0,Seed=20260929).items():setattr(m.Params,key,value)
        m.Params.LogFile='docs/v42_m1_location_grid_disjunctive_cuts/DISJUNCTIVE_STRENGTHENED_ROOT.log'
        once('STRENGTHENED_ROOT');m.optimize()
        result=dict(status=int(m.Status),runtime=float(m.Runtime),barrier_iterations=int(m.BarIterCount),matrix=matrix,
                    objective=None,objective_LB=None,optimization_calls=1,baseline_LB=BASE_LB,
                    fresh_root_solve=True,no_old_bound_or_diagnostic_UB_promotion=True,
                    settings=dict(Threads=1,Method=2,Crossover=0,TimeLimit=300))
        if m.Status==2:
            x=np.array(m.getAttr('X'));full=audit(A,d,x,tolerance=1e-8);new=audit(C,f,x,tolerance=1e-8)
            passed=full['PASS'] and new['PASS']
            result.update(original_full_row_audit=full,strengthened_row_audit=new,
                          objective=float(m.ObjVal),objective_LB=float(m.ObjVal) if passed else None,
                          numerical_audit_PASS=passed,statistics=statistics(d,x))
            np.savez_compressed(OUT/'STRENGTHENED_ROOT_SOLUTION.npz',names=d['names'],values=x,types=d['types'])
        result['material_gate']=material(result['objective_LB'],read(OUT/'DISJUNCTIVE_EPIGRAPH_VALIDITY_PROOF.json')['PASS'])
        result['selected']=result['material_gate']['PASS']
        write('DISJUNCTIVE_STRENGTHENED_ROOT_RESULT.json',result)
        print('STRENGTHENED_ROOT',result,flush=True)
    finally:m.dispose()
    if result['selected']:canary()
    else:
        write('DISJUNCTIVE_MIP_CANARY_RESULT.json',dict(status='NOT_RUN',reason='MATERIAL_GATE_FAIL',
              verdict='FAILED',optimization_calls=0,first_nonroot=None,first_branch=None,LB=None,UB=None,gap=None,
              next_direction='route-transition / multi-time disjunction',additional_experiments=0))

def canary():
    gate('canary_before_setup')
    assert read(OUT/'DISJUNCTIVE_STRENGTHENED_ROOT_RESULT.json')['selected']
    import gurobipy as gp
    A,d,B,e,identity,_=inputs();m,_=model(B,e,identity)
    try:
        install(m)
        policy=dict(Threads=1,Method=2,NodeMethod=1,Crossover=2,DegenMoves=0,CutPasses=1,MIPFocus=3,
              MIPGap=.005,FeasibilityTol=1e-8,OptimalityTol=1e-8,IntFeasTol=1e-8,Seed=20260929,TimeLimit=600)
        for key,value in policy.items():setattr(m.Params,key,value)
        m.Params.LogFile='docs/v42_m1_location_grid_disjunctive_cuts/DISJUNCTIVE_MIP_CANARY.log'
        events=[];first_nonroot=None;first_branch=None;last_bound=[None]
        def callback(model,where):
            nonlocal first_nonroot,first_branch
            if where==gp.GRB.Callback.MIPNODE:
                nodes=model.cbGet(gp.GRB.Callback.MIPNODE_NODCNT)
                if nodes>0 and first_nonroot is None:
                    first_nonroot=model.cbGet(gp.GRB.Callback.RUNTIME)
            if where==gp.GRB.Callback.MIP:
                t=model.cbGet(gp.GRB.Callback.RUNTIME);nodes=model.cbGet(gp.GRB.Callback.MIP_NODCNT)
                open_nodes=model.cbGet(gp.GRB.Callback.MIP_NODLFT);bound=model.cbGet(gp.GRB.Callback.MIP_OBJBND)
                if open_nodes>1 and first_branch is None:first_branch=t
                if abs(bound)<1e90 and (last_bound[0] is None or bound>last_bound[0]+1e-8):
                    events.append(dict(runtime=t,nodes=nodes,open_nodes=open_nodes,LB=bound));last_bound[0]=bound
        once('MIP_CANARY');m.optimize(callback)
        lower=float(m.ObjBound) if abs(m.ObjBound)<1e90 else None
        upper=float(m.ObjVal) if m.SolCount else None
        audit_result=None
        if m.SolCount:audit_result=audit(A,d,np.array(m.getAttr('X')),integral=True,tolerance=1e-5)
        progression=bool(events and lower is not None and lower>=BASE_LB-1e-8 and lower>BASE_LB+1e-8)
        verdict='SUCCESS' if (first_nonroot is not None or first_branch is not None) and progression else 'PARTIAL'
        write('DISJUNCTIVE_MIP_CANARY_RESULT.json',dict(status=verdict,verdict=verdict,solver_status=m.Status,
              runtime=m.Runtime,optimization_calls=1,settings=policy,first_nonroot=first_nonroot,first_branch=first_branch,
              LB=lower,UB=upper,gap=float(m.MIPGap) if m.SolCount else None,
              bound_events=events,valid_bound_progression=progression,incumbent_original_audit=audit_result,
              zero_action_Start_attempts=0,production_MIP_1800_calls=0))
    finally:m.dispose()

if __name__=='__main__':run()
