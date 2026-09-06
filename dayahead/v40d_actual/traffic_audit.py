"""Read-only Stage25F lineage and independent reduced-link entry-time replay."""
from datetime import datetime,timedelta,timezone
import inspect
import math
from pathlib import Path
import numpy as np
import pandas as pd
from dayahead.paper_analysis.storage import read,sha,reference,write_json,write_parquet,digest
from .capacity_audit import write_csv
from .contracts import ReplayError


def independent_route(links, departure_slot, table, day):
    """No calls to production traverse; lookup by (reduced_link_id, slot5)."""
    start=datetime.fromisoformat(day).replace(tzinfo=timezone(timedelta(hours=10)))
    elapsed=0.;edges=[]
    for index,link in enumerate(links):
        entry_offset=departure_slot*900+elapsed
        bucket=math.floor(entry_offset/300)
        try:duration=float(table.loc[(link,bucket),"final_tt_sec"])
        except KeyError:raise ReplayError("SUMO_INDEPENDENT_LOOKUP_MISSING") from None
        if not math.isfinite(duration) or duration<=0:raise ReplayError("SUMO_INDEPENDENT_LOOKUP_INVALID")
        edges.append({"edge_sequence_index":index,"edge_id":link,"actual_entry_offset_sec":entry_offset,
            "actual_entry_timestamp":(start+timedelta(seconds=entry_offset)).isoformat(),
            "SUMO_lookup_slot5":bucket,"SUMO_lookup_timestamp":(start+timedelta(seconds=bucket*300)).isoformat(),
            "SUMO_realized_travel_time_sec":duration,"actual_exit_timestamp":(start+timedelta(seconds=entry_offset+duration)).isoformat(),
            "source_value_semantics":"STAGE25F_OBSERVATION_ANCHORED_CALIBRATED_SUMO_FINAL_TT_SEC"})
        elapsed+=duration
    return elapsed,edges


def _long(p):
    s=str(p)
    return Path("\\\\?\\UNC\\"+s[2:]) if s.startswith("\\\\") and len(s)>245 else Path(s)


