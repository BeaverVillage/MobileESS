"""96-slot electrical screening of the strict-geometry witness, without Native.

No background scale in this study is an observed daily load series. No candidate
may become a production scenario without installed connection/facility evidence.
"""
from __future__ import annotations
import os
os.environ.setdefault('OPENBLAS_NUM_THREADS','1')
os.environ.setdefault('OMP_NUM_THREADS','1')
import numpy as np
from .ac import IEEE8500AC
from .capacity import CAPACITY_SCALES, build_candidate
from .common import REPORT, DATA, read, write, table, receipt
from .geometry import read_csv
from .screening import demand, axes_document

BG_SCALES=(1.0,.8,.65,.552)
FOLDER=REPORT/'joint_selection_v2'/'scale_screening'
MAPPING=REPORT/'joint_selection_v2'/'expanded_orientation_v1'/'JOINT_SERVICE_MAPPING.csv'


def freeze_policy():
    mapping=read_csv(MAPPING)
    if len(mapping)!=24 or len({x['candidate_bus'] for x in mapping})!=24:
        raise ValueError('STRICT_24_LOCATION_WITNESS_REQUIRED')
    audit=read_csv(MAPPING.parent/'RELATIVE_POSITION_AUDIT.csv')
    geometry=read(MAPPING.parent/'GEOMETRY_RESULT.json')
    if geometry['geometric_feasibility'] is not True:raise ValueError('GEOMETRY_WITNESS_REQUIRED')
    policy=dict(schema='JOINT_GEOMETRY_WITNESS_SCALE_SCREEN_V1',candidate_mapping=receipt(MAPPING),
        geometry_audit=receipt(MAPPING.parent/'RELATIVE_POSITION_AUDIT.csv'),relative_pairs=len(audit),
        interpretation='electrical upstream-host equivalents; not existing installed AIDC/vehicle ports',
        new_transformers_added=0, STA_mode='MV_3PH_UNQUALIFIED_GEOMETRY_WITNESS',
        background_scales=list(BG_SCALES),background_scale_rule='original 1.0 plus predetermined .8,.65 and historical .552 counterfactual; never adjusted to meet rho target',
        background_time_series='ORIGINAL_STATIC_LOADS scaled uniformly, unchanged PF, no observed daily demand authority',
        capacity_scales=list(CAPACITY_SCALES),capacity_rule='GPU installed capacity only; same jobs, compatibility and anonymous demand, no flexible fraction changes',
        AIDC_workload_scale=1.0,PV_objects=0,PV_rule='no original active PV in Master; no invented PV',
        MESS_count=6,MESS_vehicle_design=dict(Pmax_kw=450,PCS_kva=600,Emax_kwh=1800),
        MESS_B0_power_kw=0,certified_PCC_port_limits='MISSING, cannot assume vehicle rating at any host',
        source_pu=1.05,original_Vreg_V=[126.5,125.0],automatic_controls='all original RegControl and CapControl, sequential96slots independently initialized each case',
        original_ratings_unchanged=True,voltage_band=[.95,1.05],rho_target=[.80,.85],rho_target_is_hard=False,
        eligible_final_selection_rule='physical host and installed equipment first, all276 signs, certified available flexibility/access, causal capacity, full96AC then controllability; no policy outcomes',
        physically_eligible_candidate_count=0, no_scenario_can_be_selected_from_these_unqualified_probes=True,
        development_date='2025-05-01',development_date_already_exposed=True,independent_eval_date=None,
        B1_B2_B3_used=False,Native_calls=0,full_model_builds=0)
    path=FOLDER/'PREREGISTRATION.json'
    if path.exists() and read(path)!=policy:raise ValueError('SCALE_POLICY_DRIFT')
    write(path,policy)
    return mapping,policy


