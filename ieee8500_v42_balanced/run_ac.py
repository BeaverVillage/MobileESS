"""Four independent official Balanced P5 AC days; no optimizer imports."""
import time
import numpy as np
from ieee8500_v42.ac import _complex
from ieee8500_v42.screening import axes_document
from ieee8500_v42_aemo.archives import save_arrays, CORE_KEYS
from ieee8500_v42_aemo.run_b0 import summary
from ieee8500_v42_aemo.data_binding import STARTS, ENDS
from .common import *
from .engine import BalancedEngine


def run_day(source, fresh=False):
    started=time.perf_counter(); tag='BALANCED_'+source+('_FRESH' if fresh else '')
    e=BalancedEngine(tag); folder=REPORT/'ac'/tag
    data=dict(np.load(DATA/'derived'/f'{source}_INPUTS.npz',allow_pickle=False))
    axes=axes_document(e); write(folder/'AC_AXES.json',axes); write(folder/'INITIAL_CONTROL_STATE.json',e.initial_state)
    slots=[]; states=[]; controls=[]; arrays=[]; customers=[]; nominal=[]; legs=[]; PV=[]; pcc=[]; balances=[]; caps=[]
    groups={}
    for i,r in enumerate(e.line_axes):
        if r['objective_included']:groups.setdefault(r['element'],[]).append(i)
    top20=[]; violation_rows=[]
    for t in range(96):
        e.apply_inputs(t,data['gross_factor'][t],data['pv_factor'][t],data['PCC_P_kw'][t],data['PCC_Q_kvar'][t])
        a=e.settle(); a['line_complex_A']=_complex(e.d.PDElements.AllCurrents())[e._line_indices]
        a['line_complex_kVA']=_complex(e.d.PDElements.AllPowers())[e._line_indices]
        a['node_complex_V']=_complex(e.d.Circuit.AllBusVolts())
        arrays.append({k:a[k] for k in (*CORE_KEYS,'line_complex_A','line_complex_kVA','node_complex_V')})
        actual,pv,error,balance=e.load_measurements()
        assert np.abs(balance).max()<1e-5, 'POWER_BALANCE_FAILED'
        expected=np.column_stack((e.expected_p,e.expected_q))
        # All original customer legs are inside Model1's characteristic interval under P5.
        # Keep numerical differences, rather than divide measured total artificially.
        leg_error=float(np.abs(e.last_legs-expected[:,None,:]/2).max())
        assert leg_error<1e-5, ('ACTUAL_BALANCED_LEG_SPLIT_FAILED',t,leg_error)
        customers.append(actual); nominal.append(expected); legs.append(e.last_legs); PV.append(pv)
        pcc.append(e.last_pcc); balances.append(balance); caps.append(e.last_capacitor_pq)
        s=summary(e,a)
        slots.append(dict(stage=tag,source=source,slot=t,interval_start=STARTS[t].isoformat(),interval_end=ENDS[t].isoformat(),
            **s,customer_nominal_P_kw=float(expected[:,0].sum()),customer_nominal_Q_kvar=float(expected[:,1].sum()),
            customer_actual_P_kw=float(actual[:,0].sum()),customer_actual_Q_kvar=float(actual[:,1].sum()),
            PV_nominal_P_kw=float(e.expected_pv.sum()),PV_actual_P_kw=float(pv[:,0].sum()),PV_actual_Q_kvar=float(pv[:,1].sum()),
            AIDC_actual_P_kw=float(e.last_pcc[:12,0].sum()),AIDC_actual_Q_kvar=float(e.last_pcc[:12,1].sum()),
            capacitor_consumption_Q_kvar=float(e.last_capacitor_pq[1]),balanced_leg_PQ_max_error=leg_error,
            customer_property_PQ_max_error=error,power_balance_max_error=float(np.abs(balance).max())))
        states.append(e.control_state()); controls.extend(e.state_rows(tag,t))
        for i,v in enumerate(a['node_voltage_pu']):
            if v<.95 or v>1.05: violation_rows.append(dict(slot=t,node=e.node_axes[i],voltage_pu=float(v)))
        ordered=sorted(groups,key=lambda n:(-float(a['line_rho'][groups[n]].max()),n))
        for rank,name in enumerate(ordered[:20],1):
            i=max(groups[name],key=lambda k:a['line_rho'][k]); r=e.line_axes[i]
            top20.append(dict(source=source,slot=t,rank=rank,line=name,group=r['group'],parent_terminal=r['terminal'],
                local_node=r['node'],conductor=r['conductor'],I_A=float(a['line_amps'][i]),NormalAmps=r['normal_amps'],rho=float(a['line_rho'][i])))
        second=float(a['line_rho'][groups[ordered[1]]].max())
        slots[-1].update(second_line=ordered[1],second_line_rho=second,next_line_gap_rho=s['rho_max']-second)
        if (t+1)%24==0: print(tag,t+1,'rho',s['rho_max'],'V',s['Vmin'],s['Vmax'],flush=True)
    packed={k:np.array([a[k] for a in arrays]) for k in arrays[0]}
    focus=save_arrays(folder,packed,axes)
    np.savez_compressed(folder/'CUSTOMER_PV_PQ_96.npz',original_nominal=np.array(nominal),actual_customer=np.array(customers),
        actual_legs=np.array(legs),actual_PV=np.array(PV),actual_PCC=np.array(pcc),capacitor_PQ=np.array(caps),balance_PQ=np.array(balances))
    table(folder/'SLOTS.csv',slots); table(folder/'TOP20_LINES_96.csv',top20)
    table(folder/'CONTROL_STATES_96.csv',controls); write(folder/'CONTROL_STATES.json',states)
    table(folder/'VOLTAGE_VIOLATIONS.csv',violation_rows or [dict(slot='',node='NONE_ALL96',voltage_pu='')])
    peak=max(slots,key=lambda r:r['rho_max'])
    receipt_doc=dict(stage=tag,source=source,master=e.master,policy='P5',slots=96,
        rho_max=peak['rho_max'],peak_slot=peak['slot'],binding_line=peak['binding_line'],binding_group=peak['binding_group'],
        binding_local_node=peak['binding_local_node'],next_line_gap_at_peak=peak['next_line_gap_rho'],
        Vmin=min(r['Vmin'] for r in slots),Vmax=max(r['Vmax'] for r in slots),
        Primary_rho_max=max(r['Primary_rho_max'] for r in slots),Triplex_rho_max=max(r['Triplex_rho_max'] for r in slots),
        Secondary_rho_max=max(r['Secondary_rho_max'] for r in slots),hard_constraints_PASS=all(r['hard_constraints_PASS'] for r in slots),
        full_both_terminal_conductor_rho_max=max(r['full_both_terminal_conductor_rho_max'] for r in slots),
        transformer_current_rho_max=max(r['transformer_current_rho_max'] for r in slots),
        transformer_nameplate_kva_rho_max=max(r['transformer_nameplate_kva_rho_max'] for r in slots),
        voltage_violation_cells=sum(r['voltage_violation_cells'] for r in slots),
        full_line_overload_cells=sum(r['full_line_overload_cells'] for r in slots),
        transformer_current_overload_cells=sum(r['transformer_current_overload_cells'] for r in slots),
        transformer_nameplate_overload_cells=sum(r['transformer_nameplate_overload_cells'] for r in slots),
        Triplex_binding_slots=sum(r['binding_group']=='Triplex' for r in slots),Primary_binding_slots=sum(r['binding_group']=='Primary' for r in slots),
        original_tpx21459660c0_binding_slots=sum(r['binding_line'].lower()=='line.tpx21459660c0' for r in slots),
        binding_line_changes=sum(a['binding_line']!=b['binding_line'] for a,b in zip(slots,slots[1:])),
        customer_leg_split_max_error=max(r['balanced_leg_PQ_max_error'] for r in slots),
        balance_max_error=float(np.abs(balances).max()),BG_SCALE=BG_SCALE,B0_MESS_PQ=0,Native_calls=0,
        source_initial_states_independent=True,Planning_tap_replay=False,parameters=e.verify_parameters(),
        runtime_seconds=time.perf_counter()-started,full_original_axis_archive=receipt(folder/'AC_96.npz'),focus=focus)
    write(folder/'RECEIPT.json',receipt_doc)
    print(tag,'COMPLETE',json.dumps(receipt_doc,ensure_ascii=False)[:750],flush=True)
    return receipt_doc


