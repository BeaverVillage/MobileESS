"""Read-only audit of sealed MPS incidence and route-energy departure coefficients."""
from collections import Counter,defaultdict
import re
import numpy as np
import gurobipy as gp
from .common import *

def audit():
    graph,sites,initial,bundle,battery=graph_inputs()
    with gp.Env(params={'OutputFlag':0}) as env:
        m=original(env);A=m.getA().tocsr();rhs=np.array(m.getAttr('RHS'));sense=np.array(m.getAttr('Sense'));names=m.getAttr('VarName');axis={n:i for i,n in enumerate(names)}
        arcs={};out=defaultdict(dict);inc=defaultdict(dict);arcset=set()
        for j,n in enumerate(names):
            match=re.fullmatch(r'arc\[([^,]+),(\d+)\]',n)
            if not match:continue
            u,k=match[1],int(match[2]);arcs[u,k]=j;arcset.add(j);a=graph[k]
            out[u,a[0],a[1]][j]=1.;inc[u,a[2],a[3]][j]=1.
        def sig(d,b):return (float(b),tuple(sorted((j,float(v)) for j,v in d.items() if v)))
        observed=Counter()
        for i in np.flatnonzero((sense=='=') & np.isin(rhs,[0.,1.])):
            js=A.indices[A.indptr[i]:A.indptr[i+1]];vs=A.data[A.indptr[i]:A.indptr[i+1]]
            if all(int(j) in arcset for j in js):observed[sig(dict(zip(map(int,js),map(float,vs))),rhs[i])]+=1
        expected=Counter()
        for u,origin in initial.items():
            for s in sites:
                for t in range(96):
                    d=dict(out[u,s,t])
                    for j,v in inc[u,s,t].items():d[j]=d.get(j,0.)-v
                    expected[sig(d,int(t==0 and s==origin))]+=1
            terminal={j:1. for (unit,k),j in arcs.items() if unit==u and graph[k][3]==96}
            expected[sig(terminal,1)]+=1
        assert all(observed[k]>=v for k,v in expected.items()),'SEALED_MPS_CONNECT_INCIDENCE_MISMATCH'
        energy_error=0.;soc_rows=0;initial_terminal_rows=0
        csc=A.tocsc()
        for u in initial:
            for t in range(96):
                j0=axis[f'SOC[{u},{t}]'];j1=axis[f'SOC[{u},{t+1}]']
                candidates=set(csc[:,j0].indices)&set(csc[:,j1].indices)
                rows=[i for i in candidates if sense[i]=='=' and A[i,j0]==-1. and A[i,j1]==1.]
                assert len(rows)==1,('SOC_ROW_AMBIGUITY',u,t,rows)
                row=rows[0];actual={int(j):float(v) for j,v in zip(A[row].indices,A[row].data) if int(j) in arcset}
                wanted={j:graph[k][-1].energy_kwh for (unit,k),j in arcs.items() if unit==u and graph[k][-1] is not None and graph[k][1]==t and graph[k][-1].energy_kwh!=0}
                assert set(actual)==set(wanted),('SEALED_DEPARTURE_TIMING_MISMATCH',u,t)
                energy_error=max(energy_error,max([abs(actual[j]-v) for j,v in wanted.items()]+[0.]));soc_rows+=1
                # Other SOC terms retain original per-unit Pch/Pdis with original efficiencies.
                for j,v in zip(A[row].indices,A[row].data):
                    n=names[int(j)]
                    if n.startswith('Pch['):assert n.startswith(f'Pch[{u},') and n.endswith(f',{t}]') and abs(v+battery.dt_hours*battery.eta_charge)<=1e-12
                    elif n.startswith('Pdis['):assert n.startswith(f'Pdis[{u},') and n.endswith(f',{t}]') and abs(v-battery.dt_hours/battery.eta_discharge)<=1e-12
            for t,value in [(0,battery.initial),(96,battery.terminal)]:
                j=axis[f'SOC[{u},{t}]'];rows=[i for i in csc[:,j].indices if A.indptr[i+1]-A.indptr[i]==1 and sense[i]=='=' and A[i,j]==1. and rhs[i]==value]
                assert rows,('INITIAL_TERMINAL_SOC',u,t);initial_terminal_rows+=1
        assert energy_error<=1e-12,'SEALED_ROUTE_ENERGY_AUTHORITY_MISMATCH'
        result=dict(PASS=True,optimize_calls=0,source='Exact original sealed F3 MPS, not the compact matrix',
            audited_flow_and_terminal_rows=sum(expected.values()),audited_SOC_recurrence_rows=soc_rows,
            audited_initial_terminal_SOC_rows=initial_terminal_rows,route_energy_coefficient_max_absolute_error=energy_error,
            movement_endpoint='connect',travel_debit_time='depart',unit_reachable_arcs=len(arcs),
            native_record_graph_size=len(graph),all_native_incidence_signatures_present=True)
        dump('ORIGINAL_NATIVE_NETWORK_AUDIT.json',result);m.dispose();return result
if __name__=='__main__':print(audit(),flush=True)
