"""New B0 reference/causal realization and independent Forecast/Actual Fresh.

Only immutable request descriptors, forecast/raw exogenous sources and frozen
power authorities are inputs. No old schedule, solution, physical NPZ, model
point, voltage response or policy result is read. B0 retains grid-blind FCFS,
capacity-admitted CC4 and zero MESS; the Original Fresh body is unchanged.
"""
from contextlib import ExitStack
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import csv
import importlib
import inspect
import json
import sys
import zipfile

import numpy as np
import pandas as pd

from v42_b3_joint.contracts import canonical, digest, require, require_sha
from .integration import record, scenario_scope, validate_scenario

VERSION = "V42_B0_NEW_SOURCE_PLANNING_ACTUAL_DSTATCOM_V1"


def _read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def _write(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("x",encoding="utf8",newline="\n") as stream:
        stream.write(canonical(value)+"\n")


def _resolve(receipt,folder=None,name=None):
    from v42_capacity.common import resolve
    try:
        path=Path(resolve(receipt))
    except ValueError:
        require(folder is not None and name is not None,"B0_EXACT_RAW_SOURCE_UNAVAILABLE")
        path=Path(folder)/name
    actual=record(path)
    require(actual["sha256"]==receipt["sha256"] and actual["bytes"]==receipt["bytes"],
            "B0_NEW_RAW_SOURCE_SHA_OR_BYTES_DRIFT")
    return path


def _c1(power):
    model=_resolve(power["C1"]);implementation=_resolve(power["C1_implementation"])
    sys.path.insert(0,str(implementation.parents[2]))
    module=importlib.import_module("dayahead.v28r2.c1_affine")
    require(record(module.__file__)["sha256"]==record(implementation)["sha256"],
            "B0_NEW_ORIGINAL_C1_IMPLEMENTATION_REQUIRED")
    return module,module.load_c1(model),[record(implementation),record(model)]


def build_planning(day,input_folder,output):
    """Original grid-blind B0 arithmetic; this function never reads Actual files."""
    from v42_capacity.reference import build_reference
    from v42_capacity.queue import allocate,conservation
    from v42_modelable.power import known_occupancy
    folder,output=Path(input_folder).resolve(),Path(output).resolve()
    names=("PLANNING_INPUT_BUNDLE.json","SOURCE_PROVENANCE.json","POWER_AUTHORITY.json")
    sources=[record(folder/name) for name in names]
    p,provenance,power=[_read(folder/name) for name in names]
    require(p["day"]==provenance["day"]==day and p["slots"]==96
            and p.get("future_actual_arrival_IDs_present") is False and p.get("input_gate_PASS") is True,
            "B0_NEW_CAUSAL_PLANNING_DESCRIPTOR_REQUIRED")
    require(len(p["capacities"])==12 and sum(p["capacities"].values())==780,
            "B0_NEW_ORIGINAL_12_SITE_780_GPU_REQUIRED")
    forecast_path=_resolve(provenance["daily_sources"]["aemo_forecast.json"])
    weather_path=_resolve(provenance["daily_sources"]["gfs_d1_weather.parquet"])
    forecast=_read(forecast_path)
    require(forecast==p["forecast_inputs"]["AEMO"] and len(forecast["timestamps_96"])==96,
            "B0_NEW_FORECAST_SOURCE_BINDING_DRIFT")
    issue=pd.Timestamp(p["issue_time"])
    require(issue.tzinfo is not None and issue.date()<pd.Timestamp(day).date(),"B0_NEW_D1_ISSUE_REQUIRED")
    for key in ("demand_issue","pv_issue","cutoff_fixed_aest"):
        require(pd.Timestamp(forecast[key])<=issue,"B0_NEW_FUTURE_FORECAST_VINTAGE")
    refs,audit=build_reference(p["known_population"],p["capacities"],p["rack_compatibility"],issue_time=p["issue_time"])
    require(audit["full_reference_ready"],"B0_NEW_REFERENCE_SOURCE_BLOCKED")
    sites=sorted(p["capacities"]);caps=np.array([p["capacities"][s] for s in sites])
    known=known_occupancy(refs,sites)
    cc4=p["forecast_inputs"]["current_CC4"]
    require(cc4["target_day"]==day and cc4["future_job_ids"]==[],"B0_NEW_ORIGINAL_CC4_DAY_BOUND_REQUIRED")
    anonymous,incoming,outgoing=allocate(known,cc4["nominal_unknown_GPU_96"],caps)
    gpu=known+anonymous
    cons=conservation(sum(cc4["Q50_GPUh"]),anonymous,outgoing[-1],cc4["full_tail_nominal_GPUh"])
    weather=pd.read_parquet(weather_path)
    require(len(weather)==96 and np.isfinite(weather[["t_wb_c","rh_pct"]].to_numpy()).all(),
            "B0_NEW_FORECAST_WEATHER_96_REQUIRED")
    if "issue_utc" in weather:
        require(not (pd.to_datetime(weather.issue_utc,utc=True)>issue).any(),"B0_NEW_FUTURE_FORECAST_WEATHER")
    c1,params,c1sources=_c1(power)
    idle,swing=power["current_IT_idle_kW_per_installed_GPU"],power["current_IT_swing_kW_per_active_GPU"]
    it=idle*caps+swing*gpu
    slopes=np.empty((96,12));intercepts=slopes.copy();coefficients=[]
    for t,w in enumerate(weather.itertuples(index=False)):
        for j,site in enumerate(sites):
            coeff=c1.endpoint_secant(site,t,idle*caps[j],(idle+swing)*caps[j],float(w.t_wb_c),float(w.rh_pct),params)
            slopes[t,j],intercepts[t,j]=coeff.slope,coeff.intercept_kw
            coefficients.append(dict(asdict(coeff),aidc_id=site,slot=t))
    pcc=slopes*it+intercepts;q=pcc*np.tan(np.arccos(.95))
    arrays=dict(sites=np.array(sites),capacities=caps,known_gpu=known,cc4_served_gpu=anonymous,
                GPU=gpu,IT_kw=it,PCC_P_kw=pcc,PCC_Q_kvar=q)
    require(np.isfinite(pcc).all() and np.isfinite(q).all() and (gpu<=caps+1e-9).all(),
            "B0_NEW_ORIGINAL_PLANNING_PHYSICAL_CAPACITY_FAILURE")
    output.mkdir(parents=True,exist_ok=True)
    np.savez_compressed(output/"PLANNING_PHYSICAL.npz",**arrays)
    _write(output/"REFERENCE.json",dict(rows=refs,audit=audit))
    with (output/"C1_PLANNING_COEFFICIENTS.csv").open("x",encoding="utf-8-sig",newline="") as stream:
        writer=csv.DictWriter(stream,list(coefficients[0]));writer.writeheader();writer.writerows(coefficients)
    sources += [record(forecast_path),record(weather_path),*c1sources]
    receipt=dict(schema=VERSION,day=day,arm="B0",phase="NEW_NONFLEX_PLANNING_GENERATED",
        PASS=True,reference_generated=True,CC4_conservation=cons,grid_reads_by_schedule=0,
        Actual_arrays_or_service_truth_reads=0,old_solution_schedule_or_modelpoint_reads=0,
        AIDC_flex_optimization_calls=0,MESS_PQ=0,Native_optimizer_calls=0,
        sources=sources,physical=record(output/"PLANNING_PHYSICAL.npz"),reference=record(output/"REFERENCE.json"),
        C1_coefficients=record(output/"C1_PLANNING_COEFFICIENTS.csv"))
    _write(output/"B0_NEW_PLANNING_GENERATION.json",receipt)
    return dict(day=day,planning=p,provenance=provenance,power=power,forecast=forecast,
                arrays=arrays,refs=refs,sources=sources,receipt=receipt)


def _truth(population,archive):
    """Source-row private completion extraction, performed only after Freeze."""
    import pyarrow.parquet as pq
    wanted={};members={}
    for r in population:
        key=(r["source_member"],int(r["source_row"]));uid=r["job_uid"]
        require(key not in wanted or wanted[key]==uid,"B0_NEW_ACTUAL_SOURCE_ROW_CONFLICT")
        wanted[key]=uid;members.setdefault(key[0],set()).add(key[1])
    path=_resolve(archive);truth={}
    columns=["id","submit_time","start_time","end_time"]
    with zipfile.ZipFile(path) as z:
        for member,indices in sorted(members.items()):
            require(any(f"/year=2025/month={m}/" in member for m in (4,5)),"B0_NEW_RAW_MONTH_AUTHORITY_REQUIRED")
            with z.open(member) as stream:
                offset=0
                for batch in pq.ParquetFile(stream).iter_batches(columns=columns,batch_size=32768,use_threads=False):
                    frame=batch.to_pandas();frame["source_row"]=np.arange(offset,offset+len(frame));offset+=len(frame)
                    for r in frame[frame.source_row.isin(indices)].to_dict("records"):
                        uid=str(r["id"]);key=(member,int(r["source_row"]))
                        require(wanted[key]==uid and uid not in truth,"B0_NEW_EXACT_REALIZED_UID_SOURCE_JOIN")
                        start,end,submit=r["start_time"],r["end_time"],r["submit_time"]
                        require(pd.notna(start) and pd.notna(end) and end>=start>=submit,
                                "B0_NEW_REALIZED_SERVICE_MISSING_NO_IMPUTATION")
                        truth[uid]=dict(job_uid=uid,start_time=start.isoformat(),end_time=end.isoformat(),
                            realized_seconds=(end-start).total_seconds(),source_member=member,source_row=key[1],
                            source_SHA=archive["sha256"],private_future_duration_hidden_from_controller=True)
    require(set(truth)==set(wanted.values()),"B0_NEW_PRIVATE_SOURCE_REALIZATION_POPULATION_INCOMPLETE")
    return truth,record(path)


def build_actual(plan,input_folder,output,planning_freeze):
    from v42_capacity.actual import Request,Environment,replay
    folder,output=Path(input_folder).resolve(),Path(output).resolve()
    freeze=_read(planning_freeze)
    require(freeze["schema"]==VERSION and freeze["Planning_frozen"] is True
            and freeze["day"]==plan["day"] and record(freeze["physical"]["path"])==freeze["physical"],
            "B0_NEW_SOURCE_PLANNING_FREEZE_BEFORE_ACTUAL_REQUIRED")
    actual_path=folder/"ACTUAL_INPUT_BUNDLE.json";actual=_read(actual_path)
    p=plan["planning"];require(actual["day"]==p["day"] and actual["capacities"]==p["capacities"],
                               "B0_NEW_ACTUAL_DESCRIPTOR_DAY_CAPACITY_DRIFT")
    population=p["known_population"]+actual["post_issue_arrivals"]
    truth,archive_receipt=_truth(population,plan["provenance"]["archive"])
    issue=datetime.fromisoformat(p["issue_time"]);mapping={r["job_uid"]:r for r in plan["refs"]}
    requests,running,durations,completions=[],[],{},{}
    def seconds(value): return (datetime.fromisoformat(value)-issue).total_seconds()
    for j in population:
        uid=j["job_uid"];t=truth[uid]
        request=Request(uid,seconds(j["submit_time"]),j["GPU_gang"],tuple(j["compatible_sites"]),
                        j["Q50_total_seconds"],j["source_site"])
        durations[uid]=t["realized_seconds"]
        if j["state_at_D1_cutoff"]=="RUNNING":
            start,end=seconds(t["start_time"]),seconds(t["end_time"])
            require(start<=0<end,"B0_NEW_OBSERVED_RUNNING_SOURCE_TRUTH_DRIFT")
            running.append((request,mapping[uid]["reference_site"],start));completions[uid]=end
        else: requests.append(request)
    gpu,queue_rows,causal=replay(p["capacities"],requests,Environment(durations,completions),running=running)
    weather_path=_resolve(plan["provenance"]["daily_sources"]["noaa_actual_weather.parquet"],folder,"DERIVED_NOAA_ACTUAL.parquet")
    weather=pd.read_parquet(weather_path)
    require(len(weather)==96 and np.isfinite(weather[["t_wb_c","rh_pct"]].to_numpy()).all(),"B0_NEW_ACTUAL_WEATHER_96_REQUIRED")
    c1,params,c1sources=_c1(plan["power"]);sites=sorted(p["capacities"])
    caps=np.array([p["capacities"][s] for s in sites]);power=plan["power"]
    it=power["current_IT_idle_kW_per_installed_GPU"]*caps+power["current_IT_swing_kW_per_active_GPU"]*gpu
    pcc=np.array([c1.exact_c1_pcc_kw(it[t],float(w.t_wb_c),float(w.rh_pct),params) for t,w in enumerate(weather.itertuples(index=False))])
    arrays=dict(sites=np.array(sites),GPU=gpu,IT_kw=it,PCC_P_kw=pcc,PCC_Q_kvar=pcc*np.tan(np.arccos(.95)))
    output.mkdir(parents=True,exist_ok=True);np.savez_compressed(output/"ACTUAL_PHYSICAL.npz",**arrays)
    _write(output/"PRIVATE_REALIZED_SOURCE.json",dict(rows=list(truth.values()),archive=archive_receipt,
        extraction_after_Planning_freeze=record(planning_freeze),controller_receives_future_duration=False))
    _write(output/"ACTUAL_QUEUE_LEDGER.json",queue_rows)
    sources=[record(actual_path),archive_receipt,record(weather_path),*c1sources]
    receipt=dict(schema=VERSION,day=p["day"],arm="B0",phase="NEW_CAUSAL_NONFLEX_ACTUAL_GENERATED",PASS=True,
        causal_policy=causal,Planning_freeze=record(planning_freeze),sources=sources,
        physical=record(output/"ACTUAL_PHYSICAL.npz"),old_Actual_physical_or_result_reads=0,
        Actual_CC4_physical_GPU=0,Actual_PQ_repair=0,Actual_global_reoptimization=0,
        Native_optimizer_calls=0,MESS_PQ=0,IT_recomputed_from_actual_occupancy=True,
        DayAhead_power_arrays_copied=False,Planning_tap_Q_or_controller_state_copied=False)
    _write(output/"B0_NEW_ACTUAL_GENERATION.json",receipt)
    return arrays,sources,receipt


def fresh_environment(plan,arrays,input_folder,output,*,namespace,progress=None):
    """New physical inputs through exact Original 96-slot Fresh OpenDSS body."""
    from .b0_replay import _bindings
    authority,background,isolated_compile,native_zero,backend,mapping,FrozenTrajectory,CODE=_bindings()
    require(namespace in ("DAYAHEAD","ACTUAL"),"B0_NEW_EXPLICIT_ENVIRONMENT_REQUIRED")
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=False)
    if namespace=="DAYAHEAD":
        exo=plan["forecast"];stamps=exo["timestamps_96"];demand,pv=exo["demand_mw_96"],exo["pv_mw_96"]
        exo_receipt=plan["sources"][3]
    else:
        raw=_resolve(plan["provenance"]["daily_sources"]["aemo_actual.parquet"],input_folder,"DERIVED_AEMO_ACTUAL.parquet")
        exo=pd.read_parquet(raw);stamps=[pd.Timestamp(t).tz_convert("Etc/GMT-10").isoformat() for t in exo.ts_fixed_aest_end]
        demand,pv=exo.demand_mw.tolist(),exo.rooftop_pv_mw.tolist();exo_receipt=record(raw)
        require(pd.DatetimeIndex(stamps).tz_convert("UTC").equals(pd.DatetimeIndex(plan["forecast"]["timestamps_96"]).tz_convert("UTC")),
                "B0_NEW_FORECAST_ACTUAL_TIMESTAMP_AXIS_DRIFT")
    bg=background(stamps,demand,pv);m=authority.source()
    engine,adapter,initial=authority.compile_verified()
    try:
        branches,topology=m["oriented_branches"](engine)
        nodes=tuple(sorted(n.lower() for n in engine.Circuit.AllNodeNames() if n.rsplit(".",1)[-1] in ("1","2","3")))
        native=m["NativeAllocation"].from_adapter(adapter)
    finally: engine.Basic.ClearAll()
    binding=SimpleNamespace(factories=[SimpleNamespace(data=SimpleNamespace(branches=branches))])
    context=SimpleNamespace(legacy_context=(None,None,bg,binding,None,None))
    zeros=np.zeros((96,4));locations=np.asarray([("STA01","STA12","STA08","STA06") for _ in range(96)],dtype=str)
    trajectory=FrozenTrajectory(plan["day"],namespace,"B0",arrays["PCC_P_kw"],arrays["PCC_Q_kvar"],zeros,zeros,
        ("MESS01","MESS02","MESS03","MESS04"),locations,digest(dict(day=plan["day"],namespace=namespace,
            p=arrays["PCC_P_kw"].tolist(),q=arrays["PCC_Q_kvar"].tolist(),exo=exo_receipt)))
    trajectory.validate();original_compile=authority.compile_verified;original_voltage=backend._voltage_vector
    logs,applied,compilations=[],[],[];body=backend.run_fresh_opendss.__code__
    def compile_current(_assets):
        engine,ad,inventory=isolated_compile(original_compile,output,compilations)
        native.validate_native_engine(engine);require(inventory==initial,"B0_NEW_FRESH_SOURCE_INITIAL_STATE_DRIFT")
        return engine,ad
    def apply_current(engine,ad,_context,tr,slot):
        totals,ledger,allocation=native.apply(engine,bg,slot)
        for r in ad["pv_generators"]:
            key=(str(r["bus"]).lower(),"ABC"[int(r["phase"])-1])
            mapping._set_generator(engine,r["generator_name"],bg.pv_generation_kw_96[slot].get(key,0),0)
        for j in range(12): mapping._set_load(engine,f"IDC_IDC{j+1:02d}",tr.pcc_p_kw[slot,j],tr.pcc_q_kvar[slot,j])
        for name in engine.Generators.AllNames():
            if name.lower().startswith("mess_dis_"): mapping._set_generator(engine,name,0,0)
        for name in engine.Loads.AllNames():
            if name.lower().startswith("mess_chg_"): mapping._set_load(engine,name,0,0)
        authority.assert_inventory(m["inventory"](engine))
        observed=[]
        for j in range(12):
            engine.Loads.Name(f"IDC_IDC{j+1:02d}");observed.append([float(engine.Loads.kW()),float(engine.Loads.kvar())])
        require(np.array_equal(np.asarray(observed),np.column_stack((tr.pcc_p_kw[slot],tr.pcc_q_kvar[slot]))),
                "B0_NEW_ENGINE_APPLIED_AIDC_POWER_DRIFT")
        applied.append(dict(slot=slot,PCC_P_kw=tr.pcc_p_kw[slot].tolist(),PCC_Q_kvar=tr.pcc_q_kvar[slot].tolist(),
            native_load_PQ=totals,allocation=allocation,MESS_PQ=0))
    def controls(engine,_voltage,slot): authority.assert_inventory(m["inventory"](engine))
    def measure(engine,axis):
        result=original_voltage(engine,axis);authority.assert_inventory(m["inventory"](engine))
        require(engine.Solution.ControlActionsDone(),"B0_NEW_ORIGINAL_CONTROL_ACTIONS_INCOMPLETE")
        taps,caps=m["native_state"](engine)
        logs.append(dict(slot=len(logs),taps=taps,caps=caps,ControlActionsDone=True,
            ControlIterations=int(engine.Solution.ControlIterations()),Iterations=int(engine.Solution.Iterations()),
            MaxControlIterations=int(engine.Solution.MaxControlIterations()),MaxIterations=int(engine.Solution.MaxIterations())))
        return result
    sources=[record(inspect.getfile(f)) for f in (backend.run_fresh_opendss,authority.compile_verified,background,m["branch_measurement"])]
    with ExitStack() as stack:
        for key,function in (("compile_clean_engine",compile_current),("apply_trajectory_slot",apply_current),
            ("apply_frozen_native_state",controls),("_branch_measurement",m["branch_measurement"]),("_voltage_vector",measure)):
            stack.enter_context(patch.object(backend,key,function))
        denied=stack.enter_context(native_zero())
        result=backend.run_fresh_opendss(repo=CODE,context=context,voltage=dict(node_names=nodes),trajectory=trajectory,
                                       output=output/"fresh",progress=progress)
        require(not denied,"B0_NEW_PHYSICAL_OPTIMIZER_FORBIDDEN")
    require(backend.run_fresh_opendss.__code__ is body,"B0_NEW_ORIGINAL_96_SLOT_BODY_MUTATED")
    require(all(record(r["path"])==r for r in sources),"B0_NEW_ORIGINAL_PHYSICAL_SOURCE_MUTATED")
    line=np.array(result.branch_kinds)=="line";tx=~line
    strict=dict(voltage_violation_cells=int(np.sum((result.voltage_pu<.95)|(result.voltage_pu>1.05))),
        line_current_violation_cells=int(np.sum(result.phase_current_loading_pu[:,line]>1)),
        transformer_current_violation_cells=int(np.sum(result.phase_current_loading_pu[:,tx]>1)),
        transformer_kVA_violation_cells=int(np.sum(result.transformer_total_kva_loading_pu[:,tx]>1)))
    passed=bool(result.convergence.all()) and len(logs)==96 and not any(strict.values())
    _write(output/"RAW_CONTROL_LOG.json",dict(day=plan["day"],namespace=namespace,source_initial_inventory=initial,slots=logs))
    _write(output/"RAW_PHYSICAL_INPUT_LOG.json",dict(day=plan["day"],namespace=namespace,slots=applied,
        exogenous=exo_receipt,alpha_BG=1.15,PV_scaled_by_alpha_BG=False,Planning_control_state_transfer=False))
    receipt=dict(schema=VERSION,arm="B0",day=plan["day"],namespace=namespace,PASS=passed,
        voltage_min_pu=float(result.voltage_pu.min()),voltage_max_pu=float(result.voltage_pu.max()),
        logical_Fresh_slots=96,converged_slots=int(result.convergence.sum()),literal_physical_violations=strict,
        maximum_original_line_loading_percent=float(result.phase_current_loading_pu[:,line].max()*100),
        original_line_phase_count=int(line.sum()),original_branch_phase_count=len(line),
        Original_96_slot_backend_body_unchanged=True,Native_optimizer_calls=0,MESS_PQ=0,
        source_initial_inventory=initial,original_source_receipts=sources,exogenous=exo_receipt,
        raw_AC_receipt=record(output/"fresh/OPENDSS_PHASE_ARRAYS.npz"),topology=topology)
    _write(output/"B0_NEW_FRESH_RESULT.json",receipt)
    return receipt


