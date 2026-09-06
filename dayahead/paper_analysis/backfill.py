"""Lossless export of accepted results. Never imports or runs an optimizer."""
from datetime import datetime, timedelta, timezone
from itertools import combinations
from pathlib import Path
import math
import shutil
import subprocess
import numpy as np
import pandas as pd
from .storage import SCHEMA, MISSING, STAGES, atomic, read, sha, digest, reference, write_json, write_npz, write_parquet, seal

MOBILITY = ("mess_id", "slot", "mode", "service_id", "origin_service_id", "destination_service_id",
            "departure_slot", "route_link_ids", "connection_ready_slot", "travel_slots_15min",
            "energy_safe_kwh", "energy_nominal_kwh", "route_q10_eta_sec", "route_q50_eta_sec", "route_q90_eta_sec", "route_safe_eta_sec")


def copy_file(source, destination):
    with Path(source).open("rb") as src, atomic(destination) as dst:
        shutil.copyfileobj(src, dst)


def stage_objectives(old, planning, fresh):
    a, m, b, f = (old[k] for k in ("J_A0", "J_M1", "J_A1", "J_FINAL"))
    return {"schema_id": SCHEMA, "stage_aliases": STAGES, "J_A1": a, "J_M1": m, "J_A2": b, "J_M2": f,
        "DELTA_J_M1": a-m, "DELTA_J_A2": m-b, "DELTA_J_M2": b-f, "DELTA_J_TOTAL": a-f,
        "J_PRE_AC_FINAL": f, "J_POST_RESTORATION_PLANNING": planning, "FRESH_AC_RHO": fresh}


def job_tables(a0, a1, ledger, accepted):
    base = {str(r["job_id"]): r for r in ledger.to_dict("records")}
    if len(a0) != len(a1) or {r["job_uid"] for r in a0} != {r["job_uid"] for r in a1} or set(base) != {r["job_uid"] for r in a0}:
        raise RuntimeError("PAPER_JOB_UID_COMPLETENESS_FAIL")
    old = {r["job_uid"]: r for r in a0}
    frames = []
    for internal, jobs in (("A0", a0), ("A1", a1)):
        rows = []
        for job in jobs:
            r = dict(job)
            l, before = base[r["job_uid"]], old[r["job_uid"]]
            r.update(internal_stage=internal, paper_stage=STAGES[internal], submit_time=l["submit_time"],
                partition=l["partition"], requested_walltime=l["requested_walltime_seconds"],
                predicted_runtime_seconds=l["diagnostic_point_total_seconds"],
                safe_runtime_seconds=r["safe_duration_seconds"], feedback_eligible=r["eligible_standby"],
                completion_relative_to_H=r["end_slot"] - 120, running_pending_classification=r["state_at_issue"])
            if internal == "A1":
                shift = r["start_slot"] - before["start_slot"]
                site = r["AIDC_site"] != before["AIDC_site"]
                overlap = max(0, min(r["end_slot"], before["end_slot"]) - max(r["start_slot"], before["start_slot"]))
                symmetric = r["requested_GPU"] * (r["end_slot"] - r["start_slot"] + before["end_slot"] - before["start_slot"] - 2 * (0 if site else overlap))
                r.update(start_changed=bool(shift), start_shift_slots=shift, site_changed=site,
                    GPU_slots_shifted_temporal=abs(shift)*r["requested_GPU"],
                    GPU_slots_shifted_spatial=(r["end_slot"]-r["start_slot"])*r["requested_GPU"] if site else 0,
                    changed_GPU_slots=symmetric, migration_changed=r["migration_selected"] != before["migration_selected"],
                    accepted_by_feedback=accepted)
            rows.append(r)
        frames.append(pd.DataFrame(rows))
    return frames


def route_identity(rows):
    return digest([{k: r[k] for k in MOBILITY} for r in rows])


def mess_table(rows, internal):
    result = []
    for original in rows:
        r = dict(original)
        dep = r["departure_slot"]
        r.update(internal_stage=internal, paper_stage=STAGES[internal],
            current_service=r["service_id"], origin_service=r["origin_service_id"], destination_service=r["destination_service_id"],
            arrival_slot=None if dep is None else dep + r["travel_slots_15min"],
            selected_route_id=digest(r["route_link_ids"]) if r["route_link_ids"] else None,
            ETA_Q10=r["route_q10_eta_sec"], ETA_Q50=r["route_q50_eta_sec"], ETA_Q90=r["route_q90_eta_sec"],
            Safe_ETA=r["route_safe_eta_sec"], travel_energy_kWh=r["energy_safe_kwh"],
            charge_kw=max(-r["p_kw"], 0), discharge_kw=max(r["p_kw"], 0),
            PCS_loading_fraction=math.hypot(r["p_kw"], r["q_kvar"])/700,
            connected_PCC=r["service_id"])
        result.append(r)
    return pd.DataFrame(result)


