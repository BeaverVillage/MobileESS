"""Every selected LV dock: both hot currents, full P/Q box, all96 B0 slots.

Dock hardware limits are not a promise that its full box is grid-feasible.
The unchanged grid constraints must restrict actual dispatch. No policy solve.
"""
import os
os.environ.setdefault('OPENBLAS_NUM_THREADS','1')
os.environ.setdefault('OMP_NUM_THREADS','1')
import numpy as np
from .common import REPORT,read,write,table,receipt
from .capacity import build_candidate
from .geometry import read_csv
from .screening import demand
from .selected_case_v3 import engine,MAPPING,array_summary
from .lv_sensitivity import axes_for_candidate
from .lv_port_design import command_check

FOLDER=REPORT/'joint_selection_v3/selected_port_ac'
COMMANDS=((5.,0.),(-5.,0.),(0.,3.),(0.,-3.),(5.,3.),(5.,-3.),(-5.,3.),(-5.,-3.))


def run():
    policy=dict(schema='SELECTED_LV_FULL_RATING96_AC_PREREGISTRATION',mapping=receipt(MAPPING),
        background_scale=.552,capacity_scale=1.,PV_objects=0,slots=96,commands=[list(x) for x in COMMANDS],
        positive_sign='injection',base_controls='original auto sequential96; every probe same settled state fixed',
        actual_autocontrol_validation='separate fourtime endpoints at full commands, independently initialized from original states',
        one_dock_at_a_time=True,simultaneous_six_vehicle_or_policy_feasibility_claim=False,
        hardware_rating='P±5kW Q±3kvar S6kVA 27A eachhot; original CT/Triplex/voltage constraints unchanged',
        full_box_failure='requires grid-dependent admissible domain, not rating relaxation or automatic site retuning',
        layout_changes_from_AC_results=0,Native_calls=0)
    write(FOLDER/'PREREGISTRATION.json',policy)
    allmeta={x['candidate_bus']:x for x in read_csv(REPORT/'LV_STA_CANDIDATES.csv')}
    mapping=[x for x in read_csv(MAPPING) if x['role']=='STA'];c=build_candidate(1.);e=engine('port_validation')
    local={r['location_id']:axes_for_candidate(e,allmeta[r['candidate_bus']]) for r in mapping}
    primary={site:next(k for k in li['tx_kva'] if e.transformer_winding_axes[k]['winding']==1)
             for site,li in local.items()}
    rows=[];hots=[];neutral=[];automatic=[]
    for t in range(96):
        dd=demand(c,t);e.solve(.552,dd,reset_controls=False,snapshot=False);a0=e.measurement_arrays();state=e.control_state()
        if not a0['converged'] or not a0['control_actions_done']:raise ValueError('BASE_NOT_SETTLED')
        for r in mapping:
            site=r['location_id'];bus=r['candidate_bus'];li=local[site]
            for p,q in COMMANDS:
                changed=dict(dd);changed[site]=(-p,-q)
                e.solve(.552,changed,'fixed',state,snapshot=False);a=e.measurement_arrays()
                if not a['converged']:raise ValueError('FULL_RATING_AC_DIVERGED')
                e.d.Circuit.SetActiveElement(e.pccs[site]['element'])
                currents=np.array(e.d.CktElement.Currents()).reshape(-1,2)
                powers=np.array(e.d.CktElement.Powers()).reshape(-1,2).sum(0)
                readback=float(np.max(np.abs(powers+np.array([p,q]))))
                e.d.Circuit.SetActiveBus(bus)
                vv=np.array(e.d.Bus.Voltages()).reshape(-1,2);nodes=e.d.Bus.Nodes()
                volts={n:complex(v[0],v[1]) for n,v in zip(nodes,vv)}
                hardware=command_check(p,q,volts[1],volts[2])
                local_ok=bool(a['line_rho'][li['line']].max()<=1 and a['transformer_current_rho'][li['tx_current']].max()<=1
                    and a['transformer_winding_nameplate_kva_rho'][li['tx_kva']].max()<=1
                    and a['node_voltage_pu'][li['nodes']].min()>=.95 and a['node_voltage_pu'][li['nodes']].max()<=1.05)
                row=dict(slot=t,site=site,bus=bus,P_injection_kw=p,Q_injection_kvar=q,
                    actual_PQ_readback_error=readback,hot_KCL_A=float(np.linalg.norm(currents.sum(0))),
                    port_hot1_current_A=float(np.linalg.norm(currents[0])),port_hot2_current_A=float(np.linalg.norm(currents[1])),
                    actual_VLL_V=abs(volts[1]-volts[2]),interface_envelope_PASS=hardware['interface_envelope_PASS'],
                    local_PCC_Vmin=float(a['node_voltage_pu'][li['nodes']].min()),local_PCC_Vmax=float(a['node_voltage_pu'][li['nodes']].max()),
                    local_triplex_rho_max=float(a['line_rho'][li['line']].max()),
                    original_CT_current_rho_max=float(a['transformer_current_rho'][li['tx_current']].max()),
                    original_CT_nameplate_rho_max=float(a['transformer_winding_nameplate_kva_rho'][li['tx_kva']].max()),
                    original_CT_primary_P_kw=float(a['transformer_winding_complex_kva'][primary[site]].real),
                    original_CT_secondary_max_P_kw=float(max(a['transformer_winding_complex_kva'][k].real
                        for k in li['tx_kva'] if e.transformer_winding_axes[k]['winding']!=1)),
                    local_original_grid_constraints_PASS=local_ok,
                    new_global_line_overload_cells=int(((a['line_rho']>1)&(a0['line_rho']<=1)).sum()),
                    new_global_voltage_violation_cells=int((((a['node_voltage_pu']<.95)|(a['node_voltage_pu']>1.05))
                        &((a0['node_voltage_pu']>=.95)&(a0['node_voltage_pu']<=1.05))).sum()),
                    full_grid_AC_constraints_PASS=bool(a['line_rho'].max()<=1 and a['transformer_current_rho'].max()<=1
                        and a['transformer_winding_nameplate_kva_rho'].max()<=1 and a['node_voltage_pu'].min()>=.95 and a['node_voltage_pu'].max()<=1.05),
                    original_taps_caps_fixed_same_base=True,field_installed_or_protection_approved=False,policy_schedule=False)
                if readback>1e-6 or row['hot_KCL_A']>1e-9:raise ValueError('PCC_READBACK_OR_KCL_FAILED')
                rows.append(row)
                for k in li['line']:
                    hots.append(dict(slot=t,site=site,P_injection_kw=p,Q_injection_kvar=q,**e.line_axes[k],
                        baseline_current_A=float(a0['line_amps'][k]),actual_current_A=float(a['line_amps'][k]),
                        current_change_A=float(a['line_amps'][k]-a0['line_amps'][k]),actual_rho=float(a['line_rho'][k])))
                # axes_for_candidate is [Triplex segment, terminal]; each
                # terminal has its own reconstructed neutral-current audit.
                for k in li['neutral'].ravel():
                    neutral.append(dict(slot=t,site=site,P_injection_kw=p,Q_injection_kvar=q,**e.triplex_terminal_axes[k],
                        baseline_implied_neutral_A=float(a0['triplex_implied_neutral_amps'][k]),
                        actual_implied_neutral_A=float(a['triplex_implied_neutral_amps'][k]),independent_rating='UNVERIFIED_SOURCE_KRON_REDUCED'))
                if t in (0,9,48,75):
                    e.solve(.552,changed,'auto',reset_controls=True,snapshot=False);aa=e.measurement_arrays()
                    automatic.append(dict(slot=t,site=site,P_injection_kw=p,Q_injection_kvar=q,**array_summary(e,aa),
                        fixed_vs_auto_max_current_A=float(np.abs(a['line_amps']-aa['line_amps']).max()),
                        tap_state=e.control_state()['taps']))
            # Restore baseline before the next site's endpoints and next time.
            e.restore_control_state(state)
        if t%16==15:
            write(FOLDER/'PROGRESS.json',dict(completed_slots=t+1,total_slots=96,endpoint_cases=len(rows),Native_calls=0))
            print('selected12 docks fullrating',t+1,'/96',flush=True)
    table(FOLDER/'PCC_FULL_RATING96_RESULTS.csv',rows)
    table(FOLDER/'TRIPLEX_ALL_HOT_CURRENT96.csv',hots)
    table(FOLDER/'TRIPLEX_IMPLIED_NEUTRAL96.csv',neutral)
    table(FOLDER/'AUTOMATIC_FULL_RATING4_TIME.csv',automatic)
    summary=[]
    for r in mapping:
        rr=[x for x in rows if x['site']==r['location_id']]
        ph=[x for x in hots if x['site']==r['location_id'] and x['P_injection_kw']==5 and x['Q_injection_kvar']==0]
        ch=[x for x in hots if x['site']==r['location_id'] and x['P_injection_kw']==-5 and x['Q_injection_kvar']==0]
        summary.append(dict(site=r['location_id'],bus=r['candidate_bus'],commands_checked=len(rr),
            hardware_full_box_PASS=all(x['interface_envelope_PASS'] for x in rr),
            full_box_local_grid_PASS=all(x['local_original_grid_constraints_PASS'] for x in rr),
            local_grid_failed_command_cells=sum(not x['local_original_grid_constraints_PASS'] for x in rr),
            minimum_discharge5kw_hot_current_change_A=min(x['current_change_A'] for x in ph),
            maximum_discharge5kw_hot_current_change_A=max(x['current_change_A'] for x in ph),
            maximum_charge5kw_hot_current_change_A=max(x['current_change_A'] for x in ch),
            maximum_charge5kw_rho=max(x['actual_rho'] for x in ch),
            maximum_original_CT_nameplate_rho=max(x['original_CT_nameplate_rho_max'] for x in rr),
            # Passive transformer signs: ordinary secondary delivery is
            # negative P. Reverse upstream flow is negative PRIMARY P.
            reverse_service_primary_power_seen=any(x['original_CT_primary_P_kw']<0 for x in rr),
            reverse_individual_leg_power_seen=any(x['original_CT_secondary_max_P_kw']>0 for x in rr),
            field_reverse_power_protection='UNVERIFIED',production_ready=False))
    table(FOLDER/'PORT_QUALIFICATION_SUMMARY.csv',summary)
    write(FOLDER/'RECEIPT.json',dict(status='COMPLETE12_DOCK_FULL_RATING96_REAL_AC',slots=96,ports=12,
        fixed_endpoint_cases=len(rows),additional_auto_cases=len(automatic),
        actual_readback_maximum_error=max(x['actual_PQ_readback_error'] for x in rows),
        balanced_hot_KCL_maximum_A=max(x['hot_KCL_A'] for x in rows),
        original_source_identity=e.verify_source_unchanged(),original_transformer_or_line_added=0,
        entire_box_is_not_blanket_dispatch_permission=True,Native_calls=0))


if __name__=='__main__':run()
