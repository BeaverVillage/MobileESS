"""Bounded AC precheck at frozen baseline timestamps, not feasible schedules."""
import time
import numpy as np
from ieee8500_v42_aemo.diagnostics import topology, path_to
from ieee8500_v42_aemo.run_b0 import summary
from ieee8500_v42_aemo.sensitivity import port_audit
from .common import *
from .engine import BalancedEngine


def run():
    begin=time.perf_counter(); folder=REPORT/'precheck'; folder.mkdir(parents=True,exist_ok=True)
    stage=REPORT/'ac/BALANCED_PLANNING'; axes=read(stage/'AC_AXES.json')
    base=dict(np.load(stage/'AC_96.npz')); states=read(stage/'CONTROL_STATES.json')
    slots=rows(stage/'SLOTS.csv'); groups={}
    for i,r in enumerate(axes['lines']):
        if r['objective_included']:groups.setdefault(r['element'],[]).append(i)
    ordered=sorted(groups,key=lambda n:(-float(base['line_rho'][:,groups[n]].max()),n))
    primary=[n for n in ordered if axes['lines'][groups[n][0]]['group']=='Primary'][:5]
    targets=list(dict.fromkeys(ordered[:20]+primary+['Line.tpx21459660c0']))
    probe=sorted(set(read(REPORT/'PREREGISTRATION.json')['probe_slots']+
        [int(max(slots,key=lambda r:float(r['rho_max']))['slot']),int(max(slots,key=lambda r:float(r['Primary_rho_max']))['slot'])]))
    initial=list(read(PR193/'integration_contracts/RESEARCH_FLEET_CONFIGURATION.json')['initial_locations'].values())
    write(folder/'PREREGISTRATION.json',dict(targets=targets,probe_slots=probe,steps_P_kw=1,steps_Q_kvar=1,
        target_basis='Balanced B0 only, deterministic predeclared rule; no optimization policy result',
        finite_STA_corners=[[-5,-3],[-5,3],[5,-3],[5,3]],six_parked_ports=initial,
        coupled_all_AIDC='instantaneous known eligible upper bounds, not a QoS-feasible workload schedule',
        Actual_AIDC_eligible_bound='UNVERIFIED; do not apply Planning flexible-workload bounds to Actual',
        Native_calls=0,operating_policy_retuning=False))
    e=BalancedEngine('PRECHECK'); parent=topology(e); sites=sorted(e.pccs)
    mapping={r['location_id']:r for r in rows(MAPPING)}
    paths={s:path_to(parent,mapping[s]['candidate_bus']) for s in sites}
    table(REPORT/'PCC_SOURCE_PATHS.csv',[dict(PCC=s,path_index=i,**r) for s in sites for i,r in enumerate(paths[s])])
    downstream={(s,n):n.lower() in {r['element'].lower() for r in paths[s]} for s in sites for n in targets}
    flex={(int(r['slot']),r['aidc_id']):r for r in rows(PR193/'FLEXIBLE_WORKLOAD_AUDIT.csv')}
    data=dict(np.load(DATA/'derived/PLANNING_INPUTS.npz'))
    differential=[]; finite=[]; ports=[]; counts=dict(base=0,fixed_tap=0,automatic=0)
    max_error=0.
    for t in probe:
        e.apply_inputs(t,data['gross_factor'][t],data['pv_factor'][t],data['PCC_P_kw'][t],data['PCC_Q_kvar'][t])
        a=e.settle('fixed',states[t]); counts['base']+=1
        error=float(np.abs(a['line_rho']-base['line_rho'][t]).max()); max_error=max(max_error,error)
        assert error<1e-7
        demand=dict(e.base_pcc); index={n:max(groups[n],key=lambda i:base['line_rho'][t,i]) for n in targets}
        bounds={s:float(flex[t,s]['known_only_reducible_P_upper_bound_kW']) for s in sites if s.startswith('AIDC')}
        qfactor={s:float(flex[t,s]['injected_Q_per_injected_P']) for s in bounds}
        for site in sites:
            derivatives={}
            for dim in (0,1):
                endpoints=[]
                for sign in (-1,1):
                    changed=dict(demand); x=list(changed[site]); x[dim]+=sign; changed[site]=tuple(x)
                    e.set_pcc(changed); a=e.settle('fixed',states[t]); counts['fixed_tap']+=1
                    endpoints.append(a['line_rho'][[index[n] for n in targets]])
                derivatives[dim]=(endpoints[1]-endpoints[0])/2
            bound=bounds[site] if site in bounds else 5.; qf=qfactor.get(site,0.)
            for j,n in enumerate(targets):
                r=axes['lines'][index[n]]; dp=float(derivatives[0][j]); dq=float(derivatives[1][j])
                differential.append(dict(source='PLANNING',slot=t,PCC=site,bus=mapping[site]['candidate_bus'],line=n,group=r['group'],
                    base_rho=float(base['line_rho'][t,index[n]]),parent_terminal=r['terminal'],local_node=r['node'],
                    NormalAmps=r['normal_amps'],direct_downstream=downstream[site,n],
                    d_rho_d_consumption_kw=dp,d_rho_d_consumption_kvar=dq,d_I_A_d_kw=dp*r['normal_amps'],d_I_A_d_kvar=dq*r['normal_amps'],
                    P_reduction_bound_kw=bound,coupled_Q_reduction_bound_kvar=bound*qf,
                    linear_coupled_relief_rho=bound*(dp+qf*dq),independent_Q_actuator=site.startswith('STA'),
                    fixed_settled_controls=True,dispatch_certificate=False,LV_450kw_extrapolation=False))
            changes=[(-bound,-bound*qf)] if site in bounds else [(-5,-3),(-5,3),(5,-3),(5,3)]
            for dp,dq in changes:
                changed=dict(demand); p,q=changed[site]; changed[site]=(p+dp,q+dq)
                assert changed[site][0]>=-5-1e-8
                endpoint(e,states[t],changed,t,site,dp,dq,targets,groups,base,finite,ports,counts)
        # Bounds are upper endpoints, not an assertion of simultaneously schedulable jobs.
        for case,with_aidc,with_mess in [('SIX_PARKED_STA',False,True),('ALL_AIDC_BOUNDS',True,False),('AIDC_PLUS_SIX_STA',True,True)]:
            changed=dict(demand)
            if with_aidc:
                for site,p in bounds.items():
                    x,y=changed[site]; changed[site]=(x-p,y-p*qfactor[site])
            if with_mess:
                for site in initial:changed[site]=(-5.,0.)
            endpoint(e,states[t],changed,t,case,-sum(bounds.values())*(1 if with_aidc else 0)-30*(1 if with_mess else 0),
                -sum(bounds[s]*qfactor[s] for s in bounds)*(1 if with_aidc else 0),targets,groups,base,finite,ports,counts,
                port_sites=initial if with_mess else [])
        print('precheck slot',t,'calls',counts,flush=True)
    # Actual probes independently use only bounded vehicle port tests. Their
    # AIDC workload flexibility is not inferred from Planning's eligible UID mask.
    astage=REPORT/'ac/BALANCED_ACTUAL'; actual_slots=rows(astage/'SLOTS.csv')
    actual_probe=sorted({int(max(actual_slots,key=lambda r:float(r['rho_max']))['slot']),
                         int(max(actual_slots,key=lambda r:float(r['Primary_rho_max']))['slot'])})
    adata=dict(np.load(DATA/'derived/ACTUAL_INPUTS.npz')); abase=dict(np.load(astage/'AC_96.npz')); astates=read(astage/'CONTROL_STATES.json')
    actual_finite=[]; actual_ports=[]
    for t in actual_probe:
        e.apply_inputs(t,adata['gross_factor'][t],adata['pv_factor'][t],adata['PCC_P_kw'][t],adata['PCC_Q_kvar'][t])
        demand=dict(e.base_pcc)
        for site in [s for s in sites if s.startswith('STA')]:
            for dp,dq in [(-5,-3),(-5,3),(5,-3),(5,3)]:
                changed=dict(demand); changed[site]=(dp,dq)
                endpoint(e,astates[t],changed,t,site,dp,dq,targets,groups,abase,actual_finite,actual_ports,counts)
        changed=dict(demand)
        for s in initial:changed[s]=(-5.,0.)
        endpoint(e,astates[t],changed,t,'SIX_PARKED_STA',-30,0,targets,groups,abase,actual_finite,actual_ports,counts,port_sites=initial)
    for r in actual_finite:r['source']='ACTUAL'
    table(REPORT/'PCC_CONTROLLABILITY_PRECHECK.csv',differential)
    table(folder/'AUTOMATIC_BOUNDED_ENDPOINTS.csv',finite)
    table(folder/'LV_PORT_ACTUAL_LEGS.csv',ports)
    table(folder/'ACTUAL_BOUNDED_STA_ENDPOINTS.csv',actual_finite)
    table(folder/'ACTUAL_LV_PORT_LEGS.csv',actual_ports)
    write(folder/'RECEIPT.json',dict(PASS=True,probe_slots=probe,Actual_probe_slots=actual_probe,AC_calls=counts,
        maximum_baseline_rho_error=max_error,parameters=e.verify_parameters(),
        automatic_Planning_hard_PASS=all(r['hard_constraints_PASS'] for r in finite),
        automatic_Actual_hard_PASS=all(r['hard_constraints_PASS'] for r in actual_finite),
        all_LV_ports_PASS=all(r['port_limits_PASS'] for r in ports+actual_ports),
        real_AC=True,Native_calls=0,feasible_workload_or_SOC_route_dispatch_proven=False,runtime_seconds=time.perf_counter()-begin))