def route_summary(rows):
    moves = [r for r in rows if r["mode"] == "TRANSIT" and r["departure_slot"] == r["slot"]]
    return {"number_of_moves": len(moves), "vehicles_moved": len({r["mess_id"] for r in moves}),
        "total_Q50_travel_seconds": sum(r["route_q50_eta_sec"] for r in moves),
        "total_safe_travel_seconds": sum(r["route_safe_eta_sec"] for r in moves),
        "total_safe_travel_energy_kWh": sum(r["energy_safe_kwh"] for r in moves),
        "route_identity_SHA": route_identity(rows), "move_count_rule": "one record per vehicle and departure; transit slots not summed",
        "total_travel_distance": MISSING}


def delta_pq(m1, m2):
    if route_identity(m1) != route_identity(m2):
        raise RuntimeError("PAPER_M2_ROUTE_MUTATION")
    old = {(r["mess_id"], r["slot"]): r for r in m1}
    rows = []
    for r in m2:
        a = old[r["mess_id"], r["slot"]]
        rows.append({"mess_id": r["mess_id"], "slot": r["slot"], "service_PCC": r["service_id"],
            "P_M1": a["p_kw"], "Q_M1": a["q_kvar"], "energy_M1": a["battery_energy_kwh"], "SoC_M1": a["soc_fraction"],
            "P_M2": r["p_kw"], "Q_M2": r["q_kvar"], "energy_M2": r["battery_energy_kwh"], "SoC_M2": r["soc_fraction"],
            "delta_P": r["p_kw"]-a["p_kw"], "delta_Q": r["q_kvar"]-a["q_kvar"],
            "delta_energy": r["battery_energy_kwh"]-a["battery_energy_kwh"]})
    return pd.DataFrame(rows)


def aligned_branch_frame(a, topology):
    nodes = {str(n).lower(): i for i, n in enumerate(a["node_names"])}
    branches = {(r["branch_id"].lower(), r["phase"]): r for r in topology}
    frames = []
    for i, (name, phase, kind) in enumerate(zip(a["branch_names"], a["branch_phases"], a["branch_kinds"], strict=True)):
        if kind != "line":
            continue
        r = branches[str(name).lower(), str(phase)]
        suffix = str("ABC".index(str(phase)) + 1)
        send, recv = str(r["sending_bus"]).lower(), str(r["receiving_bus"]).lower()
        vs = a["voltage_pu"][:, nodes[send + "." + suffix]]
        vr = a["voltage_pu"][:, nodes[recv + "." + suffix]]
        frames.append(pd.DataFrame({"slot": np.arange(96), "line_id": str(name), "phase": str(phase),
            "sending_bus": send, "receiving_bus": recv, "V_send_pu": vs, "V_recv_pu": vr,
            "delta_V_pu": vs-vr, "abs_delta_V_pu": np.abs(vs-vr),
            "I_amp": a["phase_current_a"][:, i], "I_loading_pu": a["phase_current_loading_pu"][:, i],
            "P_flow_kW": np.nan, "Q_flow_kvar": np.nan, "power_flow_status": MISSING}))
    return pd.concat(frames, ignore_index=True)


def fresh_extrema(a):
    line = a["phase_current_loading_pu"][:, a["branch_kinds"] == "line"]
    tx = a["phase_current_loading_pu"][:, a["branch_kinds"] == "transformer"]
    kva = a["transformer_total_kva_loading_pu"][:, a["branch_kinds"] == "transformer"]
    v = a["voltage_pu"]
    return {"rho_max_AC": float(line.max()), "Vmin_pu": float(v.min()), "Vmax_pu": float(v.max()),
        "max_voltage_deviation_pu": float(np.abs(v-1).max()),
        "transformer_phase_current_loading_max": float(tx.max()), "transformer_total_kva_loading_max": float(kva.max()),
        "voltage_violation_count": int(((v < .95-1e-9) | (v > 1.05+1e-9)).sum()),
        "line_current_violation_count": int((line > 1+1e-9).sum()),
        "transformer_current_violation_count": int((tx > 1+1e-9).sum()),
        "transformer_kva_violation_count": int((kva > 1+1e-9).sum()),
        "losses_kwh": float(a["losses_kw_kvar"][:, 0].sum()*.25)}


