"""Full original-network B0 policy diagnostics, independent Fresh and Actual."""
import argparse
import time
import numpy as np
from ieee8500_v42.ac import _complex
from ieee8500_v42.screening import axes_document
from .common import *
from .engine import StudyEngine,POLICIES
from .data_binding import STARTS,ENDS

ARRAY_KEYS=("line_amps","line_rho","node_voltage_pu","transformer_amps",
            "transformer_current_rho","transformer_winding_nameplate_kva_rho",
            "line_complex_A","line_complex_kVA","node_complex_V")


def summary(e,a):
    mask=e.objective_line_mask
    k=int(np.argmax(np.where(mask,a["line_rho"],-np.inf)))
    v=a["node_voltage_pu"];low=int(v.argmin());high=int(v.argmax())
    out=dict(converged=bool(a["converged"]),controls_settled=bool(a["control_actions_done"]),
        rho_max=float(a["line_rho"][k]),binding_line=e.line_axes[k]["element"],
        binding_parent_terminal=e.line_axes[k]["terminal"],binding_local_node=e.line_axes[k]["node"],
        binding_conductor=e.line_axes[k]["conductor"],binding_group=e.line_axes[k]["group"],
        Vmin=float(v[low]),Vmax=float(v[high]),Vmin_node=e.node_axes[low],Vmax_node=e.node_axes[high],
        full_both_terminal_conductor_rho_max=float(a["line_rho"].max()),
        transformer_current_rho_max=float(a["transformer_current_rho"].max()),
        transformer_nameplate_kva_rho_max=float(a["transformer_winding_nameplate_kva_rho"].max()),
        undervoltage_cells=int((v<.95).sum()),overvoltage_cells=int((v>1.05).sum()),
        voltage_violation_cells=int(((v<.95)|(v>1.05)).sum()),
        full_line_overload_cells=int((a["line_rho"]>1).sum()),
        transformer_current_overload_cells=int((a["transformer_current_rho"]>1).sum()),
        transformer_nameplate_overload_cells=int((a["transformer_winding_nameplate_kva_rho"]>1).sum()),
        source_kw=float(a["source_kw_kvar"][0]),source_kvar=float(a["source_kw_kvar"][1]),
        loss_kw=float(a["loss_kw_kvar"][0]),loss_kvar=float(a["loss_kw_kvar"][1]))
    for group in ("Primary","Triplex","Secondary"):
        groupmask=np.array([r["group"]==group for r in e.line_axes])&mask
        if groupmask.any():
            index=int(np.argmax(np.where(groupmask,a["line_rho"],-np.inf)))
            out[group+"_rho_max"]=float(a["line_rho"][index])
            out[group+"_binding_line"]=e.line_axes[index]["element"]
        else:out[group+"_rho_max"]=0.;out[group+"_binding_line"]=""
    out["hard_constraints_PASS"]=out["converged"] and out["controls_settled"] and sum(
        out[name] for name in ("voltage_violation_cells","full_line_overload_cells",
        "transformer_current_overload_cells","transformer_nameplate_overload_cells"))==0
    return out


