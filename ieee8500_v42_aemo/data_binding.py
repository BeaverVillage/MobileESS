"""Causal forecast input freeze followed by separate private Actual realization."""
import csv
from datetime import datetime
from functools import lru_cache
import importlib.util
import io
import sys
import zipfile
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from .common import *

FOLDER=ROOT/"docs/v42_may_b0_zero_margin_holdout"
INPUT=FOLDER/"INPUT/BUNDLE/DAY_20250501"
TZ="Etc/GMT-10"
START=pd.Timestamp(DAY,tz=TZ)
STARTS=pd.date_range(START,periods=96,freq="15min")
ENDS=STARTS+pd.Timedelta(minutes=15)


def axis_equal(actual,expected):
    axis=pd.DatetimeIndex(actual)
    assert not axis.has_duplicates and axis.tz is not None
    assert axis.tz_convert("UTC").equals(expected.tz_convert("UTC")), "EXACT_TIME_AXIS_MISMATCH"


def archive_rows(path):
    from v42_holdout.realization import archive_rows as original
    yield from original(path)


def copy_source(record,name):
    from .source_audit import copy_verified
    return copy_verified(record,DATA/"sources"/name)


@lru_cache(None)
def normalization():
    path=DATA/"authority/grid_background_v16_2.py"
    authority=read(REPORT/"SOURCE_AUTHORITY.json")["ieee123_background_source"]["copied"]
    assert sha(path)==authority["sha256"]
    spec=importlib.util.spec_from_file_location("ieee8500_exact_v42_normalization",path)
    module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module
    spec.loader.exec_module(module)
    assert abs(module.P95_REFERENCE_MW/module.ANNUAL_MAX_REFERENCE_MW-module.ALPHA_GRID)<1e-15
    return module


def temporal_factors(demand_mw,pv_mw,pv_capacity_fraction):
    """The exact V42 scalar gross/solar algebra, with IEEE8500 native weights.

    IEEE123 bus clusters and empirical Q variation cannot establish individual
    IEEE8500 customer traces. Uniform original P/Q shares preserve each PF.
    Original Fixed loads are separately kept constant; this status split is
    disclosed and never asserted to be actual regional customer consumption.
    """
    module=normalization()
    demand=np.asarray(demand_mw,float);pv=np.asarray(pv_mw,float)
    assert demand.shape==pv.shape==(96,) and np.isfinite(demand).all() and np.isfinite(pv).all()
    assert (demand>=0).all() and (pv>=0).all()
    solar=module.ALPHA_GRID*pv/module.PV_REFERENCE_MAX_MW
    gross=module.ALPHA_GRID*demand/module.P95_REFERENCE_MW+pv_capacity_fraction*solar
    assert (solar<=1).all(), "RAW_PV_EXCEEDS_INSTALLED_NAMEPLATE_NO_CLIPPING"
    return gross,solar


def forecast_raw_audit(forecast):
    selected={}
    sources=[]
    for kind in ("demand","pv"):
        path=Path(forecast["cross_month_archive_authority"][kind+"_path"])
        record=dict(path=str(path),sha256=forecast[kind+"_source_sha256"])
        path=resolve(record);sources.append(receipt(path))
        selection=[]
        for row in archive_rows(path):
            if row.get("REGIONID")!="VIC1":continue
            identity=forecast[kind+"_identity"]
            if any(str(row.get(key,""))!=str(value) for key,value in identity.items()):continue
            stamp=row.get("DATETIME" if kind=="demand" else "INTERVAL_DATETIME")
            if stamp is None:stamp=row.get("SETTLEMENTDATE")
            if stamp is None:continue
            ending=pd.Timestamp(stamp,tz=TZ)
            if START<ending<=START+pd.Timedelta(days=1):
                selection.append(row)
        assert len(selection)==48, ("FORECAST_RAW_HALF_HOURLY_COUNT",kind,len(selection))
        stamp_key="DATETIME" if kind=="demand" else "INTERVAL_DATETIME"
        if stamp_key not in selection[0]:stamp_key="SETTLEMENTDATE"
        selection.sort(key=lambda r:r[stamp_key])
        column="DEMAND" if kind=="demand" else "POWERMEAN"
        if column not in selection[0] and kind=="demand":column="TOTALDEMAND"
        values=np.array([float(r[column]) for r in selection])
        target=np.asarray(forecast["demand_mw_96" if kind=="demand" else "pv_mw_96"])
        assert np.max(np.abs(np.repeat(values,2)-target))<1e-10
        raw_energy=float(values.sum()*.5);target_energy=float(target.sum()*.25)
        assert abs(raw_energy-target_energy)<1e-9
        table(DATA/"sources"/f"FORECAST_SELECTED_{kind.upper()}_30MIN.csv",selection)
        selected[kind]=dict(raw=receipt(path),interval_minutes=30,unit="MW",
                            raw_selected_rows=48,derived_rows=96,
                            issue=forecast[kind+"_issue"],cutoff=forecast["cutoff_fixed_aest"],
                            interval_ending=True,conversion="piecewise constant repeat2",
                            original_energy_MWh=raw_energy,derived_energy_MWh=target_energy,
                            exact_source_value_error=0.)
    return selected


