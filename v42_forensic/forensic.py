"""Independent original-face recomputation and active-horizon energy audit."""
from collections import Counter
import math
from .common import *

def control(c,v,anchor,units,t):
    x=[]
    for i,n in enumerate(c.control_names):
        s=n.split('[')[1][:-1]
        if n.startswith('aidc_load_kw'):x.append(float(anchor['controls'][t][i]))
        elif n.startswith('mess_p_kw'):x.append(sum(v.get(f'Pdis[{u},{s},{t}]',0.)-v.get(f'Pch[{u},{s},{t}]',0.) for u in units))
        elif n.startswith('mess_q_kvar'):x.append(sum(v.get(f'Q[{u},{s},{t}]',0.) for u in units))
        else:raise ValueError(n)
    return np.asarray(x)

def faces(c,x):
    cos=np.cos(2*np.pi*np.arange(16)/16);sin=np.sin(2*np.pi*np.arange(16)/16)
    ap=c.branch_limits*math.cos(math.pi/16);pa=c.flow_p_constant+c.flow_p_matrix@c.anchor;qa=c.flow_q_constant+c.flow_q_matrix@c.anchor
    raw=(pa[:,None]*cos+qa[:,None]*sin)/ap[:,None];f=np.argmax(raw,axis=1)
    grad=(cos[f,None]*c.flow_p_matrix+sin[f,None]*c.flow_q_matrix)/ap[:,None]
    correction=c.current_matrix.T-grad;bias=c.current_constant+c.current_matrix.T@c.anchor-np.max(raw,axis=1)
    p=c.flow_p_constant+c.flow_p_matrix@x;q=c.flow_q_constant+c.flow_q_matrix@x
    polygon=p[:,None]*cos+q[:,None]*sin;adjust=correction@(x-c.anchor)+bias
    return polygon/ap[:,None]+adjust[:,None],polygon,adjust,ap

