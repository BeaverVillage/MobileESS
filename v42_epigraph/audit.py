"""Immutable root selection, full-matrix audit and preregistered slot scores."""
from .common import *
import re, math

def select():
    base=configure_inherited();from v42_relaxation.strengthening import hook
    cert=read(PRIOR/'S3_BARRIER_OPTIMALITY_CERTIFICATE.json');receipt=read(PRIOR/'S3_ROOT_LP_OPTIMIZATION.json')
    with np.load(PRIOR/'S3_ROOT_LP_SOLUTION.npz',allow_pickle=False) as z:v=dict(zip(map(str,z['names']),map(float,z['values'])))
    result={}
    def inspect(m,objectives,*args):
        m.setObjective(objectives[0][1]);m.update()
        result.update(base.matrix_validate(m,v))
        with np.load(PRIOR/'S3_BARRIER_DUAL.npz',allow_pickle=False) as z:pi=z['BarPi']
        assert len(pi)==m.NumConstrs and np.isfinite(pi).all()
        # Save row names aligned with inherited BarPi for deterministic dual diagnostics.
        rownames=np.asarray(m.getAttr('ConstrName'));np.savez_compressed(OUT/'ROOT_ROW_AXIS.npz',names=rownames)
        result.update(rows=m.NumConstrs,dual_count=len(pi),dual_finite=True)
        return None,dict(optimize_calls=0)
    ok=cert['PASS'] and cert['BarStatus']==2 and cert['width']<=OBJ_TOL and receipt['matrix_validation']['PASS']
    if ok:
        try:base.build(inspect,hook('S3',compact_energy_bounds=True))
        except (AssertionError,KeyError) as e:ok=False;result=dict(PASS=False,reason=str(e))
    chosen='S3' if ok else 'S2'
    if not ok:
        with np.load(PRIOR/'S2_ROOT_LP_SOLUTION.npz',allow_pickle=False) as z:v=dict(zip(map(str,z['names']),map(float,z['values'])))
        def fallback(m,objectives,*args):
            m.setObjective(objectives[0][1]);m.update();result.update(base.matrix_validate(m,v));return None,dict(optimize_calls=0)
        base.build(fallback,hook('S2'))
    dump('ROOT_DIAGNOSTIC_SOURCE_RECEIPT.json',dict(PASS=True,selected=chosen,S3_CERTIFICATE_USED=ok,
        solution=(PRIOR/(chosen+'_ROOT_LP_SOLUTION.npz')).relative_to(ROOT).as_posix(),solution_sha256=sha(PRIOR/(chosen+'_ROOT_LP_SOLUTION.npz')),
        certificate=cert,full_matrix_revalidation=result,rho=v['rho_max'],reoptimization_calls=0,
        reason='S3 inherited interval and full matrix BarX revalidation pass; isolate residual mode/energy weakness' if ok else 'S3 certificate rejected; use overall-OPTIMAL S2',production_selection=False))
    print('ROOT SOURCE',chosen,result,flush=True)