def export_fresh(npz_path, summary, out, topology_meta):
    with np.load(npz_path, allow_pickle=False) as z:
        a = {k: z[k].copy() for k in z.files}
    ext = fresh_extrema(a)
    for k, v in ext.items():
        if k in summary and v != summary[k]:
            raise RuntimeError("PAPER_FRESH_SUMMARY_ARRAY_MISMATCH:" + k)
    if not np.asarray(a["convergence"]).all() or a["voltage_pu"].shape[0] != 96:
        raise RuntimeError("PAPER_FRESH_INCOMPLETE")
    write_npz(out / "bus_phase_voltage.npz", node_names=a["node_names"], node_phases=a["node_phases"], Vmag_pu=a["voltage_pu"])
    for kind in ("line", "transformer"):
        mask = a["branch_kinds"] == kind
        i, rho = a["phase_current_a"][:, mask], a["phase_current_loading_pu"][:, mask]
        rating = np.divide(i, rho, out=np.full_like(i, np.nan), where=rho != 0)
        write_npz(out / f"{kind}_phase_current.npz", branch_names=a["branch_names"][mask], phase=a["branch_phases"][mask],
            I_amp=i, loading_pu=rho, rating_amp_derived_from_recorded_ratio=rating)
    mask = a["branch_kinds"] == "transformer"
    write_npz(out / "transformer_kva.npz", transformer=a["branch_names"][mask], phase=a["branch_phases"][mask],
        kVA_loading_pu=a["transformer_total_kva_loading_pu"][:, mask])
    write_npz(out / "feeder_losses.npz", losses_kw_kvar=a["losses_kw_kvar"])
    for source, file, id_field, value_field, names in (
        ("regulator_taps", "regulator_states.parquet", "regulator_id", "tap_position", topology_meta["regulator_ids"]),
        ("capacitor_states", "capacitor_states.parquet", "capacitor_id", "status", topology_meta["capacitor_ids"])):
        values = a[source]
        if values.shape != (96, len(names)):
            raise RuntimeError("PAPER_NATIVE_CONTROL_AXIS")
        write_parquet(out / file, pd.DataFrame({"slot": np.repeat(np.arange(96), len(names)),
            id_field: np.tile(names, 96), value_field: values.ravel()}))
    write_parquet(out / "branch_power_flow.parquet", aligned_branch_frame(a, topology_meta["topology"]))
    write_json(out / "fresh_summary.json", {"schema_id": SCHEMA, **summary, **ext,
        "arrays_summary_extrema_exact": True, "raw_source": reference(npz_path),
        "branch_P_Q": MISSING, "feeder_P_Q": MISSING,
        "rating_recovery": "derived I/loading ratio retained; zero-current ratios missing, no invented ratings",
        "native_control_action_count_scope": "inter-slot state transitions only; within-slot actions not recorded"})
    return ext


def runtime_predictions(day, ledger, obs):
    f = ledger.copy()
    f["job_uid"] = f.job_id.astype(str)
    x = obs.set_index("id").reindex(f.job_uid)
    issue = pd.Timestamp(day, tz="+10:00") - pd.Timedelta(hours=6)
    total = (x.end_time-x.start_time).dt.total_seconds().to_numpy()
    remaining = (x.end_time-issue).dt.total_seconds().clip(lower=0).to_numpy()
    f["issue_time"] = issue.isoformat()
    f["runtime_point_prediction_sec"] = f.diagnostic_point_total_seconds
    f["safe_runtime_sec"] = f.RSP_duration_seconds
    f["calibration_margin_sec"] = f.q_selected_seconds
    f["actual_runtime_sec"] = total
    f["actual_remaining_runtime_sec"] = np.where(f.state_at_issue.eq("RUNNING"), remaining, np.nan)
    f["absolute_error_point"] = np.abs(f.runtime_point_prediction_sec-total)
    target = np.where(f.state_at_issue.eq("RUNNING"), remaining, total)
    f["absolute_error_safe"] = np.abs(f.safe_runtime_sec-target)
    f["covered_by_safe_runtime"] = target <= f.safe_runtime_sec
    f["actual_field_role"] = "EVALUATION_ONLY_NEVER_DA_DECISION_INPUT"
    f["point_model_evaluation_eligible"] = f.duration_authority.eq("SAFE_CAUSAL_RUNTIME_PENDING") & f.runtime_point_prediction_sec.notna()
    f["actual_runtime_source_member"] = x.source_member.to_numpy()
    return f


