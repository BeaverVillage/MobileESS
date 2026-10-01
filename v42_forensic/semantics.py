"""Bounded exhaustive path checks for window occupancy integrality."""
from collections import defaultdict
import gurobipy as gp
from .common import *

def fixture_checks():
    # Original authority semantics: travel occupies [depart,connect), arrival
    # does not prematurely enable connection; boundary crossing is selected.
    from v42_native.mess import RouteArc
    sites=('A','B','C');H=6
    routes=(RouteArc('AB','A','B',0,2,4,.1,'a'*64),RouteArc('AC','A','C',1,2,3,.1,'b'*64),
            RouteArc('BC','B','C',4,5,5,.1,'c'*64),RouteArc('CA','C','A',3,4,5,.1,'d'*64))
    arcs=arcs_for(sites,routes,H);outgoing=defaultdict(list);incoming=defaultdict(list)
    for k,a in enumerate(arcs):outgoing[a[0],a[1]].append(k);incoming[a[2],a[3]].append(k)
    paths=[]
    def walk(s,t,path):
        if t==H:paths.append(path);return
        for k in outgoing[s,t]:walk(arcs[k][2],arcs[k][3],path+[k])
    walk('A',0,[])
    rows=[]
    for window in [(2,2),(2,3),(4,5),(0,5)]:
        selected=[k for k,a in enumerate(arcs) if selected_arc(a,*window)]
        assert len(selected)==len(set(selected))
        crossing=[k for k,a in enumerate(arcs) if a[-1] is not None and a[1]<window[0]<a[3]]
        assert all(k in selected for k in crossing)
        for path in paths:
            for t in range(window[0],window[1]+1):assert sum(arcs[k][1]<=t<arcs[k][3] for k in path)==1
        m=gp.Model();m.Params.OutputFlag=0;m.Params.Threads=1;m.Params.MIPGap=0
        x=m.addVars(range(len(arcs)),lb=0,ub=1)
        for k in selected:x[k].VType=gp.GRB.BINARY
        for s in sites:
            for t in range(H):m.addConstr(gp.quicksum(x[k] for k in outgoing[s,t])-gp.quicksum(x[k] for k in incoming[s,t])==int(s=='A' and t==0))
        m.addConstr(gp.quicksum(x[k] for k,a in enumerate(arcs) if a[3]==H)==1)
        for t in range(window[0],window[1]+1):
            for state in [*sites,'TRANSIT']:
                ks=[k for k,a in enumerate(arcs) if a[1]<=t<a[3] and (state=='TRANSIT' and a[-1] is not None or state!='TRANSIT' and a[-1] is None and a[0]==state)]
                y=gp.quicksum(x[k] for k in ks);z=m.addVar(lb=0,ub=.5);c1=m.addConstr(z<=y);c2=m.addConstr(z<=1-y)
                m.setObjective(z,gp.GRB.MAXIMIZE);m.optimize();assert m.Status==gp.GRB.OPTIMAL and m.ObjVal<=OBJ_TOL
                rows.append(dict(window_start=window[0],window_end=window[1],time=t,state=state,complete_original_paths=len(paths),restored_arcs=len(selected),
                    before_window_crossing_arcs_selected=len(crossing),maximum_fractional_state_mass=m.ObjVal,all_original_integer_paths_retained=True,PASS=True))
                m.remove([c1,c2,z]);m.update()
        m.dispose()
    table('WINDOW_INTEGRALITY_VALIDATION.csv',rows)
    dump('WINDOW_INTEGRALITY_VALIDATION_SUMMARY.json',dict(PASS=True,checks=len(rows),original_paths=len(paths),no_new_arc_pruning=True,
        semantics='stay occupied slot in W; travel depart<=t<connect intersects W; all arcs departing a W node selected',
        proof='A nonnegative unit DAG flow crosses every time cut with total mass one. Every crossing arc at a time in W is binary, so precisely one is one and all others zero. Window physical state cannot be fractional even when outside flow is continuous. Every original integral path trivially satisfies these restored domains.'))
    print('WINDOW SEMANTICS PASS',len(rows),flush=True)
if __name__=='__main__':fixture_checks()
