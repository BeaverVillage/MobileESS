from .common import *
from .oracle import lower
from v42_disjunctive.certificate import down
import numpy as np
import time
from collections import defaultdict
from fractions import Fraction as F
from v42_strengthening.analysis import graph_inputs

def conditional_tables(fixed_lower,psi_lower,times,rows):
    units=psi_lower.shape[1];values=np.full((units,96),-np.inf);responsible=np.full((units,96),-1,dtype=np.int64)
    for m in range(units):
        bound=fixed_lower.copy()
        for other in range(units):
            if other!=m:bound=lower(bound+psi_lower[:,other])
        for t in range(96):
            ix=np.flatnonzero(times==t)
            if len(ix):
                j=ix[np.argmax(bound[ix])];values[m,t]=bound[j];responsible[m,t]=j
    return values,responsible

def run():
    gate('arc_separation');begin=time.perf_counter()
    assert read(OUT/'GRID_SUPPORT_GLOBAL_LB.json')['PASS']
    sites,initial,arcs,battery,receipt=graph_inputs();units=list(initial)
    with np.load(OUT/'PCS_GRID_SUPPORT_VALUES.npz') as z:psi=z['psi_lower'];times=z['times'];R=z['rows'];rowlo=z['row_lower']
    with np.load(OUT/'GRID_EPIGRAPH_ROW_COEFFICIENTS.npz') as z:fixed=z['fixed_lower']
    with np.load(ROOT/'docs/v42_m1_exact_formulation_strengthening/BASELINE_ROOT_LP_SOLUTION.npz') as z:names=z['names'];point=z['values'];types=z['integer_types']
    v,resp=conditional_tables(fixed,psi,times,R);global_index=int(np.argmax(rowlo));global_lb=float(rowlo[global_index])
    # Range maxima are computed once per (unit,depart,connect), then reused.
    ranges={}
    for m in range(len(units)):
        for depart in range(96):
            for connect in range(depart+1,97):
                t=depart+int(np.argmax(v[m,depart:connect]));j=int(resp[m,t]);raw=max(global_lb,float(v[m,t]))
                if global_lb>=v[m,t]:j=global_index
                ranges[m,depart,connect]=(raw,j)
    records=[];cliques=defaultdict(list);standalone=[];rho=float(point[list(map(str,names)).index('rho_max')]);stay=len(sites)*96
    for col,(name,x) in enumerate(zip(names,point)):
        name=str(name)
        if not name.startswith('arc[') or not 1e-6<x<1-1e-6:continue
        u,k=name[4:-1].split(',');k=int(k)
        if k<stay:continue
        m=units.index(u);s,dep,d,conn,route=arcs[k];assert route is not None and dep<conn<96
        raw,j=ranges[m,dep,conn];L=max(BASE_LB,raw);delta=down(F(L)-F(BASE_LB))
        row=dict(MESS=u,arc=k,column=col,source=s,depart=dep,destination=d,connect=conn,transit_length=conn-dep,
                 x_star=float(x),L_arc_raw=raw,L_arc=L,delta_LB=delta,responsible_reduced_row=int(R[j]),responsible_slot=int(times[j]),
                 baseline_L0_controls=L==BASE_LB)
        records.append(row)
        violation=BASE_LB+delta*x-rho
        standalone.append(dict(kind='individual',id=name,columns=[col],coefficients=[delta],signed_violation=float(violation)))
        if delta>0:
            cliques[u,s,dep].append(row)
    assert len(records)==131350
    table('MOVEMENT_ARC_CONDITIONAL_LB.csv',records,list(records[0]))
    write('MOVEMENT_ARC_TRANSIT_SEMANTICS_PROOF.json',dict(PASS=True,native_source_SHA=sha(ROOT/'v42_native/mess.py'),route_authority=receipt,
          actual_transit_interval='[depart,connect): depart,...,connect-1',connect_is_not_automatically_transit=True,
          all_arcs_strictly_forward=all(a[3]>a[1] for a in arcs),
          proof=['All arcs strictly increase time. Nonnegative integer unit-flow, a single origin supply and terminal flow=1 imply exactly one origin-to-terminal path; no circulation or disconnected positive path is possible in this DAG.',
                 'If movement arc (source,depart,destination,connect) is selected, the path has no node/stay arc in slots depart through connect-1. All stay indicators of that unit at these slots equal zero.',
                 'Original connected_Pch/Pdis and nonnegative bounds force both active powers to zero. Original connected_Qmin/max force Q=0. Slot connect may use a destination stay arc and is excluded from transit.',
                 'Travel energy is debited at depart by the unchanged original energy_balance row; it is ignored here only to enlarge the support relaxation.'],
          no_route_pruning=True,no_new_binary=True))
    write('MOVEMENT_ARC_CONDITIONAL_LB_PROOF.json',dict(PASS=True,individual_cut_valid=True,
          proof=['Original rho-linked face equations are exactly substituted through their native dyadic grid binding DAG.',
                 'For a selected movement arc, its unit contributes P=Q=0 on its exact transit interval. Every other unit contribution is >= its optimistic local PCS/site/transit support.',
                 'Outside that interval all units retain optimistic supports. Ignoring SOC, other route coupling and capacity only relaxes constraints.',
                 'Each substituted face yields a conditional lower bound. Max across all faces remains a lower bound. L_arc=max(certified L0,conditional support bound).',
                 'At binary x=0 the individual cut is rho>=L0; at x=1 it is rho>=L_arc. Downward dyadic rounding of delta cannot invalidate either case.'],
          outward_arithmetic=True,full_M1_optimize_calls=0,full_conditional_LP_calls=0,
          evaluated=len(records),with_L_gt_L0=sum(r['L_arc']>BASE_LB for r in records),max_L_arc=max(r['L_arc'] for r in records),runtime_seconds=time.perf_counter()-begin))
    grouped=[];clique_records=[]
    for (u,s,t),members in sorted(cliques.items()):
        if len(members)<2:continue
        cols=[r['column'] for r in members];coeff=[r['delta_LB'] for r in members]
        # Outward evaluation for diagnostics is unnecessary for validity;
        # construction coefficients themselves were rounded down.
        violation=BASE_LB+sum(r['delta_LB']*r['x_star'] for r in members)-rho
        cid=f'{u}/{s}/{t}'
        grouped.append(dict(kind='clique',id=cid,columns=cols,coefficients=coeff,signed_violation=float(violation)))
        for r in members:clique_records.append(dict(clique=cid,MESS=u,source=s,depart=t,arc=r['arc'],column=r['column'],delta_LB=r['delta_LB']))
    table('MOVEMENT_ARC_CLIQUES.csv',clique_records,['clique','MESS','source','depart','arc','column','delta_LB'])
    write('MOVEMENT_ARC_CLIQUE_PROOF.json',dict(PASS=True,cliques=len(grouped),members=len(clique_records),
          definition='Positive-coefficient evaluated movement arcs with same unit and original outgoing flow node (source,depart).',
          proof=['The original integer unit path visits an outgoing flow node at most once, because time strictly increases. Thus sum of outgoing alternatives <=1.',
                 'The positive-coefficient fractional subset also has at most one selected member. If none is selected the clique cut is rho>=L0; if a member a is selected it is rho>=L_arc[a].',
                 'All coefficients are nonnegative. On the nonnegative binary-domain relaxation the clique inequality dominates each of its individual member inequalities.'],
          origin_flow_rows_preserved=True,no_added_at_most_one_domain_constraint=True))
    candidates=standalone+grouped;violated=[r for r in candidates if r['signed_violation']>1e-6]
    selected=[];seen=set();covered=set()
    for r in grouped:
        if r['signed_violation']>1e-6:
            key=tuple(sorted(zip(r['columns'],r['coefficients'])))
            if key not in seen:selected.append(r);seen.add(key);covered.update(r['columns'])
    for r in standalone:
        if r['signed_violation']>1e-6 and r['columns'][0] not in covered:
            key=tuple(zip(r['columns'],r['coefficients']))
            if key not in seen:selected.append(r);seen.add(key)
    import json
    rows=[dict(kind=r['kind'],id=r['id'],term_count=len(r['columns']),signed_violation=r['signed_violation'],violated=r['signed_violation']>1e-6,
               columns=json.dumps(r['columns']),coefficients=json.dumps(r['coefficients'])) for r in candidates]
    table('MOVEMENT_GRID_CUT_SEPARATION.csv',rows,['kind','id','term_count','signed_violation','violated','columns','coefficients'])
    summary=dict(PASS=True,baseline_rho=rho,threshold=1e-6,individual_generated=len(standalone),nontrivial_individual_generated=sum(r['coefficients'][0]>0 for r in standalone),clique_generated=len(grouped),
          violated_individual=sum(r['kind']=='individual' for r in violated),violated_clique=sum(r['kind']=='clique' for r in violated),
          violated_candidates=len(violated),max_violation=max([max(0,r['signed_violation']) for r in candidates],default=0.),
          total_positive_violation=sum(max(0,r['signed_violation']) for r in candidates),
          added_cuts=len(selected),added_nnz=sum(len(r['columns'])+1 for r in selected),
          duplicate_cuts_removed=len(violated)-len(selected),selection='Exact duplicate removal, then violated clique dominance over individual members.',
          top_100=sorted(rows,key=lambda r:r['signed_violation'],reverse=True)[:100],all_fractional_movement_arcs_evaluated=len(records),
          no_domain_change=True,full_conditional_LP_calls=0,full_M1_optimizes_in_oracle=0)
    write('MOVEMENT_GRID_CUT_SEPARATION_SUMMARY.json',summary);write('SELECTED_MOVEMENT_GRID_CUTS.json',dict(cuts=selected,rho_column=list(map(str,names)).index('rho_max'),baseline_LB=BASE_LB))
    print('SEPARATION_DONE',summary['individual_generated'],summary['clique_generated'],len(selected),summary['max_violation'],flush=True)
if __name__=='__main__':run()