def run():
    v=root_values();bundle,anchor,inc,sites,initial,routes,b=inputs();units=sorted(initial);iv=inc['values'];arcs=arcs_for(sites,routes)
    with np.load(OUT/'ROOT_DUAL_AXIS.npz',allow_pickle=False) as z:dual=z['Pi'];names=z['names']
    linedual=dual[names=='line_thermal_face'];termdual=dual[names=='terminal_SOC'];energydual=dual[names=='energy_balance'];assert len(termdual)==4 and len(energydual)==384
    arc_terminal_duals={u:float(dual[np.flatnonzero(names==f'G_terminal[{u}]')[0]]) if np.any(names==f'G_terminal[{u}]') else 0. for u in units}
    from v42_bootstrap.grid import coefficients
    _,coeff=coefficients(bundle);rho=v['rho_max'];recomputed=[];allfaces=[];offset=0
    for t,c in enumerate(coeff):
        x=control(c,v,anchor,units,t);xx=control(c,iv,anchor,units,t);ff,poly,adj,ap=faces(c,x);incfaces=faces(c,xx)[0]
        mask=np.array([not n.lower().startswith('transformer.') for n in c.branch_names]);indices=np.flatnonzero(mask)
        pd=linedual[offset:offset+len(indices)*16].reshape(len(indices),16);offset+=len(indices)*16
        slot=float(ff[mask].max());nr,kf=np.unravel_index(np.argmax(ff[mask]),(len(indices),16));k=indices[nr]
        mass=float(abs(pd).sum());epigraph=rho-slot<=OBJ_TOL;dualactive=mass>=EPS
        recomputed.append(dict(time=t,rho_root=slot,rho_inc=float(incfaces[mask].max()),rho_star=rho,slack=rho-slot,
            dual_mass=mass,epigraph_active=epigraph,dual_active=dualactive,T_ACTIVE=epigraph and dualactive,
            maximum_line=c.branch_names[k].split('::')[0],maximum_phase=c.branch_names[k].split('::')[-1],maximum_face=kf,
            raw_affine_loading_kVA_equiv=float(ff[k,kf]*ap[k]),normalized_loading=slot))
        for j,f in zip(*np.where(ff[mask]>=slot-OBJ_TOL)):
            k=indices[j];name=c.branch_names[k]
            allfaces.append(dict(time=t,line=name.split('::')[0],phase=name.split('::')[-1],face=int(f),branch_index=int(k),
                raw_polygon_kVA=float(poly[k,f]),affine_current_correction_normalized=float(adj[k]),raw_affine_loading_kVA_equiv=float(ff[k,f]*ap[k]),
                normalization_ap=float(ap[k]),normalized_loading=float(ff[k,f]),slot_rho=slot,global_slack=float(rho-ff[k,f]),P1_dual=float(pd[j,f]),T_ACTIVE=epigraph and dualactive))
    assert offset==len(linedual)
    with (PRIOR/'ROOT_SLOT_LOADING.csv').open(encoding='utf8') as f:old=list(csv.DictReader(f))
    maxdiff=max(abs(r['rho_root']-float(o['rho_root'])) for r,o in zip(recomputed,old));dualdiff=max(abs(r['dual_mass']-float(o['root_dual_mass'])) for r,o in zip(recomputed,old))
    assert len(recomputed)==96 and maxdiff<=OBJ_TOL and dualdiff<=EPS,('STOP_INDEPENDENT_RECOMPUTATION_DISAGREEMENT',maxdiff,dualdiff)
    active=[r['time'] for r in recomputed if r['T_ACTIVE']];assert active,'EMPTY_ACTIVE_SET_STOP'
    start,end=min(active),max(active);window=dict(T_ACTIVE=active,W_ACTIVE=[start,end],W_BUFFER=[max(0,start-8),95],BUFFER=8,
        derived_before_new_optimization=True,selection='Independent original coefficient/vector recomputation; active epigraph AND dual thresholds',
        active_contiguous=active==list(range(start,end+1)),old_PR110_ranking_reused=False)
    if (OUT/'WINDOW_DEFINITION.json').exists():assert read(OUT/'WINDOW_DEFINITION.json')==window,'FROZEN_WINDOW_MUST_NOT_CHANGE'
    else:dump('WINDOW_DEFINITION.json',window)
    table('ROOT_SLOT_RECOMPUTATION.csv',recomputed);table('ROOT_EPIGRAPH_ACTIVE_SLOTS.csv',recomputed)
    table('ROOT_ALL_NEAR_MAX_FACES.csv',allfaces);mapping=[r for r in allfaces if r['T_ACTIVE']];table('ROOT_ACTIVE_LINE_FACE_MAP.csv',mapping)
    total=sum(r['dual_mass'] for r in recomputed);amass=sum(recomputed[t]['dual_mass'] for t in active)
    # All contiguous windows, without choosing a post-result integrality buffer.
    windows=[dict(start=a,end=z,dual_mass=sum(recomputed[t]['dual_mass'] for t in range(a,z+1)),fraction=sum(recomputed[t]['dual_mass'] for t in range(a,z+1))/total) for a in range(96) for z in range(a,96)]
    table('ROOT_CONTIGUOUS_DUAL_WINDOWS.csv',windows)
    dump('ROOT_DUAL_MASS_SUMMARY.json',dict(PASS=True,total=total,active=amass,active_fraction=amass/total,
        epigraph_active=[r['time'] for r in recomputed if r['epigraph_active']],dual_active=[r['time'] for r in recomputed if r['dual_active']],T_ACTIVE=active,
        epigraph_active_only=[r['time'] for r in recomputed if r['epigraph_active'] and not r['dual_active']],dual_active_only=[r['time'] for r in recomputed if r['dual_active'] and not r['epigraph_active']],
        largest_slot_mass_fractions={str(k):sum(sorted([r['dual_mass'] for r in recomputed],reverse=True)[:k])/total for k in [1,3,5,10]},
        shortest_contiguous_mass_windows={str(q):min((r for r in windows if r['fraction']>=q),key=lambda r:(r['end']-r['start'],r['start'])) for q in [.5,.9,.95,.99]},
        independent_loading_max_difference_vs_PR110=maxdiff,independent_dual_max_difference_vs_PR110=dualdiff,
        peak_slot=max(recomputed,key=lambda r:r['dual_mass'])['time'],window_cumulative_file='ROOT_CONTIGUOUS_DUAL_WINDOWS.csv',expected_plateau_used_as_authority=False))
    lc=Counter();pc=Counter();lpc=Counter()
    for t in active:
        mm=[r for r in mapping if r['time']==t]
        lc.update(set(r['line'] for r in mm));pc.update(set(r['phase'] for r in mm));lpc.update(set((r['line'],r['phase']) for r in mm))
    dominant_line=lc.most_common(1)[0];dominant_phase=pc.most_common(1)[0];dominant_lp=lpc.most_common(1)[0]
    canonical=[(recomputed[t]['maximum_line'],recomputed[t]['maximum_phase'],recomputed[t]['maximum_face']) for t in active]
    switches=sum(a!=z for a,z in zip(canonical,canonical[1:]))
    dump('ROOT_ACTIVE_LINE_FACE_SUMMARY.json',dict(dominant_line=dominant_line[0],dominant_line_share=dominant_line[1]/len(active),
        dominant_phase=dominant_phase[0],dominant_phase_share=dominant_phase[1]/len(active),dominant_line_phase=dominant_lp[0],dominant_line_phase_share=dominant_lp[1]/len(active),
        unique_line_phases=len(lpc),face_switches=switches,canonical_tie_break='branch authority order then smallest face; all within-1e-7 faces separately retained',
        classification='SAME_LINE_PHASE_DOMINATES' if dominant_lp[1]/len(active)>=.8 else 'SMALL_REPEATING_SET' if len(lpc)<=4 else 'HETEROGENEOUS',line_slot_counts=dict(lc),phase_slot_counts=dict(pc)))
    comparison=[];details=[];energy=[];recurrence=[]
    for ui,u in enumerate(units):
        for t in active:
            row=dict(MESS=u,time=t)
            for label,value in [('root',v),('incumbent',iv)]:
                mass=np.asarray([value.get(f'arc[{u},{sites.index(s)*96+t}]',0.) for s in sites]);travel=sum(value.get(f'arc[{u},{k}]',0.) for k,a in enumerate(arcs) if a[-1] is not None and a[1]<=t<a[3])
                ch=np.array([value.get(f'Pch[{u},{s},{t}]',0.) for s in sites]);dis=np.array([value.get(f'Pdis[{u},{s},{t}]',0.) for s in sites]);q=np.array([value.get(f'Q[{u},{s},{t}]',0.) for s in sites]);p=dis-ch
                positive=np.array([a for a in [*mass,travel] if a>EPS]);weights=positive/positive.sum()
                row.update({label+'_'+k:z for k,z in dict(site_location=';'.join(f'{s}:{y:.12g}' for s,y in zip(sites,mass) if y>EPS),stay_mass=float(mass.sum()),travel_mass=float(travel),
                    Pch=float(ch.sum()),Pdis=float(dis.sum()),Pnet=float(p.sum()),Q=float(q.sum()),SOC=value[f'SOC[{u},{t}]'],charge_mode=value[f'charge_mode[{u},{t}]'],
                    positive_sites=int(sum(mass>EPS)),location_entropy=float(-(weights*np.log(weights)).sum()),Q_dispersion=1-float(abs(q).max())/float(abs(q).sum()) if abs(q).sum()>EPS else 0.,
                    P_dispersion=1-float(abs(p).max())/float(abs(p).sum()) if abs(p).sum()>EPS else 0.).items()})
                assert abs(float(mass.sum())+travel-1)<=TOL
                for i,s in enumerate(sites):details.append(dict(MESS=u,time=t,point=label,site=s,stay_mass=float(mass[i]),Pch=float(ch[i]),Pdis=float(dis[i]),Pnet=float(p[i]),Q=float(q[i])))
            comparison.append(row)
        for label,value in [('root',v),('incumbent',iv)]:
            ch=b.dt_hours*b.eta_charge*sum(value.get(f'Pch[{u},{s},{t}]',0.) for s in sites for t in range(start,96))
            dis=b.dt_hours/b.eta_discharge*sum(value.get(f'Pdis[{u},{s},{t}]',0.) for s in sites for t in range(start,96))
            travel=sum(a[-1].energy_kwh*value.get(f'arc[{u},{k}]',0.) for k,a in enumerate(arcs) if a[-1] is not None and start<=a[1]<96)
            first=value[f'SOC[{u},{start}]'];last=value[f'SOC[{u},96]'];residual=last-first-ch+dis+travel;assert abs(residual)<=TOL
            energy.append(dict(MESS=u,point=label,start=start,end=95,E_start=first,terminal_E=last,required_net_change=last-first,
                cumulative_charge_energy=ch,cumulative_discharge_energy=dis,cumulative_travel_energy=travel,energy_balance_residual=residual,terminal_SOC_equality_dual=float(termdual[ui]) if label=='root' else None,
                arc_energy_terminal_equality_dual=arc_terminal_duals[u] if label=='root' else None,combined_terminal_RHS_dual=float(termdual[ui])+arc_terminal_duals[u] if label=='root' else None))
        for t in range(96):recurrence.append(dict(MESS=u,time=t,energy_balance_dual=float(energydual[ui*96+t])))
    table('ACTIVE_HORIZON_ROOT_VS_INCUMBENT.csv',comparison);table('ACTIVE_HORIZON_SITE_DETAIL.csv',details)
    table('TERMINAL_SOC_COUPLING_AUDIT.csv',energy);table('SOC_RECURRENCE_DUALS.csv',recurrence)
    dump('TERMINAL_SOC_DUAL_SUMMARY.json',dict(available=True,source='Inherited S3 BarPi aligned through fresh zero-optimize construction',
        terminal_SOC_duals={u:float(termdual[i]) for i,u in enumerate(units)},maximum_absolute_terminal_dual=float(abs(termdual).max()),
        arc_energy_terminal_duals=arc_terminal_duals,combined_terminal_RHS_duals={u:float(termdual[i])+arc_terminal_duals[u] for i,u in enumerate(units)},
        interpretation='S3 also has G_terminal with the same scientific terminal-energy RHS. Native terminal_SOC dual alone has cancellation/nonunique unit attribution. Combined native+arc-energy target dual is the local S3 RHS sensitivity, not an F3 counterfactual derivative; no unit-dominance inference is made from the raw native dual.',
        recurrence_dual_maximum=float(abs(energydual).max()),units='objective rho per kWh equality RHS',dual_alone_not_causal=True))
    print('INDEPENDENT ROOT AUDIT PASS',window,'dominant',dominant_lp,'dual fraction',amass/total,flush=True)
if __name__=='__main__':run()
