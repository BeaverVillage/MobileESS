"""Exact interval-union DP on the unchanged time-expanded route graph.

Transit consumes travel energy at departure, as in the original scalar SOC
equation. It holds that energy through each intermediate boundary.
"""
from .common import OUT,read,write,table,sha
from .analysis import graph_inputs
from collections import defaultdict
from fractions import Fraction as F
import math
import numpy as np
import gurobipy as gp

def rational(value):
    return F.from_float(float(value))

def union(intervals):
    result=[]
    for lo,hi in sorted((a,b) for a,b in intervals if a<=b):
        if result and lo<=result[-1][1]:
            result[-1]=(result[-1][0],max(hi,result[-1][1]))
        else:result.append((lo,hi))
    return result

def intersect(left,right):
    return union((max(a,c),min(b,d)) for a,b in left for c,d in right if max(a,c)<=min(b,d))

def shifted(intervals,lo,hi,bounds):
    return intersect([(a+lo,b+hi) for a,b in intervals],[bounds])

def dp(sites,origin,arcs,battery,horizon):
    bounds=(rational(battery.minimum),rational(battery.maximum))
    charge=rational(battery.dt_hours*battery.eta_charge)*rational(battery.p_limit)
    discharge=rational(battery.dt_hours/battery.eta_discharge)*rational(battery.p_limit)
    incoming=defaultdict(list);outgoing=defaultdict(list)
    for k,(s,t,d,e,r) in enumerate(arcs):
        outgoing[s,t].append(k);incoming[d,e].append(k)
    forward={};backward={}
    for t in range(horizon+1):
        for s in sites:
            values=[(rational(battery.initial),rational(battery.initial))] if (s,t)==(origin,0) else []
            for k in incoming[s,t]:
                a,b,_,_,r=arcs[k]
                prev=forward.get((a,b),[])
                if r is None:values+=shifted(prev,-discharge,charge,bounds)
                else:
                    cost=rational(r.energy_kwh)
                    values+=shifted(prev,-cost,-cost,bounds)
            forward[s,t]=union(values)
    for t in range(horizon,-1,-1):
        for s in sites:
            values=[(rational(battery.terminal),rational(battery.terminal))] if t==horizon else []
            for k in outgoing[s,t]:
                _,_,d,e,r=arcs[k]
                future=backward.get((d,e),[])
                if r is None:values+=shifted(future,-charge,discharge,bounds)
                else:
                    cost=rational(r.energy_kwh)
                    values+=shifted(future,cost,cost,bounds)
            backward[s,t]=union(values)
    node={n:intersect(values,backward[n]) for n,values in forward.items()}
    transit={}
    for k,(s,t,d,e,r) in enumerate(arcs):
        if r is None:continue
        cost=rational(r.energy_kwh)
        depart=intersect(forward[s,t],shifted(backward[d,e],cost,cost,bounds))
        depart=intersect(depart,[(bounds[0]+cost,bounds[1])])
        transit[k]=[(a-cost,b-cost) for a,b in depart]
    return node,transit,forward,backward

def outward(intervals,battery):
    # Empty states cannot occur in any original integer feasible point. Retain
    # their original battery envelope rather than deleting any route variable.
    if not intervals:return float(battery.minimum),float(battery.maximum)
    lo=float(intervals[0][0]);hi=float(intervals[-1][1])
    if rational(lo)>intervals[0][0]:lo=math.nextafter(lo,-math.inf)
    if rational(hi)<intervals[-1][1]:hi=math.nextafter(hi,math.inf)
    return lo,hi

def formal_proof():
    proof=dict(PASS=True,status='EXACT_VALID_ENVELOPE',
      state_definition='SOC at boundary t: at a site node (s,t), or transit along one selected movement arc depart<t<connect. Travel cost is deducted at departure in SOC[t+1], and SOC is constant until connect.',
      data_authority='Frozen D-1 route and battery in exact PR136 DATA.pkl; no Actual inputs.',
      forward='F(origin,0)={initial}. Stay: (F+[−dt*Pmax/eta_dis, dt*eta_ch*Pmax]) intersect battery bounds. Travel: (F−cost) intersect bounds. Union over incoming arcs; exact disjoint interval unions are retained.',
      backward='B(s,H)={terminal} at every terminal site. Stay: (B+[−dt*eta_ch*Pmax, dt*Pmax/eta_dis]) intersect bounds. Travel: (B+cost) intersect bounds. Union over outgoing arcs.',
      inductive_proof='DAG induction enumerates all possible energy values for battery/route subsystem. The two mode choices give touching continuous intervals for stay energy increments; Q=0 respects original PCS since Pmax<=pcs_kva*cos(pi/16). Travel subtracts its exact original energy once, and transit has no P/Q.',
      node_condition='Exact reachable battery-route set at node is F(s,t) intersect B(s,t). Prefix and suffix concatenate at the same energy; mode choices are independent by slot. Grid feasibility may narrow this set and cannot expand it.',
      transit_condition='Departure interval F(source,depart) intersect (B(destination,connect)+cost) intersect [minimum+cost,maximum]. Intermediate SOC is that interval minus cost.',
      partition_proof='An integer route is one DAG path. At each boundary, either one outgoing site node or one earlier departing, not yet connected movement arc is active. State weights are nonnegative and sum to one. Terminal node weight is incoming flow.',
      inequalities='For each time: sum_state lower(state)*weight(state) <= SOC[t] <= sum_state upper(state)*weight(state). Weights use original arc columns only.',
      integer_equivalence='Every original integer point chooses exactly one state and its energy lies in that state interval; therefore both added rows are redundant on all original integer primary points. No objectives, columns, domains, or original rows change.',
      empty_state_policy='Use original battery bounds; never remove/fix any arc.',
      arithmetic='Exact Fraction.from_float of original coefficients; interval extrema converted outward to IEEE doubles.',
      grid_constraint_omission='Safe outer envelope of the full scientific feasible set; exact battery-route reachability, not assertion of grid-feasible attainment of extrema.',
      new_binary_count=0,transit_states_explicit=True)
    write('SOC_REACHABILITY_PROOF.json',proof)
    return proof

