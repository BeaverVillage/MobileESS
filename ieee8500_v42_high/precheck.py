"""All-original-line P/Q derivatives and nonlinear endpoints, never schedules."""
import time
import numpy as np
from ieee8500_v42_aemo.diagnostics import topology,path_to
from ieee8500_v42_aemo.run_b0 import summary
from ieee8500_v42_aemo.sensitivity import port_audit
from .common import *
from .engine import HighEngine


def run(base_tag='FINAL_B0_PLANNING'):
    begin=time.perf_counter();stage=REPORT/'ac'/base_tag;folder=REPORT/'precheck';folder.mkdir(parents=True,exist_ok=True)
    axes=read(stage/'AC_AXES.json');base=dict(np.load(stage/'AC_96.npz'));states=read(stage/'CONTROL_STATES.json')
    receipt0=read(stage/'RECEIPT.json');data=dict(np.load(receipt0['AIDC_input']['path']))
    groups={}
    for i,r in enumerate(axes['lines']):
        if r['objective_included']:groups.setdefault(r['element'],[]).append(i)
    ordered=sorted(groups,key=lambda n:(-float(base['line_rho'][:,groups[n]].max()),n))
    targets=list(dict.fromkeys(ordered[:20]+[n for n in ordered if axes['lines'][groups[n][0]]['group']=='Primary'][:5]+['Line.tpx21459660c0']))
    slots=rows(stage/'SLOTS.csv');probe=sorted(set(read(REPORT/'SCENARIO_PREREGISTRATION.json')['finite_slots']+
        [int(receipt0['peak_slot']),int(max(slots,key=lambda r:float(r['Primary_rho_max']))['slot'])]))
    initial=list(read(PR193/'integration_contracts/RESEARCH_FLEET_CONFIGURATION.json')['initial_locations'].values())
    prereg=dict(base=base_tag,targets=targets,probe_slots=probe,all_original_line_conductor_axes=True,
        central_step_kw_kvar=1.,finite_STA_corners=[[-5,-3],[-5,3],[5,-3],[5,3]],
        AIDC_bound='known-source eligible occupancy relaxation only, PF .95 coupled; certified nonzero96 flex unavailable',
        six_parked_ports=initial,Actual_AIDC_bounds='NOT_INFERRED',Native_calls=0,schedule_certificate=False)
    path=folder/'PREREGISTRATION.json'
    if path.exists():assert read(path)==prereg
    else:write(path,prereg)
    e=HighEngine('PRECHECK',receipt0['bg']);sites=sorted(e.pccs);mapping={r['location_id']:r for r in rows(MAPPING)}
    parent=topology(e);paths={s:path_to(parent,mapping[s]['candidate_bus']) for s in sites}
    table(REPORT/'PCC_SOURCE_PATHS.csv',[dict(PCC=s,path_index=i,**r) for s in sites for i,r in enumerate(paths[s])])
    downstream={(s,n):n.lower() in {r['element'].lower() for r in paths[s]} for s in sites for n in targets}
    differential=[];finite=[];ports=[];all_derivatives=[];max_error=0.;count=dict(base=0,fixed=0,automatic=0)
    qfactor=float(np.tan(np.arccos(.95)))
    def endpoint(t,case,changed,dp,dq,base_array,state,source='PLANNING',port_sites=()):
        e.set_pcc(changed);a=e.settle('auto',state);count['automatic']+=1;s=summary(e,a)
        ports.extend(dict(slot=t,source=source,case=case,**r) for r in port_audit(e,port_sites))
        before_global=float(np.where(e.objective_line_mask,base_array[t],-np.inf).max())
        for n in targets:
            before=float(base_array[t,groups[n]].max());after=float(a['line_rho'][groups[n]].max())
            finite.append(dict(source=source,slot=t,case=case,d_consumption_P_kw=dp,d_consumption_Q_kvar=dq,
                target_line=n,target_group=axes['lines'][groups[n][0]]['group'],base_target_rho=before,new_target_rho=after,
                target_relief_rho=before-after,base_global_rho=before_global,global_relief_rho=before_global-s['rho_max'],
                **s,dispatch_certificate=False,scope='instantaneous AC, not96 QoS/SOC/travel schedule'))
    for t in probe:
        e.apply_inputs(t,data);a=e.settle('fixed',states[t]);count['base']+=1
        error=float(np.abs(a['line_rho']-base['line_rho'][t]).max());max_error=max(max_error,error);assert error<1e-7
        demand=dict(e.base_pcc);indices={n:max(groups[n],key=lambda i:base['line_rho'][t,i]) for n in targets}
        bounds={s:float(data['source_mask_P_upper_bound_kw'][t,i]) for i,s in enumerate(sorted(s for s in sites if s.startswith('AIDC')))}
        derivatives_slot=[]
        for site in sites:
            derivatives=[]
            for dim in (0,1):
                endpoints=[]
                for sign in (-1,1):
                    changed=dict(demand);x=list(changed[site]);x[dim]+=sign;changed[site]=tuple(x)
                    e.set_pcc(changed);a=e.settle('fixed',states[t]);count['fixed']+=1;endpoints.append(a['line_rho'].copy())
                derivatives.append((endpoints[1]-endpoints[0])/2)
            derivatives_slot.append(derivatives)
            bound=bounds.get(site,5.);qf=qfactor if site.startswith('AIDC') else 0.
            for n in targets:
                i=indices[n];meta=axes['lines'][i];dp=float(derivatives[0][i]);dq=float(derivatives[1][i])
                differential.append(dict(slot=t,PCC=site,bus=mapping[site]['candidate_bus'],line=n,group=meta['group'],
                    base_rho=float(base['line_rho'][t,i]),parent_terminal=meta['terminal'],local_node=meta['node'],
                    NormalAmps=meta['normal_amps'],direct_downstream=downstream[site,n],
                    d_rho_d_consumption_kw=dp,d_rho_d_consumption_kvar=dq,d_I_A_d_kw=dp*meta['normal_amps'],d_I_A_d_kvar=dq*meta['normal_amps'],
                    source_mask_P_relaxation_kw=bound,certified_AIDC_reducible_P_kw=0. if site.startswith('AIDC') else '',
                    linear_relaxation_relief_rho=bound*(dp+qf*dq),independent_Q_actuator=site.startswith('STA'),
                    fixed_controls=True,dispatch_certificate=False))
            corners=[(-bound,-bound*qf)] if site.startswith('AIDC') else [(-5,-3),(-5,3),(5,-3),(5,3)]
            for dp,dq in corners:
                changed=dict(demand);p,q=changed[site];changed[site]=(p+dp,q+dq)
                endpoint(t,site,changed,dp,dq,base['line_rho'],states[t],port_sites=[site] if site.startswith('STA') else [])
        all_derivatives.append(derivatives_slot)
        for case,use_a,use_m in [('AIDC_RELAXATION',True,False),('SIX_STA_INSTANT',False,True),('JOINT_RELAXATION',True,True)]:
            changed=dict(demand)
            if use_a:
                for s,p in bounds.items():x,y=changed[s];changed[s]=(x-p,y-p*qfactor)
            if use_m:
                for s in initial:changed[s]=(-5.,0.)
            endpoint(t,case,changed,-sum(bounds.values())*use_a-30*use_m,-sum(bounds.values())*qfactor*use_a,
                base['line_rho'],states[t],port_sites=initial if use_m else [])
        print('High precheck slot',t,'calls',count,flush=True)
    np.savez_compressed(folder/'ALL_ORIGINAL_LINE_PQ_DERIVATIVES.npz',slots=np.array(probe),sites=np.array(sites),
        d_rho_d_consumption=np.array(all_derivatives),normal_amps=np.array([r['normal_amps'] for r in axes['lines']]))
    # Actual tests are vehicle endpoints only. Their timing cannot choose the scenario.
    astage=REPORT/'ac/FINAL_B0_ACTUAL';adata=dict(np.load(read(astage/'RECEIPT.json')['AIDC_input']['path']))
    abase=dict(np.load(astage/'AC_96.npz'));astates=read(astage/'CONTROL_STATES.json');ar=read(astage/'RECEIPT.json')
    t=int(ar['peak_slot']);e.apply_inputs(t,adata);demand=dict(e.base_pcc)
    for site in [s for s in sites if s.startswith('STA')]:
        for dp,dq in [(-5,-3),(-5,3),(5,-3),(5,3)]:
            changed=dict(demand);changed[site]=(dp,dq)
            endpoint(t,site,changed,dp,dq,abase['line_rho'],astates[t],'ACTUAL',[site])
    changed=dict(demand)
    for s in initial:changed[s]=(-5.,0.)
    endpoint(t,'SIX_STA_INSTANT',changed,-30,0,abase['line_rho'],astates[t],'ACTUAL',initial)
    table(REPORT/'PCC_CONTROLLABILITY_PRECHECK.csv',differential);table(folder/'AUTOMATIC_BOUNDED_ENDPOINTS.csv',finite)
    table(folder/'LV_PORT_ACTUAL_LEGS.csv',ports)
    write(folder/'RECEIPT.json',dict(PASS=True,AC_calls=count,baseline_error=max_error,
        all_original_line_axes=True,all_tested_ports_PASS=all(r['port_limits_PASS'] for r in ports),
        all_endpoints_grid_hard_PASS=all(r['hard_constraints_PASS'] for r in finite),parameters=e.verify_parameters(),
        Native_calls=0,dispatch_certificate=False,runtime_seconds=time.perf_counter()-begin))


if __name__=='__main__':run()