def planning():
    from .engine import StudyEngine
    from v42_capacity.reference import build_reference
    from v42_modelable.power import known_occupancy
    from v42_capacity.queue import allocate,conservation
    from ieee8500_v42.capacity import load_c1_module
    bundle=read(ROOT/"ieee8500_v42/data/v42_inputs/PLANNING_INPUT_BUNDLE.json")
    assert digest(bundle)==digest(read(INPUT/"PLANNING_INPUT_BUNDLE.json"))
    provenance=read(INPUT/"SOURCE_PROVENANCE.json")
    forecast_record=provenance["daily_sources"]["aemo_forecast.json"]
    weather_record=provenance["daily_sources"]["gfs_d1_weather.parquet"]
    copies=[copy_source(forecast_record,"AEMO_FORECAST.json"),
            copy_source(weather_record,"GFS_D1_WEATHER.parquet")]
    forecast=read(DATA/"sources/AEMO_FORECAST.json")
    axis_equal(forecast["timestamps_96"],ENDS)
    issue=pd.Timestamp(bundle["issue_time"])
    assert issue==pd.Timestamp(forecast["cutoff_fixed_aest"])
    assert all(pd.Timestamp(forecast[k+"_issue"])<=issue for k in ("demand","pv"))
    raw=forecast_raw_audit(forecast)
    weather=pd.read_parquet(DATA/"sources/GFS_D1_WEATHER.parquet")
    axis_equal(weather.ts_fixed_aest,STARTS)
    assert np.isfinite(weather[["t_wb_c","rh_pct","lead_hours"]]).all().all()
    initialization=pd.DatetimeIndex(weather.ts_fixed_aest)-pd.to_timedelta(weather.lead_hours,unit="h")
    assert initialization.nunique()==1 and initialization[0]<=issue
    # Initialization <= cutoff is necessary; publication latency is not in
    # the frozen cache. Do not fabricate a real-time availability certificate.
    reference,audit=build_reference(bundle["known_population"],bundle["capacities"],
                                    bundle["rack_compatibility"],issue_time=bundle["issue_time"])
    assert audit["full_reference_ready"]
    sites=sorted(bundle["capacities"]);cap=np.array([bundle["capacities"][s] for s in sites])
    known=known_occupancy(reference,sites)
    cc4=bundle["forecast_inputs"]["current_CC4"]
    assert not cc4["future_job_ids"] and not bundle["future_actual_arrival_IDs_present"]
    anon,incoming,outgoing=allocate(known,cc4["nominal_unknown_GPU_96"],cap)
    conserved=conservation(sum(cc4["Q50_GPUh"]),anon,outgoing[-1],cc4["full_tail_nominal_GPUh"])
    assert (known+anon<=cap+1e-9).all()
    power=read(ROOT/"ieee8500_v42/data/v42_inputs/POWER_AUTHORITY.json")
    c1=load_c1_module();params=c1.load_c1(ROOT/"ieee8500_v42/data/v42_inputs/C1_MODEL.json")
    it=power["current_IT_idle_kW_per_installed_GPU"]*cap+power["current_IT_swing_kW_per_active_GPU"]*(known+anon)
    P=np.zeros((96,12));coefficients=[]
    for t,w in enumerate(weather.itertuples(index=False)):
        for i,site in enumerate(sites):
            coefficient=c1.endpoint_secant(site,t,power["current_IT_idle_kW_per_installed_GPU"]*cap[i],
                (power["current_IT_idle_kW_per_installed_GPU"]+power["current_IT_swing_kW_per_active_GPU"])*cap[i],
                float(w.t_wb_c),float(w.rh_pct),params)
            P[t,i]=coefficient.slope*it[t,i]+coefficient.intercept_kw
            coefficients.append(dict(slot=t,site=site,slope=coefficient.slope,intercept_kw=coefficient.intercept_kw))
    Q=P*np.tan(np.arccos(power["PF_AIDC"]))
    with np.load(ROOT/"ieee8500_v42/data/v42_inputs/PLANNING_PHYSICAL.npz",allow_pickle=False) as baseline:
        errors={key:float(np.max(np.abs(value-baseline[key]))) for key,value in
                [("known_gpu",known),("cc4_served_gpu",anon),("total_gpu",known+anon),
                 ("IT_kw",it),("PCC_P_kw",P),("PCC_Q_kvar",Q)]}
    assert max(errors.values())<1e-10, "PR193_B0_SCHEDULE_POWER_DRIFT"
    e=StudyEngine("input_registry",pv=True)
    fraction=float(e.pv_capacity.sum()/e.base_p.sum())
    gross,solar=temporal_factors(forecast["demand_mw_96"],forecast["pv_mw_96"],fraction)
    table(REPORT/"FIXED_VARIABLE_LOAD_AUDIT.csv",[
        dict(load=r["name"],bus=r["buses"][0],primary_phase=r["primary_phase"],local_hot=r["node_order"][0],
             status=r["status"],enabled=r["enabled"],original_P_kw=r["kw"],original_Q_kvar=r["kvar"],
             PF=r["pf"],model=r["model"],kv=r["kv"],phases=r["phases"],
             Vminpu=r["vminpu_load_characteristic"],Vmaxpu=r["vmaxpu_load_characteristic"],
             study_static_BG=BG_SCALE,daily_shape_applied=r["status"]=="variable",
             source_status_unchanged=True,connection_unchanged=True)
        for r in e.load_records])
    table(REPORT/"PV_PCC_CAPACITY_AUDIT.csv",[
        dict(generator=name,source_load=r["name"],bus=r["buses"][0],primary_phase=r["primary_phase"],
             local_hot=r["node_order"][0],phase_count=1,connection="delta" if r["delta"] else "wye",
             nominal_kv=r["kv"],original_load_kw=r["kw"],installed_kw=capacity,
             inverter_kva=capacity,planning_actual_same_capacity=True,PV_Q_kvar=0.,
             capacity_rule="PR62 construction original_kW*PV_ratio, dispatch replaced by current V42 solar normalization",
             source_model="research Generator model1 overlay; original IEEE8500 PVcount0",
             field_installation="UNVERIFIED",new_transformer=False)
        for r,name,capacity in zip(e.load_records,e.pv_names,e.pv_capacity)])
    arrays=dict(sites=np.array(sites),capacities=cap,known_gpu=known,cc4_gpu=anon,total_gpu=known+anon,
                IT_kw=it,PCC_P_kw=P,PCC_Q_kvar=Q,demand_mw=np.asarray(forecast["demand_mw_96"]),
                pv_mw=np.asarray(forecast["pv_mw_96"]),gross_factor=gross,pv_factor=solar)
    (DATA/"derived").mkdir(parents=True,exist_ok=True)
    np.savez_compressed(DATA/"derived/PLANNING_INPUTS.npz",**arrays)
    write(DATA/"derived/REFERENCE.json",dict(rows=reference,audit=audit))
    table(DATA/"derived/C1_PLANNING_COEFFICIENTS.csv",coefficients)
    module=normalization()
    freeze=dict(PASS=True,scope="Planning input identity, not physical or global causal-model certification",
        day=DAY,issue_time=bundle["issue_time"],sources=copies,raw_forecast=raw,
        arrays=receipt(DATA/"derived/PLANNING_INPUTS.npz"),
        reference=receipt(DATA/"derived/REFERENCE.json"),PR193_PQ_reproduction_errors=errors,
        installed_GPU=int(cap.sum()),original_population=len(bundle["known_population"]),
        original_job_population_sha256=audit["population_sha256"],CC4_conservation=conserved,
        source_PV_capacity_kw=float(e.pv_capacity.sum()),source_PV_capacity_fraction=fraction,
        source_native_P_kw=float(e.base_p.sum()),source_fixed_P_kw=float(e.base_p[e.fixed].sum()),
        source_variable_P_kw=float(e.base_p[~e.fixed].sum()),Fixed_count=int(e.fixed.sum()),Variable_count=int((~e.fixed).sum()),
        normalization=dict(P95_REFERENCE_MW=module.P95_REFERENCE_MW,
            ANNUAL_MAX_REFERENCE_MW=module.ANNUAL_MAX_REFERENCE_MW,
            ALPHA_GRID=module.ALPHA_GRID,PV_REFERENCE_MAX_MW=module.PV_REFERENCE_MAX_MW,
            source=receipt(DATA/"authority/grid_background_v16_2.py"),
            algebra="gross_factor=ALPHA_GRID*(demand/P95 + PV_ratio*rooftop/PV_REFERENCE_MAX); solar=ALPHA_GRID*rooftop/PV_REFERENCE_MAX",
            empirical_reference_available_at_D1="UNVERIFIED",
            status="inherited frozen engineering normalization; no new fit or Actual peak normalization"),
        GFS_initialization=initialization[0].isoformat(),GFS_initialization_before_cutoff=True,
        GFS_publication_available_before_cutoff="UNVERIFIED",
        inherited_CC4_Runtime_fit_ingestion_causality="UNVERIFIED",
        actual_values_read_by_planning_binding=0,optimizer_calls=0,workload_multiplier=1,
        source_original_phase_connections_preserved=True,customer_metered_profile_claim=False)
    write(REPORT/"PLANNING_INPUT_FREEZE.json",freeze)
    print("Planning frozen: demand/PV Forecast, GFS,C1,1649Jobs/780GPU; originalPQmaxerror",max(errors.values()),flush=True)


