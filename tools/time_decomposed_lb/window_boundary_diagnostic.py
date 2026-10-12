"""Exact physical-only witness for free Window boundary SOC weakening.

No optimization, Gurobi import, full-horizon model, or Grid feasibility claim.
The active Native Window model is never edited.
"""
from collections import Counter
from fractions import Fraction as F
from pathlib import Path
import json
import time
import numpy as np
from scipy import sparse

from tools.time_decomposed_lb.grid import ROOT, SOURCE, CASE, require, read, write, sha

DOCS=ROOT/'docs/v42_b2_time_decomposed_global_lb'
BETA=F(4740631186705785,18014398509481984)


def run():
    started=time.perf_counter();literal=DOCS/'window_native0';compact=DOCS/'window_compact_native0'
    mapping=read(compact/'COMPACT_WINDOW_MAPPING.json')
    A=sparse.load_npz(literal/'WINDOW_PHYSICS_A.npz').tocsr()
    with np.load(literal/'WINDOW_PHYSICS_DATA.npz',allow_pickle=False) as z:d={k:z[k] for k in z.files}
    names=list(map(str,d['names']));lookup={n:j for j,n in enumerate(names)}
    rows=[]
    for i,name in enumerate(d['row_names']):
        if ':energy_balance:' not in str(name):continue
        lo,hi=A.indptr[i:i+2];coeff={names[int(j)]:F(float(v)) for j,v in zip(A.indices[lo:hi],A.data[lo:hi])}
        soc=[n for n in coeff if n.startswith('SOC[')];require(len(soc)==2,'SOURCE_WINDOW_SOC_ROW')
        ordered=sorted(soc,key=lambda n:int(n.rstrip(']').rsplit(',',1)[1]));unit=ordered[0].split('[',1)[1].split(',',1)[0]
        nextcoef=coeff[ordered[1]];require(coeff[ordered[0]]==-nextcoef and abs(nextcoef)==1,'SOURCE_SOC_CONSERVATION_COEFFICIENTS')
        dis=[c/nextcoef for n,c in coeff.items() if n.startswith('Pdis[')]
        require(len(dis)==24 and all(c==BETA for c in dis),'STORED_WINDOW_BETA_AUTHORITY')
        rows.append(dict(original_physical_row=i,unit=unit,name=str(name),stored_beta_exact=str(BETA)))
    require(len(rows)==32,'ALL_WINDOW_ENERGY_ROWS_COVERED')
    x=[F(0) for _ in names];site='IDC01';units=[f'MESS{m:02d}' for m in range(1,5)]
    for arc in mapping['arc_metadata']:
        if arc['route'] is None and arc['origin']==arc['destination']==site and 88<=arc['depart']<96:
            x[arc['column']]=F(1)
    for unit in units:
        for t in range(88,97):
            n=f'SOC[{unit},{t}]';j=lookup[n]
            require(float(d['lb'][j])==440. and float(d['ub'][j])==1080.,'SOURCE_SOC_BOX')
            x[j]=F(1080)-BETA*300*(t-88)
        for t in range(88,96):
            x[lookup[f'Pdis[{unit},{site},{t}]']]=F(300)
    failures=[];kinds=Counter()
    for i,label in enumerate(d['row_names']):
        lo,hi=A.indptr[i:i+2]
        activity=sum((F(float(v))*x[int(j)] for j,v in zip(A.indices[lo:hi],A.data[lo:hi])),F(0));rhs=F(float(d['rhs'][i]));sense=str(d['senses'][i])
        violation=abs(activity-rhs) if sense=='=' else activity-rhs if sense=='<' else rhs-activity
        if violation>0:failures.append(dict(row=i,name=str(label),violation_exact=str(violation)))
        pieces=str(label).split(':');kinds[pieces[1] if len(pieces)>1 else pieces[0]]+=1
    require(not failures,'EXACT_PHYSICAL_STATIONARY_WITNESS_FAILED')
    for j,value in enumerate(x):
        require(F(float(d['lb'][j]))<=value<=F(float(d['ub'][j])),'EXACT_PHYSICAL_WITNESS_BOX')
        if str(d['vtypes'][j])=='B':require(value in (0,1),'EXACT_PHYSICAL_WITNESS_INTEGER')
    compactA=sparse.load_npz(compact/'WINDOW_PHYSICS_A.npz').tocsr()
    with np.load(compact/'WINDOW_PHYSICS_DATA.npz',allow_pickle=False) as z:cd={k:z[k] for k in z.files}
    cx=x+[F(0)]*(compactA.shape[1]-len(x));clookup={str(n):j for j,n in enumerate(cd['names'])}
    for unit in units:
        for t in range(88,97):cx[clookup[f'node_activity[{unit},{site},{t}]']]=F(1)
    for i in range(compactA.shape[0]):
        lo,hi=compactA.indptr[i:i+2];lhs=sum((F(float(v))*cx[int(j)] for j,v in zip(compactA.indices[lo:hi],compactA.data[lo:hi])),F(0))
        b=F(float(cd['rhs'][i]));s=str(cd['senses'][i]);err=abs(lhs-b) if s=='=' else lhs-b if s=='<' else b-lhs
        require(err<=0,'EXACT_COMPACT_PHYSICAL_WITNESS_FAILED')
    draw=BETA*300*8;end=F(1080)-draw;original_budget=F(1080)-F(760)
    value=dict(PASS=True,schema='V42_WINDOW_BOUNDARY_PHYSICAL_WEAKENING_DIAGNOSTIC_V1',source18r=SOURCE,case_sha=CASE,window=[88,96],
        objective_or_Global_LB_claimed=False,Grid_feasibility_checked=False,causal_LB_delta_isolated=False,
        active_Native_model_modified=False,Native_optimize_calls=0,Gurobi_imported=False,Full96_model_constructed=False,
        stored_beta_exact=str(BETA),beta_source_energy_rows=rows,SOC_box=dict(lower=440,upper=1080),
        original_FULL_terminal_SOC=760,selected_FIXED_STAY_site=site,all4_MESS_same_site_allowed_in_constructed_Window_physics=True,
        physical_point=dict(Pdis_each_car_each_slot_kW=300,Pch=0,Q=0,charge_mode=0,travel=0,E88=1080,
            net_draw_kWh_exact=str(draw),net_draw_kWh=float(draw),E96_exact=str(end),E96=float(end),
            available_free_boundary_netdraw_kWh=640,all32_energy_rows_exactly_satisfied=True,
            literal_physical_rows_exact_checked=A.shape[0],compact_physical_rows_exact_checked=compactA.shape[0],
            exact_physical_feasibility=True,Grid_feasibility_claim=False),
        original_terminal_contrast=dict(assumptions='No charge/no travel inside88..95, E88<=1080, original FULL E96=760.',
            maximum_draw_kWh=320,maximum_uniform_Pdis_kW_exact=str(original_budget/(8*BETA)),
            maximum_uniform_Pdis_kW=float(original_budget/(8*BETA)),
            witness_above_is_not_original_FULL_feasible_because_terminal_E96_differs=True),
        conclusion='Free start/end SOC boxes allow a physical no-charge 300kW stationary discharge on all8 slots per car; source fixed terminal760 forbids this netdraw. This diagnoses one conservative boundary weakening mechanism, but does not prove this plan satisfies any Grid row or isolate how much it changes the optimized LB.',
        follow_up='Existing K48 Selective Integrality keeps96-slot SOC/endpoints and may deserve separate review; no gain/practicality assumed and no Native authorized here.',
        source_records={str(p):sha(p) for p in [literal/'WINDOW_PHYSICS_A.npz',literal/'WINDOW_PHYSICS_DATA.npz',compact/'WINDOW_PHYSICS_A.npz',compact/'WINDOW_PHYSICS_DATA.npz',compact/'COMPACT_WINDOW_MAPPING.json']},
        wall_seconds=time.perf_counter()-started,code_sha256=sha(__file__))
    write(DOCS/'WINDOW_BOUNDARY_WEAKENING_DIAGNOSTIC.json',value)
    print(json.dumps({k:value[k] for k in ['PASS','Native_optimize_calls','stored_beta_exact']}));return value


if __name__=='__main__':run()