def compare_fresh(source):
    a=REPORT/'ac'/('BALANCED_'+source); b=REPORT/'ac'/('BALANCED_'+source+'_FRESH')
    errors={}
    for filename in ('AC_96.npz','CUSTOMER_PV_PQ_96.npz','PHASOR_FORENSICS.npz'):
        with np.load(a/filename) as x,np.load(b/filename) as y:
            assert x.files==y.files
            for k in x.files: errors[filename+':'+k]=float(np.abs(x[k]-y[k]).max())
    assert max(errors.values())<1e-8
    assert read(a/'CONTROL_STATES.json')==read(b/'CONTROL_STATES.json')
    return dict(source=source,PASS=True,new_DSS_context_and_compile=True,initial_controls_independent=True,
        Planning_states_replayed_to_Actual=False,all_array_absolute_errors=errors)


def run():
    result=[]
    for source in ('PLANNING','ACTUAL'):
        result.extend([run_day(source),run_day(source,True)])
    write(REPORT/'BALANCED_B0_FRESH_RECEIPT.json',dict(PASS=True,sources=[compare_fresh(s) for s in ('PLANNING','ACTUAL')],
        slots=384,Native_calls=0,independence_scope='new compile/context on same already-exposed day, not an unseen holdout'))
    write(REPORT/'RUN_RECEIPT.json',dict(cases=result,Native_calls=0,campaign_writes=0,final_freeze=False))


if __name__=='__main__':run()