def run():
    mapping,policy=freeze_policy()
    candidates=[build_candidate(s) for s in CAPACITY_SCALES]
    results=[]
    for bg in BG_SCALES:
        for c in candidates:
            tag=f'bg{str(bg).replace(".","p")}_gpu{str(c["scale"]).replace(".","p")}'
            folder=FOLDER/tag
            e=IEEE8500AC(output_dir=folder/'dss')
            for r in mapping:e.add_pcc(r['location_id'],r['candidate_bus'],'MV_3PH')
            if bg==1.0 and c['scale']==1.0:write(folder/'AC_AXES.json',axes_document(e))
            nline=len(e.line_axes);nnode=len(e.node_axes)
            maxima=np.zeros(nline);vlow=np.full(nnode,np.inf);vhigh=np.full(nnode,-np.inf)
            xfcurrent=np.zeros(len(e.transformer_axes));xfkva=np.zeros(len(e.transformer_winding_axes))
            slots=[];taps=[];caps=[];archive=[]
            for t in range(96):
                snap=e.solve(bg,demand(c,t),reset_controls=False)
                a=e.measurement_arrays()
                if not a['converged'] or not a['control_actions_done'] or a['control_queue_size']:
                    raise ValueError('AC_OR_CONTROL_SETTLING_FAILED:'+tag)
                for s,pq in demand(c,t).items():
                    measured=snap['pcc_actual'][s]
                    if max(abs(measured['p_kw']-pq[0]),abs(measured['q_kvar']-pq[1]))>1e-6:
                        raise ValueError('AIDC_PQ_READBACK_DRIFT')
                slots.append(dict(case=tag,slot=t,background_scale=bg,capacity_scale=c['scale'],**snap['summary']))
                for r in snap['regcontrols']:
                    taps.append(dict(case=tag,slot=t,name=r['name'],enabled=r['enabled'],tap_number=r['tap_number'],
                        tap_pu=r['tap_pu'],control_actions_done=True,original_Vreg_unchanged=True))
                caps.append(dict(slot=t,state=snap['control_state']['capacitors']))
                maxima=np.maximum(maxima,a['line_rho']);vlow=np.minimum(vlow,a['node_voltage_pu']);vhigh=np.maximum(vhigh,a['node_voltage_pu'])
                xfcurrent=np.maximum(xfcurrent,a['transformer_current_rho']);xfkva=np.maximum(xfkva,a['transformer_winding_nameplate_kva_rho'])
                if bg==1.0 and c['scale']==1.0:archive.append(a)
            line_rows=[dict(**axis,maximum_96slot_rho=float(maxima[k])) for k,axis in enumerate(e.line_axes)]
            node_rows=[dict(node=axis,minimum_96slot_pu=float(vlow[k]),maximum_96slot_pu=float(vhigh[k])) for k,axis in enumerate(e.node_axes)]
            table(folder/'ALL_LINE_CONDUCTOR_96_SLOT_MAX.csv',line_rows)
            table(folder/'ALL_NODE_96_SLOT_MIN_MAX.csv',node_rows)
            table(folder/'SLOT_ELECTRICAL_SUMMARY.csv',slots)
            table(folder/'REGCONTROL_TAP_VALIDATION.csv',taps)
            write(folder/'CAPACITOR_STATES.json',caps)
            np.savez_compressed(folder/'ALL_TRANSFORMER_96_SLOT_MAX.npz',current_rho=xfcurrent,nameplate_kva_rho=xfkva)
            if archive:
                keys=('line_amps','line_rho','node_voltage_pu','transformer_amps','transformer_current_rho','transformer_winding_nameplate_kva_rho')
                np.savez_compressed(folder/'AC_96.npz',**{key:np.array([a[key] for a in archive]) for key in keys})
            peak=max(slots,key=lambda s:s['rho_max'])
            result=dict(case=tag,status='UNQUALIFIED_GEOMETRY_WITNESS_ELECTRICAL_DIAGNOSTIC',
                background_scale=bg,capacity_scale=c['scale'],installed_GPU=sum(c['capacities'].values()),
                workload_scale=1.0,maximum_total_AIDC_kw=float(c['P_kw'].sum(1).max()),
                rho_max=peak['rho_max'],peak_slot=peak['slot'],binding_line=peak['binding_line'],
                Vmin=min(s['vmin_pu'] for s in slots),Vmax=max(s['vmax_pu'] for s in slots),
                transformer_current_rho_max=float(xfcurrent.max()),transformer_nameplate_kva_rho_max=float(xfkva.max()),
                voltage_violation_cells=sum(s['node_voltage_violations_095_105'] for s in slots),
                line_overload_conductor_cells=sum(s['line_conductor_overloads'] for s in slots),
                transformer_overload_conductor_cells=sum(s['transformer_conductor_overloads'] for s in slots),
                transformer_nameplate_winding_overloads=sum(s['transformer_nameplate_winding_overloads'] for s in slots),
                maximum_power_balance_residual_kw=max(abs(s['balance_residual_kw']) for s in slots),
                maximum_power_balance_residual_kvar=max(abs(s['balance_residual_kvar']) for s in slots),
                converged_slots=96,settled_slots=96,all_276_geometry_pairs_pass=True,
                physical_port_qualification=False,AIDC_facility_qualification=False,production_selected=False,
                source_identity_unchanged=e.verify_source_unchanged(),Native_calls=0)
            result['AC_electrical_constraints_pass']=all(result[k]==0 for k in ('voltage_violation_cells','line_overload_conductor_cells',
                'transformer_overload_conductor_cells','transformer_nameplate_winding_overloads'))
            results.append(result)
            write(folder/'AC_RECEIPT.json',result)
            table(FOLDER/'SCALE_SCREENING.csv',results)
            write(FOLDER/'PROGRESS.json',dict(completed_cases=len(results),total_cases=len(BG_SCALES)*len(candidates),Native_calls=0))
            print(tag,'96/96','rho',result['rho_max'],'V',result['Vmin'],result['Vmax'],flush=True)
    table(REPORT/'JOINT_SCALE_SCREENING.csv',results)
    write(FOLDER/'RECEIPT.json',dict(status='COMPLETE_DIAGNOSTIC_NOT_FINAL_SELECTION',cases=len(results),AC_slots=len(results)*96,
        all_original_axes_validated=True,physically_eligible_final_candidates=0,selected_scenario=None,
        no_B1_B2_B3_outcomes_used=True,Native_calls=0,preregistration=receipt(FOLDER/'PREREGISTRATION.json')))


if __name__=='__main__':run()
