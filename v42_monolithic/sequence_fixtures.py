"""Supplemental feasible multi-move physics cases; core frozen fixtures unchanged."""
import numpy as np
import gurobipy as gp
from .fixtures import CASES,make,paths
from .formulation import Compact
from .common import dump

EXTRA={
    'feasible_immediate_connect_departure':[('A',0,'B',2,.05),('B',2,'C',3,.05)],
    'feasible_three_moves':[('A',0,'B',1,.05),('B',1,'C',2,.05),('C',2,'A',3,.05)],
}
def run(write=True):
    records=[]
    with gp.Env(params={'OutputFlag':0}) as env:
        for name,routes in EXTRA.items():
            assert name not in CASES
            CASES[name]=routes
            try:
                o,g,x=make(env,name);c=Compact(o,g,{'M':'A'},4);n=c.build(env);n.Params.OutputFlag=0
                path=next(p for p in paths(g,x) if sum(g[k][-1] is not None for k in p)==len(routes))
                zero=np.zeros(o.NumVars)
                for k in path:zero[x[k].index]=1
                mapped=c.forward(zero)
                for k,var in x.items():var.LB=var.UB=int(k in path)
                for p in list(c.z.values())+list(c.movement_columns.values()):n.getVars()[p].LB=n.getVars()[p].UB=mapped[p]
                for m in [o,n]:m.Params.Heuristics=0;m.Params.Threads=1;m.Params.MIPGap=0;m.optimize()
                assert o.Status==n.Status==gp.GRB.OPTIMAL,'FEASIBLE_SEQUENCE_BECAME_INFEASIBLE'
                a=np.array(o.getAttr('X'));b=np.array(n.getAttr('X'));inv=c.inverse(b)
                assert abs(o.ObjVal-n.ObjVal)<=1e-8 and c.residual(b)<=1e-8 and c.residual(c.forward(a))<=1e-8
                soc=[]
                for t in range(5):
                    j=o.getVarByName(f'SOC[{t}]').index;assert abs(a[j]-inv[j])<=1e-8;soc.append(float(inv[j]))
                assert abs(soc[0]-1)<=1e-8 and abs(soc[-1]-1)<=1e-8
                for k in path:
                    arc=g[k]
                    if arc[-1] is not None:
                        assert c.connected(b,'M',arc[0],arc[1])==0
                        for prefix in ['Pch','Pdis','Q']:assert abs(inv[o.getVarByName(f'{prefix}[M,{arc[0]},{arc[1]}]').index])<=1e-8
                records.append(dict(fixture=name,PASS=True,movement_count=len(routes),original_objective=o.ObjVal,compact_objective=n.ObjVal,
                    same_SOC=soc,selected_path=list(path),terminal_equality=True,departure_transit_PQ_zero=True,original_compact_physical_path_feasible=True))
                o.dispose();n.dispose()
            finally:del CASES[name]
    result=dict(PASS=True,extra_fixtures=records,core_frozen_fixture_inputs_unchanged=True,full_M1_physics_unchanged=True)
    if write:dump('FEASIBLE_SEQUENCE_FIXTURES.json',result)
    return result
if __name__=='__main__':print(run(),flush=True)
