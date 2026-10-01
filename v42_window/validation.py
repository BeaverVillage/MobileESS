"""Enumerated physical fixtures for W7 G1/G2/G3 conditional lower bounds."""
from itertools import combinations,product
from dataclasses import replace
import gurobipy as gp
from .common import *
from .grid import add_window
from .oracle import lower_certificate

CASES={'stationary':'all_stay','travel_inside_window':'multiple_movement_choices','travel_spanning_condition_boundary':'route_dependent_connection',
    'charging':'P_charge_only','discharging':'P_discharge_only','Q_only':'positive_Q','joint_PQ':'PQ_within_PCS','SOC_minimum':'SOC_limited',
    'terminal_SOC':'terminal_SOC_binding','voltage_binding':'upper_voltage_binding','transformer_binding':'transformer_kVA_binding','line_P1_binding':'line_face_binding'}

def run():
    import v42_native.mess as native
    from v42_m1_sparse.equivalence import fixture,route_patterns
    from v42_native.grid import add_grid,GridAuthority
    from v42_native.voltage import Stage
    rows=[]
    for case,source in CASES.items():
        sites,H,initial,b,routes,coeff=fixture(source)
        if case=='travel_spanning_condition_boundary':routes=tuple(replace(r,connect=3) for r in routes if r.depart==1)
        patterns,arcs=route_patterns(sites,H,routes,initial);holder={};authority=GridAuthority(*(['c'*64]*4),.912025,1.092025,True,stage=Stage.M1)
        def grid(m,p,q):
            # Fixture actions are retained in both original and W7, before grid.
            m.update()
            def var(f,s='A',t=1,u='M0'):return m.getVarByName(f'{f}[{u},{s},{t}]')
            if case=='Q_only':
                for v in m.getVars():
                    if v.VarName.startswith(('Pch[','Pdis[')):m.addConstr(v==0,name='fixture_action')
                m.addConstr(var('Q')==2,name='fixture_action')
            if case=='joint_PQ':m.addConstr(var('Pdis')==1,name='fixture_action');m.addConstr(var('Q')==2,name='fixture_action')
            if case=='charging':m.addConstr(var('Pch')==1,name='fixture_action')
            if case=='discharging':m.addConstr(var('Pdis')==1,name='fixture_action')
            m.update();holder['grid_start']=m.NumConstrs
            controls=[[0.]+[p[s,t] for s in sites]+[q[s,t] for s in sites] for t in range(H)]
            return [('rho',add_grid(m,coeff,controls,authority)),('reserve_shortfall',0.)]
        def hook(m,c):holder['context']=c
        def inspect(m,obj,*args,**kwargs):
            m.update();exact=[];m.Params.Method=2;m.Params.Threads=1;m.Params.MIPGap=0
            for index,path in enumerate(patterns):
                active={f'arc[{u},{k}]' for u,ks in path.items() for k in ks}
                for v in m.getVars():
                    if v.VarName.startswith('arc['):v.LB=v.UB=float(v.VarName in active)
                m.setObjective(obj[0][1]);m.optimize();assert m.Status in (gp.GRB.OPTIMAL,gp.GRB.INFEASIBLE)
                if m.Status==gp.GRB.OPTIMAL:
                    states={}
                    for u in initial:
                        for t in range(H):
                            a=[arcs[k] for k in path[u] if arcs[k][1]<=t<arcs[k][3]];assert len(a)==1
                            states[u,t]=a[0][0] if a[0][-1] is None else 'TRANSIT'
                    exact.append(dict(states=states,P1=m.ObjVal))
            for v in m.getVars():
                if v.VarName.startswith('arc['):v.LB=0;v.UB=1
            m.update();lp=m.copy();lp.remove(lp.getConstrs()[holder['grid_start']:]);lp.setObjective(0);lp.remove(lp.getVarByName('rho_max'));lp.update()
            variables={v.VarName:v for v in lp.getVars()}
            p={(s,t):gp.quicksum(variables.get(f'Pdis[{u},{s},{t}]',0.)-variables.get(f'Pch[{u},{s},{t}]',0.) for u in initial) for s in sites for t in range(H)}
            q={(s,t):gp.quicksum(variables.get(f'Q[{u},{s},{t}]',0.) for u in initial) for s in sites for t in range(H)}
            controls=[[0.]+[p[s,t] for s in sites]+[q[s,t] for s in sites] for t in range(H)]
            rho=add_window(lp,coeff,controls,authority,'M1-F0',[],[],range(1,4));lp.setObjective(rho);lp.update()
            lo=np.array(lp.getAttr('LB'));hi=np.array(lp.getAttr('UB'));lp.setAttr('VType',[gp.GRB.CONTINUOUS]*lp.NumVars);lp.setAttr('LB',lo);lp.setAttr('UB',hi)
            lp.Params.Method=2;lp.Params.Threads=1;lp.update();variables={v.VarName:v for v in lp.getVars()}
            from v42_epigraph.common import reachable_arcs
            reachable=reachable_arcs(sites,initial,routes,H);axes={}
            for u in initial:
                for t in [1,3]:axes[u,t]=[s for s in [*sites,'TRANSIT'] if set(state_indices(arcs,t)[s])&reachable[u]]
            conditions=[('G1',[(u,1,s)]) for u in initial for s in axes[u,1]]
            conditions += [('G2',[(u,1,a),(v,1,z)]) for u,v in combinations(initial,2) for a,z in product(axes[u,1],axes[v,1])]
            # Reachability for G3 is authority-only: every complete route pattern,
            # even if its physical/grid decisions have no feasible integer point.
            for u in initial:
                pairs=set()
                for path in patterns:
                    states=[]
                    for t in [1,3]:
                        arc=next(arcs[k] for k in path[u] if arcs[k][1]<=t<arcs[k][3]);states.append(arc[0] if arc[-1] is None else 'TRANSIT')
                    pairs.add(tuple(states))
                conditions += [('G3',[(u,1,a),(u,3,z)]) for a,z in sorted(pairs)]
            for kind,cond in conditions:
                fixed=[lp.addConstr(gp.quicksum(variables.get(f'arc[{u},{k}]',0.) for k in state_indices(arcs,t)[s])==1) for u,t,s in cond]
                lp.optimize();opt=[r['P1'] for r in exact if all(r['states'][u,t]==s for u,t,s in cond)]
                bound=None
                if lp.Status==gp.GRB.OPTIMAL:
                    bound,certificate,_=lower_certificate(lp,lp.getAttr('Pi'),(lo,hi))
                    assert not opt or bound<=min(opt)+OBJ_TOL,(case,kind,cond,bound,opt)
                else:assert lp.Status==gp.GRB.INFEASIBLE and not opt
                rows.append(dict(case=case,kind=kind,conditions=str(cond),route_patterns=len(patterns),conditional_feasible_integer_paths=len(opt),
                    W7_LP_bound=bound,exact_full_conditional_integer_P1=min(opt) if opt else None,status=int(lp.Status),PASS=True))
                lp.remove(fixed);lp.update()
            lp.dispose();return None,dict(bounded_only=True)
        class Budget:
            stage='M1'
            def check(self):pass
        old=native.optimize;native.optimize=inspect
        try:native.solve('M1',Budget(),sites,initial,routes,b,H,grid,strengthening_hook=hook)
        finally:native.optimize=old
        print('W7 VALIDATION',case,'PASS',flush=True)
    table('W7_VALIDATION.csv',rows);dump('W7_VALIDATION_SUMMARY.json',dict(PASS=True,cases=list(CASES),conditional_checks=len(rows),G1_G2_G3_tested=True,complete_route_patterns_enumerated=True,mode_bits_integer_optimal=True))
if __name__=='__main__':run()