def b3(repo, source, output, obs):
    day = source.parent.name
    checkpoint = read(source / "COOPT_PLANNING_CHECKPOINT.json")
    planning = read(source / "PLANNING_PHYSICAL_GATES.json")
    fresh = read(source / "FRESH_AC_RESULT.json")["summary"]
    objective = stage_objectives(read(source / "COOPT_STAGE_OBJECTIVES.json"), planning["rho_max"], fresh["rho_max_AC"])
    write_json(output / "stage_objectives.json", objective)
    coupling = read(source / "COOPT_COUPLING_SUMMARY.json")
    accepted = coupling["AIDC_FEEDBACK_ACCEPTED"]
    ledger = pd.read_parquet(repo / "dayahead/artifacts/v37_r4a_per_day_aidc/days" / day / "V37_R4A_JOB_LEDGER.parquet")
    a1, a2 = job_tables(checkpoint["a0"], checkpoint["a1"], ledger, accepted)
    write_parquet(output / "A1_jobs.parquet", a1)
    write_parquet(output / "A2_jobs.parquet", a2)
    changed = a2.start_changed | a2.site_changed | a2.migration_changed
    terminal = read(source / "COOPT_TERMINAL_AUDIT.json")
    feedback = {"internal_stage": "A1", "paper_stage": "A2", "eligible_jobs": int(a2.feedback_eligible.sum()),
        "changed_jobs": int(changed.sum()), "start_changed_jobs": int(a2.start_changed.sum()), "site_changed_jobs": int(a2.site_changed.sum()),
        "changed_GPU_slots": int(a2.changed_GPU_slots.sum()), "temporal_shift_GPU_slots": int(a2.GPU_slots_shifted_temporal.sum()),
        "spatial_shift_GPU_slots": int(a2.GPU_slots_shifted_spatial.sum()),
        "temporal_shift_definition": "sum requested_GPU * absolute start shift; complete frozen interval",
        "changed_GPU_slots_definition": "site-time occupancy symmetric difference; complete frozen interval",
        "A2_candidate_status": read(source / "A1_SOLVER_RESULT.json")["status"],
        "A2_accepted": accepted, "A2_strict_improvement": objective["DELTA_J_A2"] > 1e-6,
        "A2_accepted_no_change": accepted and not bool(changed.any()), "A2_fallback_to_A1": not accepted,
        "J_M1": objective["J_M1"], "J_A2": objective["J_A2"], "DELTA_J_A2": objective["DELTA_J_A2"],
        "relative_DELTA_J_A2_percent": 100*objective["DELTA_J_A2"]/objective["J_M1"],
        "terminal_audit_status": terminal["status"], "additional_RUNNING_migrations": coupling["A0_to_A1_running_migrations_added"],
        "additional_post_H_work": terminal["REPAIR_INDUCED_INCREMENTAL_POST_MIDNIGHT_GPU_H"]}
    write_json(output / "A2_feedback_summary.json", feedback)
    write_json(output / "stage_acceptance.json", {"A2": feedback, "M2_accepted": coupling["MF_ACCEPTED"]})
    m1, m2 = checkpoint["m1"], checkpoint["mf"]
    write_parquet(output / "M1_mess_trajectory.parquet", mess_table(m1, "M1"))
    write_parquet(output / "M2_mess_trajectory.parquet", mess_table(m2, "MF"))
    write_parquet(output / "M2_delta_pq.parquet", delta_pq(m1, m2))
    search = read(source / "M1_FULL_SEARCH_RESULT.json")
    write_json(output / "M1_route_summary.json", {**route_summary(m1), "beam_trace": search["trace"],
        "execution_identity": search["V40A_execution_identity"], "beam_attempts": search["V40A_beam_attempts"]})
    counts = checkpoint["counts"]
    if counts["SECOND_MESS_FULL_ROUTE_SEARCH_CALLS"] != 0:
        raise RuntimeError("PAPER_M2_ROUTE_SEARCH_NONZERO")
    write_json(output / "M2_summary.json", {"internal_stage": "MF", "paper_stage": "M2",
        "M1_route_SHA": route_identity(m1), "M2_route_SHA": route_identity(m2), "ROUTE_IDENTITY_PASS": True,
        "M2_accepted": coupling["MF_ACCEPTED"], "M2_strict_improvement": objective["DELTA_J_M2"] > 1e-6,
        "M2_fallback": not coupling["MF_ACCEPTED"], "J_A2": objective["J_A2"], "J_M2": objective["J_M2"],
        "DELTA_J_M2": objective["DELTA_J_M2"], "relative_DELTA_J_M2_percent": 100*objective["DELTA_J_M2"]/objective["J_A2"],
        "route_search_calls": 0, "candidate_enumeration_calls": 0, "scope": "PRE_AC_FIXED_ROUTE_REFINEMENT"})
    post = read(source / "postfreeze/POSTFREEZE_VERIFICATION.json")
    for p in (source / "postfreeze").rglob("*"):
        if p.is_file():
            copy_file(p, output / "restoration" / p.relative_to(source / "postfreeze"))
    write_json(output / "restoration/restoration_summary.json", {**post,
        "triggered": post["restoration_rounds"] > 0, "raw_rounds_preserved": True,
        "triggering_violations": "round_NN/fresh/OPENDSS_VIOLATIONS.json",
        "derivatives_and_cuts": "round_NN/AC_RESTORATION.json",
        "P_Q_before_and_after": "round_NN/JOINT_DECISION_PAYLOAD.json and next round"})
    final = read(source / "FINAL_JOINT_DECISION_PAYLOAD.json")["MESS_trajectory"]
    write_parquet(output / "restoration/final_mess_trajectory.parquet", mess_table(final, "MF"))
    runtime = read(source / "COOPT_RUNTIME_PROFILE.json")
    events = []
    for i, e in enumerate(runtime["solver_events"]):
        events.append({**e, "internal_stage": e["stage"], "paper_stage": STAGES.get(e["stage"], e["stage"]),
            "optimize_call_index_in_saved_order": i, "incumbent": MISSING, "bound": MISSING,
            "MIP_gap": MISSING, "node_count": MISSING, "Threads": MISSING, "WorkLimit": MISSING,
            "candidate_ID": e["model_name"], "candidate_ID_semantics": "recorded model name; not inferred search key",
            "K_level": MISSING, "beam_state": MISSING})
    write_json(output / "solver_runtime.json", {"original_runtime_profile": runtime,
        "runtime_A1": runtime["A0"], "runtime_M1": runtime["M1"], "runtime_A2": runtime["A1"], "runtime_M2": runtime["MF"],
        "runtime_PlanningValidation": runtime["Planning_verification"], "runtime_Fresh": runtime["Fresh"],
        "runtime_ACRestoration": runtime["AC_restoration"], "runtime_Total": runtime["Total"],
        "solver_subproblems": events, "stage_overlap_note": runtime["stage_overlap_note"],
        "solver_stage_results": {"A2": read(source / "A1_SOLVER_RESULT.json"), "M2": read(source / "MF_SOLVER_RESULT.json")}})
    write_parquet(output / "ml/runtime_predictions.parquet", runtime_predictions(day, ledger, obs))
    traffic = read(source / "D1_TRAFFIC_AUTHORITY.json")
    write_json(output / "ml/traffic_route_inputs.json", traffic)
    metadata = read(output / "planning/numeric_recovery.json")
    last = source / "postfreeze" / f"round_{post['restoration_rounds']:02d}" / "fresh/OPENDSS_PHASE_ARRAYS.npz"
    ext = export_fresh(last, fresh, output / "fresh_ac", metadata)
    write_json(output / "planning/planning_summary.json", {"schema_id": SCHEMA, **planning,
        "planning_rho_max": planning["rho_max"], "planning_objective_J": planning["rho_max"],
        "limiting_line": planning["critical_line"].split("::")[0], "limiting_phase": planning["critical_phase"], "limiting_slot": planning["critical_slot"],
        "line_amp_estimate": MISSING, "reason": "Planning current surrogate is saved in its original normalized and kVA-surrogate units"})
    summary = {"schema_id": SCHEMA, "date": day, "case": "B3", "planning_rho_max": planning["rho_max"],
        "planning_objective_J": planning["rho_max"], "Planning_J": planning["rho_max"], "Fresh_AC_rho": ext["rho_max_AC"],
        "Actual_AC_rho": MISSING, **ext, **objective, "runtime_Total": runtime["Total"],
        "AIDC_jobs": len(a2), "AIDC_GPU_h": float(pd.read_parquet(output / "A2_site_timeseries.parquet").occupied_GPU_slots.sum()*.25),
        **{k: v for k, v in feedback.items() if k.startswith("A2_") or k.endswith("jobs")},
        **route_summary(final), "MESS_charge_kWh": sum(max(-r["p_kw"],0)*.25 for r in final),
        "MESS_discharge_kWh": sum(max(r["p_kw"],0)*.25 for r in final), "MESS_abs_Q_kvarh": sum(abs(r["q_kvar"])*.25 for r in final)}
    return summary, {"source": source, "traffic": traffic, "search": search["V40A_execution_identity"], "numeric": metadata}


