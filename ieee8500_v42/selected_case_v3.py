"""Actual 96-slot B0 of score-chosen modeled MV/LV ports; no policy solver."""
from __future__ import annotations
import os
os.environ.setdefault('OPENBLAS_NUM_THREADS','1')
os.environ.setdefault('OMP_NUM_THREADS','1')
import numpy as np
from .ac import IEEE8500AC
from .capacity import CAPACITY_SCALES,build_candidate
from .common import REPORT,read,write,table,receipt
from .geometry import read_csv
from .screening import demand,axes_document

MAPPING=REPORT/'joint_selection_v3/score_selection/JOINT_SERVICE_MAPPING.csv'
FOLDER=REPORT/'joint_selection_v3/selected_ac'
BG=(1.,.8,.65,.552)


def engine(tag):
    e=IEEE8500AC(output_dir=FOLDER/tag/'dss')
    for r in read_csv(MAPPING):
        e.add_pcc(r['location_id'],r['candidate_bus'],'MV_3PH' if r['role']=='AIDC' else 'LV_SPLIT_240')
    return e


def array_summary(e,a):
    mask=e.objective_line_mask
    k=int(np.argmax(np.where(mask,a['line_rho'],-np.inf)))
    v=a['node_voltage_pu'];iv=int(v.argmin());jv=int(v.argmax())
    return dict(converged=bool(a['converged']),control_actions_done=bool(a['control_actions_done']),
        control_queue_size=int(a['control_queue_size']),rho_max=float(a['line_rho'][k]),
        binding_line=e.line_axes[k]['element'],binding_node=e.line_axes[k]['node'],
        all_terminal_line_rho_max=float(a['line_rho'].max()),Vmin=float(v[iv]),Vmax=float(v[jv]),
        vmin_node=e.node_axes[iv],vmax_node=e.node_axes[jv],
        transformer_current_rho_max=float(a['transformer_current_rho'].max()),
        transformer_nameplate_kva_rho_max=float(a['transformer_winding_nameplate_kva_rho'].max()),
        voltage_violation_cells=int(((v<.95)|(v>1.05)).sum()),
        line_overload_conductor_cells=int((a['line_rho']>1).sum()),
        transformer_overload_conductor_cells=int((a['transformer_current_rho']>1).sum()),
        transformer_nameplate_overload_winding_cells=int((a['transformer_winding_nameplate_kva_rho']>1).sum()),
        source_kw=float(a['source_kw_kvar'][0]),source_kvar=float(a['source_kw_kvar'][1]),
        loss_kw=float(a['loss_kw_kvar'][0]),loss_kvar=float(a['loss_kw_kvar'][1]))


