"""Preregistered multi-PCC, multi-line AC response diagnostics.

These unlicensed test injections never establish an installed port rating or a
dispatch opportunity. Positive P/Q is injection (less consumption). All original
line, voltage and transformer constraints are checked at both endpoints.
"""
from __future__ import annotations

import os
os.environ.setdefault('OPENBLAS_NUM_THREADS', '1')
os.environ.setdefault('OMP_NUM_THREADS', '1')
import numpy as np
from .ac import IEEE8500AC
from .common import DATA, REPORT, read, write, table, receipt
from .geometry import read_csv
from .capacity import build_candidate, FIXED_AIDC
from .screening import demand, axes_document

SLOTS = (0, 9, 48, 75)
FOLDER = REPORT / 'joint_selection_v2' / 'sensitivity'


def freeze_policy():
    """No policy outcomes or new sensitivities are used in forming this set."""
    old = REPORT / 'diagnostics/capacity_1p0'
    axes = read(old / 'AC_AXES.json')
    a = np.load(old / 'AC_96.npz', allow_pickle=False)
    rho96 = a['line_rho']
    groups = {}
    for k, axis in enumerate(axes['lines']):
        if axes['objective_mask'][k]:
            groups.setdefault(axis['element'].lower(), []).append(k)
    ranking = sorted(groups, key=lambda name: (-float(rho96[:, groups[name]].max()), name))[:20]
    mv = read_csv(REPORT / 'MV_AIDC_CANDIDATES.csv')
    lv = read_csv(REPORT / 'LV_STA_CANDIDATES.csv')
    # Inspect every endpoint behind a top-20 Triplex plus a deterministic sample
    # of 24 other electrical endpoints. This is a diagnostic subset; no approved
    # LV candidates exist in the source evidence.
    direct = [r for r in lv if set(r['triplex_path'].split('|')) & set(ranking)]
    names = {r['candidate_bus'] for r in direct}
    others = [r for r in sorted(lv, key=lambda r:r['candidate_bus']) if r['candidate_bus'] not in names][:24]
    lv_probe = sorted(direct + others, key=lambda r:r['candidate_bus'])
    probes = [dict(probe_id=f'MV{k:04d}', bus=r['dss_bus'], mode='MV_3PH',
                   host_type='MV_ELECTRICAL_HOST', primary=r['dss_bus'], diagnostic_step=1.0,
                   engineering_ceiling_kva='', physical_port_qualified=False)
              for k,r in enumerate(mv, 1)]
    probes += [dict(probe_id=f'LV{k:04d}', bus=r['candidate_bus'], mode='LV_SPLIT_240',
                    host_type='LV_SPLIT_PHASE_DIAGNOSTIC_SUBSET', primary=r['upstream_primary_bus'],
                    diagnostic_step=0.1, engineering_ceiling_kva=r['engineering_upper_bound_kva_NOT_allowed_output'],
                    physical_port_qualified=False)
               for k,r in enumerate(lv_probe, 1)]
    policy = dict(schema='AC_SENSITIVITY_PREREGISTERED_V2', slots=list(SLOTS), development_date='2025-05-01',
        already_exposed_date=True, independent_validation_date=None, B1_B2_B3_results_used=False,
        reference_load='current V42 B0 upstream-host equivalent at historical v3 AIDC; ORIGINAL_STATIC_BACKGROUND_1',
        reference_is_candidate_final_B0=False, line_set=ranking,
        line_set_rule='20 largest maximum canonical source-parent phase rho over already-exposed diagnostic B0 96slots',
        all_MV_electrical_candidates_evaluated=len(mv), LV_inventory=len(lv), approved_LV_ports=0,
        LV_diagnostic_subset=len(lv_probe), LV_subset_rule='all top20 downstream Triplex endpoints plus first24 lexically distinct remaining endpoints',
        endpoint_steps='MV +/-1kW or kvar; LV +/-0.1kW or kvar, electrical probing ONLY',
        controls='common settled B0 taps/caps fixed for local derivatives; separate automatic finite-difference validation',
        positive_sign='P/Q injection reduces positive demand', source_pu=1.05,
        original_Vreg_and_ratings_unchanged=True, objective='original min maximum source-parent nonneutral phase current / original NormalAmps',
        controllability_final_score='undefined until actual flexible power, certified PCS/port bounds, access/ETA, and all276 directions pass',
        no_port_power_assumed_from_vehicle_450kw=True, performance_improvement_claim=False,
        inputs={n:receipt(REPORT/n) for n in ('MV_AIDC_CANDIDATES.csv','LV_STA_CANDIDATES.csv')},
        reference_archive=receipt(old/'AC_96.npz'), probes=probes)
    prior = FOLDER / 'PREREGISTRATION.json'
    if prior.exists() and read(prior) != policy:
        raise ValueError('SENSITIVITY_POLICY_DRIFT')
    write(prior, policy)
    table(FOLDER / 'PROBES.csv', probes)
    return policy