def actual_exogenous():
    freeze=read(REPORT/"PLANNING_INPUT_FREEZE.json")
    assert freeze["PASS"] and sha(DATA/"derived/PLANNING_INPUTS.npz")==freeze["arrays"]["sha256"]
    spec=read(FOLDER/"PREREGISTRATION.json");sources=spec["exogenous_sources"]
    copies={key:copy_source(record,"RAW_"+key.upper()+Path(record["path"]).suffix)
            for key,record in sources.items()}
    raw_demand=[r for r in archive_rows(Path(copies["demand"]["copied"]["path"]))
                if r.get("REGIONID")=="VIC1" and r.get("INTERVENTION","0")=="0" and "SETTLEMENTDATE" in r
                and START<pd.Timestamp(r["SETTLEMENTDATE"],tz=TZ)<=START+pd.Timedelta(days=1)]
    stamps=pd.DatetimeIndex([pd.Timestamp(r["SETTLEMENTDATE"],tz=TZ) for r in raw_demand])
    series=pd.Series([float(r["TOTALDEMAND"]) for r in raw_demand],index=stamps).sort_index()
    expected=pd.date_range(START+pd.Timedelta(minutes=5),periods=288,freq="5min")
    axis_equal(series.index,expected)
    values=series.to_numpy();demand=values.reshape(96,3).mean(1)
    old_selection=values.reshape(96,3)[:,-1]
    assert abs(values.sum()/12-demand.sum()/4)<1e-8
    table(DATA/"sources/ACTUAL_SELECTED_DEMAND_5MIN.csv",raw_demand)
    raw_pv=[r for r in archive_rows(Path(copies["pv"]["copied"]["path"]))
            if r.get("REGIONID")=="VIC1" and r.get("TYPE")=="MEASUREMENT" and "INTERVAL_DATETIME" in r
            and START<pd.Timestamp(r["INTERVAL_DATETIME"],tz=TZ)<=START+pd.Timedelta(days=1)]
    raw_pv.sort(key=lambda r:r["INTERVAL_DATETIME"])
    axis_equal([pd.Timestamp(r["INTERVAL_DATETIME"],tz=TZ) for r in raw_pv],
               pd.date_range(START+pd.Timedelta(minutes=30),periods=48,freq="30min"))
    pv30=np.array([float(r["POWER"]) for r in raw_pv]);pv=np.repeat(pv30,2)
    assert abs(pv30.sum()*.5-pv.sum()*.25)<1e-8
    table(DATA/"sources/ACTUAL_SELECTED_PV_30MIN.csv",raw_pv)
    weather=pd.read_parquet(Path(copies["weather"]["copied"]["path"]))
    weather.index=pd.DatetimeIndex(weather.ts).tz_convert(TZ)
    numeric=weather.drop(columns="ts").select_dtypes(include="number")
    realized=numeric.reindex(numeric.index.union(STARTS)).sort_index().interpolate(method="time",limit_area="inside").reindex(STARTS)
    assert np.isfinite(realized[["t_wb_c","rh_pct"]]).all().all()
    realized=realized.reset_index(names="ts_fixed_aest_start")
    realized.to_parquet(DATA/"derived/NOAA_ACTUAL_96.parquet",index=False)
    original=pd.read_parquet(INPUT/"DERIVED_AEMO_ACTUAL.parquet")
    axis_equal(original.ts_fixed_aest_end,ENDS)
    assert np.max(np.abs(original.demand_mw-old_selection))<1e-10
    assert np.max(np.abs(original.rooftop_pv_mw-pv))<1e-10
    pd.DataFrame(dict(ts_fixed_aest_end=ENDS,demand_mw=demand,rooftop_pv_mw=pv,
                     previous_V42_end_point_demand_mw=old_selection)).to_parquet(DATA/"derived/AEMO_ACTUAL_96.parquet",index=False)
    audit=dict(source_copies=copies,raw_demand_resolution_minutes=5,raw_PV_resolution_minutes=30,
        raw_demand_energy_MWh=float(values.sum()/12),new_demand_energy_MWh=float(demand.sum()/4),
        old_end_point_energy_MWh=float(old_selection.sum()/4),
        old_minus_energy_preserved_MWh=float(old_selection.sum()/4-values.sum()/12),
        maximum_point_selection_difference_MW=float(np.max(np.abs(demand-old_selection))),
        correction="aggregate3 raw5min interval powers; keep unchanged raw data, fixed15min axis and frozen normalization",
        power_values_PWC_interval_interpretation_assumption=True,
        PV_energy_MWh=float(pv.sum()/4),PV_energy_preserving=True,
        weather_interpolation="original time-linear within-day bracketing observations",
        actual_future_values_not_passed_to_Planning=True)
    write(REPORT/"ACTUAL_EXOGENOUS_AUDIT.json",audit)
    return demand,pv,realized


