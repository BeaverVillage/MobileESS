"""Rebuild the 31-day comparison from immutable result and raw current files.

Missing values stay null in JSON and blank in CSV. Fresh replay completion and
absence of measured physical violations are deliberately separate properties.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import json
import math
from pathlib import Path
from datetime import datetime, timezone
from fractions import Fraction
from typing import Any

import numpy as np

DAYS = tuple(f"2025-05-{i:02d}" for i in range(1, 32))
ALGORITHM = "V42_COMMON_MESS_PRIMAL_ANYTIME_U4_V1"
OLD_CAMPAIGN = Path(r"D:\MobileESS_V42\runtime\v42_may_campaign\native90_build_reuse_20261009_01")
OLD_AUTONOMOUS = Path(r"D:\v42_may_restart_20261010_02")
AUTHORITY = Path(r"D:\MobileESS_V42\docs\v42_transformer_normalamps_contract")


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def record(path):
    path = Path(path).resolve()
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    return {"path": str(path), "sha256": digest, "bytes": path.stat().st_size}


def finite(value):
    if isinstance(value, bool):
        return None
    try:
        value = float(Fraction(value)) if isinstance(value, str) and "/" in value else float(value)
    except (ValueError, TypeError):
        return None
    return value if math.isfinite(value) else None


def clean(value):
    if isinstance(value, dict):
        return {str(k): clean(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [clean(v) for v in value]
    if isinstance(value, np.generic):
        return clean(value.item())
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, Path):
        return str(value)
    return value


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".report.tmp")
    temporary.write_text(json.dumps(clean(value), ensure_ascii=False, indent=2,
                                    allow_nan=False) + "\n", encoding="utf8")
    temporary.replace(path)


def write_csv(path, rows):
    path = Path(path)
    names = list(dict.fromkeys(k for row in rows for k in row))
    temporary = path.with_suffix(path.suffix + ".report.tmp")
    with temporary.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=names)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: json.dumps(clean(v), ensure_ascii=False) if
                             isinstance(v, (dict, list, tuple)) else clean(v)
                             for k, v in row.items()})
    temporary.replace(path)


def first(document, *keys):
    for key in keys:
        value = document.get(key)
        if value is not None:
            return value
    return None


def coalesce(*values):
    return next((value for value in values if value is not None), None)


def load_receipt(value, provenance, errors):
    """Validate referenced bytes before a result can enter any comparison."""
    if not value:
        return None, None
    expected = value if isinstance(value, dict) else None
    raw_path = value.get("path", value.get("result")) if expected else value
    if not raw_path:
        return None, None
    path = Path(raw_path)
    try:
        actual = record(path)
        if expected and expected.get("sha256") and (
                actual["sha256"] != expected["sha256"] or
                (expected.get("bytes") is not None and actual["bytes"] != expected["bytes"])):
            raise ValueError("REFERENCED_FILE_SHA_OR_SIZE_MISMATCH")
        value = read(path)
        provenance[str(path.resolve())] = actual
        return value, path
    except (OSError, ValueError, TypeError) as error:
        errors.append({"path": str(path), "error": str(error)})
        return None, path


def result_for(root, manifest, state, arm, day, provenance, errors):
    key = arm + "/" + day
    row = state.get("dates", {}).get(key, {})
    for field in ("date_results", "results", "B1_results", "b1_results"):
        refs = manifest.get(field, {})
        if isinstance(refs, dict) and (key in refs or (arm == "B1" and day in refs)):
            return load_receipt(refs.get(key, refs.get(day)), provenance, errors)
    ref = row.get("result") or row.get("result_path")
    if ref:
        if isinstance(ref, str) and row.get("result_SHA"):
            ref = {"path": ref, "sha256": row["result_SHA"]}
        return load_receipt(ref, provenance, errors)
    folder = root / "dates" / arm / day
    paths = list(folder.glob("RESULT.json")) + list(folder.glob("attempts/*/RESULT.json"))
    if paths:
        return load_receipt(max(paths, key=lambda p: p.stat().st_mtime_ns), provenance, errors)
    return None, None


def line_authority(manifest, provenance, errors):
    path = Path(manifest.get("line_current_authority_csv", AUTHORITY / "LINE_CURRENT_AUTHORITY_UNCHANGED.csv"))
    try:
        provenance[str(path.resolve())] = record(path)
        with path.open(encoding="utf-8-sig") as stream:
            rows = list(csv.DictReader(stream))
        limits = {r["branch_phase"].lower(): float(r["NormalAmps"]) for r in rows}
        if len(limits) != len(rows) or not limits or any(not math.isfinite(v) or v <= 0 for v in limits.values()):
            raise ValueError("INVALID_OR_DUPLICATE_LINE_CURRENT_AUTHORITY")
        return limits
    except (OSError, KeyError, ValueError) as error:
        errors.append({"path": str(path), "error": str(error)})
        return {}


def current_metric(path, limits, provenance):
    """100 * max(abs(I_actual_line_phase_A) / corresponding Line NormAmps)."""
    path = Path(path)
    before = record(path)
    with np.load(path, allow_pickle=False) as archive:
        names = archive["branch_names"].astype(str)
        if "phase_current_a" in archive:
            currents = archive["phase_current_a"]
            phases = archive["branch_phases"].astype(str)
            axis = [f"{name}::{phase}".lower() for name, phase in zip(names, phases)]
            kinds = archive["branch_kinds"].astype(str)
            mask = kinds == "line"
            convergence = archive["convergence"]
            stored = archive.get("phase_current_loading_pu")
        else:
            currents = archive["current_A"]
            axis = [name.lower() for name in names]
            mask = np.array([name.startswith("line.") for name in axis])
            convergence = archive["converged"]
            stored = archive.get("current_pu")
        selected = [axis[i] for i in np.flatnonzero(mask)]
        if len(axis) != len(set(axis)) or set(selected) != set(limits):
            raise ValueError("B1_LINE_SET_OR_PHASE_AXIS_AUTHORITY_MISMATCH")
        if currents.shape != (96, len(axis)) or not np.isfinite(currents[:, mask]).all():
            raise ValueError("ALL_96_SLOT_FINITE_LINE_CURRENTS_REQUIRED")
        if convergence.shape != (96,):
            raise ValueError("ALL_96_SLOT_CONVERGENCE_AXIS_REQUIRED")
        ratios = np.abs(currents[:, mask]) / np.array([limits[k] for k in selected])
        if stored is not None and not np.allclose(ratios, stored[:, mask], rtol=0, atol=5e-12):
            raise ValueError("STORED_LINE_CURRENT_DENOMINATOR_DRIFT")
        slot, line = np.unravel_index(int(np.argmax(ratios)), ratios.shape)
        metric = dict(actual_maximum_line_loading_percent=100 * float(ratios[slot, line]),
                      max_slot=int(slot), max_branch_phase=selected[line],
                      line_phase_count=len(selected), valid_slots=96,
                      convergence_count=int(np.count_nonzero(convergence)),
                      current_formula="100*max(abs(Actual line phase current A)/source Line NormAmps A)",
                      line_axis_sha=hashlib.sha256(json.dumps(sorted(selected)).encode()).hexdigest(),
                      raw_current_receipt=before)
    if record(path) != before:
        raise ValueError("RAW_CURRENT_BYTES_CHANGED_DURING_REPORT")
    provenance[str(path.resolve())] = before
    return metric


def evaluation_of(result, path, provenance, errors):
    # B3 wraps the original DDAY result, whose physical output is fresh_ac.
    actual_ref = result.get("actual")
    if actual_ref:
        actual, _ = load_receipt(actual_ref, provenance, errors)
        if actual:
            body = actual.get("result", {})
            ac = body.get("fresh_ac", body.get("ac", {}))
            if ac.get("summary"):
                folder = Path(ac["folder"]).parent if ac.get("folder") else None
                partial = result.get("evaluation", {}).get("Fresh", {})
                if not folder and partial.get("folder"):
                    folder = Path(partial["folder"]).parent
                return dict(PASS=body.get("PASS") is True and ac.get("PASS") is True,
                    summary=ac["summary"], Fresh=dict(ac, **({"folder":str(folder/"FRESH")} if folder else {})),
                    Actual={"folder":str(folder/"ACTUAL")} if folder else {},
                    folder=str(folder) if folder else None, physical_violation=ac["summary"].get("physical_violation"),
                    Actual_reoptimization=int(body.get("global_MILP_calls", 0)),
                    local_PQ_repair=int(body.get("local_p_repair") is True or body.get("local_q_repair") is True),
                    global_PQ_repair=int(body.get("full_reoptimization") is True))
    for key in ("evaluation", "operations", "Actual_Fresh", "Fresh_AC"):
        value = result.get(key)
        if isinstance(value, dict) and not ("path" in value and "summary" not in value):
            return value
        if value:
            loaded, _ = load_receipt(value, provenance, errors)
            if loaded:
                return loaded
    field = result.get("fields", {})
    if isinstance(field.get("Fresh_AC"), dict):
        return field["Fresh_AC"]
    if path:
        for p in (path.parent / "output/OPERATIONS/OPERATIONS_RESULT.json",
                  path.parent / "OPERATIONS/OPERATIONS_RESULT.json"):
            if p.exists():
                loaded, _ = load_receipt(p, provenance, errors)
                return loaded or {}
    return {}


def metric_from_result(result, path, evaluation, limits, provenance, errors):
    candidates = []
    for value in (result.get("actual_current_arrays"), evaluation.get("actual_current_arrays"),
                  evaluation.get("Fresh", {}).get("raw_arrays")):
        if value:
            candidates.append(Path(value["path"] if isinstance(value, dict) else value))
    fresh_folder = evaluation.get("Fresh", {}).get("folder")
    if fresh_folder:
        candidates += [Path(fresh_folder) / "fresh/OPENDSS_PHASE_ARRAYS.npz",
                       Path(fresh_folder) / "OPENDSS_PHASE_ARRAYS.npz"]
    if evaluation.get("folder"):
        candidates.append(Path(evaluation["folder"]) / "FRESH/fresh/OPENDSS_PHASE_ARRAYS.npz")
    if path:
        candidates += [path.parent / "output/OPERATIONS/FRESH/fresh/OPENDSS_PHASE_ARRAYS.npz",
                       path.parent / "OPERATIONS/FRESH/fresh/OPENDSS_PHASE_ARRAYS.npz"]
    for p in dict.fromkeys(candidates):
        if p.exists():
            try:
                return current_metric(p, limits, provenance)
            except (ValueError, KeyError, OSError) as error:
                errors.append({"path": str(p), "error": str(error)})
                return {}
    # rho_max_AC may include transformers; it is never substituted for the line metric.
    return {}


def stage_documents(result, result_path, arm, provenance, errors):
    stages = result.get("stage_outputs", result.get("stages", {}))
    if isinstance(stages, list):
        stages = {s.get("stage", s.get("stage_identity", str(i))): s for i, s in enumerate(stages)}
    if not isinstance(stages, dict):
        stages = {}
    if arm == "B2" and not stages:
        stage_path = result_path.parent / "output/M_STAGE_RESULT.json" if result_path else None
        if stage_path and stage_path.exists():
            value,_=load_receipt(stage_path,provenance,errors)
        else:
            value=result.get("M", result.get("scientific", result))
        stages = {"M": value}
    answer = {}
    for name in (("M",) if arm == "B2" else ("A1", "M1", "A2", "M2")):
        value = stages.get(name)
        if isinstance(value, dict) and "path" in value and len(value) <= 5:
            value, _ = load_receipt(value, provenance, errors)
        elif isinstance(value, str):
            value, _ = load_receipt(value, provenance, errors)
        if not value and result_path:
            for p in (result_path.parent / f"output/{name}/STAGE_RESULT.json",
                      result_path.parent / f"output/{name}/M_STAGE_RESULT.json"):
                if p.exists():
                    value, _ = load_receipt(p, provenance, errors)
                    break
        value = dict(value) if isinstance(value, dict) else {}
        state=result.get("stage_native_accounting",{}).get(name)
        ledger_ref=result.get("stage_native_ledger_receipts",{}).get(name)
        if ledger_ref:
            actual_ledger,_=load_receipt(ledger_ref,provenance,errors)
            if actual_ledger:
                value["__report_stage_wall_seconds"]=actual_ledger.get("wall_seconds")
        if not any(not key.startswith("__report_") for key in value) and state in ("MEASURED","NOT_ENTERED","UNKNOWN"):
            value.update(native_runtime_seconds=result.get("stage_native_runtime",{}).get(name),
                         termination_reason=state,native_accounting_state=state)
        elif state:
            value["native_accounting_state"]=state
        answer[name] = value
    return answer


def stage_row(arm, day, stage, document, result_path):
    wrapper = document
    if isinstance(document.get("source_result"), dict):
        document = dict(document["source_result"])
    ledger = wrapper.get("ledger_receipt", {})
    if isinstance(ledger, str):
        ledger = json.loads(ledger)
    bounds = wrapper.get("global_evidence", {})
    physical = wrapper.get("physical_evidence", {})
    identity = document.get("stage_identity", {})
    request = wrapper.get("request", {})
    authority = request.get("authority", {})
    fields = document.get("fields", {})
    feasibility = first(document, "feasible_accepted", "FULL_feasible_accepted")
    if stage.startswith("A") and feasibility is None:
        feasibility = physical.get("original_integer_physical_verified")
    certified = coalesce(first(document, "global_gap_certified", "GLOBAL_GAP_CERTIFIED"), bounds.get("global_gap_certified"))
    upper = coalesce(first(document,"verified_UB","UB","exact_Global_UB","exact_UB"),fields.get("UB"),bounds.get("exact_UB"))
    lower = coalesce(first(document,"certified_Global_LB","independent_Global_LB","exact_Global_LB"),fields.get("independent_Global_LB"))
    if lower is None and bounds.get("original_global_bound_verified") is True and bounds.get("bound_scope")=="STAGE_FIXED_INPUT_GLOBAL":
        lower=bounds.get("exact_LB")
    upper,lower=finite(upper),finite(lower)
    measured_gap=(upper-lower)/abs(upper) if upper is not None and lower is not None and upper>0 else 0. if upper==lower==0 else None
    target=.03 if stage.startswith("M") else .005
    claim_valid=certified is True and measured_gap is not None and 0<=lower<=upper and measured_gap<=target+1e-14
    if stage.startswith("A") and certified is None:
        claim_valid=bounds.get("original_global_bound_verified") is True and measured_gap is not None and measured_gap<=target
    row = dict(arm=arm, day=day, stage=stage,
               feasible_accepted=feasibility if isinstance(feasibility, bool) else None,
               global_gap_certified=claim_valid if document else None,
               global_gap_claim=certified,
               gap_claim_consistent=claim_valid if certified is True else None,
               verified_UB=upper, certified_Global_LB=lower,
               certified_gap=finite(coalesce(first(document, "certified_gap", "global_gap"), fields.get("certified_gap"),measured_gap)),
               native_best_bound_diagnostic=finite(document.get("native_best_bound_diagnostic")),
               termination_reason=first(document, "termination_reason", "status"),
               native_runtime_seconds=finite(coalesce(first(document, "native_runtime_seconds", "Native_Runtime", "Native_runtime", "native_seconds"),ledger.get("measured_native_runtime"))),
               stage_wall_seconds=finite(coalesce(first(document, "stage_wall_seconds", "wall_seconds", "optimization_seconds"),wrapper.get("__report_stage_wall_seconds"),ledger.get("wall_seconds"),ledger.get("wall_elapsed_seconds"))),
               native_accounting_state=coalesce(wrapper.get("native_accounting_state"),document.get("native_accounting_state")),
               scientific_case_sha=coalesce(first(document, "scientific_case_sha", "case_sha"),wrapper.get("model_sha")),
               matrix_sha=coalesce(first(document, "matrix_sha", "Matrix_SHA"),bounds.get("original_model_sha")),
               domain_sha=coalesce(first(document, "domain_sha", "Domain_SHA"),bounds.get("global_domain_sha")),
               fixed_input_sha=coalesce(first(document, "fixed_input_sha", "fixed_AIDC_SHA"),identity.get("fixed_input_sha"),ledger.get("fixed_input_sha")),
               source_sha=coalesce(first(document, "source_sha", "source_SHA", "Source_SHA"),identity.get("source_SHA"),ledger.get("source_sha"),authority.get("source_sha")),
               initial_UB=finite(first(document, "initial_UB", "initial_verified_UB")),
               result_path=str(result_path) if result_path else None)
    row["native_budget_seconds"] = 1800 if stage.startswith("M") else None
    row["native_budget_overrun_seconds"] = (max(0., row["native_runtime_seconds"] - 1800)
                                               if stage.startswith("M") and row["native_runtime_seconds"] is not None else None)
    row["UB_improvement"] = (row["initial_UB"] - row["verified_UB"]
                              if row["initial_UB"] is not None and row["verified_UB"] is not None else None)
    return row


def mess_statistics(result, evaluation, result_path, provenance, errors, documents=None):
    statistics = dict(result.get("mess_statistics") or {})
    for key in ("movement_count", "movement_energy_kwh", "dispatch_utilization_fraction",
                "charge_energy_kwh", "discharge_energy_kwh", "reactive_energy_kvarh", "SOC_min_kwh", "SOC_max_kwh"):
        statistics.setdefault(key, None)
    scientific=result.get("scientific",{})
    plan=scientific.get("mess",result.get("mess",{})) or {}
    stage=(documents or {}).get("M2",{})
    if not plan and stage.get("mess",{}).get("variables_json"):
        variables=json.loads(stage["mess"]["variables_json"])
        plan={"routes":variables.get("movement"),"SOC_kwh":variables.get("SOC")}
    if plan:
        routes=plan.get("routes")
        if isinstance(routes,list) and all(isinstance(row,dict) and finite(row.get("energy_kwh")) is not None for row in routes):
            statistics["movement_count"]=len(routes)
            statistics["movement_energy_kwh"]=sum(float(row["energy_kwh"]) for row in routes)
        if plan.get("SOC_kwh") is not None:
            soc=np.asarray(plan["SOC_kwh"],float)
            if np.isfinite(soc).all():
                statistics["SOC_min_kwh"]=float(soc.min());statistics["SOC_max_kwh"]=float(soc.max())
    folder = evaluation.get("Actual", {}).get("folder")
    p = Path(folder) / "ACTUAL_MESS_TRAJECTORY.npz" if folder else None
    if p and p.exists():
        try:
            provenance[str(p.resolve())] = record(p)
            with np.load(p, allow_pickle=False) as archive:
                power = archive["P_kw"]
                reactive = archive["Q_kvar"]
                if power.shape == (96, 4) and np.isfinite(power).all():
                    statistics["dispatch_utilization_fraction"] = float(np.count_nonzero(np.abs(power) > 1e-8) / power.size)
                    statistics["charge_energy_kwh"] = float(np.maximum(-power, 0).sum() * .25)
                    statistics["discharge_energy_kwh"] = float(np.maximum(power, 0).sum() * .25)
                    statistics["reactive_energy_kvarh"] = float(np.abs(reactive).sum() * .25)
                if "SOC_kwh" in archive:
                    statistics["SOC_min_kwh"] = float(archive["SOC_kwh"].min())
                    statistics["SOC_max_kwh"] = float(archive["SOC_kwh"].max())
        except (KeyError, ValueError, OSError) as error:
            errors.append({"path": str(p), "error": str(error)})
    # Location transitions alone do not count travel arcs or determine travel energy.
    return statistics


def physical_row(arm, day, evaluation, metric, result_path):
    summary = evaluation.get("summary", evaluation.get("Fresh", {}).get("summary", {}))
    counts = {k: summary.get(k) for k in ("voltage_violation_count", "line_current_violation_count",
               "transformer_current_violation_count", "transformer_kva_violation_count")}
    converged = metric.get("convergence_count")
    complete = (evaluation.get("PASS") is True or evaluation.get("Fresh",{}).get("PASS") is True) and converged == 96
    zero_violations = all(v == 0 for v in counts.values())
    return dict(arm=arm, day=day, fresh_replay_completed=complete,
                actual_fresh_physical_pass=complete and zero_violations,
                physical_violation=summary.get("physical_violation"), **counts,
                fresh_convergence_failure_count=96-converged if converged is not None else None,
                Vmin_pu=finite(summary.get("Vmin_pu")), Vmax_pu=finite(summary.get("Vmax_pu")),
                Actual_reoptimization=evaluation.get("Actual_reoptimization"),
                local_PQ_repair=evaluation.get("local_PQ_repair"), global_PQ_repair=evaluation.get("global_PQ_repair"),
                result_path=str(result_path) if result_path else None)


def summarize(campaign_root, manifest_path=None, output_root=None):
    """Write a snapshot with 62 explicit official dates; return its status document.

    The controller can call this after each result. Manifest keys accepted:
    B1_results/b1_results, date_results/results, b0_reclassification,
    line_current_authority_csv. Existing journals/results are never written.
    """
    root = Path(campaign_root).resolve()
    output = Path(output_root).resolve() if output_root else root / "reports"
    output.mkdir(parents=True, exist_ok=True)
    provenance, errors = {}, []
    manifest_path = Path(manifest_path) if manifest_path else next((root / name for name in
                         ("COMMON_U4_CAMPAIGN_MANIFEST.json", "COMMON_U4_QUALIFICATION_MANIFEST.json", "CAMPAIGN_MANIFEST.json", "AUTONOMOUS_MANIFEST.json") if (root/name).exists()), None)
    manifest, _ = load_receipt(manifest_path, provenance, errors) if manifest_path else ({}, None)
    manifest = manifest or {}
    if manifest.get("qualification_manifest"):
        qualification,_=load_receipt(manifest["qualification_manifest"],provenance,errors)
        if qualification:manifest=dict(qualification,**manifest)
    state_path = next((root / name for name in ("COMMON_U4_CAMPAIGN_STATE.json", "CAMPAIGN_STATE.json", "SUPERVISOR_STATE.json", "EXECUTION_STATUS.json")
                       if (root/name).exists()), None)
    state = read(state_path) if state_path else {}
    if state_path:
        provenance[str(state_path.resolve())] = record(state_path)
    baseline_manifest = manifest
    if not manifest.get("B1_results", manifest.get("b1_results")):
        default_baseline = Path(manifest.get("baseline_manifest", OLD_AUTONOMOUS / "AUTONOMOUS_MANIFEST.json"))
        baseline_manifest, _ = load_receipt(default_baseline, provenance, errors)
        baseline_manifest = baseline_manifest or {}
    limits = line_authority(manifest, provenance, errors)
    b0, _ = load_receipt(manifest.get("b0_reclassification", AUTHORITY / "MAY_B0_CURRENT_RECLASSIFICATION.json"), provenance, errors)
    b0_rows, b0_refs = {}, []
    if b0:
        for ref in b0.get("source_files", []):
            try:
                actual = record(ref["path"])
                if (actual["sha256"] != ref["sha256"] or actual["bytes"] != ref["bytes"]
                        or Path(actual["path"]).resolve() != Path(ref["path"]).resolve()):
                    raise ValueError("B0_SOURCE_SHA_MISMATCH")
                day = next(d for d in DAYS if d.replace("-", "") in ref["path"])
                b0_rows[day] = current_metric(ref["path"], limits, provenance)
                b0_refs.append(dict(actual, declared_path=ref["path"]))
            except (OSError, ValueError, KeyError, StopIteration) as error:
                errors.append({"path": ref.get("path"), "error": str(error)})
    data, physical, stages, executions, movement, attempts = {}, [], [], [], [], []
    for arm in ("B1", "B2", "B3"):
        for day in DAYS:
            r, path = result_for(root, baseline_manifest if arm == "B1" else manifest,
                                 state, arm, day, provenance, errors)
            r = r or {}
            evaluation = evaluation_of(r, path, provenance, errors)
            metric = metric_from_result(r, path, evaluation, limits, provenance, errors)
            p = physical_row(arm, day, evaluation, metric, path)
            physical.append(p)
            fields = r.get("fields", {})
            planning = finite(coalesce(first(r, "planning_rho_max", "verified_UB"), fields.get("planning_rho_max")))
            data[(arm,day)] = dict(metric=metric, physical=p, planning=planning, result=r, path=path)
            if arm == "B1":
                continue
            documents = stage_documents(r, path, arm, provenance, errors)
            local_stages = [stage_row(arm, day, name, document, path) for name,document in documents.items()]
            stages += local_stages
            m_rows = [s for s in local_stages if s["stage"].startswith("M")]
            physical_feasible = bool(m_rows) and all(s["feasible_accepted"] is True for s in m_rows)
            source = first(r, "source_sha", "source_SHA", "implementation_SHA")
            expected = manifest.get("source_sha", manifest.get("source_SHA", manifest.get("execution_SHA",manifest.get(arm+"_source_SHA"))))
            source_match = source == expected if expected else None
            operational_status = state.get("dates", {}).get(arm+"/"+day, {}).get("status", "PENDING")
            status = r.get("status", operational_status)
            if r and p["fresh_replay_completed"] and not p["actual_fresh_physical_pass"]:
                status = "ACTUAL_AC_FAILED"
            elif r.get("PASS") is True and physical_feasible and p["actual_fresh_physical_pass"]:
                status = "COMPLETED_PHYSICAL_PASS"
            executions.append(dict(arm=arm,day=day,status=status,
                feasible_accepted=physical_feasible,global_gap_certified=all(s["global_gap_certified"] is True for s in m_rows),
                actual_fresh_completed=p["fresh_replay_completed"],actual_fresh_physical_pass=p["actual_fresh_physical_pass"],
                actual_maximum_line_loading_percent=metric.get("actual_maximum_line_loading_percent"),
                source_sha=source,expected_source_sha=expected,source_match=source_match,
                result_receipt=record(path) if path and r else None,
                date_wall_seconds=finite(first(r,"worker_wall_seconds","total_worker_wall_seconds","total_date_wall_seconds")),
                stage_count=len(documents),error=first(r,"error","failure_reason","reason","termination_reason")))
            movement.append(dict(arm=arm,day=day,**mess_statistics(r,evaluation,path,provenance,errors,documents)))
            for attempt_path in sorted((root/"dates"/arm/day).glob("attempts/*/RESULT.json")):
                try:
                    ar=read(attempt_path)
                    attempts.append(dict(arm=arm,day=day,attempt=attempt_path.parent.name,status=ar.get("status"),
                        native_runtime_seconds=finite(first(ar,"native_runtime_seconds","Native_Runtime")),
                        wall_seconds=finite(first(ar,"total_worker_wall_seconds","total_date_wall_seconds","wall_seconds")),
                        result_receipt=record(attempt_path)))
                except (ValueError,OSError) as error:
                    errors.append({"path":str(attempt_path),"error":str(error)})
    comparison=[]
    for day in DAYS:
        row={"day":day,"B0_actual_line_loading_percent":b0_rows.get(day,{}).get("actual_maximum_line_loading_percent")}
        for arm in ("B1","B2","B3"):
            d=data[(arm,day)];value=d["metric"].get("actual_maximum_line_loading_percent")
            row[arm+"_actual_line_loading_percent"]=value
            row[arm+"_actual_physical_pass"]=d["physical"]["actual_fresh_physical_pass"]
            row[arm+"_planning_rho_max"]=d["planning"]
            row[arm+"_planning_to_actual_line_difference_pp"]=value-100*d["planning"] if value is not None and d["planning"] is not None else None
            row[arm+"_result_SHA"]=record(d["path"])["sha256"] if d["path"] and d["result"] else None
        for left,right in (("B2","B1"),("B3","B1"),("B3","B2")):
            a,b=row[left+"_actual_line_loading_percent"],row[right+"_actual_line_loading_percent"]
            row[left+"_minus_"+right+"_pp"]=a-b if a is not None and b is not None else None
            row[left+"_"+right+"_paired_physical_valid"]=row[left+"_actual_physical_pass"] and row[right+"_actual_physical_pass"]
        comparison.append(row)
    summary={}
    for arm in ("B2","B3"):
        es=[r for r in executions if r["arm"]==arm];ss=[s for s in stages if s["arm"]==arm and s["stage"].startswith("M")]
        paired=[r[arm+"_minus_B1_pp"] for r in comparison if r[arm+"_B1_paired_physical_valid"] and r[arm+"_minus_B1_pp"] is not None]
        native=[r["native_runtime_seconds"] for r in ss]
        all_stage_native=[r["native_runtime_seconds"] for r in stages if r["arm"]==arm]
        walls=[r["date_wall_seconds"] for r in es]
        summary[arm]=dict(total_dates=31,result_dates=sum(r["result_receipt"] is not None for r in es),
            physical_feasible_dates=sum(r["feasible_accepted"] for r in es),
            actual_fresh_completed_dates=sum(r["actual_fresh_completed"] for r in es),
            actual_fresh_physical_pass_dates=sum(r["actual_fresh_physical_pass"] for r in es),
            source_verified_dates=sum(r["source_match"] is True for r in es),
            status_counts=dict(Counter(r["status"] for r in es)),
            feasible_acceptance_rate=sum(s["feasible_accepted"] is True for s in ss)/len(ss),
            global_gap_certification_rate=sum(s["global_gap_certified"] is True for s in ss)/len(ss),
            native_runtime_known_seconds=sum(v for v in native if v is not None),
            native_runtime_unknown_stages=sum(v is None for v in native),
            all_stage_native_runtime_known_seconds=sum(v for v in all_stage_native if v is not None),
            all_stage_native_runtime_unknown_stages=sum(v is None for v in all_stage_native),
            date_worker_wall_known_seconds=sum(v for v in walls if v is not None),
            date_worker_wall_unknown_dates=sum(v is None for v in walls),
            paired_B1_physical_valid_dates=len(paired),paired_mean_difference_pp=float(np.mean(paired)) if paired else None,
            all_31_verified_results=sum(r["status"]=="COMPLETED_PHYSICAL_PASS" and r["source_match"] is True for r in es)==31)
    execution_version=manifest.get("algorithm_version","HISTORICAL_PRE_COMMON_U4_UNQUALIFIED")
    status=dict(schema="V42_COMMON_MAY31_REPORT_V1",algorithm_version=execution_version,report_target_algorithm=ALGORITHM,
        generated_UTC=datetime.now(timezone.utc).isoformat(),campaign_root=str(root),
        official_date_count=62,summary=summary,dates=executions,attempts=attempts,
        baseline_B0_verified_raw_dates=len(b0_rows),baseline_B1_result_dates=sum(bool(data[("B1",d)]["result"]) for d in DAYS),
        baseline_B1_actual_fresh_physical_pass_dates=sum(data[("B1",d)]["physical"]["actual_fresh_physical_pass"] for d in DAYS),
        audit_errors=errors,missing_values="null JSON / blank CSV; never zero",paper_experiment_usable=all(s["all_31_verified_results"] for s in summary.values()) and not errors)
    write_csv(output/"B2_B3_ACTUAL_COMPARISON.csv",comparison)
    write_csv(output/"MAY31_STAGE_RUNTIME.csv",[{k:v for k,v in s.items() if k in
        ("arm","day","stage","native_runtime_seconds","stage_wall_seconds","native_budget_seconds","native_budget_overrun_seconds","initial_UB","verified_UB","UB_improvement","termination_reason","result_path")} for s in stages])
    write_csv(output/"MAY31_FEASIBLE_GAP_AUDIT.csv",stages)
    write_csv(output/"MAY31_PHYSICAL_VIOLATION_AUDIT.csv",physical)
    write_csv(output/"MAY31_MESS_OPERATION.csv",movement)
    write_json(output/"MAY31_EXECUTION_STATUS.json",status)
    write_json(output/"MAY31_SOURCE_MODEL_SHA_MANIFEST.json",dict(schema="V42_COMMON_REPORT_SHA_V1",files=list(provenance.values()),
        execution_source_SHA=coalesce(manifest.get("source_SHA"),manifest.get("execution_SHA")),
        execution_source_commit=manifest.get("source_commit"),execution_sources=manifest.get("execution_sources",{}),
        input_receipts=manifest.get("input_receipts",{}),stage_identities=stages,
        line_authority_csv=manifest.get("line_current_authority_csv",str(AUTHORITY/"LINE_CURRENT_AUTHORITY_UNCHANGED.csv")),B0_source_files=b0_refs))
    for arm in ("B2","B3"):
        s=summary[arm]
        lines=[f"# {arm} 2025년 5월 캠페인 결과", "", f"실행 알고리즘: `{execution_version}`. 새 통합 목표: `{ALGORITHM}`.", "",
            f"실제 결과 파일 {s['result_dates']}/31일, M 물리 가능해 수용 {s['physical_feasible_dates']}/31일, Actual/Fresh 실행 {s['actual_fresh_completed_dates']}/31일, Actual/Fresh 무위반 {s['actual_fresh_physical_pass_dates']}/31일.","",
            f"동일 소스 확인 {s['source_verified_dates']}/31일. M 단계 인증률 {100*s['global_gap_certification_rate']:.2f}%. 알려진 M Native Runtime {s['native_runtime_known_seconds']:.3f}초; 시간 미상 단계 {s['native_runtime_unknown_stages']}개.","",
            f"B1과 물리 유효 공통 날짜 {s['paired_B1_physical_valid_dates']}일. 평균 Actual 최대선로부하율 차이(%p): {s['paired_mean_difference_pp'] if s['paired_mean_difference_pp'] is not None else '미확보'}.","",
            "최대선로부하율은 원본 Actual 전류에서 선로·상별 Line NormAmps로 다시 계산한다. 변압기는 제외한다. 미완료/실패일의 수치는 공란이다.","",
            "B1은 31일 Replay를 완료했으나 May28에 전압 위반 2개를 기록했다. 해당 날짜는 무위반 Paired Comparison에서 제외되며 원본 증거는 보존된다.","",
            "| 날짜 | 상태 | Actual 최대선로부하율(%) | 무위반 |", "|---|---|---:|---|"]
        for e in executions:
            if e["arm"]==arm:
                value=e["actual_maximum_line_loading_percent"]
                lines.append(f"| {e['day']} | {e['status']} | {value:.6f}"+f" | {e['actual_fresh_physical_pass']} |" if value is not None else f"| {e['day']} | {e['status']} |  | {e['actual_fresh_physical_pass']} |")
        (output/f"{arm}_MAY31_CAMPAIGN_RESULT_KO.md").write_text("\n".join(lines)+"\n",encoding="utf8")
    failure_lines=["# 5월 실패·미완료 및 재시도 보고", "", "실패 기록을 삭제하거나 상태를 성공으로 바꾸지 않는다. 이전 Attempt 비용은 원본 Ledger에서 유지된다.", "",
        "| Case | 날짜 | 상태 | 원인 |", "|---|---|---|---|"]
    for e in executions:
        if e["status"]!="COMPLETED_PHYSICAL_PASS":
            failure_lines.append(f"| {e['arm']} | {e['day']} | {e['status']} | {str(e['error'] or '결과 또는 후속 검증 미완료').replace('|','/').replace(chr(10),' ')} |")
    failure_lines += ["",f"보고 자료 감사 오류 {len(errors)}개. 오류 상세는 MAY31_EXECUTION_STATUS.json을 참조한다."]
    (output/"MAY31_FAILURE_AND_RETRY_REPORT_KO.md").write_text("\n".join(failure_lines)+"\n",encoding="utf8")
    algorithm_doc=output/"FINAL_COMMON_MESS_ALGORITHM_KO.md"
    if not algorithm_doc.exists():
        algorithm_doc.write_text(f"# 공통 MESS 알고리즘\n\n버전: `{ALGORITHM}`. B2 M, B3 M1/M2의 공통 U4 Neighborhood 엔진. 각 M 단계의 초기해 및 탐색을 합친 Native 예산은 1,800초이다. FULL 물리 가능해 수용과 동일 Case의 Global Gap 인증은 독립 필드이다. A1/A2 인증 계약은 유지한다.\n\n이 보고서는 실행된 결과와 원본 전류 증거만 집계한다. 결과가 없는 날짜는 완료로 표시하지 않는다.\n",encoding="utf8")
    plots(output,comparison,stages,movement)
    return status


def plots(output,comparison,stages,movement):
    try:
        import matplotlib
    except ImportError:
        return svg_plots(output, comparison, stages, movement)
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    def values(rows,key):return [r.get(key) if r.get(key) is not None else float("nan") for r in rows]
    def save(figure,name):
        figure.tight_layout();figure.savefig(output/(name+".svg"));figure.savefig(output/(name+".png"),dpi=160);plt.close(figure)
    x=list(range(1,32));fig,ax=plt.subplots(figsize=(11,4))
    for arm in ("B1","B2","B3"):ax.plot(x,values(comparison,arm+"_actual_line_loading_percent"),label=arm,marker=".")
    ax.set(xlabel="May 2025 day",ylabel="Actual maximum line loading (%)",xticks=x);ax.legend();ax.grid(alpha=.25)
    save(fig,"01_ACTUAL_LINE_LOADING")
    fig,ax=plt.subplots(figsize=(11,4))
    for arm in ("B2","B3"):
        rows=[dict(value=r[arm+"_minus_B1_pp"] if r[arm+"_B1_paired_physical_valid"] else None) for r in comparison]
        ax.plot(x,values(rows,"value"),label=arm+" minus B1",marker=".")
    ax.axhline(0,color="grey",lw=.8);ax.set(xlabel="May 2025 day",ylabel="Paired difference (percentage points)",xticks=x);ax.legend();ax.grid(alpha=.25)
    save(fig,"02_PAIRED_ACTUAL_DIFFERENCE")
    fig,axs=plt.subplots(2,1,figsize=(11,7),sharex=True)
    for arm,stage in (("B2","M"),("B3","M1"),("B3","M2")):
        rows=[r for r in stages if r["arm"]==arm and r["stage"]==stage]
        axs[0].plot(x,values(rows,"native_runtime_seconds"),label=arm+" "+stage,marker=".")
        axs[1].plot(x,values(rows,"UB_improvement"),label=arm+" "+stage,marker=".")
    axs[0].axhline(1800,color="grey",ls="--",label="1800 second budget");axs[0].set(ylabel="Cumulative Native Runtime (s)");axs[0].legend();axs[1].set(xlabel="May 2025 day",ylabel="Verified UB reduction",xticks=x)
    save(fig,"03_M_RUNTIME_AND_UB")
    fig,axs=plt.subplots(3,1,figsize=(11,8),sharex=True)
    for arm in ("B2","B3"):
        rows=[r for r in movement if r["arm"]==arm]
        for ax,key,label in zip(axs,("movement_count","movement_energy_kwh","dispatch_utilization_fraction"),("Travel arc count","Travel energy (kWh)","P dispatch slot fraction")):
            ax.plot(x,values(rows,key),label=arm,marker=".");ax.set_ylabel(label);ax.legend()
    axs[-1].set(xlabel="May 2025 day",xticks=x)
    save(fig,"04_MESS_OPERATION")


def svg_plots(output, comparison, stages, movement):
    """Standard SVG fallback for execution environments without Matplotlib."""
    from html import escape
    colors=("#255b88","#c04d27","#298067")
    def panel(series, label, top, reference=None):
        known=[value for _, values in series for value in values if value is not None and math.isfinite(value)]
        if reference is not None:known.append(reference)
        low, high=(min(known),max(known)) if known else (0.,1.)
        if low==high:low-=max(abs(low)*.05,.5);high+=max(abs(high)*.05,.5)
        pad=(high-low)*.12;low-=pad;high+=pad
        def point(day,value):return (90+(day-1)*29,(top+170)-(value-low)/(high-low)*145)
        body=[f'<text x="90" y="{top+14}" font-size="14" font-weight="600">{escape(label)}</text>']
        for i in range(5):
            value=low+(high-low)*i/4; _, y=point(1,value)
            body += [f'<line x1="90" x2="960" y1="{y:.2f}" y2="{y:.2f}" stroke="#dde3e9"/>',
                     f'<text x="80" y="{y+4:.2f}" text-anchor="end" font-size="11">{value:.3g}</text>']
        if reference is not None:
            _,y=point(1,reference);body.append(f'<line x1="90" x2="960" y1="{y:.2f}" y2="{y:.2f}" stroke="#888" stroke-dasharray="5 4"/>')
        for j,(name,values) in enumerate(series):
            color=colors[j%len(colors)];segment=[]
            def flush():
                if len(segment)>1:body.append('<polyline points="'+' '.join(segment)+f'" fill="none" stroke="{color}" stroke-width="1.8"/>')
                segment.clear()
            for day,value in enumerate(values,1):
                if value is None or not math.isfinite(value):flush();continue
                x,y=point(day,value);segment.append(f'{x:.2f},{y:.2f}')
                body.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="2.2" fill="{color}"><title>{escape(name)} May {day}: {value:.8g}</title></circle>')
            flush();body.append(f'<text x="{90+j*210}" y="{top+199}" font-size="12" fill="{color}">{escape(name)}</text>')
        for day in range(1,32):
            x,_=point(day,low);body.append(f'<text x="{x:.2f}" y="{top+186}" text-anchor="middle" font-size="10">{day}</text>')
        if not known:body.append(f'<text x="525" y="{top+100}" text-anchor="middle" fill="#777">No verified observations</text>')
        return '\n'.join(body)
    def save(name,title,panels):
        height=80+len(panels)*230
        content=[f'<svg xmlns="http://www.w3.org/2000/svg" width="1050" height="{height}" viewBox="0 0 1050 {height}">',
                 '<rect width="100%" height="100%" fill="white"/>',
                 '<g font-family="Arial, sans-serif" fill="#263746">',
                 f'<text x="90" y="30" font-size="20" font-weight="600">{escape(title)}</text>']
        for i,(series,label,reference) in enumerate(panels):content.append(panel(series,label,50+i*230,reference))
        content += [f'<text x="90" y="{height-14}" font-size="11" fill="#64748b">May 2025 day · Missing values remain gaps; transformer loading is excluded from the line metric.</text>', '</g></svg>']
        (output/(name+'.svg')).write_text('\n'.join(content)+'\n',encoding='utf8')
    def selected(rows,key):return [row.get(key) for row in rows]
    save('01_ACTUAL_LINE_LOADING','Actual maximum line loading',[(
        [(arm,selected(comparison,arm+'_actual_line_loading_percent')) for arm in ('B1','B2','B3')], 'Actual maximum line loading (%)',None)])
    paired=[]
    for arm in ('B2','B3'):
        paired.append((arm+' minus B1',[r[arm+'_minus_B1_pp'] if r[arm+'_B1_paired_physical_valid'] else None for r in comparison]))
    save('02_PAIRED_ACTUAL_DIFFERENCE','Paired Actual line loading difference',[(paired,'Difference (percentage points)',0.)])
    runtime=[];improvement=[]
    for arm,stage in (('B2','M'),('B3','M1'),('B3','M2')):
        rows=[r for r in stages if r['arm']==arm and r['stage']==stage]
        runtime.append((arm+' '+stage,selected(rows,'native_runtime_seconds')))
        improvement.append((arm+' '+stage,selected(rows,'UB_improvement')))
    save('03_M_RUNTIME_AND_UB','M optimization time and verified UB improvement',[(runtime,'Cumulative Native Runtime (seconds)',1800.),(improvement,'Verified UB reduction',None)])
    panels=[]
    for key,label in (('movement_count','Travel arc count'),('movement_energy_kwh','Travel energy (kWh)'),('dispatch_utilization_fraction','P dispatch slot fraction')):
        panels.append(([(arm,selected([r for r in movement if r['arm']==arm],key)) for arm in ('B2','B3')],label,None))
    save('04_MESS_OPERATION','MESS operation by date',panels)


if __name__ == "__main__":
    parser=argparse.ArgumentParser();parser.add_argument("campaign_root");parser.add_argument("--manifest");parser.add_argument("--output")
    args=parser.parse_args();result=summarize(args.campaign_root,args.manifest,args.output)
    print(json.dumps({"summary":result["summary"],"audit_error_count":len(result["audit_errors"])},ensure_ascii=False))
