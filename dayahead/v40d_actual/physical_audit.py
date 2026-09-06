"""Independent C1 arithmetic and readback of applied Actual engine setpoints."""
from contextlib import contextmanager
from pathlib import Path
import numpy as np
from dayahead.paper_analysis.storage import read, reference, write_json, write_npz
from .contracts import ReplayError


def c1_recalculation(repo, power, weather):
    from dayahead.v28r2.c1_affine import FROZEN_NLR_EQUIVALENT_SCALE
    from dayahead.v28.thermal import GFS_NORMALIZATION_FACTOR
    from dayahead.v39a.contracts import POWER_TOLERANCE_KW
    from dayahead.v36.contracts import PF_TAN
    path=Path(repo)/"dayahead/artifacts/v24t_thermal_aware_aidc/V24T_C1_QUASISTATIC_MODEL.json"
    x=read(path); c=x["coefficients"]; other=x["other_model_coefficients"]
    independent=np.empty((96,12))
    scale=FROZEN_NLR_EQUIVALENT_SCALE
    for t in range(96):
        wb=float(weather.iloc[t].t_wb_c); rh=float(weather.iloc[t].rh_pct)
        excess=max(wb-x["t_ref_c"],0.)
        for s in range(12):
            it=float(power["IT"][t,s]); mw=it*scale/1000
            thermal=(c["intercept"]+c["it_mw"]*mw+c["it_mw_squared"]*mw**2+c["wetbulb_c"]*wb
                +c["wetbulb_excess_c"]*excess+c["it_mw_x_wetbulb_excess_c"]*mw*excess+c["rh_pct"]*rh)
            other_latent=other["intercept"]+other["it_mw"]*mw
            independent[t,s]=it+GFS_NORMALIZATION_FACTOR/scale*(np.logaddexp(0.,thermal)+np.logaddexp(0.,other_latent))
    error=float(np.max(np.abs(independent-power["PCC_P"])))
    q_error=float(np.max(np.abs(independent*PF_TAN-power["PCC_Q"])))
    if max(error,q_error)>float(POWER_TOLERANCE_KW):
        raise ReplayError("ACTUAL_OBSERVED_WEATHER_C1_RECALCULATION_FAIL")
    return {"status":"PASS", "independent_C1_PCC_P_max_error_kW":error,"independent_C1_PCC_Q_max_error_kvar":q_error,
        "tolerance_kW":str(POWER_TOLERANCE_KW),"C1_source":reference(path),
        "thermal_input":"OBSERVED_WEATHER","C1_applications_in_physical_chain":1,
        "DayAhead_Fresh_PCC_reuse_count":0,"PRE_DAY_COMPLETE_job_PCC_contribution_kWh":0,
        "PRE_DAY_COMPLETE_power_accounting":"No admitted gang or GPU contribution; site idle and C1 base loads are not attributed to excluded jobs"}