def baseline(binding, output, topology_meta, fresh_index):
    cert = read(binding["certificate"])
    checkpoint_path = Path(cert.get("historical_checkpoint", cert.get("checkpoint")))
    cp = read(checkpoint_path)
    root = Path(cert.get("historical_case_root", cert.get("case_root")))
    result = cp["result"]
    original = read(root / "summary/OBJECTIVE.json")
    planning = result["Planning"]
    day, case = binding["day"], binding["case"]
    write_json(output / "planning/planning_summary.json", {"schema_id": SCHEMA, **planning,
        "planning_rho_max": planning["rho"], "planning_objective_J": original["primary_objective_J"],
        "limiting_line": planning["binding_asset"].split("::")[0], "limiting_phase": planning["binding_asset"].split("::")[-1],
        "limiting_slot": planning["binding_slot"], "original_objective": original})
    bus = pd.read_parquet(root / "planning/PLANNING_BUS_PHASE_96.parquet")
    line = pd.read_parquet(root / "planning/PLANNING_LINE_PHASE_96.parquet")
    def matrix(frame, key, value):
        return frame.pivot(index="slot", columns=key, values=value).sort_index(axis=1)
    v = matrix(bus, "bus_phase_key", "voltage_magnitude_pu")
    write_npz(output / "planning/planning_voltage_arrays.npz", node_names=np.asarray(v.columns), voltage_pu=v.to_numpy(),
              voltage_squared_pu=v.to_numpy()**2, voltage_lower_pu=np.asarray(.95), voltage_upper_pu=np.asarray(1.05))
    rho = matrix(line, "branch_phase_key", "phase_current_loading_pu")
    arrays = {"branch_phase_names": np.asarray(rho.columns), "phase_current_loading_pu": rho.to_numpy()}
    for key, value in (("flow_p_kw", "P_flow_kW"), ("flow_q_kvar", "Q_flow_kvar"),
                       ("branch_limit_kVA_surrogate", "current_limit_kVA_surrogate"), ("transformer_kva_loading_pu", "transformer_loading_pu")):
        arrays[key] = matrix(line, "branch_phase_key", value).to_numpy()
    write_npz(output / "planning/planning_line_arrays.npz", **arrays)
    write_npz(output / "planning/planning_transformer_arrays.npz", **arrays)
    for family in ("aidc", "mess", "solver"):
        for p in (root / family).glob("*"):
            if p.suffix == ".parquet":
                copy_file(p, output / family / p.name)
            elif p.suffix == ".csv":
                write_parquet(output / family / (p.stem + ".parquet"), pd.read_csv(p))
    target_sha = result["Fresh"]["schedule_sha256"]
    if target_sha not in fresh_index:
        namespace = checkpoint_path.parents[2]
        for p in namespace.rglob("OPENDSS_SUMMARY.json"):
            if (p.parent / "OPENDSS_PHASE_ARRAYS.npz").is_file():
                x = read(p)
                fresh_index.setdefault(x.get("schedule_sha256"), []).append(p.parent / "OPENDSS_PHASE_ARRAYS.npz")
    matches = fresh_index.get(target_sha, [])
    if not matches:
        raise RuntimeError("PAPER_FINAL_BASELINE_FRESH_CACHE_NOT_FOUND:" + day + case)
    ext = export_fresh(matches[0], result["Fresh"], output / "fresh_ac", topology_meta)
    write_json(output / "restoration/restoration_summary.json", {"source_checkpoint": reference(checkpoint_path),
        "recorded_result": result.get("restoration", MISSING), "round_details": MISSING})
    runtime = read(root / "summary/COMPUTE_SUMMARY.json")
    prov = read(root / "inputs/RUN_PROVENANCE.json")
    write_json(output / "solver_runtime.json", {"original_compute_summary": runtime, "runtime_Total": prov.get("wallclock_seconds", MISSING),
        "runtime_Fresh": runtime.get("Fresh_wallclock_seconds", MISSING), "stage_breakdown": MISSING,
        "solver_rows": "solver/SOLVER_RUNS.parquet"})
    site = pd.read_parquet(root / "aidc/IDC_FACILITY_96.parquet")
    m = pd.read_parquet(root / "mess/MESS_TRAJECTORY_96.parquet")
    moves = pd.read_parquet(root / "mess/MESS_MOVE_EVENTS.parquet")
    summary = {"schema_id": SCHEMA, "date": day, "case": case, "planning_rho_max": planning["rho"],
        "planning_objective_J": original["primary_objective_J"], "Planning_J": original["primary_objective_J"],
        "Fresh_AC_rho": ext["rho_max_AC"], "Actual_AC_rho": MISSING, **ext,
        "runtime_Total": prov.get("wallclock_seconds", MISSING), "number_of_moves": len(moves),
        "MESS_charge_kWh": float((-m.P_kW).clip(lower=0).sum()*.25),
        "MESS_discharge_kWh": float(m.P_kW.clip(lower=0).sum()*.25), "MESS_abs_Q_kvarh": float(m.Q_kvar.abs().sum()*.25),
        "AIDC_IT_kWh": float(site.IT_power_kW.sum()*.25), "AIDC_PCC_kWh": float(site.PCC_P_kW.sum()*.25)}
    return summary, {"source": root, "original_provenance": prov, "original_input_authority": read(root / "inputs/INPUT_AUTHORITY.json"),
        "execution_fingerprint": cp["execution_fingerprint"], "checkpoint": reference(checkpoint_path), "numeric": topology_meta}


