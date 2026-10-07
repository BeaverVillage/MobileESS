"""Read-only semantic census and original-physical causal attribution."""
import re,json,csv
from collections import defaultdict,Counter
import numpy as np
from scipy import sparse
from pure_lp import ROOT,OUT,PARENT,load,write,rows,sha
from v42_strengthening.analysis import graph_inputs
SOURCE=__import__('pathlib').Path('C:/Users/kjw39/Documents/Codex/2026-10-03/single-worker-single-thread-a1-m1/SINGLE_THREAD_LOCAL')
TOL=1e-8

def context():
    A,d,start=load()
    with np.load(OUT/'PURE_LP_POINT.npz') as z:point=z['x'];dual=z['dual'];slack=z['slack']
    sites,initial,arcs,battery,receipt=graph_inputs()
    steps=json.loads((ROOT/'docs/v42_m1_supercompact_exact_20261006/C2_ELIMINATION_CERTIFICATES.json').read_text())
    with np.load(ROOT/'docs/v42_m1_supercompact_exact_20261006/C2_RETAINED_AXES.npz') as z:retained=z['columns']
    n=len(retained)+len(steps);target=np.full(n,-1,int);offset=np.zeros(n);target[retained]=np.arange(len(retained));seen=set(map(int,retained))
    for s in reversed(steps):
        j=s['column'];assert j not in seen
        if s['terms']:
            k,w=next(iter(s['terms'].items()));k=int(k);assert k in seen and w==1
            target[j]=target[k];offset[j]=s['constant']+offset[k]
        else:offset[j]=s['constant']
        seen.add(j)
    assert len(seen)==n
    with np.load(SOURCE/'FULL_DATA.npz') as z:full={k:z[k] for k in z.files}
    assert sha(SOURCE/'FULL_DATA.npz')=='ba6eacea23b71db0b5c6d4e18d6370942906ce2790276127139dbc2ece1d2912'
    origindex={str(n):i for i,n in enumerate(full['names'])};index={str(n):i for i,n in enumerate(d['names'])}
    assert len(full['names'])<=n
    def expr(name):
        j=origindex.get(name)
        if j is None:return {},0.
        k=target[j];return ({} if k<0 else {int(k):1.}),float(offset[j])
    def value(name,x=point):
        terms,c=expr(name);return c+sum(w*x[j] for j,w in terms.items())
    return dict(A=A,d=d,start=start,point=point,dual=dual,slack=slack,sites=sites,initial=initial,arcs=arcs,battery=battery,receipt=receipt,full=full,index=index,expr=expr,value=value,target=target,offset=offset)

def stats(v):
    v=np.asarray(v,float);m=np.minimum(v,1-v);mask=(v>TOL)&(v<1-TOL)
    return dict(binary_count=len(v),fractional_count=int(mask.sum()),fractionality_rate=float(mask.mean()) if len(v) else 0.,max_min_x_1mx=float(m.max(initial=0)),sum_min_x_1mx=float(m.sum()),mean_min_x_1mx=float(m.mean()) if len(v) else 0.)