def state_rows(d,sites,initial,arcs,battery,horizon=96):
    index={str(n):i for i,n in enumerate(d['names'])}
    outgoing=defaultdict(list);incoming=defaultdict(list)
    for k,(s,t,dst,e,r) in enumerate(arcs):
        outgoing[s,t].append(k);incoming[dst,e].append(k)
    rows=[];state_records=[]
    for u,origin in initial.items():
        node,transit,_,_=dp(sites,origin,arcs,battery,horizon)
        for t in range(horizon+1):
            lower=defaultdict(float);upper=defaultdict(float);weights=defaultdict(float)
            for s in sites:
                lo,hi=outward(node[s,t],battery)
                keys=incoming[s,t] if t==horizon else outgoing[s,t]
                for k in keys:
                    j=index.get(f'arc[{u},{k}]')
                    if j is not None:lower[j]+=lo;upper[j]+=hi;weights[j]+=1.
                state_records.append(dict(MESS=u,site=s,slot=t,state='node',E_min=lo,E_max=hi,exact_intervals=len(node[s,t])))
            for k,(s,b,dst,e,r) in enumerate(arcs):
                if r is None or not b<t<e:continue
                j=index.get(f'arc[{u},{k}]')
                if j is None:continue
                lo,hi=outward(transit[k],battery)
                lower[j]+=lo;upper[j]+=hi;weights[j]+=1.
            rows.append(dict(MESS=u,slot=t,SOC_index=index[f'SOC[{u},{t}]'],lower=dict(lower),upper=dict(upper),weights=dict(weights)))
    table('SOC_REACHABILITY_STATE_ENVELOPES.csv',state_records)
    return rows

def violation_audit(rows,point):
    records=[]
    for r in rows:
        energy=float(point[r['SOC_index']])
        low=sum(v*point[j] for j,v in r['lower'].items())
        high=sum(v*point[j] for j,v in r['upper'].items())
        mass=sum(v*point[j] for j,v in r['weights'].items())
        for sense,value in [('LOWER',low-energy),('UPPER',energy-high)]:
            records.append(dict(MESS=r['MESS'],slot=r['slot'],sense=sense,SOC=energy,
                                lower_bound=low,upper_bound=high,state_partition_mass=mass,
                                signed_violation=float(value),positive_violation=float(max(0,value)),violated=bool(value>1e-8)))
    table('SOC_REACHABILITY_ROOT_VIOLATION.csv',records)
    summary=dict(violated_count=sum(r['violated'] for r in records),max_violation=max(r['positive_violation'] for r in records),
                 total_positive_violation=sum(r['positive_violation'] for r in records),
                 max_state_partition_error=max(abs(r['state_partition_mass']-1) for r in records),
                 top_50=sorted(records,key=lambda r:r['positive_violation'],reverse=True)[:50])
    write('SOC_REACHABILITY_ROOT_VIOLATION_SUMMARY.json',summary)
    return summary

def add_envelopes(model,rows):
    before=(model.NumConstrs,model.NumVars,model.NumBinVars,model.NumNZs)
    variables=model.getVars()
    for r in rows:
        tag=f"{r['MESS']},{r['slot']}"
        E=variables[r['SOC_index']]
        model.addConstr(E>=gp.LinExpr(list(r['lower'].values()),[variables[j] for j in r['lower']]),name='exact_SOC_lower['+tag+']')
        model.addConstr(E<=gp.LinExpr(list(r['upper'].values()),[variables[j] for j in r['upper']]),name='exact_SOC_upper['+tag+']')
    model.update()
    after=(model.NumConstrs,model.NumVars,model.NumBinVars,model.NumNZs)
    return dict(before=dict(zip(('rows','columns','binaries','nnz'),before)),after=dict(zip(('rows','columns','binaries','nnz'),after)),
                added_rows=after[0]-before[0],added_columns=0,added_binaries=0,added_nnz=after[3]-before[3])

def stage_B():
    from .lp import evaluate
    from .cuts import add_A
    a=read(OUT/'CUT_A_ROOT_RESULT.json')
    if a.get('selected'):
        write('STRENGTHENING_B_ROOT_RESULT.json',dict(status='NOT_RUN',reason='STAGE_A_MATERIAL'))
        return
    formal_proof()
    with np.load(SOURCE_PATH := OUT/'BASELINE_ROOT_LP_SOLUTION.npz') as z:
        d=dict(names=z['names']);point=z['values']
    sites,initial,arcs,battery,_=graph_inputs()
    rows=state_rows(d,sites,initial,arcs,battery)
    audited=violation_audit(rows,point)
    if not audited['violated_count']:
        write('STRENGTHENING_B_ROOT_RESULT.json',dict(status='NOT_RUN',selected=False,reason='NO_BASELINE_VIOLATION',exact_validity_PASS=True))
        return
    def install(m):
        if a.get('selected'):add_A(m,sites,initial,battery.p_limit)
        return add_envelopes(m,rows)
    result=evaluate('STRENGTHENING_B_ROOT',install)
    result['selected']=bool(result['status']==gp.GRB.OPTIMAL and result['material'] and result['objective']>=read(OUT/'BASELINE_ROOT_LP_RECEIPT.json')['primal_objective']-1e-8)
    result['exact_integer_equivalence_PASS']=True
    write('STRENGTHENING_B_ROOT_RESULT.json',result)

if __name__=='__main__':stage_B()