def common_provenance(repo, binding, extra):
    source = extra["source"]
    original = extra.get("original_provenance", {})
    meta = extra["numeric"]
    day = binding["day"]
    method = read(repo / "dayahead/artifacts/v40b_v40a_may_launch/V40B_V40A_METHOD_FREEZE.json")
    execution = read(repo / "dayahead/artifacts/v40b_v40a_may_launch/V40B_EXECUTION_FREEZE.json")
    search = extra.get("search", extra.get("execution_fingerprint", {}))
    issue = (datetime.fromisoformat(day).replace(tzinfo=timezone(timedelta(hours=10))) - timedelta(hours=6)).isoformat()
    traffic = extra.get("traffic", {})
    return {"schema_id": SCHEMA, "operating_date": day, "case_id": binding["case"], "issue_timestamp": issue,
        "D_minus_1_cutoff": issue, "timezone": "FIXED_AEST_UTC_PLUS_10_NO_DST", "slot_minutes": 15,
        "stage_aliases": [{"internal_stage": k, "paper_stage": v} for k, v in STAGES.items()],
        "repository": "BeaverVillage/MobileESS", "PR": 27, "branch": "codex/v40a-bounded-iterative-aidc-mess-coopt",
        "git_commit_sha": original.get("integration_Git_HEAD", MISSING),
        "backfill_git_commit_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip(),
        "method_id": method["identity"]["method"], "method_SHA": method["method_SHA"],
        "execution_fingerprint": extra.get("execution_fingerprint", execution["execution_SHA"]),
        "input_fingerprint": binding.get("execution_fingerprint_SHA", meta["input_references"]),
        "traffic_forecast_SHA": traffic.get("forecast_SHA", original.get("traffic_authority_SHA", MISSING)),
        "route_table_SHA": traffic.get("route_table_SHA", MISSING), "runtime_model_SHA": MISSING,
        "AIDC_power_model_SHA": reference(repo / "dayahead/v39a/power.py"),
        "C1_PCC_model_SHA": reference(repo / "dayahead/artifacts/v24t_thermal_aware_aidc/V24T_C1_QUASISTATIC_MODEL.json"),
        "IEEE123_OpenDSS_model": meta["feeder_assets"], "solver_version": original.get("solver_versions", MISSING),
        "Python_version": original.get("Python_version", MISSING), "DSS_version": original.get("OpenDSS_version", MISSING),
        "random_seed": original.get("random_seed", MISSING), "Threads": search.get("solver_relevant_configuration", MISSING),
        "WorkLimit": search.get("WorkLimit", MISSING), "K": search.get("K", MISSING), "beam_width": search.get("beam", MISSING),
        "seed_width": search.get("seed", MISSING), "restoration_radius": MISSING,
        "restoration_max_rounds": MISSING, "restoration_policy_reference": reference(repo / "dayahead/v40d/policy.py"),
        "decision_binding": binding, "source_root": str(source), "original_provenance": original,
        "original_input_authority": extra.get("original_input_authority", {}),
        "scientific_output_modified": False, "reoptimization_calls": 0,
        "missing_field_semantics": MISSING, "backfill_mode": "EXACT_SAVED_DATA_AND_FROZEN_CACHE_ONLY"}


