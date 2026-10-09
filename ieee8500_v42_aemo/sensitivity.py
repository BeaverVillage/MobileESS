"""New-point AC derivatives and bounded automatic-control counterfactuals.

Demand-positive convention. Derivatives are not schedules or a control envelope
certificate. All counterfactuals start from an already voltage-ineligible P3 base.
"""
import time
import numpy as np
from ieee8500_v42.ac import _complex
from .common import *
from .engine import StudyEngine
from .diagnostics import topology,path_to
from .run_b0 import summary


def targets(axes,base):
    groups={}
    for i,r in enumerate(axes['lines']):
        if r['objective_included']:groups.setdefault(r['element'],[]).append(i)
    ordered=sorted(groups,key=lambda name:(-float(base[:,groups[name]].max()),name))[:20]
    return ordered,groups


def port_audit(e,sites):
    result=[]
    for site in sites:
        if not site.startswith('STA'):continue
        e.d.Circuit.SetActiveElement(e.pccs[site]['element'])
        current=np.abs(_complex(e.d.CktElement.Currents()))
        v=_complex(e.d.CktElement.Voltages())
        pq=np.asarray(e.d.CktElement.Powers()).reshape(-1,2).sum(0)
        result.append(dict(site=site,actual_P_kw=float(pq[0]),actual_Q_kvar=float(pq[1]),
            actual_S_kva=float(np.linalg.norm(pq)),hot1_A=float(current[0]),hot2_A=float(current[1]),
            line_line_V=float(abs(v[0]-v[1])),port_limits_PASS=bool(max(current)<=27+1e-7
                and np.linalg.norm(pq)<=6+1e-7 and abs(pq[0])<=5+1e-7 and abs(pq[1])<=3+1e-7)))
    return result