def actual_jobs():
    from v42_capacity.actual import Request,Environment,replay
    plan=read(ROOT/"ieee8500_v42/data/v42_inputs/PLANNING_INPUT_BUNDLE.json")
    actual=read(INPUT/"ACTUAL_INPUT_BUNDLE.json")
    assert actual["capacities"]==plan["capacities"] and actual["rack_compatibility"]==plan["rack_compatibility"]
    jobs=plan["known_population"]+actual["post_issue_arrivals"]
    uids={str(r["job_uid"]) for r in jobs};assert len(uids)==len(jobs)
    truth={r["job_uid"]:r for r in rows(FOLDER/"ACTUAL_REALIZED_SERVICE_AUTHORITY_LEDGER.csv") if r["job_uid"] in uids}
    assert set(truth)==uids
    spec=read(FOLDER/"PREREGISTRATION.json")
    archive=resolve(spec["archive"]);needed={}
    for uid,row in truth.items():needed.setdefault(row["source_member"],{})[int(row["source_row"])]=uid
    verified=0;raw_projection=[]
    with zipfile.ZipFile(archive) as z:
        for member,selected in needed.items():
            with z.open(member) as stream:
                parquet=pq.ParquetFile(stream);offset=0
                columns=["id","submit_time","start_time","end_time","gpus_requested"]
                for batch in parquet.iter_batches(columns=columns,batch_size=32768,use_threads=False):
                    frame=batch.to_pandas()
                    indices=[i-offset for i in selected if offset<=i<offset+len(frame)]
                    for i in indices:
                        raw=frame.iloc[i];uid=selected[offset+i];row=truth[uid]
                        assert str(raw.id)==uid
                        assert pd.Timestamp(raw.submit_time)==pd.Timestamp(row["submit_time"])
                        assert pd.Timestamp(raw.start_time)==pd.Timestamp(row["start_time"])
                        assert pd.Timestamp(raw.end_time)==pd.Timestamp(row["end_time"])
                        duration=(pd.Timestamp(raw.end_time)-pd.Timestamp(raw.start_time)).total_seconds()
                        assert abs(duration-float(row["realized_seconds"]))<1e-6
                        descriptor=next(j for j in jobs if str(j["job_uid"])==uid)
                        assert int(raw.gpus_requested)==int(descriptor["GPU_gang"])
                        raw_projection.append(dict(job_uid=uid,source_member=member,source_row=offset+i,
                            source_archive_sha256=spec["archive"]["sha256"],submit_time=row["submit_time"],
                            start_time=row["start_time"],end_time=row["end_time"],realized_seconds=duration,
                            immutable_requested_GPU=int(raw.gpus_requested),controller_future_duration_access=False))
                        verified+=1
                    offset+=len(frame)
            print("private Kestrel raw join",member,verified,"rows verified",flush=True)
    assert verified==len(jobs)
    table(DATA/"sources/PRIVATE_ACTUAL_Kestrel_UID_JOIN.csv",raw_projection)
    reference=read(DATA/"derived/REFERENCE.json")["rows"];mapping={r["job_uid"]:r for r in reference}
    issue=pd.Timestamp(plan["issue_time"])
    seconds=lambda stamp:(pd.Timestamp(stamp)-issue).total_seconds()
    requests=[];running=[];durations={};completions={}
    for job in jobs:
        uid=str(job["job_uid"]);t=truth[uid]
        request=Request(uid,seconds(job["submit_time"]),job["GPU_gang"],
                        tuple(job["compatible_sites"]),job["Q50_total_seconds"],job["source_site"])
        durations[uid]=float(t["realized_seconds"])
        if job["state_at_D1_cutoff"]=="RUNNING":
            start,end=seconds(t["start_time"]),seconds(t["end_time"])
            assert start<=0<end
            running.append((request,mapping[uid]["reference_site"],start));completions[uid]=end
        else:requests.append(request)
    gpu,ledger,audit=replay(plan["capacities"],requests,Environment(durations,completions),running=running)
    assert (gpu<=np.array([plan["capacities"][s] for s in sorted(plan["capacities"])])+1e-9).all()
    table(DATA/"derived/ACTUAL_QUEUE_LEDGER.csv",ledger)
    write(REPORT/"ACTUAL_Kestrel_QUEUE_AUDIT.json",dict(**audit,raw_requested_UIDs_verified=verified,
        raw_archive=spec["archive"],original_reference_and_capacities=True,
        private_service_truth_only=True,planning_future_truth_reads=0,Actual_optimizer_calls=0))
    return gpu