def run(repo, *, days=None):
    repo = Path(repo)
    root = repo / "dayahead/artifacts/v40a_bounded_iterative_aidc_mess_coopt"
    audit = repo / "dayahead/artifacts/v40d_actual_realized_replay"
    bindings = read(audit / "V40D_ACTUAL_DECISION_BINDING_AUDIT.json")["cases"]
    obs = pd.read_parquet(audit / "V40D_FROZEN_JOB_OBSERVATIONS.parquet")
    obs["id"] = obs.id.astype(str)
    traffic_audit = read(audit / "V40D_TRAFFIC_COMPLETENESS.json")
    traffic_by_day = {r["day"]: r for r in traffic_audit["days"]}
    fresh_index, completed = {}, []
    for b in bindings:
        day, case = b["day"], b["case"]
        if days and day not in days:
            continue
        output = root / "days" / day / case
        write_json(output / "PERSISTENCE_STATUS.json", {"status": "WRITING", "schema_id": SCHEMA})
        try:
            if sha(b["certificate"]) != b["certificate_SHA"]:
                raise RuntimeError("ACCEPTED_CASE_CERTIFICATE_DRIFT")
            metadata = read(root / "days" / day / "B3/planning/numeric_recovery.json")
            if case == "B3":
                summary, extra = b3(repo, Path(b["certificate"]).parent, output, obs)
            else:
                summary, extra = baseline(b, output, metadata, fresh_index)
            write_json(output / "provenance.json", common_provenance(repo, b, extra))
            write_json(output / "case_summary.json", summary)
            write_json(output / "result_summary.json", summary)
            write_json(output / "ml/prediction_authority.json", {"schema_id": SCHEMA,
                "runtime_actual_field_role": "EVALUATION_ONLY", "Actual_campaign_executed": False,
                "frozen_runtime_observation_reference": reference(audit / "V40D_FROZEN_JOB_OBSERVATIONS.parquet"),
                "runtime_raw_authority": read(audit / "V40D_WORKLOAD_COMPLETENESS.json")["source"],
                "traffic_forecast_vs_target": traffic_by_day[day],
                "traffic_target_semantics": traffic_audit["semantics"],
                "traffic_geometry": traffic_audit["geometry_sources"],
                "authority_read_does_not_feed_DA": True})
            missing = ["Fresh branch P/Q", "Fresh root P/Q", "Fresh transformer absolute kVA/rating",
                "complete per-candidate solver incumbent/bound/gap/node count/settings", "within-slot native control actions"]
            if case != "B3":
                missing.append("historical restoration round detail")
            required = ["provenance.json", "case_summary.json", "result_summary.json", "planning/planning_summary.json",
                "planning/planning_voltage_arrays.npz", "planning/planning_line_arrays.npz", "planning/planning_transformer_arrays.npz",
                "fresh_ac/fresh_summary.json", "fresh_ac/bus_phase_voltage.npz", "fresh_ac/line_phase_current.npz",
                "fresh_ac/transformer_phase_current.npz", "fresh_ac/transformer_kva.npz", "fresh_ac/branch_power_flow.parquet",
                "fresh_ac/regulator_states.parquet", "fresh_ac/capacitor_states.parquet", "solver_runtime.json"]
            if case == "B3":
                required += ["stage_objectives.json", "stage_acceptance.json", "A1_jobs.parquet", "A2_jobs.parquet",
                    "A1_site_timeseries.parquet", "A2_site_timeseries.parquet", "A2_feedback_summary.json", "M1_mess_trajectory.parquet",
                    "M1_route_summary.json", "M2_mess_trajectory.parquet", "M2_delta_pq.parquet", "M2_summary.json", "ml/runtime_predictions.parquet"]
            result = seal(output, required, missing=missing)
            completed.append({"day": day, "case": case, "status": result["status"], "file_count": len(result["files"])})
            print(day + " " + case + " " + result["status"], flush=True)
        except Exception as error:
            write_json(output / "PERSISTENCE_STATUS.json", {"status": "RESULT_PERSISTENCE_FAIL", "error": repr(error)})
            raise
    write_json(root / "PAPER_BACKFILL_REPORT.json", {"schema_id": SCHEMA, "cases": completed,
        "case_count": len(completed), "optimization_calls": 0, "May_restarts": 0})
    return completed
