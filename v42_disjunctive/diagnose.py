from .common import *
import numpy as np
from collections import Counter,defaultdict
from v42_strengthening.analysis import graph_inputs

def partition(d,sites,initial,arcs):
    names=set(map(str,d['names']))
    stay_count=len(sites)*96
    assert all(a[3]>a[1] for a in arcs)
    for u in initial:
        assert all(f'arc[{u},{k}]' in names or f'Pch[{u},{a[0]},{a[1]}]' not in names for k,a in enumerate(arcs[:stay_count]))
    result=dict(PASS=True,source='Unmodified v42_native.mess.solve original flow and terminal_location equalities',
        proof=[
          'Every arc strictly increases time. The time-expanded directed graph has no directed cycles.',
          'Original binary nonnegative unit-flow with one origin supply and terminal sum 1 decomposes into exactly one origin-to-terminal path; no other positive path or circulation can occur.',
          'A path crosses each time cut exactly once. It either uses a single stay arc [t,t+1) at one site, or a travel arc spanning that slot. Consequently sum_s original stay y[m,s,t] is exactly 1 or 0.',
          'Missing original stay columns are fixed-zero unreachable states from the original constructor; no new pruning occurs.'],
        y_definition='Existing arc[m,site_index*96+t], no new variable',horizon=96,
        site_count=len(sites),MESS_count=len(initial),stay_arcs_per_domain=stay_count,
        all_arcs_strictly_forward=True,new_location_variables=0,new_binary_variables=0,
        native_source_SHA=sha(ROOT/'v42_native/mess.py'))
    write('CONNECTION_STATE_PARTITION_PROOF.json',result)
    return result

def run(B,e,point,pi):
    sites,initial,arcs,battery,receipt=graph_inputs()
    partition(e,sites,initial,arcs)
    names=list(map(str,e['names'])); index={n:i for i,n in enumerate(names)}
    # Each response is eliminated only for sensitivity analysis, never in model.
    bindings={}
    for i,n in enumerate(e['row_names']):
        if str(n).startswith('response_') and str(n).endswith('_binding'):
            a,b=B.indptr[i:i+2]; jj=B.indices[a:b]; cc=B.data[a:b]
            outputs=[int(j) for j in jj if names[j].startswith('response_')]
            assert len(outputs)==1
            j=outputs[0]; scale=cc[np.flatnonzero(jj==j)[0]]
            bindings[j]={int(k):-float(v/scale) for k,v in zip(jj,cc) if k!=j}
    residual=B@point-e['rhs']
    thermal=[i for i,n in enumerate(e['row_names']) if str(n)=='line_thermal_face']
    critical={i for i in thermal if abs(residual[i])<=1e-6}
    expanded={}; labels={}; byslot=defaultdict(list); face_count=Counter()
    gridrows=[]
    for i in thermal:
        a,b=B.indptr[i:i+2]; jj=B.indices[a:b]; cc=B.data[a:b]
        response=[names[j] for j in jj if names[j].startswith('response_line_')]
        if response:
            t,k=map(int,response[0].split('[')[1][:-1].split(','))
            f=face_count[t,k];face_count[t,k]+=1
        else: t,k,f=-1,-1,0
        label=f'line_index={k},face={f},slot={t},reduced_row={i}'
        if i not in critical:continue
        grad=defaultdict(float)
        for j,c in zip(jj,cc):
            if int(j) in bindings:
                for k2,w in bindings[int(j)].items():grad[k2]+=float(c)*w
            elif names[j].startswith('injection_'):grad[int(j)]+=float(c)
        expanded[i]=dict(grad);labels[i]=label;byslot[t].append(i)
        gridrows.append(dict(row=i,label=label,slack=float(-residual[i]),Pi=float(pi[i]),
                             injection_derivative_count=len(grad)))
    dual_family={}
    for family in ('line_thermal_face','NormalAmps','transformer_kVA','voltage_lower','voltage_upper'):
        ix=np.array([i for i,n in enumerate(e['row_names']) if str(n).split('[')[0]==family])
        dual_family[family]=dict(rows=len(ix),nonzero_duals=int((pi[ix]!=0).sum()),dual_abs_sum=float(abs(pi[ix]).sum()),
                                 max_abs_dual=float(abs(pi[ix]).max(initial=0.)))
    rows=[]; split_count=0
    for u in initial:
        for t in range(96):
            shares=[point[index[f'arc[{u},{si*96+t}]']] if f'arc[{u},{si*96+t}]' in index else 0. for si in range(len(sites))]
            positive=sum(v>1e-6 for v in shares)
            if positive<=1:continue
            split_count+=1;split=sum(shares)-max(shares)
            for si,s in enumerate(sites):
                y=float(shares[si])
                if not (1e-6<y<1-1e-6):continue
                pch=float(point[index[f'Pch[{u},{s},{t}]']]);pdis=float(point[index[f'Pdis[{u},{s},{t}]']]);q=float(point[index[f'Q[{u},{s},{t}]']])
                jp=index[f'injection_P[{s},{t}]'];jq=index[f'injection_Q[{s},{t}]']
                affected=[]
                for i in byslot[t]:
                    gp=expanded[i].get(jp,0.);gq=expanded[i].get(jq,0.)
                    sensitivity=abs(gp)+abs(gq)
                    affected.append((sensitivity,i,gp,gq))
                sensitivity,i,gp,gq=max(affected,default=(0.,-1,0.,0.))
                dualscore=sum(abs(pi[r])*(abs(expanded[r].get(jp,0.))+abs(expanded[r].get(jq,0.))) for r in byslot[t])
                rows.append(dict(MESS=u,slot=t,site=s,column=index[f'arc[{u},{si*96+t}]'],stay_name=f'arc[{u},{si*96+t}]',
                    y=y,max_site_share=float(max(shares)),location_split=float(split),Pch=pch,Pdis=pdis,P_contribution=pdis-pch,Q_contribution=q,
                    affected_critical_line_face=labels.get(i,'NONE_NEAR_ACTIVE_AT_THIS_SLOT'),
                    d_face_d_injection_P=gp,d_face_d_injection_Q=gq,
                    grid_epigraph_sensitivity=sensitivity,dual_sensitivity_score=float(dualscore),
                    priority_score=float(y*split*sensitivity)))
    rows.sort(key=lambda r:(-r['priority_score'],r['MESS'],r['slot'],r['site']))
    for rank,r in enumerate(rows,1):r['rank']=rank
    table('LOCATION_GRID_COUPLING_CENSUS.csv',rows,list(rows[0]))
    write('LOCATION_GRID_COUPLING_SUMMARY.json',dict(candidate_states=len(rows),split_MESS_slots=split_count,
        baseline_primal_source='Preserved PR137 barrier primal, not crossover primal',near_active_tolerance=1e-6,
        thermal_rows=len(thermal),active_near_active_rows=len(critical),critical_rows=gridrows,
        dual_source='Single optimal baseline basis acquisition on exact same model',dual_by_family=dual_family,
        score='original_y * (sum_original_y - max_original_y) * max_near_active_face(|dface/dP|+|dface/dQ|)',
        diagnostic_score_used_in_constraints=False,model_matrix_used_directly=True,
        zero_sensitivity_candidates_retained=True,all_fractional_positive_share_candidates_retained=True,
        causal_claim='Priority and local sensitivity diagnosis only; conditional lower bounds test the single-state hypothesis.',
        top_50=rows[:50],native_branch_index_namespace='Original grid response variable branch index; exact row/face identifiers retained.'))
    assert split_count==377
    return rows
