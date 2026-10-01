"""Enumerated route fixtures, conditional integer optima and LP bound checks."""
from itertools import combinations,product
from dataclasses import replace
import gurobipy as gp
from .common import *
from .oracle import add_slot_lines,finite_bound_certificate

def run():
    import v42_native.mess as native
    from v42_m1_sparse.equivalence import fixture,route_patterns
    from v42_native.grid import add_grid,GridAuthority
    from v42_native.voltage import Stage
    rows=[]
    for case in ['multiple_movement_choices','route_dependent_connection','multiple_MESS_same_site','PQ_within_PCS']:
        sites,H,initial,b,routes,coeff=fixture(case)
        if case=='route_dependent_connection':routes=tuple(replace(r,connect=3) for r in routes if r.depart==1)
        patterns,arcs=route_patterns(sites,H,routes,initial);holder={}
        authority=GridAuthority(*(['c'*64]*4),.912025,1.092025,True,stage=Stage.M1)
        def grid(m,p,q):
            controls=[[0.]+[p[s,t] for s in sites]+[q[s,t] for s in sites] for t in range(H)]
            before=m.NumConstrs;m.update();before=m.NumConstrs
            rho=add_grid(m,coeff,controls,authority);m.update()
            holder.update(grid_rows=[r.ConstrName for r in m.getConstrs()[before:]],grid_start=before,p=p,q=q,rho=rho)
            return [('rho',rho),('reserve_shortfall',0.)]
        def hook(m,c):holder['context']=c
        def inspect(m,obj,*args,**kwargs):
            m.update();c=holder['context'];names=m.getAttr('VarName');exact=[]
            m.Params.Threads=1;m.Params.MIPGap=0;m.Params.Method=2
            for index,path in enumerate(patterns):
                active={f'arc[{u},{k}]' for u,ks in path.items() for k in ks}
                for v in m.getVars():
                    if v.VarName.startswith('arc['):v.LB=v.UB=float(v.VarName in active)
                m.setObjective(obj[0][1]);m.optimize()
                assert m.Status in (gp.GRB.OPTIMAL,gp.GRB.INFEASIBLE)
                if m.Status==gp.GRB.OPTIMAL:
                    selected={}
                    for u in initial:
                        for t in range(H):
                            ks=[k for k in path[u] if arcs[k][1]<=t<arcs[k][3]];assert len(ks)==1
                            selected[u,t]=arcs[ks[0]][0] if arcs[ks[0]][-1] is None else 'TRANSIT'
                    exact.append(dict(path=index,states=selected,P1=m.ObjVal))
            for v in m.getVars():
                if v.VarName.startswith('arc['):v.LB=0;v.UB=1
            m.update()
            for t in [1,2,3]:
                lp=m.copy();lp.Params.Method=2;lp.Params.Threads=1
                lp.remove(lp.getConstrs()[holder['grid_start']:]);lp.update()
                variables={v.VarName:v for v in lp.getVars()}
                pc={key:gp.LinExpr(variables[v.VarName]) if not isinstance(v,float) else v for key,v in c.charge.items()}
                dc={key:gp.LinExpr(variables[v.VarName]) if not isinstance(v,float) else v for key,v in c.discharge.items()}
                qc={key:gp.LinExpr(variables[v.VarName]) if not isinstance(v,float) else v for key,v in c.reactive.items()}
                xx=[0.]+[gp.quicksum(dc[u,s,t]-pc[u,s,t] for u in initial) for s in sites]+[gp.quicksum(qc[u,s,t] for u in initial) for s in sites]
                add_slot_lines(lp,coeff[t],xx,variables['rho_max']);lp.setObjective(variables['rho_max'])
                lo=lp.getAttr('LB');hi=lp.getAttr('UB');lp.setAttr('VType',[gp.GRB.CONTINUOUS]*lp.NumVars);lp.setAttr('LB',lo);lp.setAttr('UB',hi);lp.update()
                indices=state_indices(arcs,t);reachable=reachable_arcs(sites,initial,routes,H)
                axes={u:[s for s in [*sites,'TRANSIT'] if set(indices[s]) & reachable[u]] for u in initial}
                conditions=[[(u,s)] for u in initial for s in axes[u]]
                conditions += [[(u,s),(v,z)] for u,v in combinations(initial,2) for s,z in product(axes[u],axes[v])]
                for cond in conditions:
                    constraints=[lp.addConstr(gp.quicksum(variables.get(f'arc[{u},{k}]',0.) for k in indices[s])==1) for u,s in cond]
                    lp.optimize();opt=[p['P1'] for p in exact if all(p['states'][u,t]==s for u,s in cond)]
                    if lp.Status==gp.GRB.OPTIMAL:
                        bound,certificate,_=finite_bound_certificate(lp,lp.getAttr('Pi'))
                        assert not opt or bound<=min(opt)+OBJ_TOL,(case,t,cond,bound,opt)
                        rows.append(dict(case=case,time=t,conditioning=str(cond),route_patterns=len(patterns),integer_feasible_patterns=len(opt),O1_beta=bound,
                            exact_conditional_integer_optimum=min(opt) if opt else None,LP_status=int(lp.Status),PASS=True,travel_connect_boundary=case=='route_dependent_connection'))
                    else:
                        assert lp.Status==gp.GRB.INFEASIBLE and not opt
                        rows.append(dict(case=case,time=t,conditioning=str(cond),route_patterns=len(patterns),integer_feasible_patterns=0,O1_beta=None,exact_conditional_integer_optimum=None,LP_status=int(lp.Status),PASS=True,travel_connect_boundary=case=='route_dependent_connection'))
                    lp.remove(constraints);lp.update()
                lp.dispose()
            return None,dict(optimize_calls='bounded validation only')
        class Budget:
            stage='M1'
            def check(self):pass
        old=native.optimize;native.optimize=inspect
        try:native.solve('M1',Budget(),sites,initial,routes,b,H,grid,strengthening_hook=hook)
        finally:native.optimize=old
        print('O1 VALIDATION',case,'PASS',flush=True)
    table('O1_VALIDATION.csv',rows)
    dump('O1_VALIDATION_SUMMARY.json',dict(PASS=True,cases=4,conditional_tests=len(rows),all_complete_route_paths_enumerated=True,integer_mode_bits_globally_optimized=True,
        LP_bound_not_incumbent=True,stay_transit_departure_connection_tested=True))

if __name__=='__main__':run()