def run(repo):
    from .mobility_inputs import actual_mobility
    from .preflight import verify_protected
    from dayahead.v33m.road_graph_authority import load_road_graph_authority
    from dayahead.v33m.mobility_physics_adapter import PhysicsMobilityEnergyAdapter
    from dayahead.v33m.contracts import CONNECTION_DELAY_SECONDS
    repo=Path(repo);root=repo/"dayahead/artifacts/v40d_actual_realized_replay";out=root/"sumo_source_audit"
    a=read(root/"V40D_TRAFFIC_COMPLETENESS.json");daily=a["days"][0]
    source=Path(daily["source"]["path"]);pipeline=source.parents[3]
    finalroot=pipeline/"08_production_5min_validated_stage25f"
    freeze=pipeline/"09_ml_dataset_freeze/stage_ml0_2019_2025_v1"
    frozen=read(freeze/"dataset_freeze_manifest.json")
    checksum=freeze/"SHA256SUMS_SOURCE.txt"
    if sha(checksum)!=frozen["source_content_manifest_sha256"]:
        raise ReplayError("SUMO_SOURCE_CONTENT_MANIFEST_DRIFT")
    checksums={line[66:]:line[:64] for line in checksum.read_text(encoding="utf-8").splitlines()}
    rows=[]
    expected_days=[f"2025-05-{d:02d}" for d in range(1,32)]
    if [d["day"] for d in a["days"]]!=expected_days:raise ReplayError("SUMO_MAY_COVERAGE")
    for d in a["days"]:
        p=Path(d["source"]["path"]);rel=p.relative_to(pipeline).as_posix();actualsha=sha(p)
        if actualsha!=checksums[rel] or actualsha!=d["source"]["sha256"]:
            raise ReplayError("SUMO_MAY_FILE_FREEZE_SHA_MISMATCH")
        f=pd.read_parquet(p,columns=["calendar_date","slot5","reduced_link_id","final_tt_sec"])
        if len(f)!=146592 or f.duplicated(["slot5","reduced_link_id"]).any() or f.slot5.nunique()!=288 or f.reduced_link_id.nunique()!=509 or set(f.calendar_date)!={d["day"]} or not np.isfinite(f.final_tt_sec).all():
            raise ReplayError("SUMO_MAY_AXIS_OR_VALUES")
        rows.append({"day":d["day"],"source":reference(p),"rows":len(f),"links":509,"slots":288,"status":"PASS"})
    f=pd.read_parquet(source)
    rawpath=pipeline/"07_production_5min_raw/year=2025/date=2025-05-01/link_tt_5min_24h.parquet"
    reportpath=rawpath.with_name("production_day_report.json")
    finalreport=source.with_name("production_day_report.json")
    for p in (rawpath,reportpath,finalreport):
        if sha(p)!=checksums[p.relative_to(pipeline).as_posix()]:raise ReplayError("SUMO_UPSTREAM_SOURCE_SHA_DRIFT")
    raw=pd.read_parquet(rawpath).sort_values(["slot5","reduced_link_id"])
    final=f.sort_values(["slot5","reduced_link_id"])
    if not np.array_equal(raw.pred_tti.to_numpy(),final.raw_pred_tti.to_numpy()):
        raise ReplayError("STAGE25F_RAW_SUMO_LINEAGE_MISMATCH")
    if not np.array_equal((final.final_tti*final.mapping_ff_tt_sec).to_numpy(),final.final_tt_sec.to_numpy()):
        raise ReplayError("STAGE25F_FINAL_TTI_SCALING_MISMATCH")
    blocks=f.sort_values(["reduced_link_id","slot5"])
    weights=blocks.sampled_seconds_sum.to_numpy().reshape(-1,3)
    weights=np.where(np.isfinite(weights)&(weights>0),weights,0.)
    weights[weights.sum(axis=1)<=1e-12,:]=1.
    anchors=blocks.corrected_anchor_tti.to_numpy().reshape(-1,3)[:,0]
    anchor_error=float(np.max(np.abs((blocks.final_tti.to_numpy().reshape(-1,3)*weights).sum(axis=1)/weights.sum(axis=1)-anchors)))
    if anchor_error>1e-9 or (blocks.final_tti<1-1e-12).any():
        raise ReplayError("STAGE25F_ANCHOR_OR_PHYSICAL_FLOOR_MISMATCH")
    rp=read(reportpath)
    if not rp["quality_gate"] or rp["sumo_process"]["returncode"]!=0 or rp["temporal_contract"]["sumo_step_sec"]!=1:
        raise ReplayError("RAW_SUMO_PRODUCTION_GATE_FAIL")
    package=pipeline/"06_stage22/packages/mobile_ess_stage25f_2019_2025_validated5min_full_production_v3_stream8_directio_resume_20260726_171739/mobile_ess_stage25f_2019_2025_validated5min_full_production_v3_stream8_directio_resume"
    model=_long(package/"frozen_stage25e/final_all2019_official_wide_physical.json")
    modelsha=sha(model)
    if modelsha!=frozen["model_sha256"]:raise ReplayError("STAGE25F_FROZEN_CALIBRATION_MODEL_DRIFT")
    modelcontract=read(_long(package/"frozen_stage25e/frozen_method_contract.json"))
    linkref=a["link_order"]
    if sha(linkref["path"])!=linkref["sha256"]:raise ReplayError("SUMO_LINK_ORDER_SHA_DRIFT")
    graph=load_road_graph_authority(Path(linkref["path"]),*(Path(r["path"]) for r in a["geometry_sources"]))
    physics=PhysicsMobilityEnergyAdapter()
    table=f.set_index(["reduced_link_id","slot5"])
    bs=read(root/"V40D_ACTUAL_DECISION_BINDING_AUDIT.json")["cases"]
    edge_rows=[];vehicles=[];case_rows=[]
    for case in ("B2","B3"):
        b=next(b for b in bs if b["day"]=="2025-05-01" and b["case"]==case)
        previous=root/"smoke/2025-05-01"/case
        saved=read(previous/"MESS_actual_moves.json")
        # Current adapter has no ML ETA diagnostic reads. Recompute mobility only
        # and prove the physical trajectory used by the existing Actual run is identical.
        fresh=actual_mobility(repo,b)
        oldframe=pd.read_parquet(previous/"MESS_executed_trajectory.parquet")
        pd.testing.assert_frame_equal(oldframe,fresh["frame"],check_dtype=False)
        write_json(out/(case+"_MESS_REPLAY_NO_ML_ETA.json"),fresh["audit"])
        if len(saved)!=len(fresh["moves"]):raise ReplayError("SUMO_SAVED_MOVE_COUNT_MISMATCH")
        for m,new in zip(saved,fresh["moves"]):
            for key in ("mess_id","route_link_ids","origin_service_id","destination_service_id","departure_slot","actual_eta_seconds","actual_arrival_slot","actual_connection_ready_slot","actual_travel_energy_kWh"):
                if m[key]!=new[key]:raise ReplayError("SUMO_ADAPTER_PHYSICAL_TRAJECTORY_CHANGED")
            elapsed,edges=independent_route(m["route_link_ids"],m["departure_slot"],table,"2025-05-01")
            error=abs(elapsed-m["actual_eta_seconds"])
            arrival=m["departure_slot"]+elapsed/900
            arrival_error=abs(arrival-m["actual_arrival_slot"])*900
            ready=m["departure_slot"]+math.ceil((elapsed+CONNECTION_DELAY_SECONDS)/900)
            if error!=0 or arrival_error!=0 or ready!=m["actual_connection_ready_slot"]:raise ReplayError("SUMO_INDEPENDENT_RECALCULATION_FAIL")
            if [(e["edge_id"],e["SUMO_lookup_slot5"],e["SUMO_realized_travel_time_sec"]) for e in edges]!=[(e["link_id"],e["entry_step5"],e["travel_seconds"]) for e in m["link_entries"]]:
                raise ReplayError("SUMO_EDGE_ENTRY_RECALCULATION_FAIL")
            selected=[graph.links_by_id[k] for k in m["route_link_ids"]]
            geometry={"route_distance_km":sum(k.distance_km for k in selected),"cumulative_ascent_m":sum(k.cumulative_ascent_m for k in selected),"cumulative_descent_m":sum(k.cumulative_descent_m for k in selected)}
            energy=physics.physics.energy_kwh(geometry,elapsed)
            if energy!=m["actual_travel_energy_kWh"]:raise ReplayError("ACTUAL_MOBILITY_ENERGY_RECALCULATION_FAIL")
            start=datetime(2025,5,1,tzinfo=timezone(timedelta(hours=10)))
            v={"case":case,"vehicle_id":m["mess_id"],"departure_time":(start+timedelta(minutes=15*m["departure_slot"])).isoformat(),
                "frozen_origin":m["origin_service_id"],"frozen_destination":m["destination_service_id"],
                "route_edge_count":len(edges),"route_sha":digest(m["route_link_ids"]),"route_edges":m["route_link_ids"],
                "sum_edge_realized_travel_time_sec":elapsed,"actual_arrival_timestamp":(start+timedelta(seconds=arrival*900)).isoformat(),
                "actual_connection_ready_timestamp":(start+timedelta(minutes=ready*15)).isoformat(),
                "max_abs_travel_time_recalc_error_sec":error,"max_abs_arrival_time_recalc_error_sec":arrival_error,
                "actual_travel_energy_kWh":energy,"travel_energy_recalc_error_kWh":0.,"SUMO_source_SHA":daily["source"]["sha256"]}
            vehicles.append(v);edge_rows.extend({**{k:v[k] for k in v if k!="route_edges"},**e} for e in edges)
        case_rows.append({"case":case,"moving_vehicle_count":len({m["mess_id"] for m in saved}),"SUMO_realized_replay_vehicle_count":len(saved),
            "ML_ETA_used_vehicle_count":0,"route_change_count":0,"reroute_count":0,"max_abs_travel_time_recalc_error_sec":0,
            "max_abs_arrival_time_recalc_error_sec":0,"route_identity_PASS":True,"SUMO_source_SHA":daily["source"]["sha256"],
            "saved_Actual_MESS_trajectory_bit_equal_after_removing_ETA_diagnostics":True})
    source_code=inspect.getsource(actual_mobility)
    if any(token in source_code for token in ("Q50_ETA_seconds","Safe_ETA_seconds","route_q50_eta_sec","route_safe_eta_sec")):
        raise ReplayError("ML_ETA_READ_BY_ACTUAL_MOBILITY")
    da_files=[p for name in ("v40a","v40b","v39e","v33m") for p in (repo/"dayahead"/name).glob("*.py")]
    da_leaks=[str(p) for p in da_files if "08_production_5min_validated_stage25f" in p.read_text(encoding="utf-8-sig") or "final_tt_sec" in p.read_text(encoding="utf-8-sig")]
    if da_leaks:raise ReplayError("OPERATING_DAY_SUMO_READ_BY_DAYAHEAD")
    guard=verify_protected(repo,root)
    if guard["status"]!="PASS":raise ReplayError("SUMO_AUDIT_PROTECTED_DRIFT")
    summary={"status":"PASS_CALIBRATED_SUMO_LINK_ENTRY_REPLAY","ACTUAL_TRAVEL_TIME_SOURCE":"SUMO_REALIZED_LINK_ENTRY",
        "source_subtype":"STAGE25F_OBSERVATION_ANCHORED_CALIBRATED_SIMULATION","uncalibrated_raw_SUMO_claim":False,
        "native_observed_5minute_claim":False,"ML_TRAVEL_TIME_USED_IN_ACTUAL":"NO_DAYAHEAD_FORECAST_ETA",
        "DAYAHEAD_ETA_USED_AS_ACTUAL":"NO","ML_ETA_READ_BY_ACTUAL_MOBILITY":"NO","FREE_FLOW_TIME_USED_AS_ACTUAL":"NO_RUNTIME_FALLBACK",
        "REALIZED_SUMO_READ_BY_DAYAHEAD":"NO_OPERATING_DAY_REALIZED_INPUT",
        "dataset_generation_uses_statistical_calibration":True,"calibration_model":reference(model),"calibration_method":modelcontract,
        "source":reference(source),"raw_SUMO_source":reference(rawpath),"raw_SUMO_production_report":reference(reportpath),
        "May01_anchor_reaggregation_max_error_TTI":anchor_error,"upstream_TTI_floor_is_part_of_frozen_calibration":True,
        "calibrated_production_report":reference(finalreport),"freeze_manifest":reference(freeze/"dataset_freeze_manifest.json"),
        "corrector_source":reference(_long(package/"run_stage25f_correct_year.py")),"corrector_model_source":reference(_long(package/"stage22mm/graph_model.py")),
        "source_coverage_dates":expected_days,"coverage":rows,"time_resolution_minutes":5,"directed_reduced_links":509,
        "link_order":linkref,"timezone":"AEST_FIXED_UTC_PLUS_10","timestamp_semantics":"[slot5*300,(slot5+1)*300); floor actual link-entry time; no interpolation",
        "timestamp_display_precision":"microseconds; numeric error comparisons use elapsed/arrival offsets without rounded timestamp strings",
        "route_edge_definition":"509 directed reduced links; physical SUMO edge geometry remains frozen, no per-physical-edge durations invented",
        "raw_SUMO_production_command":rp["sumo_process"]["command"],"raw_SUMO_warmup_seconds":rp["teleport"]["eval_begin_sec"],
        "ML_ETA_diagnostic_reads_removed":True,"physical_MESS_trajectory_changed":False,"new_OpenDSS_run_needed":False,
        "cases":case_rows,"vehicles":vehicles,"edge_row_count":len(edge_rows),"protected":guard,
        "code_trace":[reference(repo/"dayahead/v40d_actual/mobility_inputs.py"),reference(repo/"dayahead/v40d_actual/mess_replay.py"),reference(repo/"dayahead/v40d_actual/traffic_audit.py")],
        "full_campaign_authorized":False,"full_campaign_launched":False,"UNASSIGNED_blocked_cases":44,
        "approval_scope":"Existing Stage25F calibrated-simulation authority only; no claim of uncorrected native SUMO or direct observed travel times"}
    write_csv(out/"V40D_MAY01_MESS_SUMO_REALIZED_REPLAY_AUDIT.csv",edge_rows)
    write_json(out/"V40D_MAY01_MESS_SUMO_REALIZED_REPLAY_SUMMARY.json",summary)
    return {"status":summary["status"],"edge_rows":len(edge_rows),"cases":case_rows}
