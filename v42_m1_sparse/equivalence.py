"""Bounded exhaustive route-pattern comparison; free charge modes solved globally."""
from itertools import product
from types import SimpleNamespace
from collections import defaultdict
import math
import numpy as np
import gurobipy as gp
from v42_root.common import *
from v42_native.mess import Battery,RouteArc
from v42_native.grid import GridAuthority,add_grid
from v42_native.voltage import Stage
from .grid import CANDIDATES,response,add_compressed

CASES=['all_stay','one_movement','multiple_movement_choices','P_charge_only','P_discharge_only','positive_Q','negative_Q','PQ_within_PCS','near_PCS_boundary','SOC_limited','terminal_SOC_binding','lower_voltage_binding','upper_voltage_binding','line_face_binding','transformer_current_binding','transformer_kVA_binding','PR105_overvoltage','route_dependent_connection','multiple_MESS_same_site','multiple_MESS_different_sites']
def route_patterns(sites,horizon,routes,initial):
    arcs=[(s,t,s,t+1,None) for s in sites for t in range(horizon)]+[(r.source,r.depart,r.destination,r.connect,r) for r in routes]
    outgoing=defaultdict(list)
    for k,a in enumerate(arcs):outgoing[a[:2]].append(k)
    def paths(s,t,path):
        if t==horizon:return [path]
        return [p for k in outgoing[s,t] for p in paths(arcs[k][2],arcs[k][3],path+[k])]
    units=list(sorted(initial));choices=[paths(initial[u],0,[]) for u in units]
    return [dict(zip(units,p)) for p in product(*choices)],arcs
def fixture(case):
    sites=('A','B','C');H=4
    initial={'M0':'A','M1':'B'}
    if case=='multiple_MESS_same_site':initial={'M0':'A','M1':'A','M2':'A'}
    if case=='multiple_MESS_different_sites':initial={'M0':'A','M1':'B','M2':'C'}
    b=Battery(0,20,10,10,4,5,.95,.95)
    if case=='P_charge_only':b=Battery(0,20,10,10+.25*.95,4,5,.95,.95)
    if case=='P_discharge_only':b=Battery(0,20,10,10-.25/.95,4,5,.95,.95)
    if case=='SOC_limited':b=Battery(0,20,0,0,4,5,.95,.95)
    routes=tuple(RouteArc(s+d,s,d,t,t+1,t+1,.1,'a'*64) for s,d,t in [('A','B',1),('A','C',1),('B','A',2),('C','A',2)])
    if case not in ('one_movement','multiple_movement_choices','route_dependent_connection'):routes=()
    names=['aidc_load_kw[A]']+[f'mess_p_kw[{s}]' for s in sites]+[f'mess_q_kvar[{s}]' for s in sites]
    coeff=[]
    for t in range(H):
        voltage=np.array([1.,1.])
        vm=np.array([[.0001,.0002],[.001,.0011],[.0012,.0009],[.0008,.0013],[.002,.0019],[.0018,.0021],[.0022,.0017]])
        if case in ('lower_voltage_binding','upper_voltage_binding'):
            voltage[:]=.912025 if case=='lower_voltage_binding' else 1.092025;vm[:]=0
        if case=='PR105_overvoltage':voltage[:]=1.1
        wp=np.array([[.01,.05,.04,.06,.03,.02,.04],[.02,.08,.09,.07,.03,.04,.02]])
        wq=np.array([[.02,.02,.03,.04,.05,.06,.04],[.03,.05,.04,.06,.07,.06,.08]])
        cm=np.array([[0.,0.],[.01,.01],[.011,.012],[.009,.013],[.02,.02],[.018,.017],[.019,.021]])
        pc=np.array([3.,2.]);qc=np.array([1.,.5]);ic=np.array([.6,.5]);ratings=[None,8.]
        if case=='line_face_binding':pc[0]=0;qc[0]=0;wp[0]=0;wq[0]=0;cm[:,0]=0;ic[0]=.6
        if case=='transformer_current_binding':ic[1]=1.;cm[:,1]=0
        if case=='transformer_kVA_binding':ratings[1]=2./math.cos(math.pi/16);pc[1]=2.;qc[1]=0;wp[1]=0;wq[1]=0
        coeff.append(SimpleNamespace(slot=t,control_names=names,coefficient_sha256='b'*64,voltage_constant=voltage,voltage_matrix=vm,branch_limits=np.array([10.,10.]),flow_p_constant=pc,flow_q_constant=qc,flow_p_matrix=wp,flow_q_matrix=wq,anchor=np.zeros(7),current_constant=ic,current_matrix=cm,branch_names=('line.test::a','transformer.main::a'),transformer_ratings=ratings))
    return sites,H,initial,b,routes,coeff