def endpoint(e,state,changed,t,site,dp,dq,targets,groups,base,finite,ports,counts,port_sites=None):
    e.set_pcc(changed); a=e.settle('auto',state); counts['automatic']+=1; s=summary(e,a)
    tested=([site] if site.startswith('STA') else []) if port_sites is None else port_sites
    ports.extend(dict(slot=t,case=site,dP_kw=dp,dQ_kvar=dq,**r) for r in port_audit(e,tested))
    before_global=float(np.where(e.objective_line_mask,base['line_rho'][t],-np.inf).max())
    baseline_binding=e.line_axes[int(np.argmax(np.where(e.objective_line_mask,base['line_rho'][t],-np.inf)))]['element']
    for n in targets:
        before=float(base['line_rho'][t,groups[n]].max()); after=float(a['line_rho'][groups[n]].max())
        finite.append(dict(source='PLANNING',slot=t,PCC=site,d_consumption_P_kw=dp,d_consumption_Q_kvar=dq,
            target_line=n,base_target_rho=before,new_target_rho=after,target_relief_rho=before-after,
            base_global_rho=before_global,global_relief_rho=before_global-s['rho_max'],
            baseline_binding_line=baseline_binding,binding_line_changed=s['binding_line']!=baseline_binding,
            **s,dispatch_certificate=False,case_scope='instantaneous bounded AC endpoint, no QoS/SOC/route certification'))


if __name__=='__main__':run()