def topology_paths(e):
    """Original equipment paths, independent of voltage-response magnitude."""
    import collections
    adj = collections.defaultdict(list)
    for collection in ('lines','transformers','reactors'):
        for x in e.inventory.get(collection, []):
            if not x.get('enabled', True) or len(x['buses']) < 2:
                continue
            u,v = [s.lower().split('.')[0] for s in x['buses'][:2]]
            adj[u].append((v,x['element'].lower()));adj[v].append((u,x['element'].lower()))
    # The inventory is intentionally line/transformer/control-focused; the
    # original source series reactor is nevertheless a real connectivity edge.
    for name in e.d.Reactors.AllNames():
        e.d.Reactors.Name(name)
        if not e.d.CktElement.Enabled():continue
        buses=e.d.CktElement.BusNames()
        if len(buses)<2:continue
        u,v=[s.lower().split('.')[0] for s in buses[:2]]
        element='reactor.'+name.lower()
        adj[u].append((v,element));adj[v].append((u,element))
    parent = {'sourcebus': None}; edge = {}; todo = collections.deque(['sourcebus'])
    while todo:
        u=todo.popleft()
        for v, name in sorted(adj[u]):
            if v not in parent:
                parent[v]=u;edge[v]=name;todo.append(v)
    paths={}
    for bus in parent:
        p=[];u=bus
        while parent[u] is not None:
            p.append(edge[u]);u=parent[u]
        paths[bus]=set(p)
    return paths