@contextmanager
def engine_binding_observer(power, mess, output):
    from dayahead.v28r2 import opendss_backend as backend
    original=backend.apply_trajectory_slot
    aidc=np.zeros((96,12,2)); mess_rows=[]; slots=[]; engine_services=[]
    def observed(odd,adapter,context,trajectory,slot):
        original(odd,adapter,context,trajectory,slot)
        old_active=str(odd.CktElement.Name())
        try:
            for i in range(12):
                odd.Loads.Name(f"IDC_IDC{i+1:02d}")
                aidc[slot,i]=[odd.Loads.kW(),odd.Loads.kvar()]
            services={}
            for i,m in enumerate(mess["ids"]):
                location=str(mess["locations"][slot,i]).upper()
                p=float(mess["p"][slot,i]); q=float(mess["q"][slot,i])
                if location.startswith("TRANSIT_"):
                    if p!=0 or q!=0:raise ReplayError("ACTUAL_MESS_TRANSIT_POWER")
                    continue
                v=services.setdefault(location,[0.,0.]);v[0]+=p;v[1]+=q
            observed_services=set()
            for raw in odd.Generators.AllNames():
                name=str(raw)
                if not name.lower().startswith("mess_dis_"):continue
                service=name[len("MESS_DIS_"):].upper()
                observed_services.add(service)
                p,q=services.get(service,[0.,0.])
                odd.Generators.Name(name)
                gp,gq=float(odd.Generators.kW()),float(odd.Generators.kvar())
                odd.Loads.Name("MESS_CHG_"+service)
                lp,lq=float(odd.Loads.kW()),float(odd.Loads.kvar())
                error=max(abs(gp-max(p,0)),abs(gq-q),abs(lp-max(-p,0)),abs(lq))
                if error>2e-12:raise ReplayError("ACTUAL_MESS_ENGINE_BINDING_FAIL")
                mess_rows.append({"slot":slot,"service":service,"generator_P":gp,"generator_Q":gq,"load_P":lp,"load_Q":lq,"error":error})
            if not observed_services or not set(services).issubset(observed_services):
                raise ReplayError("ACTUAL_MESS_SERVICE_MAPPING_MISSING")
            engine_services.append(observed_services)
            if not np.array_equal(aidc[slot,:,0],power["PCC_P"][slot]) or not np.array_equal(aidc[slot,:,1],power["PCC_Q"][slot]):
                raise ReplayError("ACTUAL_AIDC_ENGINE_SETPOINT_BINDING_FAIL")
            slots.append(slot)
        finally:
            odd.Circuit.SetActiveElement(old_active)
    backend.apply_trajectory_slot=observed
    result={}
    try:
        yield result
        if slots!=list(range(96)) or any(s!=engine_services[0] for s in engine_services) or len(mess_rows)!=96*len(engine_services[0]):
            raise ReplayError("ACTUAL_ENGINE_READBACK_COVERAGE")
        write_npz(Path(output)/"ACTUAL_APPLIED_AIDC_PCC.npz",AIDC_P=aidc[:,:,0],AIDC_Q=aidc[:,:,1])
        write_json(Path(output)/"ACTUAL_APPLIED_MESS_PQ.json",mess_rows)
        result.update(status="PASS",AIDC_engine_setpoint_max_error=0,MESS_engine_setpoint_max_error=max(r["error"] for r in mess_rows),
            applied_slots=96,Actual_PCC_and_realized_MESS_readback=True,extra_Solve_calls=0,extra_electrical_commands=0)
        result["MESS_service_labels_from_frozen_engine"]=sorted(engine_services[0])
        write_json(Path(output)/"ACTUAL_ENGINE_BINDING_READBACK.json",result)
    finally:
        backend.apply_trajectory_slot=original


def rho_recalculation(result, output):
    path=Path(output)/"OPENDSS_PHASE_ARRAYS.npz"
    with np.load(path,allow_pickle=False) as z:
        mask=z["branch_kinds"]=="line"
        raw=z["phase_current_loading_pu"][:,mask]
        rho=float(raw.max())
        t,b=np.unravel_index(int(raw.argmax()),raw.shape)
        branch=str(z["branch_names"][mask][b]); phase=str(z["branch_phases"][mask][b])
    summary=read(Path(output)/"OPENDSS_SUMMARY.json")
    if summary["namespace"]!="ACTUAL" or rho!=summary["rho_max_AC"] or rho!=result.summary["rho_max_AC"]:
        raise ReplayError("ACTUAL_RHO_RAW_ARRAY_BINDING_FAIL")
    return {"status":"PASS", "Actual_AC_rho":rho,"source":reference(path),
        "summary_source":reference(Path(output)/"OPENDSS_SUMMARY.json"),"argmax_slot":int(t),"branch":branch,"phase":phase,
        "recalculation":"max Actual OpenDSS phase_current_loading_pu over line phases and 96 slots",
        "new_Actual_OpenDSS_solve_count":96}