def run():
    policy=dict(schema='SELECTED_STUDY_AC_V3_BEFORE_EXECUTION',mapping=receipt(MAPPING),
        scale_policy='same predetermined v2 BG and GPU scales, zero MESS B0, independent source initialization percase',
        background_scales=list(BG),capacity_scales=list(CAPACITY_SCALES),workload_scale=1.0,PV_objects=0,
        background_profile='uniform original static snapshot scale; not observed IEEE8500 day',
        source_pu=1.05,original_Vregs_unchanged=True,original_1190_transformers_and_3703_lines_unchanged=True,
        automatic_original_RegControls=12,automatic_original_CapControls=9,all_original_node_voltage_band=[.95,1.05],
        prior_policy_outcomes_used=False,selection_mapping_never_changed_from_AC_results=True,
        selected_research_reference=dict(background_scale=.552,capacity_scale=1.0,
            reason='historical-reference counterfactual and smallest original facility capacity; not a rho-target or policy-performance winner'),
        reference_is_operationally_accepted=False,production_ready=False,Native_calls=0)
    write(FOLDER/'PREREGISTRATION.json',policy)
    candidates=[build_candidate(s) for s in CAPACITY_SCALES];results=[]
    for bg in BG:
        for c in candidates:
            tag=f'bg{str(bg).replace(".","p")}_gpu{str(c["scale"]).replace(".","p")}'
            e=engine(tag);folder=FOLDER/tag
            maxima=np.zeros(len(e.line_axes));vlow=np.full(len(e.node_axes),np.inf);vhigh=np.full(len(e.node_axes),-np.inf)
            txcurrent=np.zeros(len(e.transformer_axes));txkva=np.zeros(len(e.transformer_winding_axes))
            states=[];slots=[];taprows=[];arr=[];readback_error=0.
            for t in range(96):
                dd=demand(c,t);e.solve(bg,dd,reset_controls=False,snapshot=False);a=e.measurement_arrays()
                summary=array_summary(e,a)
                if not summary['converged'] or not summary['control_actions_done'] or summary['control_queue_size']:
                    raise ValueError('B0_AC_NOT_SETTLED')
                # Every slot's actual twelve AIDC terminal P/Q, not input labels.
                for site,pq in dd.items():
                    e.d.Circuit.SetActiveElement(e.pccs[site]['element']);p=np.array(e.d.CktElement.Powers()).reshape(-1,2).sum(0)
                    readback_error=max(readback_error,float(np.max(np.abs(p-np.array(pq)))))
                state=e.control_state();states.append(state)
                for name in e.d.RegControls.AllNames():
                    e.d.RegControls.Name(name)
                    taprows.append(dict(case=tag,slot=t,name=name,tap_number=e.d.RegControls.TapNumber(),
                        original_Vreg=e.d.RegControls.ForwardVreg(),control_actions_done=True,enabled=True))
                slots.append(dict(case=tag,slot=t,background_scale=bg,capacity_scale=c['scale'],**summary))
                maxima=np.maximum(maxima,a['line_rho']);vlow=np.minimum(vlow,a['node_voltage_pu']);vhigh=np.maximum(vhigh,a['node_voltage_pu'])
                txcurrent=np.maximum(txcurrent,a['transformer_current_rho']);txkva=np.maximum(txkva,a['transformer_winding_nameplate_kva_rho'])
                if bg==.552 and c['scale']==1.:arr.append(a)
            if readback_error>1e-6:raise ValueError('AIDC_ACTUAL_PQ_MISMATCH')
            table(folder/'SLOT_ELECTRICAL_SUMMARY.csv',slots);table(folder/'REGCONTROL_TAPS.csv',taprows)
            write(folder/'CONTROL_STATES.json',states)
            table(folder/'ALL_LINE_96_SLOT_MAX.csv',[dict(**r,maximum_96slot_rho=float(maxima[k])) for k,r in enumerate(e.line_axes)])
            table(folder/'ALL_NODE_96_SLOT_MIN_MAX.csv',[dict(node=r,minimum_96slot_pu=float(vlow[k]),maximum_96slot_pu=float(vhigh[k])) for k,r in enumerate(e.node_axes)])
            np.savez_compressed(folder/'ALL_TRANSFORMER_96_SLOT_MAX.npz',current_rho=txcurrent,nameplate_kva_rho=txkva)
            if arr:
                write(folder/'AC_AXES.json',axes_document(e))
                keys=('line_amps','line_rho','node_voltage_pu','transformer_amps','transformer_current_rho','transformer_winding_nameplate_kva_rho')
                np.savez_compressed(folder/'AC_96.npz',**{key:np.array([a[key] for a in arr]) for key in keys})
            peak=max(slots,key=lambda s:s['rho_max'])
            totals={k:sum(s[k] for s in slots) for k in ('voltage_violation_cells','line_overload_conductor_cells','transformer_overload_conductor_cells','transformer_nameplate_overload_winding_cells')}
            result=dict(case=tag,background_scale=bg,capacity_scale=c['scale'],installed_GPU=sum(c['capacities'].values()),
                workload_scale=1.0,maximum_total_AIDC_kw=float(c['P_kw'].sum(1).max()),
                rho_max=peak['rho_max'],peak_slot=peak['slot'],binding_line=peak['binding_line'],
                Vmin=min(s['Vmin'] for s in slots),Vmax=max(s['Vmax'] for s in slots),
                transformer_current_rho_max=float(txcurrent.max()),transformer_nameplate_kva_rho_max=float(txkva.max()),
                **totals,AC_constraints_pass=all(v==0 for v in totals.values()),
                original_source_identity=e.verify_source_unchanged(),AIDC_PQ_readback_error=readback_error,
                geometry='all276 modeled source/proxy directions PASS; actual field geographyUNVERIFIED',
                simulation_design_authorized=True,production_ready=False,Native_calls=0)
            results.append(result);write(folder/'AC_RECEIPT.json',result)
            table(FOLDER/'SCALE_SCREENING.csv',results)
            print(tag,'96slots','rho',result['rho_max'],'V',result['Vmin'],result['Vmax'],flush=True)
    write(FOLDER/'RECEIPT.json',dict(status='COMPLETE12_STUDY_SCALE_CASES',cases=len(results),slots=len(results)*96,
        mapping=receipt(MAPPING),no_AC_based_mapping_change=True,Native_calls=0))


if __name__=='__main__':run()
