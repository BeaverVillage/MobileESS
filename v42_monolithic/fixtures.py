"""Exhaustive route-ID path and independent physical fixture comparisons."""
import itertools,math
from dataclasses import dataclass
import numpy as np
import gurobipy as gp
from .formulation import Compact
from .common import dump,table

@dataclass(frozen=True)
class Route:
    route_id:str
    energy_kwh:float
    arrive:int

CASES={
 'stay_only':[],
 'one_move':[('A',0,'B',1,.15)],
 'alternative_destinations':[('A',0,'B',1,.15),('A',0,'C',1,.2)],
 'long_connect_delay':[('A',0,'B',3,.15)],
 'terminal_soc':[('A',0,'B',3,1.5)],
 'route_energy_difference':[('A',0,'B',1,.15),('A',1,'B',2,.3)],
 'immediate_post_connect':[('A',0,'B',2,.15),('B',2,'C',3,.2)],
 'parallel_identical':[('A',0,'B',1,.15),('A',0,'B',1,.15)],
 'parallel_distinct':[('A',0,'B',1,.15),('A',0,'B',1,.4)],
 'pq_connection':[('A',1,'B',2,.15)],
 'voltage_coupling':[('A',0,'B',1,.15),('A',1,'C',2,.2)],
 'multiple_movements':[('A',0,'B',1,.15),('B',1,'C',2,.15),('C',2,'A',3,.15)],
}
def make(env,name,H=4,physical=True):
    sites=('A','B','C');graph=[(s,t,s,t+1,None) for s in sites for t in range(H)]
    graph += [(s,t,d,c,Route(str(i),e,min(t+1,c))) for i,(s,t,d,c,e) in enumerate(CASES[name])]
    reach={('A',0)}
    for t in range(H):
        for s,b,d,c,r in graph:
            if b==t and (s,b) in reach:reach.add((d,c))
    m=gp.Model('ORIGINAL_'+name,env=env);m.Params.OutputFlag=0
    x={k:m.addVar(vtype='B',name=f'arc[M,{k}]') for k,a in enumerate(graph) if a[:2] in reach}
    for s in sites:
        for t in range(H):
            m.addConstr(gp.quicksum(x[k] for k,a in enumerate(graph) if k in x and a[:2]==(s,t))-
                gp.quicksum(x[k] for k,a in enumerate(graph) if k in x and a[2:4]==(s,t))==int((s,t)==('A',0)),name='flow')
    m.addConstr(gp.quicksum(x[k] for k,a in enumerate(graph) if k in x and a[3]==H)==1,name='terminal_location')
    if physical:
        E=m.addVars(H+1,lb=0,ub=3,name='SOC');m.addConstr(E[0]==1,name='initial_SOC');m.addConstr(E[H]==1,name='terminal_SOC')
        mode=m.addVars(H,vtype='B',name='charge_mode');rho=m.addVar(lb=0,name='rho');P={};D={};Q={}
        for k,a in enumerate(graph):
            if k not in x or a[-1] is not None:continue
            s,t=a[:2];P[s,t]=m.addVar(lb=0,ub=1,name=f'Pch[M,{s},{t}]');D[s,t]=m.addVar(lb=0,ub=1,name=f'Pdis[M,{s},{t}]');Q[s,t]=m.addVar(lb=-1,ub=1,name=f'Q[M,{s},{t}]')
            m.addConstr(P[s,t]<=x[k],name='connected_Pch');m.addConstr(D[s,t]<=x[k],name='connected_Pdis');m.addConstr(Q[s,t]<=x[k],name='connected_Qmax');m.addConstr(Q[s,t]>=-x[k],name='connected_Qmin')
            m.addConstr(P[s,t]<=mode[t],name='mode_charge');m.addConstr(D[s,t]<=1-mode[t],name='mode_discharge')
            for f in range(16):m.addConstr(math.cos(2*math.pi*f/16)*(D[s,t]-P[s,t])+math.sin(2*math.pi*f/16)*Q[s,t]<=math.cos(math.pi/16)*x[k],name='PCS16')
        for t in range(H):
            p=gp.quicksum(v for (s,b),v in P.items() if b==t);d=gp.quicksum(v for (s,b),v in D.items() if b==t);q=gp.quicksum(v for (s,b),v in Q.items() if b==t)
            energy=gp.quicksum(a[-1].energy_kwh*x[k] for k,a in enumerate(graph) if k in x and a[-1] is not None and a[1]==t)
            m.addConstr(E[t+1]==E[t]+.25*(.9*p-d/.9)-energy,name=f'energy_balance_{t}')
            m.addConstr(.02*(d-p)+.01*q<=.045,name='voltage_upper');m.addConstr(.02*(d-p)+.01*q>=-.045,name='voltage_lower')
            m.addConstr(rho>=.6+.1*(p-d)+.02*q,name='line_loading')
        m.setObjective(rho,gp.GRB.MINIMIZE)
    m.update();return m,graph,x

def paths(graph,x,H=4):
    def walk(node,chosen):
        if node[1]==H:yield tuple(chosen);return
        for k,a in enumerate(graph):
            if k in x and a[:2]==node:yield from walk(a[2:4],chosen+[k])
    return list(walk(('A',0),[]))