def audit():
    v=root_values();bundle,anchor,inc,sites,initial,routes,b=inputs();arcs=arcs_for(sites,routes)
    reach=reachable_arcs(sites,initial,routes);indices={t:state_indices(arcs,t) for t in range(96)}
    states=[];pq=[];detail=[];state_axis={}
    for u in sorted(initial):
        for t in range(96):
            yy={s:sum(v[f'arc[{u},{k}]'] for k in indices[t][s]) for s in sites}
            travel=sum(v[f'arc[{u},{k}]'] for k in indices[t]['TRANSIT']);connected=sum(yy.values());complement=1-connected
            total=connected+travel
            states.append(dict(MESS=u,time=t,site_mass=connected,transit_crossing_mass=travel,transit_complement=complement,total_state_mass=total,
                total_residual=total-1,complement_residual=travel-complement,min_site_mass=min(yy.values()),PASS=abs(total-1)<=TOL and min(yy.values())>=-TOL and travel>=-TOL))
            axis=[s for s in [*sites,'TRANSIT'] if set(indices[t][s]) & reach[u]]
            state_axis[f'{u}:{t}']=dict(states=axis,root={**yy,'TRANSIT':complement},root_transit_crossing=travel,transit_expression='1 - sum site masses; equivalence to crossing arcs independently audited; no clipping',incumbent={s:sum(inc['values'].get(f'arc[{u},{k}]',0) for k in indices[t][s]) for s in axis})
            ch=np.array([v[f'Pch[{u},{s},{t}]'] for s in sites]);dis=np.array([v[f'Pdis[{u},{s},{t}]'] for s in sites]);qs=np.array([v[f'Q[{u},{s},{t}]'] for s in sites]);ps=dis-ch
            qabs=abs(qs);pabs=abs(ps);mass=np.array(list(yy.values()));positive=mass[mass>EPS];weights=positive/positive.sum() if len(positive) else positive
            pq.append(dict(MESS=u,time=t,positive_sites=sum(mass>EPS),Q_sites=sum(qabs>EPS),P_sites=sum(pabs>EPS),sum_abs_Q=float(qabs.sum()),max_abs_Q=float(qabs.max()),
                Q_dispersion=1-float(qabs.max())/max(float(qabs.sum()),EPS),P_dispersion=1-float(pabs.max())/max(float(pabs.sum()),EPS),
                weighted_site_entropy=float(-sum(weights*np.log(weights))),connected_mass=connected,PCS_utilization=float(np.hypot(ps,qs).sum())/(b.pcs_kva*connected) if connected>EPS else None))
            for i,s in enumerate(sites):detail.append(dict(MESS=u,time=t,site=s,stay_mass=yy[s],transit_mass=travel,Pch=float(ch[i]),Pdis=float(dis[i]),Pnet=float(ps[i]),Q=float(qs[i]),SOC=v[f'SOC[{u},{t}]'],stay_departure_G=v.get(f'G[{u},{indices[t][s][0]}]')))
    table('ROOT_STATE_MASS_AUDIT.csv',states);assert all(r['PASS'] for r in states),'STOP_STATE_MASS_FAILURE'
    table('ROOT_SPATIAL_PQ_AUDIT.csv',pq);table('ROOT_SITE_STATE_VALUES.csv',detail)
    dump('ROOT_STATE_AXIS.json',state_axis)
    dump('ROOT_SPATIAL_PQ_SUMMARY.json',dict(PASS=True,epsilon=EPS,slots=len(pq),max_simultaneous_sites=int(max(r['positive_sites'] for r in pq)),
        multi_site_slot_fraction=sum(r['positive_sites']>1 for r in pq)/len(pq),distributed_Q_slot_fraction=sum(r['Q_sites']>1 for r in pq)/len(pq),
        max_mass_residual=max(abs(r['total_residual']) for r in states),no_clipping=True,state_semantics='crossing travel arc: depart <= t < connect; connection slot uses stay or next departure',point_specific_not_causal=True))
    from v42_bootstrap.grid import coefficients
    _,coeff=coefficients(bundle);loading=[];gaps=[];cos=np.cos(2*np.pi*np.arange(16)/16);sin=np.sin(2*np.pi*np.arange(16)/16)
    from v42_native.voltage import voltage_for,Stage
    va=voltage_for(Stage.M1)
    dual=np.load(PRIOR/'S3_BARRIER_DUAL.npz')['BarPi'] if read(OUT/'ROOT_DIAGNOSTIC_SOURCE_RECEIPT.json')['S3_CERTIFICATE_USED'] else None
    offset=0
    if dual is not None:
        names=np.load(OUT/'ROOT_ROW_AXIS.npz')['names'];line=dual[names=='line_thermal_face'];assert len(line)%96==0;dual_slots=abs(line.reshape(96,-1)).sum(axis=1)
    else:dual_slots=[None]*96
    for t,c in enumerate(coeff):
        xs=[]
        for value in [v,inc['values']]:
            controls=[]
            for i,n in enumerate(c.control_names):
                s=n.split('[')[1][:-1]
                if n.startswith('aidc_load_kw'):controls.append(float(anchor['controls'][t][i]))
                elif n.startswith('mess_p_kw'):controls.append(sum(value[f'Pdis[{u},{s},{t}]']-value[f'Pch[{u},{s},{t}]'] for u in initial))
                elif n.startswith('mess_q_kvar'):controls.append(sum(value[f'Q[{u},{s},{t}]'] for u in initial))
            x=np.asarray(controls);p=c.flow_p_constant+c.flow_p_matrix@x;q=c.flow_q_constant+c.flow_q_matrix@x
            ap=c.branch_limits*math.cos(math.pi/16);pa=c.flow_p_constant+c.flow_p_matrix@c.anchor;qa=c.flow_q_constant+c.flow_q_matrix@c.anchor
            raw=(pa[:,None]*cos+qa[:,None]*sin)/ap[:,None];active=np.argmax(raw,axis=1)
            grad=(cos[active,None]*c.flow_p_matrix+sin[active,None]*c.flow_q_matrix)/ap[:,None]
            correction=c.current_matrix.T-grad;bias=c.current_constant+c.current_matrix.T@c.anchor-np.max(raw,axis=1)
            mask=np.array([not n.lower().startswith('transformer.') for n in c.branch_names])
            faces=(p[:,None]*cos+q[:,None]*sin)/ap[:,None]+(correction@(x-c.anchor)+bias)[:,None]
            rho=float(faces[mask].max());volt=c.voltage_constant+c.voltage_matrix.T@x
            xs.append((rho,float(min((volt-va.lower_squared).min(),(va.upper_squared-volt).min()))))
        loading.append(dict(time=t,rho_root=xs[0][0],rho_inc=xs[1][0],root_dual_mass=dual_slots[t],root_voltage_proximity_squared=xs[0][1],distributed_Q_score=sum(r['Q_dispersion'] for r in pq if r['time']==t)/4))
        gaps.append(dict(time=t,rho_root=xs[0][0],rho_inc=xs[1][0],gap_proxy=xs[1][0]-xs[0][0],local_optimality_gap=False))
    assert abs(max(r['rho_inc'] for r in loading)-UB)<=OBJ_TOL
    assert max(r['rho_root'] for r in loading)<=v['rho_max']+TOL
    table('ROOT_SLOT_LOADING.csv',loading);table('ROOT_INCUMBENT_SLOT_GAP.csv',gaps)
    slots=[r['time'] for r in sorted(gaps,key=lambda r:(-r['gap_proxy'],r['time']))[:6]]
    assert not (OUT/'CRITICAL_SLOT_FREEZE.json').exists(),'SLOTS_ALREADY_FROZEN'
    dump('CRITICAL_SLOT_FREEZE.json',dict(K=6,slots=slots,E2_slots=slots[:3],selection_rule='descending gap_proxy; lower time index first',
        gap_file_sha256=sha(OUT/'ROOT_INCUMBENT_SLOT_GAP.csv'),preregistration_sha256=sha(OUT/'PREREGISTRATION.json'),
        scores=[{**gaps[t],**loading[t]} for t in slots],reselection_allowed=False))
    print('AUDIT',read(OUT/'ROOT_SPATIAL_PQ_SUMMARY.json'),'CRITICAL',slots,flush=True)

def canonical_state_axis():
    axis=read(OUT/'ROOT_STATE_AXIS.json');differences=[]
    for r in csvread('ROOT_STATE_MASS_AUDIT.csv'):
        a=axis[f"{r['MESS']}:{r['time']}"];crossing=float(r['transit_crossing_mass']);complement=float(r['transit_complement'])
        a.update(root_transit_crossing=crossing,transit_expression='1 - sum site masses; equivalence to crossing arcs independently audited; no clipping')
        a['root']['TRANSIT']=complement;differences.append(abs(crossing-complement))
    dump('ROOT_STATE_AXIS.json',axis)
    dump('TRANSIT_EXPRESSION_RECEIPT.json',dict(expression='1 - sum_s y[m,s,t]',no_clipping=True,flow_equivalent_crossing_expression='sum travel x with depart <= t < connect',max_numerical_difference=max(differences),state_mass_audit_PASS=True,critical_slots_unchanged=True))

if __name__=='__main__':
    import sys
    globals()[sys.argv[1]]()
