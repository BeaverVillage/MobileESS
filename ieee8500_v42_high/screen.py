"""Planning-only bounded BG/capacity scan; selection before Actual outcomes."""
import time
import numpy as np
from datetime import datetime, timedelta, timezone
from ieee8500_v42.screening import axes_document
from ieee8500_v42_aemo.run_b0 import summary
from .common import *
from .engine import HighEngine

CORE=('line_amps','line_rho','node_voltage_pu','transformer_amps','transformer_current_rho','transformer_winding_nameplate_kva_rho',
      'transformer_winding_complex_kva','source_kw_kvar','loss_kw_kvar','converged','control_actions_done','control_queue_size',
      'triplex_implied_neutral_complex_A','triplex_implied_neutral_amps')


def run_day(tag,bg,capacity='C0',source='PLANNING',day='2025-05-01',layout='L0',schedule=None,full=True,input_path=None,mapping_path=None,report_dir=None):
    report=Path(report_dir) if report_dir else REPORT
    if 'ieee8500_v42_joint_pcc_reselection' in report.parts:
        if day!='2025-05-01':raise ValueError('JOINT_RESEARCH_MAY01_ONLY')
        if (report/'ac'/tag/'RECEIPT.json').exists():raise RuntimeError('COMPLETED_AC_MUST_BE_REUSED')
    begin=time.perf_counter();e=HighEngine(tag,bg,layout,mapping_path,report);path=Path(input_path) if input_path else inputs(capacity,source,day)
    data=dict(np.load(path,allow_pickle=False));folder=report/'ac'/tag
    axes=axes_document(e);write(folder/'AC_AXES.json',axes);write(folder/'INITIAL_CONTROL_STATE.json',e.initial_state)
    control=[];states=[];rows96=[];arrays=[];legs=[];customers=[];PV=[];PCC=[];balances=[];capPQ=[];ports=[];phasors=[]
    stamps=[datetime.fromisoformat(day).replace(tzinfo=timezone(timedelta(hours=10)))+timedelta(minutes=15*t) for t in range(96)]
    for t in range(96):
        e.apply_inputs(t,data,schedule[t] if schedule else None)
        a=e.settle();s=summary(e,a);actual,pv,error,balance=e.load_measurements()
        assert np.abs(balance).max()<1e-4, ('POWER_BALANCE_FAILURE',tag,t,balance)
        rows96.append(dict(stage=tag,day=day,source=source,capacity=capacity,bg=bg,layout=layout,slot=t,interval_start=stamps[t].isoformat(),
            **s,nominal_customer_P_kw=float(e.expected_p.sum()),nominal_customer_Q_kvar=float(e.expected_q.sum()),
            actual_customer_P_kw=float(actual[:,0].sum()),actual_customer_Q_kvar=float(actual[:,1].sum()),
            nominal_PV_kw=float(e.expected_pv.sum()),actual_PV_kw=float(pv[:,0].sum()),actual_PV_Q_kvar=float(pv[:,1].sum()),
            AIDC_P_kw=float(e.last_pcc[:12,0].sum()),AIDC_Q_kvar=float(e.last_pcc[:12,1].sum()),
            MESS_consumption_P_kw=float(e.last_pcc[12:,0].sum()),MESS_consumption_Q_kvar=float(e.last_pcc[12:,1].sum()),
            power_balance_error=float(np.abs(balance).max()),customer_properties_error=error))
        arrays.append({k:a[k] for k in CORE});states.append(e.control_state());control.extend(e.state_rows(tag,t))
        if full:
            from ieee8500_v42.ac import _complex
            phasors.append(dict(line_complex_A=_complex(e.d.PDElements.AllCurrents())[e._line_indices],
                line_complex_kVA=_complex(e.d.PDElements.AllPowers())[e._line_indices],node_complex_V=_complex(e.d.Circuit.AllBusVolts())))
        customers.append(actual);legs.append(e.last_legs);PV.append(pv);PCC.append(e.last_pcc);balances.append(balance);capPQ.append(e.last_capacitor_pq)
        ports.extend(dict(slot=t,**r) for r in e.port_measurements())
    packed={k:np.array([a[k] for a in arrays]) for k in CORE}
    if full:
        from ieee8500_v42_aemo.archives import save_arrays
        packed.update({k:np.array([a[k] for a in phasors]) for k in phasors[0]})
        forensic=save_arrays(folder,packed,axes)
        np.savez_compressed(folder/'AC_96.npz',**{k:packed[k] for k in CORE})
    else:
        np.savez_compressed(folder/'AC_96.npz',**packed);forensic=None
    np.savez_compressed(folder/'CUSTOMER_PV_PCC_96.npz',customer_PQ=np.array(customers),customer_legs=np.array(legs),PV_PQ=np.array(PV),PCC_PQ=np.array(PCC),
        balance_PQ=np.array(balances),capacitor_PQ=np.array(capPQ))
    table(folder/'SLOTS.csv',rows96);table(folder/'CONTROL_STATES_96.csv',control);write(folder/'CONTROL_STATES.json',states)
    write(folder/'PORT_96.json',ports)
    e.d.Vsources.Name('source')
    write(folder/'PARAMETER_SNAPSHOT.json',dict(source_pu=e.d.Vsources.PU(),inventory=e._inventory(),
        source_sha256=e._hash_source(),P5_overlay_sha256=sha(report/'overlays/P5.dss')))
    peak=max(rows96,key=lambda r:r['rho_max'])
    result=dict(tag=tag,day=day,source=source,capacity=capacity,bg=bg,layout=layout,slots=96,
        rho_max=peak['rho_max'],peak_slot=peak['slot'],binding_line=peak['binding_line'],binding_group=peak['binding_group'],binding_node=peak['binding_local_node'],
        Primary_rho_max=max(r['Primary_rho_max'] for r in rows96),Triplex_rho_max=max(r['Triplex_rho_max'] for r in rows96),
        Vmin=min(r['Vmin'] for r in rows96),Vmax=max(r['Vmax'] for r in rows96),
        full_both_ends_rho_max=max(r['full_both_terminal_conductor_rho_max'] for r in rows96),
        CT_current_max=max(r['transformer_current_rho_max'] for r in rows96),CT_nameplate_max=max(r['transformer_nameplate_kva_rho_max'] for r in rows96),
        voltage_violation_cells=sum(r['voltage_violation_cells'] for r in rows96),
        line_overload_cells=sum(r['full_line_overload_cells'] for r in rows96),
        CT_current_overload_cells=sum(r['transformer_current_overload_cells'] for r in rows96),
        CT_nameplate_overload_cells=sum(r['transformer_nameplate_overload_cells'] for r in rows96),
        grid_hard_PASS=all(r['hard_constraints_PASS'] for r in rows96),
        Primary_binding_slots=sum(r['binding_group']=='Primary' for r in rows96),Triplex_binding_slots=sum(r['binding_group']=='Triplex' for r in rows96),
        AIDC_P_max=max(r['AIDC_P_kw'] for r in rows96),AIDC_input=receipt(path),all96_power_balance_error=float(np.abs(balances).max()),
        source_parameter_audit=e.verify_parameters(),original_DSS_changed=0,Native_calls=0,campaign_mutations=0,
        field_qualified=False,mapping=receipt(e.mapping_path),phasor_archive=forensic,runtime_seconds=time.perf_counter()-begin)
    write(folder/'RECEIPT.json',result)
    print(tag,'PASS',result['grid_hard_PASS'],'rho',result['rho_max'],'V',result['Vmin'],result['Vmax'],flush=True)
    return result


