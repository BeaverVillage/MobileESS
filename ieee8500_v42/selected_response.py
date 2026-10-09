"""Finite selected-port actions and instantaneous electrical complementarity.

Known-job reduction bounds are a relaxation. Six MESS stay at their six
preserved initial stations for this diagnostic; no route/SOC/QoS policy is
claimed and no location is changed after reading these results.
"""
import os
os.environ.setdefault('OPENBLAS_NUM_THREADS', '1')
os.environ.setdefault('OMP_NUM_THREADS', '1')
import numpy as np
from .common import REPORT, read, write, table, receipt
from .geometry import read_csv
from .capacity import build_candidate
from .screening import demand
from .selected_case_v3 import engine, MAPPING, array_summary
from .lv_sensitivity import axes_for_candidate
from .lv_port_design import command_check

FOLDER = REPORT/'joint_selection_v3/selected_response'


def run():
    policy=read(REPORT/'joint_selection_v3/selection_scores/PREREGISTRATION.json')
    targets=policy['targets'];times=policy['slots']
    actions=read_csv(MAPPING.parent/'SELECTED_STA_SCORE_ACTIONS.csv')
    chosen={(int(r['slot']),r['location_id']):
            (float(r['P_design_choice_kw']),float(r['Q_design_choice_kvar'])) for r in actions}
    flex={(int(r['slot']),r['aidc_id']):float(r['known_only_reducible_P_upper_bound_kW'])
          for r in read_csv(REPORT/'FLEXIBLE_WORKLOAD_AUDIT.csv')}
    initial=sorted(policy['original_six_initial_locations'].values())
    write(FOLDER/'PREREGISTRATION.json',dict(mapping=receipt(MAPPING),
        cases='48 single-STA bounded chosen actions plus12 instantaneous group counterfactuals',
        group_cases=['known-only AIDC reduction upperbound','six STA at unchanged initial sites','combined'],
        controls='original96slot sequential automatic baseline, probes same settled fixed states',
        dates_already_exposed=True,performance_or_feasible_policy_claim=False,
        routing_SOC_QoS_global_couplings_solved=False,no_post_result_location_or_rating_change=True,Native_calls=0))
    e=engine('selected_response');c=build_candidate(1.)
    candidates={r['candidate_bus']:r for r in read_csv(REPORT/'LV_STA_CANDIDATES.csv')}
    mapping=read_csv(MAPPING)
    local={r['location_id']:axes_for_candidate(e,candidates[r['candidate_bus']])
           for r in mapping if r['role']=='STA'}
    rows=[];effects=[];groups=[]
    for t in range(max(times)+1):
        dd=demand(c,t);e.solve(.552,dd,reset_controls=False,snapshot=False)
        a0=e.measurement_arrays();state=e.control_state()
        if t not in times:continue
        indices={line:max((k for k,r in enumerate(e.line_axes)
                          if r['element'].lower()==line and e.objective_line_mask[k]),
                         key=lambda k:a0['line_rho'][k]) for line in targets}
        for r in mapping:
            if r['role']!='STA':continue
            site=r['location_id'];p,q=chosen[(t,site)];d=dict(dd);d[site]=(-p,-q)
            e.solve(.552,d,'fixed',state,snapshot=False);a=e.measurement_arrays();li=local[site]
            e.d.Circuit.SetActiveBus(r['candidate_bus'])
            vv=np.array(e.d.Bus.Voltages()).reshape(-1,2)
            vv={n:complex(*v) for n,v in zip(e.d.Bus.Nodes(),vv)}
            hardware=command_check(p,q,vv[1],vv[2])
            ok=bool(a['line_rho'][li['line']].max()<=1
                and a['transformer_current_rho'][li['tx_current']].max()<=1
                and a['transformer_winding_nameplate_kva_rho'][li['tx_kva']].max()<=1
                and a['node_voltage_pu'][li['nodes']].min()>=.95
                and a['node_voltage_pu'][li['nodes']].max()<=1.05)
            rows.append(dict(slot=t,site=site,bus=r['candidate_bus'],P_injection_kw=p,Q_injection_kvar=q,
                interface_envelope_PASS=hardware['interface_envelope_PASS'],local_original_grid_PASS=ok,
                local_voltage_min_pu=float(a['node_voltage_pu'][li['nodes']].min()),
                local_voltage_max_pu=float(a['node_voltage_pu'][li['nodes']].max()),
                local_line_rho_max=float(a['line_rho'][li['line']].max()),
                CT_current_rho_max=float(a['transformer_current_rho'][li['tx_current']].max()),
                CT_nameplate_rho_max=float(a['transformer_winding_nameplate_kva_rho'][li['tx_kva']].max()),
                **array_summary(e,a),global_feasible_policy=False))
            for line,k in indices.items():
                effects.append(dict(slot=t,site=site,bus=r['candidate_bus'],line=line,
                    P_injection_kw=p,Q_injection_kvar=q,baseline_rho=float(a0['line_rho'][k]),
                    actual_rho=float(a['line_rho'][k]),actual_change_A=float(a['line_amps'][k]-a0['line_amps'][k]),
                    actual_change_rho=float(a['line_rho'][k]-a0['line_rho'][k])))
        for label in ('AIDC_RELAXATION','SIX_INITIAL_STA','COMBINED_RELAXATION'):
            d=dict(dd)
            if label!='SIX_INITIAL_STA':
                for site in c['sites']:
                    p=flex[(t,site)];p0,q0=d[site];d[site]=(p0-p,q0-p*.3286841051788632)
                    if d[site][0]<-1e-9:raise ValueError('KNOWN_BOUND_EXCEEDS_FACILITY_LOAD')
            if label!='AIDC_RELAXATION':
                for site in initial:
                    p,q=chosen[(t,site)];d[site]=(-p,-q)
            e.solve(.552,d,'fixed',state,snapshot=False);a=e.measurement_arrays()
            if not a['converged']:raise ValueError('INSTANTANEOUS_PROBE_DIVERGED')
            for line,k in indices.items():
                groups.append(dict(slot=t,diagnostic_case=label,line=line,
                    baseline_rho=float(a0['line_rho'][k]),actual_rho=float(a['line_rho'][k]),
                    actual_change_rho=float(a['line_rho'][k]-a0['line_rho'][k]),
                    actual_change_A=float(a['line_amps'][k]-a0['line_amps'][k]),
                    baseline_global_rho=float(a0['line_rho'][e.objective_line_mask].max()),
                    **array_summary(e,a),six_vehicles_at_initial_sites=True,
                    routing_SOC_QoS_feasible=False,policy_performance_result=False))
        # Clear probe demand and restore sequential baseline before next slot.
        e.solve(.552,dd,'fixed',state,snapshot=False)
    table(FOLDER/'SELECTED_LOCAL_BOUNDED_ACTION_AC.csv',rows)
    table(FOLDER/'SELECTED_STA_TARGET_LINE_EFFECT.csv',effects)
    table(FOLDER/'INSTANTANEOUS_COMPLEMENTARITY_NOT_POLICY.csv',groups)
    write(FOLDER/'RECEIPT.json',dict(status='COMPLETE_SELECTED_FINITE_AC_DIAGNOSTICS',single_STA_actions=len(rows),
        group_cases=12,all_48_actions_local_PASS=all(r['local_original_grid_PASS'] for r in rows),
        all_48_actions_hardware_PASS=all(r['interface_envelope_PASS'] for r in rows),
        original_source_identity=e.verify_source_unchanged(),selection_changed=False,
        Native_calls=0,dispatch_or_performance_certificate=False))
    print('selected bounded actions and instantaneous complementarity complete',flush=True)


if __name__=='__main__':run()