def compare_case(case,label):
    import v42_native.mess as native
    sites,H,initial,b,routes,coeff=fixture(case);patterns,arcs=route_patterns(sites,H,routes,initial);output=[]
    authority=GridAuthority(*(['c'*64]*4),.912025,1.092025,True,stage=Stage.M1)
    def builder(m,p,q):
        bindings=[];cost=[]
        if label!='M1-F0':
            p={key:response(m,f'injection_P[{key[0]},{key[1]}]',v,bindings) for key,v in p.items()}
            q={key:response(m,f'injection_Q[{key[0]},{key[1]}]',v,bindings) for key,v in q.items()}
        controls=[[0.]+[p[s,t] for s in sites]+[q[s,t] for s in sites] for t in range(H)]
        rho=add_grid(m,coeff,controls,authority) if label=='M1-F0' else add_compressed(m,coeff,controls,authority,label,bindings,cost)
        m.update()
        def var(prefix,t=0,s='A',u='M0'):return m.getVarByName(f'{prefix}[{u},{s},{t}]')
        if case=='P_charge_only':
            for v in m.getVars():
                if v.VarName.startswith('Pdis['):m.addConstr(v==0)
            m.addConstr(var('Pch')==1)
        elif case=='P_discharge_only':
            for v in m.getVars():
                if v.VarName.startswith('Pch['):m.addConstr(v==0)
            m.addConstr(var('Pdis')==1)
        elif case in ('positive_Q','negative_Q','near_PCS_boundary'):
            m.addConstr(var('Q')==({'positive_Q':2.,'negative_Q':-2.,'near_PCS_boundary':b.pcs_kva*math.cos(math.pi/16)}[case]))
            if case=='near_PCS_boundary':m.addConstr(var('Pch')==0);m.addConstr(var('Pdis')==0)
        elif case=='PQ_within_PCS':m.addConstr(var('Pdis')==1);m.addConstr(var('Q')==2)
        elif case=='SOC_limited':m.addConstr(var('Pdis')==1) # Explicit infeasible action at minimum initial SOC.
        if case in ('one_movement','route_dependent_connection'):m.addConstr(m.getVarByName(f'arc[M0,{len(sites)*H}]')==1)
        return [('rho',rho),('reserve_shortfall',0.)]
    def optimizer(m,legacy,deadline,*args,**kwargs):
        m.Params.Threads=1;m.Params.Seed=20260929;m.Params.MIPGap=0;m.update()
        objectives=[legacy[0][1],legacy[2][1],legacy[3][1]]
        variables=[v for v in m.getVars() if v.VarName.startswith('arc[')]
        for index,pattern in enumerate(patterns):
            selected={f'arc[{u},{k}]' for u,ks in pattern.items() for k in ks}
            for v in variables:v.LB=v.UB=float(v.VarName in selected)
            locks=[];scores=[];feasible=False
            for i,obj in enumerate(objectives):
                m.setObjective(obj);m.optimize()
                if m.Status==gp.GRB.INFEASIBLE:break
                assert m.Status==gp.GRB.OPTIMAL,(case,label,m.Status)
                feasible=True;scores.append(m.ObjVal)
                if i<2:locks.append(m.addConstr(obj<=m.ObjVal+(1e-7 if i==0 else 1e-8)))
            if len(scores)!=3:feasible=False
            output.append(dict(pattern=index,feasible=feasible,scores=scores if feasible else [],route=pattern))
            for lock in locks:m.remove(lock)
            m.update()
        return None,dict(bounded_only=True)
    class Budget:
        stage='M1'
        def check(self):pass
    original=native.optimize;native.optimize=optimizer
    try:native.solve('M1',Budget(),sites,initial,routes,b,H,builder)
    finally:native.optimize=original
    return output
def run():
    rows=[];all_results={}
    for case in CASES:
        old=compare_case(case,'M1-F0');results={'M1-F0':old}
        for label in list(CANDIDATES)[1:]:
            new=compare_case(case,label);assert len(new)==len(old)
            for a,b in zip(old,new):
                assert a['route']==b['route'] and a['feasible']==b['feasible'],(case,label,a,b)
                if a['feasible']:assert np.max(np.abs(np.array(a['scores'])-b['scores']))<=1e-5,(case,label,a,b)
            results[label]=new
        feasible=[r for r in old if r['feasible']]
        best=min((tuple(r['scores']) for r in feasible),default=None)
        rows.append(dict(case=case,PASS=True,exhaustive_route_patterns=len(old),feasible_patterns=len(feasible),P1=None if best is None else best[0],P2_energy=None if best is None else best[1],P2_count=None if best is None else best[2],candidates=6,physical_set='bijective auxiliary elimination for entire continuous fiber; all complete routes enumerated; free charge modes globally optimized'))
        all_results[case]=results;print('EQUIVALENCE',case,'PASS',len(old),flush=True)
    table('BOUNDED_EQUIVALENCE_RESULTS.csv',rows)
    dump('FORMULATION_EQUIVALENCE.json',dict(PASS=True,real_algebraic_projection_proof='EXACT_PROJECTION_PROOF.md',numerical_tolerance=1e-5,fixtures=20,candidates=6,results=all_results,continuous_physical_set_proof='all grid auxiliaries have unique affine values; eliminating equalities recovers every original grid inequality; route/SOC/PCS constructor byte identical'))
if __name__=='__main__':run()