def run_day(tag,policy,source="PLANNING", *, static=False,pv_on=True,full_audit=False):
    started=time.perf_counter()
    e=StudyEngine(tag,policy,pv=not static)
    with np.load(DATA/"derived"/f"{source}_INPUTS.npz",allow_pickle=False) as z:
        data={key:z[key] for key in z.files}
    folder=REPORT/"ac"/tag;folder.mkdir(parents=True,exist_ok=True)
    write(folder/"INITIAL_CONTROL_STATE.json",e.initial_state)
    write(folder/"AC_AXES.json",axes_document(e))
    slots=[];states=[];controls=[];arrays=[];background=[];top20=[];voltage_violations=[]
    load_power=[];load_nominal=[];pv_power=[];balances=[]
    groups={}
    for i,r in enumerate(e.line_axes):
        if e.objective_line_mask[i]:groups.setdefault(r["element"],[]).append(i)
    for t in range(96):
        e.apply_inputs(t,float(data["gross_factor"][t]),float(data["pv_factor"][t]),
                       data["PCC_P_kw"][t],data["PCC_Q_kvar"][t],static=static,pv_on=pv_on)
        a=e.settle()
        a["line_complex_A"]=_complex(e.d.PDElements.AllCurrents())[e._line_indices]
        a["line_complex_kVA"]=_complex(e.d.PDElements.AllPowers())[e._line_indices]
        a["node_complex_V"]=_complex(e.d.Circuit.AllBusVolts())
        arrays.append({key:a[key] for key in ARRAY_KEYS})
        s=summary(e,a)
        row=dict(stage=tag,source=source,policy=policy,slot=t,
                 interval_start=STARTS[t].isoformat(),interval_end=ENDS[t].isoformat(),**s)
        slots.append(row);states.append(e.control_state());controls.extend(e.state_rows(tag,t))
        for i,value in enumerate(a["node_voltage_pu"]):
            if value<.95 or value>1.05:
                voltage_violations.append(dict(stage=tag,slot=t,node=e.node_axes[i],voltage_pu=float(value),
                                               violation="under" if value<.95 else "over"))
        maxima=[(max(indices,key=lambda i:a["line_rho"][i]),line) for line,indices in groups.items()]
        for rank,(index,line) in enumerate(sorted(maxima,key=lambda x:(-a["line_rho"][x[0]],x[1]))[:20],1):
            meta=e.line_axes[index]
            primary_phase=e.primary_phase_by_customer.get(e.inventory["lines"][[r["element"] for r in e.inventory["lines"]].index(line)]["buses"][1].split(".")[0].lower(),"")
            top20.append(dict(stage=tag,source=source,slot=t,rank=rank,line=line,group=meta["group"],
                parent_terminal=meta["terminal"],local_node=meta["node"],primary_phase=primary_phase,
                I_A=float(a["line_amps"][index]),NormalAmps=meta["normal_amps"],rho=float(a["line_rho"][index])))
        if full_audit:
            actual,pv,error,balance=e.load_measurements();load_power.append(actual)
            load_nominal.append(np.column_stack((e.expected_p,e.expected_q)));pv_power.append(pv);balances.append(balance)
            assert np.max(np.abs(balance))<1e-5, "AC_POWER_BALANCE_FAILURE"
            for status,mask in (("Fixed",e.fixed),("Variable",~e.fixed)):
                for phase in "ABC":
                    select=mask&np.array([r["primary_phase"]==phase for r in e.load_records])
                    expected=np.column_stack((e.expected_p,e.expected_q))[select].sum(0)
                    measured=actual[select].sum(0)
                    background.append(dict(stage=tag,source=source,slot=t,status=status,primary_phase=phase,
                        load_count=int(select.sum()),nominal_P_kw=float(expected[0]),nominal_Q_kvar=float(expected[1]),
                        actual_P_kw=float(measured[0]),actual_Q_kvar=float(measured[1]),
                        kW_property_error=error,unmodified_original_PF=True,
                        original_model_voltage_dependence=True,temporal_factor_applied=status=="Variable",
                        daily_customer_measurement_claim=False))
        if (t+1)%24==0:
            write(REPORT/"PROGRESS.json",dict(stage=tag,completed_slots=t+1,total_slots=96,
                                             Native_calls=0,campaign_writes=0))
            print(tag,t+1,"slots; rho",s["rho_max"],"V",s["Vmin"],s["Vmax"],flush=True)
    packed={key:np.array([a[key] for a in arrays]) for key in ARRAY_KEYS}
    from .archives import save_arrays
    phasor_archive=save_arrays(folder,packed,axes_document(e))
    table(folder/"SLOTS.csv",slots);table(folder/"CONTROL_STATES_96.csv",controls)
    write(folder/"CONTROL_STATES.json",states)
    table(folder/"VOLTAGE_VIOLATIONS.csv",voltage_violations if voltage_violations else [
        dict(stage=tag,slot="",node="",voltage_pu="",violation="NONE_ALL96")])
    table(folder/"TOP20_LINES_96.csv",top20)
    if full_audit:
        lp=np.array(load_power);ln=np.array(load_nominal);pp=np.array(pv_power)
        np.savez_compressed(folder/"CUSTOMER_PV_PQ_96.npz",original_nominal=ln,actual_customer=lp,actual_PV=pp)
        table(folder/"BACKGROUND_LOAD_AUDIT.csv",background)
        table(folder/"CUSTOMER_ENERGY_AUDIT.csv",[
            dict(stage=tag,source=source,load=r["name"],bus=r["buses"][0],status=r["status"],
                 primary_phase=r["primary_phase"],original_PF=r["pf"],original_model=r["model"],
                 synthetic_nominal_kWh=float(ln[:,i,0].sum()/4),
                 actual_AC_customer_kWh=float(lp[:,i,0].sum()/4),
                 actual_AC_customer_kvarh=float(lp[:,i,1].sum()/4),
                 PV_kWh=float(pp[:,i,0].sum()/4),original_status_unchanged=True)
            for i,r in enumerate(e.load_records)])
    peak=max(slots,key=lambda r:r["rho_max"])
    totals={key:sum(r[key] for r in slots) for key in
            ("voltage_violation_cells","undervoltage_cells","overvoltage_cells","full_line_overload_cells",
             "transformer_current_overload_cells","transformer_nameplate_overload_cells")}
    result=dict(stage=tag,policy=policy,source=source,static=static,PV_connected=not static and pv_on,
        slots=96,rho_max=peak["rho_max"],peak_slot=peak["slot"],binding_line=peak["binding_line"],
        binding_local_node=peak["binding_local_node"],binding_group=peak["binding_group"],
        Primary_rho_max=max(r["Primary_rho_max"] for r in slots),
        Triplex_rho_max=max(r["Triplex_rho_max"] for r in slots),
        Secondary_rho_max=max(r["Secondary_rho_max"] for r in slots),
        Vmin=min(r["Vmin"] for r in slots),Vmax=max(r["Vmax"] for r in slots),
        Vmin_node=min(slots,key=lambda r:r["Vmin"])["Vmin_node"],
        Vmax_node=max(slots,key=lambda r:r["Vmax"])["Vmax_node"],**totals,
        hard_constraints_PASS=all(r["hard_constraints_PASS"] for r in slots),
        Triplex_binding_slots=sum(r["binding_group"]=="Triplex" for r in slots),
        Primary_binding_slots=sum(r["binding_group"]=="Primary" for r in slots),
        binding_line_changes=sum(a["binding_line"]!=b["binding_line"] for a,b in zip(slots,slots[1:])),
        original_tpx21459660c0_binding_slots=sum(r["binding_line"].lower()=="line.tpx21459660c0" for r in slots),
        full_both_terminal_conductor_rho_max=max(r["full_both_terminal_conductor_rho_max"] for r in slots),
        transformer_current_rho_max=max(r["transformer_current_rho_max"] for r in slots),
        transformer_nameplate_kva_rho_max=max(r["transformer_nameplate_kva_rho_max"] for r in slots),
        source_initial_states_independent=True,Planning_tap_replay=False,
        BG_SCALE=BG_SCALE,installed_GPU=780,B0_MESS_PQ=0,
        all_originals= e.verify_parameters(),AC_arrays=receipt(folder/"AC_96.npz"),
        runtime_seconds=time.perf_counter()-started,Native_calls=0,campaign_writes=0,phasor_archive=phasor_archive)
    if full_audit:
        result["power_balance_maximum_error_kw_kvar"]=float(np.max(np.abs(balances)))
        result["background_nominal_kWh"]=float(np.array(load_nominal)[:,:,0].sum()/4)
        result["background_actual_kWh"]=float(np.array(load_power)[:,:,0].sum()/4)
        result["PV_actual_kWh"]=float(np.array(pv_power)[:,:,0].sum()/4)
    write(folder/"RECEIPT.json",result)
    print(tag,"COMPLETE",json.dumps({k:result[k] for k in ("hard_constraints_PASS","rho_max","Vmin","Vmax")}),flush=True)
    return result