def run_day(day,input_folder,output,*,scenario,source_SHA,progress=None,development=False,design_receipt=None):
    """New date computation; caller's frozen design/development authority is explicit."""
    from .authority import physical_permit
    require_sha(source_SHA);scenario,_,_=validate_scenario(scenario)
    require(day in tuple(f"2025-05-{d:02d}" for d in range(1,32)),"B0_NEW_MAY_DAY_REQUIRED")
    output=Path(output).resolve();require(not output.exists(),"B0_NEW_CAMPAIGN_OUTPUT_OVERWRITE_FORBIDDEN")
    output.mkdir(parents=True)
    plan=build_planning(day,input_folder,output/"PLANNING")
    options=dict(development=development,design_receipt=design_receipt)
    with physical_permit("B0",day,source_SHA,scenario,namespace="DAYAHEAD",**options):
        with scenario_scope(scenario,output/"PLANNING/DSTATCOM",source_SHA=source_SHA,arm="B0",day=day,namespace="DAYAHEAD") as planning_audit:
            planning_ac=fresh_environment(plan,plan["arrays"],input_folder,output/"PLANNING/AC",namespace="DAYAHEAD",progress=progress)
    planning_pass=planning_ac["PASS"] and planning_audit.result["hardware_and_controller_PASS"]
    freeze=dict(schema=VERSION,day=day,arm="B0",Planning_frozen=True,Planning_physical_PASS=planning_pass,
        physical=plan["receipt"]["physical"],reference=plan["receipt"]["reference"],
        Planning_AC=record(output/"PLANNING/AC/B0_NEW_FRESH_RESULT.json"),Planning_hardware=planning_audit.receipt,
        Source_SHA=source_SHA,scenario_SHA=scenario["scenario_SHA"],MESS_PQ=0,
        Planning_Q_Tap_or_controller_state_is_not_Actual_input=True,old_results_reused=False)
    _write(output/"PLANNING_FREEZE.json",freeze)
    arrays,actual_sources,actual_generation=build_actual(plan,input_folder,output/"ACTUAL",output/"PLANNING_FREEZE.json")
    with physical_permit("B0",day,source_SHA,scenario,namespace="ACTUAL",**options):
        with scenario_scope(scenario,output/"ACTUAL/DSTATCOM",source_SHA=source_SHA,arm="B0",day=day,namespace="ACTUAL") as actual_audit:
            actual_ac=fresh_environment(plan,arrays,input_folder,output/"ACTUAL/AC",namespace="ACTUAL",progress=progress)
    actual_pass=actual_ac["PASS"] and actual_audit.result["hardware_and_controller_PASS"]
    require(all(record(r["path"])==r for r in plan["sources"]+actual_sources),"B0_NEW_INPUT_SOURCE_MUTATED")
    from .b3_control import _independence
    independence=_independence(planning_audit,actual_audit,source_SHA,scenario["scenario_SHA"],arm="B0",day=day)
    independence.update(same_scenario_SHA=scenario["scenario_SHA"],
        separate_Source_Initial_State_compiles=independence["Planning_and_Actual_engine_objects_distinct"],
        Planning_namespace=planning_audit.result["namespace"],Actual_namespace=actual_audit.result["namespace"],
        Actual_controller_uses_only_previous_Actual_state=True)
    _write(output/"PLANNING_ACTUAL_CONTROL_INDEPENDENCE_AUDIT.json",independence)
    require(independence["PASS"],"B0_NEW_MEASURED_PLANNING_ACTUAL_CONTROL_INDEPENDENCE_FAILED")
    result=dict(schema=VERSION,day=day,arm="B0",PASS=bool(planning_pass and actual_pass),
        status="PASS" if planning_pass and actual_pass else "PHYSICAL_FAILED",Source_SHA=source_SHA,
        scenario_SHA=scenario["scenario_SHA"],new_Planning_and_Actual=True,previous_policy_result_reads=0,
        Planning=planning_ac,Actual=actual_ac,Planning_physical_PASS=bool(planning_pass),Actual_physical_PASS=bool(actual_pass),
        Planning_hardware=planning_audit.receipt,Actual_hardware=actual_audit.receipt,
        planning_freeze=record(output/"PLANNING_FREEZE.json"),control_independence=record(output/"PLANNING_ACTUAL_CONTROL_INDEPENDENCE_AUDIT.json"),
        Native_Runtime=0,Native_optimizer_calls=0,DSTATCOM_MILP_variables=0,MESS_PQ=0,Actual_plan_repair_calls=0)
    _write(output/"RESULT.json",result)
    return result