def run(primary=False,final=False,peak=False):
    begin=time.perf_counter()
    folder=REPORT/(('final_' if final else '')+('peak_' if peak else '')+('primary_sensitivity' if primary else 'sensitivity'));folder.mkdir(parents=True,exist_ok=True)
    stage=REPORT/'ac'/('FINAL_B0_PLANNING' if final else 'B0_PLANNING');axes=read(stage/'AC_AXES.json')
    operating=read(stage/'RECEIPT.json');policy=operating['policy'];base_qualified=operating['hard_constraints_PASS']
    if final:assert read(REPORT/'emergency/FINAL_VALIDATION.json')['B0_AC_physical_qualification_PASS']
    with np.load(stage/'AC_96.npz') as z:base=z['line_rho'].copy()
    names,groups=targets(axes,base)
    if primary:
        names=sorted([n for n in groups if axes['lines'][groups[n][0]]['group']=='Primary'],
                     key=lambda n:(-float(base[:,groups[n]].max()),n))[:5]
    states=read(stage/'CONTROL_STATES.json')
    with np.load(DATA/'derived/PLANNING_INPUTS.npz') as z:data={k:z[k] for k in z.files}
    flex_path=PR193/'FLEXIBLE_WORKLOAD_AUDIT.csv'
    flex={(int(r['slot']),r['aidc_id']):r for r in rows(flex_path)}
    e=StudyEngine(folder.name,policy,True);sites=sorted(e.pccs)
    parent=topology(e)
    mapping=rows(MAPPING);site_bus={r['location_id']:r['candidate_bus'].lower() for r in mapping}
    downstream={}
    for site in sites:
        elements={r['element'].lower() for r in path_to(parent,site_bus[site])}
        for name in names:downstream[site,name]=name.lower() in elements
    probe_slots=[int(operating['peak_slot'])] if peak else read(REPORT/'PREREGISTRATION.json')['sensitivity_slots']
    rule=dict(base=stage.name,selected_policy=policy if final else None,base_all96_voltage_PASS=base_qualified,
        central_steps=dict(P_kw=1.,Q_kvar=1.),central_slots=probe_slots if primary or peak else list(range(96)),
        finite_automatic_slots=probe_slots,
        peak_probe_scope='additional baseline peak snapshot; no policy outcome or siting/rating adjustment' if peak else '',
        target_rule=('top5 Primary' if primary else 'top20 global')+' new Planning maximum canonical ratio across96; stable line-name tie break',
        target_lines=names,known_bound_source=receipt(flex_path),
        known_bound='PR193 eligible-known GPU union only; same frozen jobs/GFS/C1 identity; noCC4/idle reduction',
        independent_AIDC_Q_actuator=False,all_known_job_reduction_is_feasible_schedule=False,
        all12STA_simultaneous=False,finite_STA_corners=[[-5,-3],[-5,3],[5,-3],[5,3]],
        six_initial_ports=read(PR193/'integration_contracts/RESEARCH_FLEET_CONFIGURATION.json')['initial_locations'],
        six_port_counterfactual_is_route_SOC_dispatch_certificate=False)
    write(folder/'PREREGISTRATION.json',rule)
    differential=[];finite=[];ports=[];counts=dict(fixed_tap=0,automatic=0,base=0)
    maximum_base_error=0.;step_consistency=[]
    finite_slots=set(rule['finite_automatic_slots'])
    for t in range(96):
        if (primary or peak) and t not in finite_slots:continue
        e.apply_inputs(t,data['gross_factor'][t],data['pv_factor'][t],data['PCC_P_kw'][t],data['PCC_Q_kvar'][t])
        a=e.settle('fixed',states[t]);counts['base']+=1
        error=float(np.abs(a['line_rho']-base[t]).max());maximum_base_error=max(maximum_base_error,error)
        assert error<1e-7,'NEW_POINT_BASE_REPRODUCTION_FAILED'
        demand=dict(e.base_pcc)
        index={name:max(groups[name],key=lambda i:base[t,i]) for name in names}
        for site in sites:
            values={}
            for axis in (0,1):
                endpoints=[]
                for sign in (-1,1):
                    changed=dict(demand);value=list(changed[site]);value[axis]+=sign;changed[site]=tuple(value)
                    e.set_pcc(changed);a=e.settle('fixed',states[t]);counts['fixed_tap']+=1
                    endpoints.append(a['line_rho'][[index[n] for n in names]])
                values[axis]=(endpoints[1]-endpoints[0])/2
            bound=float(flex[t,site]['known_only_reducible_P_upper_bound_kW']) if site.startswith('AIDC') else 5.
            qfactor=float(flex[t,site]['injected_Q_per_injected_P']) if site.startswith('AIDC') else 0.
            for j,name in enumerate(names):
                meta=axes['lines'][index[name]]
                dP=float(values[0][j]);dQ=float(values[1][j]);rating=meta['normal_amps']
                differential.append(dict(slot=t,PCC=site,bus=site_bus[site],line=name,group=meta['group'],
                    base_rho=float(base[t,index[name]]),parent_terminal=meta['terminal'],local_node=meta['node'],
                    d_rho_d_consumption_kw=dP,d_rho_d_consumption_kvar=dQ,
                    d_I_A_d_consumption_kw=dP*rating,d_I_A_d_consumption_kvar=dQ*rating,
                    direct_downstream=downstream[site,name],P_reduction_upper_bound_kw=bound,
                    coupled_Q_reduction_upper_bound_kvar=bound*qfactor,
                    linear_coupled_P_reduction_relief_rho=bound*(dP+qfactor*dQ),
                    independent_Q_actuator=site.startswith('STA'),base_voltage_qualified=base_qualified,
                    derivative_controlmode='off_settled_base',dispatch_certified=False))
            if t not in finite_slots:continue
            changes=[(-bound,-bound*qfactor)] if site.startswith('AIDC') else rule['finite_STA_corners']
            for dp,dq in changes:
                changed=dict(demand);p,q=changed[site];changed[site]=(p+dp,q+dq)
                assert changed[site][0]>=-5-1e-8
                e.set_pcc(changed);a=e.settle('auto',states[t]);counts['automatic']+=1
                s=summary(e,a);changed_state=e.control_state()
                ports.extend(dict(slot=t,case=site,dP_kw=dp,dQ_kvar=dq,**r) for r in port_audit(e,[site]))
                for name in names:
                    before=float(base[t,groups[name]].max());after=float(a['line_rho'][groups[name]].max())
                    finite.append(dict(slot=t,PCC=site,bus=site_bus[site],d_consumption_P_kw=dp,d_consumption_Q_kvar=dq,
                        target_line=name,base_target_rho=before,new_target_rho=after,target_relief_rho=before-after,
                        base_voltage_qualified=base_qualified,**s,control_state_changed=changed_state!=states[t],
                        dispatch_certified=False,case_scope='isolated bounded AC endpoint; no feasible schedule claim'))
        # Six existing initial ports: no movement or use of twelve simultaneous docks.
        if t in finite_slots:
            initial=list(rule['six_initial_ports'].values());changed=dict(demand)
            for site in initial:changed[site]=(-5.,0.)
            e.set_pcc(changed);a=e.settle('auto',states[t]);counts['automatic']+=1
            ports.extend(dict(slot=t,case='SIX_INITIAL_PORTS',dP_kw=-5,dQ_kvar=0,**r) for r in port_audit(e,initial))
            for name in names:
                before=float(base[t,groups[name]].max());after=float(a['line_rho'][groups[name]].max())
                finite.append(dict(slot=t,PCC='SIX_INITIAL_PORTS',bus='',d_consumption_P_kw=-30,d_consumption_Q_kvar=0,
                    target_line=name,base_target_rho=before,new_target_rho=after,target_relief_rho=before-after,
                    base_voltage_qualified=base_qualified,**summary(e,a),control_state_changed=e.control_state()!=states[t],
                    dispatch_certified=False,case_scope='instantaneous six parked ports; no SOC/route certificate'))
        e.set_pcc(demand);e.restore_control_state(states[t])
        if (t+1)%12==0:print('sensitivity',t+1,'/96; ACcalls',counts,flush=True)
    output=REPORT/(('FINAL_' if final else '')+('PEAK_' if peak else '')+('PRIMARY_PCC_CONTROLLABILITY.csv' if primary else 'PCC_PQ_CONTROLLABILITY.csv'))
    table(output,differential)
    table(folder/'AUTOMATIC_BOUNDED_ENDPOINTS.csv',finite)
    table(folder/'LV_PORT_ACTUAL_LEGS.csv',ports)
    write(folder/'RECEIPT.json',dict(PASS=True,scope='AC diagnostic execution only; no physical-operating qualification',
        rows=len(differential),automatic_rows=len(finite),AC_calls=counts,
        maximum_base_current_rho_reproduction_error=maximum_base_error,
        preserved_parameter_check=e.verify_parameters(),elapsed_seconds=time.perf_counter()-begin,
        original_sensitivity_arrays_used=False,Native_calls=0,base_operational_PASS=base_qualified,
        differential_csv=receipt(output)))
    print('sensitivity COMPLETE',counts,flush=True)


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--primary',action='store_true');parser.add_argument('--final',action='store_true');parser.add_argument('--peak',action='store_true')
    args=parser.parse_args();run(args.primary,args.final,args.peak)