def compare(a,b,target):
    folder_a=REPORT/"ac"/a;folder_b=REPORT/"ac"/b
    with np.load(folder_a/"AC_96.npz",allow_pickle=False) as x,np.load(folder_b/"AC_96.npz",allow_pickle=False) as y:
        errors={key:float(np.max(np.abs(x[key]-y[key]))) for key in ARRAY_KEYS[:6]}
    with np.load(folder_a/'PHASOR_FORENSICS.npz') as x,np.load(folder_b/'PHASOR_FORENSICS.npz') as y:
        errors.update({'phasor_'+key:float(np.max(np.abs(x[key]-y[key]))) for key in x.files})
    assert max(errors.values())<1e-8, "INDEPENDENT_FRESH_DRIFT"
    xa=read(folder_a/"CONTROL_STATES.json");yb=read(folder_b/"CONTROL_STATES.json")
    assert xa==yb, "INDEPENDENT_CONTROL_STATES_DRIFT"
    result=dict(PASS=True,source_stage=a,fresh_stage=b,maximum_absolute_errors=errors,
                same_input_new_compile=True,independent_initial_RegControl_CapControl=True,
                Planning_state_setters_used=False,unseen_day=False)
    write(REPORT/target,result)
    return result


def run():
    assert read(REPORT/"ACTUAL_INPUT_FREEZE.json")["PASS"]
    static=run_day("STATIC_PR193_P0","P0",static=True)
    old=PR193/"joint_selection_v3/selected_ac/bg0p552_gpu1p0"
    with np.load(old/"AC_96.npz",allow_pickle=False) as x,np.load(REPORT/"ac/STATIC_PR193_P0/AC_96.npz",allow_pickle=False) as y:
        errors={key:float(np.max(np.abs(x[key]-y[key]))) for key in ARRAY_KEYS[:6]}
    assert max(errors.values())<1e-6, "STATIC_PR193_REGRESSION_FAILED"
    write(REPORT/"STATIC_PR193_REGRESSION.json",dict(PASS=True,maximum_absolute_errors=errors,
        original_PR193_results_unchanged=True,case=static,
        difference_note="new direct kW API versus prior12significant-digit PCC command; tolerance1e-6 in saved arrays"))
    candidates=[]
    for policy in read(REPORT/"PREREGISTRATION.json")["policy_priority"]:
        result=run_day("POLICY_"+policy,policy)
        candidates.append(result)
        table(REPORT/"VOLTAGE_CONTROL_POLICY_COMPARISON.csv",candidates)
    qualified=[r for r in candidates if r["hard_constraints_PASS"]]
    chosen=qualified[0]["policy"] if qualified else None
    policy=chosen or "P3"
    write(REPORT/"PLANNING_VOLTAGE_POLICY_SELECTION.json",
        dict(selected_policy=chosen,diagnostic_reference=policy,selection_from_Planning_only=True,
             Actual_policy_outcomes_used=False,rule=read(REPORT/"PREREGISTRATION.json")["policy_selection"],
             candidates=[{"policy":r["policy"],"PASS":r["hard_constraints_PASS"]} for r in candidates],
             final_operating_qualification=False))
    # A new source compile provides the full-customer audit and the independent
    # Planning Fresh. No tap state is imported from the policy diagnostic.
    plan=run_day("B0_PLANNING",policy,full_audit=True)
    fresh=run_day("B0_PLANNING_FRESH",policy)
    compare("B0_PLANNING","B0_PLANNING_FRESH","PLANNING_FRESH_VERIFICATION.json")
    actual=run_day("B0_ACTUAL",policy,source="ACTUAL",full_audit=True)
    actual_fresh=run_day("B0_ACTUAL_FRESH",policy,source="ACTUAL")
    compare("B0_ACTUAL","B0_ACTUAL_FRESH","ACTUAL_FRESH_VERIFICATION.json")
    # Attribution uses the chosen policy and the same frozen GPU/C1 input,
    # never changes BG/GPU/nameplate or positions.
    without_pv=run_day("TIME_VARIABLE_NO_PV",policy,pv_on=False)
    static_policy=run_day("STATIC_SELECTED_POLICY",policy,static=True)
    write(REPORT/"RUN_RECEIPT.json",dict(status="B0_AC_DIAGNOSTICS_COMPLETE",policies=candidates,
        selected_planning_policy=chosen,reference_policy=policy,
        static_old=static,static_new_policy=static_policy,dynamic_no_PV=without_pv,
        planning=plan,actual=actual,independent_Planning_Fresh=fresh,independent_Actual_Fresh=actual_fresh,
        AC_slots=1056,full_scale_screen_not_repeated=True,Native_calls=0,
        original_campaign_writes=0,operating_configuration_finalized=False))


if __name__=="__main__":
    run()