def run():
    policy=freeze_policy();c=build_candidate(1.0)
    e=IEEE8500AC(output_dir=FOLDER/'dss')
    for site,bus in FIXED_AIDC.items():e.add_pcc(site,bus,'MV_3PH')
    for p in policy['probes']:e.add_pcc(p['probe_id'],p['bus'],p['mode'])
    write(FOLDER/'AC_AXES.json', axes_document(e))
    paths=topology_paths(e)
    mask=e.objective_line_mask
    target_indices={name:np.array([k for k,x in enumerate(e.line_axes)
        if mask[k] and x['element'].lower()==name],dtype=int) for name in policy['line_set']}
    results=[];line_results=[];mat=[];validations=[];base_records=[]
    previous=read(REPORT/'diagnostics/capacity_1p0/CONTROL_STATES.json')
    for slot in SLOTS:
        base_demand=demand(c,slot)
        e.restore_control_state(previous[slot])
        base=e.solve(1.,base_demand,control_mode='auto',reset_controls=False)
        a0=e.measurement_arrays()
        if not a0['converged'] or not a0['control_actions_done']:raise ValueError('BASE_NOT_SETTLED')
        base_records.append(dict(slot=slot,**base['summary']))
        critical=int(np.argmax(np.where(mask,a0['line_rho'],-np.inf)))
        critical_meta=e.line_axes[critical]
        peakaxes=[int(idx[np.argmax(a0['line_rho'][idx])]) for idx in target_indices.values()]
        for count,p in enumerate(policy['probes']):
            pid=p['probe_id'];step=p['diagnostic_step']
            response=e.local_injection_sensitivity(pid,1.,base_demand,step,step,'fixed',base)
            for component in ('P','Q'):
                d=response['derivatives'][component];endpoint=response['endpoints'][component]
                minus,plus=endpoint['minus_injection'],endpoint['plus_injection']
                if not minus['converged'] or not plus['converged']:raise ValueError('PROBE_NONCONVERGENCE')
                if any(v['control_queue_size'] or not v['control_actions_done'] for v in (minus,plus)):
                    raise ValueError('PROBE_CONTROL_QUEUE_NOT_EMPTY')
                if minus['control_state'] != base['control_state'] or plus['control_state'] != base['control_state']:
                    raise ValueError('FIXED_CONTROL_STATE_DRIFT')
                k=int(np.argmax(np.abs(np.where(mask,d['line_rho'],0))))
                record=dict(slot=slot,probe_id=pid,bus=p['bus'],host_type=p['host_type'],component=component,
                    positive_sign='INJECTION', step_kw_or_kvar=step, controls='FIXED_SHARED_SETTLED',
                    critical_line=critical_meta['element'],critical_parent_terminal=critical_meta['terminal'],critical_node=critical_meta['node'],
                    critical_base_rho=float(a0['line_rho'][critical]),
                    rho_derivative_pu_per_unit=float(d['line_rho'][critical]),
                    critical_line_amps_derivative=float(d['line_amps'][critical]),
                    maximum_abs_current_derivative=float(np.max(np.abs(d['line_amps']))),
                    maximum_abs_voltage_derivative=float(np.max(np.abs(d['node_voltage_pu']))),
                    most_sensitive_line=e.line_axes[k]['element'],most_sensitive_node=e.line_axes[k]['node'],
                    most_sensitive_rho_derivative=float(d['line_rho'][k]),
                    maximum_abs_transformer_current_rho_derivative=float(np.max(np.abs(d['transformer_current_rho']))),
                    maximum_abs_transformer_nameplate_kva_rho_derivative=float(np.max(np.abs(d['transformer_winding_nameplate_kva_rho']))),
                    minus_injection_rho_max=float(minus['line_rho'][mask].max()),plus_injection_rho_max=float(plus['line_rho'][mask].max()),
                    minus_injection_Vmin=float(minus['node_voltage_pu'].min()),plus_injection_Vmin=float(plus['node_voltage_pu'].min()),
                    minus_injection_Vmax=float(minus['node_voltage_pu'].max()),plus_injection_Vmax=float(plus['node_voltage_pu'].max()),
                    minus_injection_overload_cells=int((minus['line_rho']>1).sum()),plus_injection_overload_cells=int((plus['line_rho']>1).sum()),
                    minus_injection_voltage_violations=int(((minus['node_voltage_pu']<.95)|(minus['node_voltage_pu']>1.05)).sum()),
                    plus_injection_voltage_violations=int(((plus['node_voltage_pu']<.95)|(plus['node_voltage_pu']>1.05)).sum()),
                    minus_injection_transformer_current_rho_max=float(minus['transformer_current_rho'].max()),
                    plus_injection_transformer_current_rho_max=float(plus['transformer_current_rho'].max()),
                    minus_injection_transformer_nameplate_kva_rho_max=float(minus['transformer_winding_nameplate_kva_rho'].max()),
                    plus_injection_transformer_nameplate_kva_rho_max=float(plus['transformer_winding_nameplate_kva_rho'].max()),
                    minus_injection_transformer_current_overload_cells=int((minus['transformer_current_rho']>1).sum()),
                    plus_injection_transformer_current_overload_cells=int((plus['transformer_current_rho']>1).sum()),
                    minus_injection_transformer_nameplate_overload_cells=int((minus['transformer_winding_nameplate_kva_rho']>1).sum()),
                    plus_injection_transformer_nameplate_overload_cells=int((plus['transformer_winding_nameplate_kva_rho']>1).sum()),
                    endpoints_settled_controls_queue_empty=True,
                    engineering_ceiling_kva_NOT_permission=p['engineering_ceiling_kva'],
                    certified_available_P_kw='',certified_available_Q_kvar='',physical_port_qualified=False,
                    feasible_dispatch_weighted_controllability='',new_bottleneck_checked_all_original_axes=True,
                    production_policy_performance_predicted=False)
                results.append(record)
                for name,axis in zip(policy['line_set'],peakaxes):
                    group=target_indices[name]
                    line_results.append(dict(slot=slot,probe_id=pid,bus=p['bus'],component=component,
                        line=name,group=e.line_axes[axis]['group'],baseline_binding_node=e.line_axes[axis]['node'],
                        baseline_rho=float(a0['line_rho'][axis]),dI_A_per_unit=float(d['line_amps'][axis]),
                        dRho_pu_per_unit=float(d['line_rho'][axis]),dV_max_pu_per_unit=record['maximum_abs_voltage_derivative'],
                        original_source_to_PCC_path_contains_line=name in paths.get(p['bus'],set()),
                        maximum_rho_plus=float(plus['line_rho'][group].max()),maximum_rho_minus=float(minus['line_rho'][group].max()),
                        actual_usable_power_certified=False))
                mat.append(d['line_rho'][peakaxes])
            # Predetermined first MV and first LV at each slot get half-step,
            # independent automatic endpoints, and actual balanced-leg readback.
            if count in (0, policy['all_MV_electrical_candidates_evaluated']):
                half=e.local_injection_sensitivity(pid,1.,base_demand,step/2,step/2,'fixed',base)
                auto=e.local_injection_sensitivity(pid,1.,base_demand,step,step,'auto',base)
                for component in ('P','Q'):
                    err=float(np.max(np.abs(response['derivatives'][component]['line_amps']-half['derivatives'][component]['line_amps'])))
                    validations.append(dict(slot=slot,probe_id=pid,component=component,
                        fixed_halfstep_max_current_derivative_difference=err,
                        automatic_minus_converged=auto['endpoints'][component]['minus_injection']['converged'],
                        automatic_plus_converged=auto['endpoints'][component]['plus_injection']['converged'],
                        automatic_minus_settled=auto['endpoints'][component]['minus_injection']['control_actions_done'],
                        automatic_plus_settled=auto['endpoints'][component]['plus_injection']['control_actions_done'],
                        automatic_vs_fixed_max_current_derivative_difference=float(np.max(np.abs(
                            response['derivatives'][component]['line_amps']-auto['derivatives'][component]['line_amps']))),
                        automatic_original_initial_state_restored=True, half_step_PASS=err<.01))
            if (count+1)%60==0:
                write(FOLDER/'PROGRESS.json',dict(slot=slot,probes_completed=count+1,total_probes=len(policy['probes']),Native_calls=0))
                print('AC sensitivity slot',slot,'PCC',count+1,'/',len(policy['probes']),flush=True)
        table(FOLDER/f'PCC_SUMMARY_SLOT_{slot:02d}.csv',[x for x in results if x['slot']==slot])
        table(FOLDER/f'TOP20_RESPONSE_SLOT_{slot:02d}.csv',[x for x in line_results if x['slot']==slot])
    table(REPORT/'SENSITIVITY_RESULTS.csv',line_results)
    table(REPORT/'SENSITIVITY_PCC_SUMMARY.csv',results)
    table(FOLDER/'FINITE_DIFFERENCE_AND_AUTO_VALIDATION.csv',validations)
    write(FOLDER/'BASE_SUMMARIES.json',base_records)
    np.savez_compressed(FOLDER/'TOP20_DERIVATIVES.npz',derivative=np.array(mat),line=np.array(policy['line_set']),
        slot=np.array([x['slot'] for x in results]),probe=np.array([x['probe_id'] for x in results]),component=np.array([x['component'] for x in results]))
    write(FOLDER/'RECEIPT.json',dict(status='COMPLETE_ELECTRICAL_DIAGNOSTIC_ONLY',probes=len(policy['probes']),
        MV_probes=policy['all_MV_electrical_candidates_evaluated'],LV_subset=policy['LV_diagnostic_subset'],
        slots=SLOTS,central_difference_rows=len(results),top20_response_rows=len(line_results),
        no_physical_port_power_authorized=True, no_final_dispatch_improvement_claim=True,
        all_original_line_node_transformer_axes_measured=True, source_identity=e.verify_source_unchanged(),
        half_step_validation_PASS=all(x['half_step_PASS'] for x in validations),Native_calls=0,full_model_builds=0,
        artifacts={name:receipt(FOLDER/name) for name in ('PREREGISTRATION.json','TOP20_DERIVATIVES.npz','FINITE_DIFFERENCE_AND_AUTO_VALIDATION.csv')}))
    print('AC sensitivity complete',len(results),flush=True)


if __name__=='__main__':run()