def run(env,write=True):
    rows=[];census={};max_error=0.;integrality_probes=0;path_comparisons=0
    for name in CASES:
        o,g,x=make(env,name);c=Compact(o,g,{'M':'A'},4);n=c.build(env);n.Params.OutputFlag=0
        for m in (o,n):
            for key,val in dict(Threads=1,Heuristics=0,FeasibilityTol=1e-9,OptimalityTol=1e-9,IntFeasTol=1e-9,MIPGap=0).items():m.setParam(key,val)
        route_paths=paths(g,x);feasible=[];objectives=[]
        for path in route_paths:
            selected=set(path);ov=np.zeros(o.NumVars)
            for k,v in x.items():ov[v.index]=int(k in selected)
            nv=c.forward(ov)
            oa=o.copy();na=n.copy()
            for k,v in x.items():oa.getVars()[v.index].LB=oa.getVars()[v.index].UB=int(k in selected)
            for p in list(c.z.values())+list(c.movement_columns.values()):na.getVars()[p].LB=na.getVars()[p].UB=float(nv[p])
            oa.optimize();na.optimize();assert oa.Status==na.Status,(name,path,oa.Status,na.Status)
            if oa.Status==gp.GRB.OPTIMAL:
                err=abs(oa.ObjVal-na.ObjVal);assert err<=1e-8,(name,path,err);max_error=max(max_error,err)
                a=np.array(oa.getAttr('X'));b=np.array(na.getAttr('X'));assert np.max(abs(c.inverse(c.forward(a))-a))<=1e-12
                assert c.residual(c.forward(a))<=1e-8 and c.residual(b)<=1e-8
                # Both entire physical polytopes correspond, not just a possibly nonunique optimum.
                inv=c.inverse(b);r=o.getA()@inv-np.array(o.getAttr('RHS'));s=np.array(o.getAttr('Sense'))
                assert np.max(np.where(s=='=',abs(r),np.where(s=='<',r,-r)))<=1e-8
                for p in c.movement_columns.values():assert abs(b[p]-round(b[p]))<=1e-9
                feasible.append(path);objectives.append(oa.ObjVal)
            else:assert oa.Status==gp.GRB.INFEASIBLE
            oa.dispose();na.dispose();path_comparisons+=1
        # Exhaustively enumerate compact physical trajectory patterns; omit modes from no-good.
        enum=n.copy();patterns=[];binary=list(c.z.values())+c.selectors
        while True:
            enum.optimize()
            if enum.Status==gp.GRB.INFEASIBLE:break
            assert enum.Status==gp.GRB.OPTIMAL
            v=np.array(enum.getAttr('X'));old=c.inverse(v);pattern=tuple(k for k,var in x.items() if old[var.index]>.5)
            pattern=tuple(sorted(pattern,key=lambda k:g[k][1]));assert pattern in feasible and pattern not in patterns
            patterns.append(pattern);vs=enum.getVars();enum.addConstr(gp.quicksum(1-vs[p] if v[p]>.5 else vs[p] for p in binary)>=1)
        assert set(patterns)==set(feasible);enum.dispose()
        # Stronger negative probe: ANY fractional nonselector movement with integer z is infeasible,
        # tested on the whole mobility feasible set without SOC/grid removing counterexamples.
        mob,mg,mx=make(env,name,physical=False);mc=Compact(mob,mg,{'M':'A'},4);mn=mc.build(env);mn.Params.OutputFlag=0
        for p in mc.movement_columns.values():
            probe=mn.copy();probe.Params.OutputFlag=0;probe.getVars()[p].LB=.01;probe.getVars()[p].UB=.99;probe.optimize()
            assert probe.Status==gp.GRB.INFEASIBLE,('FRACTIONAL_MOVEMENT',name,p);probe.dispose();integrality_probes+=1
        # Free root relaxations have the same optimum and bidirectional mapped primal feasibility.
        lp_o=o.relax();lp_n=n.relax();lp_o.Params.OutputFlag=lp_n.Params.OutputFlag=0;lp_o.optimize();lp_n.optimize()
        assert lp_o.Status==lp_n.Status==gp.GRB.OPTIMAL and abs(lp_o.ObjVal-lp_n.ObjVal)<=1e-8
        assert c.residual(c.forward(np.array(lp_o.getAttr('X'))))<=1e-8
        assert c.residual(np.array(lp_n.getAttr('X')))<=1e-8
        rows.append(dict(fixture=name,PASS=True,original_paths=len(route_paths),original_physical_feasible_paths=len(feasible),compact_physical_feasible_paths=len(patterns),objective_error_max=max_error,root_original=lp_o.ObjVal,root_compact=lp_n.ObjVal,parallel_selectors=len(c.selectors),movement_columns=len(c.movement_columns)))
        best=min(objectives);optimal=[list(p) for p,obj in zip(feasible,objectives) if abs(obj-best)<=1e-8]
        census[name]=dict(all_original_paths=[list(p) for p in route_paths],physical_feasible_paths=[list(p) for p in feasible],compact_feasible_paths=[list(p) for p in patterns],same_optimal_route_sets=optimal,path_objectives=objectives,all_route_ids=[r[-1].route_id for r in g if r[-1] is not None],exact_polytope_mapping=True)
        for m in (lp_o,lp_n,o,n,mob,mn):m.dispose()
    result=dict(PASS=True,fixtures=len(rows),path_comparisons=path_comparisons,fractionality_infeasibility_probes=integrality_probes,maximum_objective_error=max_error,census=census)
    if write:table('FIXTURE_EXACTNESS_RESULTS.csv',rows);dump('FIXTURE_PATH_CENSUS.json',result)
    return result
if __name__=='__main__':
    with gp.Env(params={'OutputFlag':0}) as env:print(run(env),flush=True)