def main():
    c=context();A,d,x=c['A'],c['d'],c['point'];val=c['value'];sites=c['sites'];arcs=c['arcs'];units=sorted(c['initial']);b=c['battery']
    ledger={int(r['column']):r for r in csv.DictReader((PARENT/'ALL_COLUMN_DECISIONS.csv').open(encoding='utf-8'))}
    assert len(ledger)==len(x)
    families=defaultdict(list);bytime=defaultdict(list);byunit=defaultdict(list);byloc=defaultdict(list);mapping=[]
    for j in np.flatnonzero(d['types']!='C'):
        name=str(d['names'][j]);family=ledger[int(j)]['family']
        if family=='node_activity':
            u,s,t=name[len('node_activity['):-1].split(',');t=int(t)
            semantics='Unit DAG departure-event node mass; equals outgoing route-flow sum (incoming at terminal). Not a transit-interval physical-location indicator. Compact source maps binary node activity to integral original route decisions.'
        elif family=='charge_mode':
            u,t=name[len('charge_mode['):-1].split(',');t=int(t);s='ALL'
            semantics='Original global unit/slot active-power direction: 1 permits charge, 0 permits discharge; reactive Q is mode-independent.'
        else:raise AssertionError((j,name,family))
        mapping.append(dict(column=int(j),name=name,family=family,MESS=u,slot=t,site=s,LP_value=x[j],fractional=bool(TOL<x[j]<1-TOL),min_x_1mx=min(x[j],1-x[j]),ledger_decision=ledger[int(j)]['decision'],semantic_authority='PR162 ALL_COLUMN_DECISIONS.csv; v42_supercompact/formulation.py:Compact; v42_native/mess.py:solve',semantics=semantics))
        families[family].append(x[j]);bytime[u,t,family].append(x[j]);byunit[u,family].append(x[j]);byloc[u,s,family].append(x[j])
    assert len(mapping)==9322 and Counter(r['family'] for r in mapping)=={'node_activity':8938,'charge_mode':384}
    rows('DISCRETE_VARIABLE_FAMILY_MAP.csv',mapping)
    census=[dict(family=f,applicable=True,**stats(v)) for f,v in sorted(families.items())]
    for f,reason in [('route_selection','No retained binary parallel selector; continuous route flow coupled to binary nodes.'),('route_flow_state','Continuous compact route-flow columns, not part of 9322 discrete columns.'),('stay_move_state','Derived from original arc path; no separate retained binary.'),('transit_state','Route arcs span transit/wait interval; no separate binary.'),('connection_state','Stay arc flow defines connected status; no separate binary.'),('PCS_operating_mode','Direction is charge_mode, counted once; no additional PCS binary.'),('other_discrete_physical_state','Absent in verified typed column axis.')]:census.append(dict(family=f,applicable=False,**stats([]),reason=reason))
    rows('FRACTIONALITY_CENSUS.csv',census)
    rows('FRACTIONALITY_BY_MESS.csv',[dict(MESS=u,family=f,**stats(v)) for (u,f),v in sorted(byunit.items())])
    rows('FRACTIONALITY_BY_LOCATION.csv',[dict(MESS=u,site=s,family=f,**stats(v)) for (u,s,f),v in sorted(byloc.items())])
    slotrows=[];routerows=[]
    for u in units:
        flow=np.asarray([val(f'arc[{u},{k}]') for k in range(len(arcs))])
        for k,a in enumerate(arcs):
            if flow[k]>TOL:
                routerows.append(dict(MESS=u,arc=k,kind='STAY' if a[-1] is None else 'MOVE',source=a[0],depart=a[1],destination=a[2],connect=a[3],route_id='' if a[-1] is None else a[-1].route_id,value=flow[k],fractional=bool(TOL<flow[k]<1-TOL),min_x_1mx=min(flow[k],1-flow[k])))
        for t in range(96):
            stay=np.asarray([val(f'arc[{u},{i*96+t}]') for i in range(len(sites))]);Y=float(stay.sum())
            outgoing=[(k,flow[k]) for k,a in enumerate(arcs) if a[1]==t and flow[k]>TOL]
            move=sum(v for k,v in outgoing if arcs[k][-1] is not None)
            move_out=[k for k,v in outgoing if arcs[k][-1] is not None]
            branches=Counter(arcs[k][0] for k,v in outgoing)
            transit=sum(flow[k] for k,a in enumerate(arcs) if a[-1] is not None and a[1]<=t<a[3])
            node=bytime[u,t,'node_activity'];mode=bytime[u,t,'charge_mode'];assert len(mode)==1
            row=dict(MESS=u,slot=t,**stats(node+mode),node_fractional=stats(node)['fractional_count'],node_mass=stats(node)['sum_min_x_1mx'],mode=mode[0],mode_fractional=bool(TOL<mode[0]<1-TOL),stay_mass=Y,transit_mass=transit,departing_move_mass=move,positive_stay_sites=int((stay>TOL).sum()),location_split_mass=Y-float(stay.max(initial=0)),positive_departing_arcs=len(outgoing),positive_departing_move_routes=len(move_out),multiple_move_route_use=bool(len(move_out)>1),same_source_departure_branch=bool(any(n>1 for n in branches.values())),departure_arc_mixture=bool(len(outgoing)>1),move_stay_mix=bool(Y>TOL and move>TOL),connection_transit_mix=bool(Y>TOL and transit>TOL),C=sum(val(f'Pch[{u},{s},{t}]') for s in sites),D=sum(val(f'Pdis[{u},{s},{t}]') for s in sites),Q=sum(val(f'Q[{u},{s},{t}]') for s in sites),SOC=val(f'SOC[{u},{t}]'))
            assert abs(Y+transit-1)<1e-6,(u,t,Y,transit)
            slotrows.append(row)
    # All original discrete columns also include terminal incoming node states
    # at t=96. They have no operating P/Q or charge-mode variable.
    terminalrows=[]
    for u in units:
        nv=bytime[u,96,'node_activity'];assert not bytime[u,96,'charge_mode']
        terminalrows.append(dict(MESS=u,slot=96,time_kind='TERMINAL_INCOMING_NODE_STATE',**stats(nv),node_fractional=stats(nv)['fractional_count'],node_mass=stats(nv)['sum_min_x_1mx'],mode=None,mode_fractional=False,terminal_node_sum=float(sum(nv)),positive_terminal_sites=sum(v>TOL for v in nv),terminal_location_split_mass=float(sum(nv)-max(nv,default=0.))))
    assert sum(r['binary_count'] for r in slotrows+terminalrows)==9322
    rows('FRACTIONALITY_BY_TIME.csv',slotrows+terminalrows);rows('ROUTE_STATE_CENSUS.csv',routerows)
    adjacent=[];windows=[]
    for u in units:
        for t in range(95):
            rr=[r for r in slotrows if r['MESS']==u and t<=r['slot']<=t+1]
            adjacent.append(dict(MESS=u,start=t,end=t+1,fractionality_mass=sum(r['sum_min_x_1mx'] for r in rr),fractional_count=sum(r['fractional_count'] for r in rr),location_split_mass=sum(r['location_split_mass'] for r in rr)))
        rr=[r for r in slotrows+terminalrows if r['MESS']==u and r['slot']>=95]
        adjacent.append(dict(MESS=u,start=95,end=96,time_kind='LAST_OPERATING_SLOT_TO_TERMINAL',fractionality_mass=sum(r['sum_min_x_1mx'] for r in rr),fractional_count=sum(r['fractional_count'] for r in rr),location_split_mass=None))
        for width in [1,2,3,4]:
            for t in range(97-width):
                rr=[r for r in slotrows if r['MESS']==u and t<=r['slot']<t+width]
                windows.append(dict(MESS=u,start=t,end=t+width-1,width=width,fractionality_mass=sum(r['sum_min_x_1mx'] for r in rr),fractional_count=sum(r['fractional_count'] for r in rr)))
    rows('FRACTIONALITY_ADJACENT_PAIRS.csv',adjacent)
    ranked=sorted(mapping,key=lambda r:(-r['min_x_1mx'],r['column']));total=sum(r['min_x_1mx'] for r in ranked);cum=np.cumsum([r['min_x_1mx'] for r in ranked])
    core=dict(total=stats([x[j] for j in np.flatnonzero(d['types']!='C')]),top20_variables=ranked[:20],top20_time_blocks=sorted(slotrows,key=lambda r:(-r['sum_min_x_1mx'],r['MESS'],r['slot']))[:20],top_windows=sorted(windows,key=lambda r:(-r['fractionality_mass'],r['MESS'],r['start']))[:20],minimum_variable_count_for_80pct_fractionality_mass=int(np.searchsorted(cum,.8*total)+1),minimum_variable_count_for_90pct_fractionality_mass=int(np.searchsorted(cum,.9*total)+1),location_split_slots=sum(r['positive_stay_sites']>1 for r in slotrows),multiple_move_route_slots=sum(r['multiple_move_route_use'] for r in slotrows),same_source_departure_branch_slots=sum(r['same_source_departure_branch'] for r in slotrows),move_stay_mix_slots=sum(r['move_stay_mix'] for r in slotrows),connection_transit_mix_slots=sum(r['connection_transit_mix'] for r in slotrows),mode_split_slots=sum(r['mode_fractional'] for r in slotrows),simultaneous_charge_discharge_slots=sum(min(r['C'],r['D'])>TOL for r in slotrows),max_simultaneous_charge_discharge=max(min(r['C'],r['D']) for r in slotrows),threshold=TOL)
    write('FRACTIONAL_CORE.json',core)
    # Binding rows are actual C3A rows; expand only their immutable equality closure.
    fam=[str(n).split('[')[0] for n in d['names']];defs={}
    for i,rn in enumerate(d['row_names']):
        f=str(rn).split('[')[0]
        if f.endswith('_binding'):
            js=A.indices[A.indptr[i]:A.indptr[i+1]];matches=[int(j) for j in js if fam[j]==f[:-8]]
            assert len(matches)==1;defs[matches[0]]=i
    cache={}
    def expand(j):
        if j in cache:return cache[j]
        if fam[j] in ['Pch','Pdis','Q']:out=({j:1.},0.)
        elif d['lower'][j]==d['upper'][j]:out=({},float(d['lower'][j]))
        else:
            i=defs[j];js=A.indices[A.indptr[i]:A.indptr[i+1]];ws=A.data[A.indptr[i]:A.indptr[i+1]];own=float(ws[list(js).index(j)]);terms=defaultdict(float);constant=float(d['rhs'][i])/own
            for k,w in zip(js,ws):
                if k==j:continue
                e,cc=expand(int(k));constant-=w*cc/own
                for q,v in e.items():terms[q]-=w*v/own
            out=(dict(terms),constant)
        cache[j]=out;return out
    rho=int(np.flatnonzero(d['names']=='rho_max')[0]);critical=[];contrib=[];binding={}
    # C3/C2/C1/C0/original axes preserve target line identity through exact aliases.
    with np.load(PARENT/'C3_RETAINED_AXES.npz') as z:c3rows=z['rows']
    with np.load(ROOT/'docs/v42_m1_supercompact_exact_20261006/C2_RETAINED_AXES.npz') as z:c2rows=z['rows'];c1orig=z['C1_original_rows']
    with np.load(SOURCE/'REDUCTION_AXES.npz') as z:original_keep=z['keep']
    fullA=sparse.load_npz(SOURCE/'FULL_A.npz')
    assert sha(SOURCE/'FULL_A.npz')=='35bdc6e7c2664b763d3d0456b7296b7c8830d7c7c39a61a3cb32e699f8bb2024'
    for f in ['line_thermal_face','voltage_upper','voltage_lower','PCS16','energy_balance']:
        binding[f]=int(sum(abs(c['slack'][i])<=TOL for i,n in enumerate(d['row_names']) if str(n).split('[')[0]==f))
    indices=[i for i,n in enumerate(d['row_names']) if str(n)=='line_thermal_face' and abs(c['slack'][i])<=TOL]
    for i in indices:
        js=A.indices[A.indptr[i]:A.indptr[i+1]];ws=A.data[A.indptr[i]:A.indptr[i+1]];rhow=float(ws[list(js).index(rho)]);assert rhow<0 and d['sense'][i]=='<'
        metadata=[];terms=defaultdict(float);constant=0.
        for j,w in zip(js,ws):
            if j==rho:continue
            name=str(d['names'][j]);metadata.append(name);e,cc=expand(int(j));constant+=w*cc
            for k,v in e.items():terms[k]+=w*v
        c0row=int(c1orig[c2rows[c3rows[i]]]);assert c0row<len(original_keep)
        originalrow=int(original_keep[c0row]);assert str(c['full']['row_names'][originalrow])=='line_thermal_face'
        original_names=[str(c['full']['names'][j]) for j in fullA.indices[fullA.indptr[originalrow]:fullA.indptr[originalrow+1]]]
        ids=[re.fullmatch(r'response_line_(?:P|Q|correction)\[(\d+),(\d+)\]',n) for n in original_names];ids=[(int(m[1]),int(m[2])) for m in ids if m];assert len(set(ids))==1
        time,line=ids[0] if ids else (-1,-1)
        lp_effect=sum(w*x[j] for j,w in terms.items());start_effect=sum(w*c['start'][j] for j,w in terms.items())
        required_lp=(constant+lp_effect-float(d['rhs'][i]))/(-rhow);required_start=(constant+start_effect-float(d['rhs'][i]))/(-rhow)
        assert abs(required_lp-x[rho])<1e-6
        critical.append(dict(row=i,original_native_row=originalrow,slot=time,line_index=line,native_variables=';'.join(metadata),original_native_variables=';'.join(original_names),dual=c['dual'][i],LP_slack=c['slack'][i],rho_coefficient=rhow,baseline_required_rho=(constant-float(d['rhs'][i]))/(-rhow),LP_MESS_rho_contribution=lp_effect/(-rhow),integer_start_MESS_rho_contribution=start_effect/(-rhow),LP_required_rho=required_lp,integer_start_required_rho=required_start,delta_required_rho=required_start-required_lp))
        # Detailed exact native affine attribution, units/site and all influencing node/mode values.
        grouped=defaultdict(lambda:defaultdict(float))
        for j,w in terms.items():
            f=fam[j];u,s,t=str(d['names'][j]).split('[',1)[1][:-1].split(',');t=int(t);assert t==time
            grouped[u,s][f+'_coefficient']=w/(-rhow);grouped[u,s][f+'_LP']=x[j];grouped[u,s][f+'_integer_start']=c['start'][j]
        for (u,s),g in grouped.items():
            if max(abs(g.get(f+'_LP',0.)) for f in ['Pch','Pdis','Q'])<TOL and max(abs(g.get(f+'_integer_start',0.)) for f in ['Pch','Pdis','Q'])<TOL:continue
            contrib.append(dict(row=i,slot=time,line_index=line,MESS=u,site=s,LP_stay=val(f'arc[{u},{sites.index(s)*96+time}]'),integer_start_stay=val(f'arc[{u},{sites.index(s)*96+time}]',c['start']),LP_mode=val(f'charge_mode[{u},{time}]'),integer_start_mode=val(f'charge_mode[{u},{time}]',c['start']),**g,LP_rho_contribution=sum(g.get(f+'_coefficient',0)*g.get(f+'_LP',0) for f in ['Pch','Pdis','Q']),integer_start_rho_contribution=sum(g.get(f+'_coefficient',0)*g.get(f+'_integer_start',0) for f in ['Pch','Pdis','Q'])))
    rows('CRITICAL_LINE_TIME_AUDIT.csv',critical);rows('CRITICAL_MESS_PQ_CONTRIBUTIONS.csv',contrib)
    write('ACTIVE_PHYSICAL_CONSTRAINTS.json',dict(binding_row_counts=binding,SOC_bound_active_count=int(sum(min(abs(x[j]-d['lower'][j]),abs(x[j]-d['upper'][j]))<=TOL for j,f in enumerate(fam) if f=='SOC')),all_row_slacks_and_duals_in='PURE_LP_POINT.npz',critical_line_rows=len(critical),closure_expansion_checked=True,attribution_uses_float_affine_evaluation_not_rational_validity_proof=True,max_closure_residual=max((abs(sum(w*x[k] for k,w in e.items())+cc-x[j]) for j,(e,cc) in cache.items()),default=0.)))
    write('SEMANTIC_AUTHORITY.json',dict(PASS=True,discrete_columns_mapped=len(mapping),ledger_SHA=sha(PARENT/'ALL_COLUMN_DECISIONS.csv'),native_source_SHA=sha(ROOT/'v42_native/mess.py'),compact_source_SHA=sha(ROOT/'v42_supercompact/formulation.py'),graph_receipt=c['receipt'],full_data_SHA=sha(SOURCE/'FULL_DATA.npz'),inverse_steps=len(c['target'])-len(x),continuous_route_flow_is_not_an_additional_binary_family=True,unchanged_P1_P2=True))
    print('SEMANTIC_CENSUS_DONE',core['total'],'critical_rows',len(critical),flush=True)

if __name__=='__main__':main()