def actual():
    assert read(REPORT/"PLANNING_INPUT_FREEZE.json")["PASS"]
    demand,pv,weather=actual_exogenous()
    gpu=actual_jobs()
    from ieee8500_v42.capacity import load_c1_module
    module=load_c1_module();params=module.load_c1(ROOT/"ieee8500_v42/data/v42_inputs/C1_MODEL.json")
    power=read(ROOT/"ieee8500_v42/data/v42_inputs/POWER_AUTHORITY.json")
    plan=read(ROOT/"ieee8500_v42/data/v42_inputs/PLANNING_INPUT_BUNDLE.json")
    cap=np.array([plan["capacities"][s] for s in sorted(plan["capacities"])])
    it=power["current_IT_idle_kW_per_installed_GPU"]*cap+power["current_IT_swing_kW_per_active_GPU"]*gpu
    P=np.array([module.exact_c1_pcc_kw(it[t],float(w.t_wb_c),float(w.rh_pct),params)
                for t,w in enumerate(weather.itertuples(index=False))])
    Q=P*np.tan(np.arccos(power["PF_AIDC"]))
    with np.load(FOLDER/"BUNDLE/DAY_20250501/ACTUAL_PHYSICAL.npz",allow_pickle=False) as z:
        errors={k:float(np.max(np.abs(v-z[k]))) for k,v in [("GPU",gpu),("IT_kw",it),("PCC_P_kw",P),("PCC_Q_kvar",Q)]}
    assert max(errors.values())<1e-10, "ORIGINAL_CAUSAL_ACTUAL_REPLAY_DRIFT"
    fraction=read(REPORT/"PLANNING_INPUT_FREEZE.json")["source_PV_capacity_fraction"]
    gross,solar=temporal_factors(demand,pv,fraction)
    np.savez_compressed(DATA/"derived/ACTUAL_INPUTS.npz",sites=np.array(sorted(plan["capacities"])),
        capacities=cap,total_gpu=gpu,IT_kw=it,PCC_P_kw=P,PCC_Q_kvar=Q,
        demand_mw=demand,pv_mw=pv,gross_factor=gross,pv_factor=solar)
    write(REPORT/"ACTUAL_INPUT_FREEZE.json",dict(PASS=True,scope="realized input/source join, not operating PASS",
        arrays=receipt(DATA/"derived/ACTUAL_INPUTS.npz"),original_causal_replay_PQ_errors=errors,
        future_duration_controller_reads=0,CC4_not_double_counted_with_actual_jobs=True,
        Actual_C1_exact=True,Planning_C1_affine=True,original_PF=power["PF_AIDC"],
        GPU_capacity_violation_cells=int((gpu>cap+1e-9).sum()),all288_raw_demand_intervals_used=True))
    with np.load(DATA/"derived/PLANNING_INPUTS.npz",allow_pickle=False) as f:
        forecast_weather=pd.read_parquet(DATA/"sources/GFS_D1_WEATHER.parquet")
        alignment=[]
        for t in range(96):
            alignment.append(dict(slot=t,interval_start=STARTS[t].isoformat(),interval_end=ENDS[t].isoformat(),
                timezone="fixed AEST UTC+10",interval_seconds=900,grid_interval_ending=True,
                weather_GPU_power_interval_start=True,
                Forecast_demand_MW=float(f["demand_mw"][t]),Actual_demand_MW=float(demand[t]),
                Forecast_PV_MW=float(f["pv_mw"][t]),Actual_PV_MW=float(pv[t]),
                Forecast_gross_factor=float(f["gross_factor"][t]),Actual_gross_factor=float(gross[t]),
                Forecast_solar_factor=float(f["pv_factor"][t]),Actual_solar_factor=float(solar[t]),
                Forecast_wetbulb_C=float(forecast_weather.t_wb_c.iloc[t]),
                Actual_wetbulb_C=float(weather.t_wb_c.iloc[t]),
                timestamp_exact_match=True,duplicates=0,missing=0))
    table(REPORT/"AEMO_PV_96SLOT_ALIGNMENT.csv",alignment)
    print("Actual frozen: independent private source/queue/C1; energy-preserved demand; originalPQerror",max(errors.values()),flush=True)


if __name__=="__main__":
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument("action",choices=("planning","actual"))
    globals()[parser.parse_args().action]()