def fresh_compare(first,fresh,report_dir=None):
    report=Path(report_dir) if report_dir else REPORT
    errors={}
    files=['AC_96.npz','CUSTOMER_PV_PCC_96.npz']
    if (report/'ac'/first/'PHASOR_FORENSICS.npz').exists():files.append('PHASOR_FORENSICS.npz')
    for file in files:
        with np.load(report/'ac'/first/file) as a,np.load(report/'ac'/fresh/file) as b:
            assert a.files==b.files
            for key in a.files:
                if a[key].dtype.kind=='b':errors[file+':'+key]=float(not np.array_equal(a[key],b[key]))
                else:errors[file+':'+key]=float(np.abs(a[key]-b[key]).max())
    assert max(errors.values())<1e-8
    assert read(report/'ac'/first/'CONTROL_STATES.json')==read(report/'ac'/fresh/'CONTROL_STATES.json')
    result=dict(PASS=True,first=first,fresh=fresh,new_compile_and_DSS_context=True,input_reused=True,array_errors=errors,unseen_day=False)
    write(report/'ac'/fresh/'FRESH_COMPARISON.json',result)
    return result


def run():
    policy=preregister();results=[]
    for cap in CAPACITY_CANDIDATES:
        assert inputs(cap).exists(),str(inputs(cap))
        for bg in BG_CANDIDATES:
            tag=f'E1_{cap}_BG{bg:.3f}'
            results.append(run_day(tag,bg,cap))
            table(REPORT/'BG_AIDC_SCALE_SCREENING.csv',results)
    acceptable=[r for r in results if r['grid_hard_PASS'] and .75<=r['rho_max']<=.85 and r['capacity']=='C0']
    # C1/C2 are audited idle-capacity engineering counterfactuals. Actual hardware
    # nameplates are absent; they cannot displace a source-backed C0 target.
    selected=min(acceptable,key=lambda r:(abs(r['rho_max']-.8),r['bg'])) if acceptable else None
    write(REPORT/'PLANNING_SCENARIO_SELECTION.json',dict(selected=selected,rule=policy['candidate_priority'],
        Actual_outcomes_used=False,selection_before_MESS_effects=True,C1_C2_hardware_NOT_PROMOTED=True,
        target_PASS=selected is not None,final_Production_freeze=False))
    if selected:
        with np.load(BALANCED_REPORT/'ac/BALANCED_PLANNING/AC_96.npz') as old,np.load(REPORT/'ac/E1_C0_BG0.552/AC_96.npz') as current:
            diff={k:float(np.abs(old[k]-current[k]).max()) for k in old.files}
        assert max(diff.values())<1e-6,'PR197_BASELINE_REGRESSION_FAILURE'
        write(REPORT/'PR197_REGRESSION.json',dict(PASS=True,maximum_errors=diff))
    return results


if __name__=='__main__':run()
