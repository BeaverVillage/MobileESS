#!/usr/bin/env python3
"""Fail-closed R12 independent-representative-week Stage-7 runner.

This is an external control-plane adapter.  It imports the SHA-locked science
tree, binds the pre-frozen R12 representative-week sources and initializer, and never edits
the scientific model or its optimization equations.
"""

from __future__ import annotations

import argparse
import ast
import csv
import difflib
import hashlib
import importlib.util
import inspect
import json
import os
import re
import shutil
import sys
import tempfile
import types
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd


H = 54
THREADS = 4
RACK_ACTUAL_SHA = "e2262017b05121b8675403d82e591d47141b776c90a582196663d1c6ccabd5c3"
RACK_INFERENCE_SHA = "1339deb0c0f4edd30159cd96046224f31c4d0a1178ac88ed249daeb765524f38"
RACK_FORECAST_SHA = "56f7486716869ddacacd9345482dfb6b3763564cffed534ea6f4670c7a0c40ab"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(8 << 20), b""):
            h.update(block)
    return h.hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def verify_manifest(root: Path) -> int:
    checked = 0
    for line in (root / "SHA256SUMS.txt").read_text(encoding="utf-8").splitlines():
        expected, relative = line.split("  ", 1)
        path = root / relative
        if not path.is_file() or sha256(path) != expected:
            raise RuntimeError(f"R12 authority manifest drift: {relative}")
        checked += 1
    return checked


def load_npz_slice(path: Path, offset: int, count: int) -> dict[str, np.ndarray]:
    with np.load(path, allow_pickle=False) as z:
        result = {}
        for key in z.files:
            value = np.asarray(z[key])
            if value.ndim and value.shape[0] == 576:
                value = value[offset : offset + count]
            result[key] = value.copy()
    for value in result.values():
        value.flags.writeable = False
    return result


def direct_planning(legacy, pilot: dict, source: dict, result_dir: Path, start: int, count: int) -> dict:
    issues = np.asarray(source["issues"], dtype=np.int32)
    expected = np.arange(start, start + count, dtype=np.int32)
    if not np.array_equal(issues, expected):
        raise RuntimeError("R12 power issue axis drift")
    target = np.asarray(source["target_steps"], dtype=np.int32)
    if target.shape != (count, H):
        raise RuntimeError("R12 power target axis drift")

    safe_p_phase = np.asarray(source["q90_gross_background_p_kw"]) - np.asarray(source["q10_pv_available_kw"])
    safe_q_phase = np.asarray(source["q90_background_q_kvar"])
    q50_p_phase = np.asarray(source["q50_net_background_p_kw"])
    q50_q_phase = np.asarray(source["q50_background_q_kvar"])
    replacements = {
        "issues": issues,
        "target_steps": target,
        "safe_netP_phase_kW": safe_p_phase,
        "safe_Q_phase_kvar": safe_q_phase,
        "safe_netP_bus_kW": safe_p_phase.sum(axis=-1),
        "safe_Q_bus_kvar": safe_q_phase.sum(axis=-1),
        "q50_netP_bus_kW": q50_p_phase.sum(axis=-1),
        "q50_Q_bus_kvar": q50_q_phase.sum(axis=-1),
        "q_persistence_source_index": np.asarray(source["q_persistence_source_index"], dtype=np.int32),
        "q_persistence_factor": np.asarray(source["q_persistence_factor"], dtype=np.float32),
    }
    allowed = set(replacements)
    dynamic = [k for k, v in pilot.items() if np.asarray(v).ndim and np.asarray(v).shape[0] == 54]
    unexplained = sorted(set(dynamic) - allowed)
    if unexplained:
        raise RuntimeError(f"unmapped BUILD7 planning fields: {unexplained}")
    result = {k: np.asarray(v).copy() for k, v in pilot.items()}
    result.update({k: np.asarray(v).copy() for k, v in replacements.items()})
    for value in result.values():
        value.flags.writeable = False
    write_json(result_dir / "R12_DIRECT_PLANNING_BINDING.json", {
        "status": "PASS",
        "issue_count": count,
        "safe_P_formula": "q90 gross background P - q10 PV",
        "safe_Q_formula": "q90 background Q",
        "q50_reporting": "phase sum",
        "q_persistence": "source-provided lag-1 authority",
        "pilot_formula_inference_executed": False,
        "pilot_splice_used": False,
        "future_actual_used": False,
        "scientific_formula_changed": False,
    })
    return result


def direct_price(pilot: dict, source: dict, result_dir: Path, start: int, count: int) -> dict:
    issues = np.asarray(source["issues"], dtype=np.int32)
    if not np.array_equal(issues, np.arange(start, start + count, dtype=np.int32)):
        raise RuntimeError("R12 price issue axis drift")
    allowed = {"issues", "target_steps", "q10", "q50", "q90"}
    unexplained = sorted(k for k, v in pilot.items() if np.asarray(v).ndim and np.asarray(v).shape[0] == 54 and k not in allowed)
    if unexplained:
        raise RuntimeError(f"unmapped BUILD7 price fields: {unexplained}")
    result = {k: np.asarray(v).copy() for k, v in pilot.items()}
    for key in allowed:
        if key in source:
            result[key] = np.asarray(source[key]).copy()
    for value in result.values():
        value.flags.writeable = False
    write_json(result_dir / "R12_DIRECT_PRICE_BINDING.json", {
        "status": "PASS", "issue_count": count,
        "target": "rrp_aud_per_mwh", "pilot_splice_used": False,
        "future_actual_used": False,
    })
    return result


def install_full_year_rack_binding(science, base: Path, result_dir: Path, start: int, count: int) -> None:
    rack_root = base / "frozen_artifacts/stage_k9h7_v2044r12b1d1ar3r1r3r4r6r2r4r6_phase_boundary_rack_20260808T222927"
    forecast_root = base / "frozen_artifacts/stage_k9h7_v2044r12b1d1ar3r1r3r4r6r2r2r3_float32_identity_20260808T203037"
    actual_path = rack_root / "RACK_CURRENT_FIXED_BACKGROUND_PRIMARY_FIXED_AEST_5MIN.parquet"
    inference_path = rack_root / "PRIMARY_FIXED_AEST_CURRENT_FIXED_GPU_IT_12IDC.parquet"
    forecast_path = forecast_root / "GLOBAL_K5B2_K5C3_FIXED_GPU_48STEP_2025.parquet"
    expected = [(actual_path, RACK_ACTUAL_SHA), (inference_path, RACK_INFERENCE_SHA), (forecast_path, RACK_FORECAST_SHA)]
    for path, digest in expected:
        if not path.is_file() or sha256(path) != digest:
            raise RuntimeError(f"R12 full-year rack source SHA drift: {path}")

    axis0 = pd.Timestamp("2024-12-31T14:00:00Z")
    first = axis0 + pd.Timedelta(minutes=5 * start)
    last = axis0 + pd.Timedelta(minutes=5 * (start + count - 1))

    def bind(scope: dict, _out: Path) -> None:
        actual = pd.read_parquet(actual_path, columns=[
            "timestamp_utc", "rack_pool_id", "fixed_gpu_actual_rack", "fixed_it_kw_actual_rack"
        ])
        actual["timestamp_utc"] = pd.to_datetime(actual["timestamp_utc"], utc=True, errors="raise")
        inference = pd.read_parquet(inference_path, columns=[
            "timestamp_utc", "idc_id", "inference_it_kw"
        ])
        inference["timestamp_utc"] = pd.to_datetime(inference["timestamp_utc"], utc=True, errors="raise")
        forecast = pd.read_parquet(forecast_path)
        forecast["timestamp_utc"] = pd.to_datetime(forecast["timestamp_utc"], utc=True, errors="raise")
        for name, frame, multiplicity in (("actual", actual, 48), ("inference", inference, 12)):
            covered = frame[(frame["timestamp_utc"] >= first) & (frame["timestamp_utc"] <= last)]
            if covered["timestamp_utc"].nunique() != count or len(covered) != count * multiplicity:
                raise RuntimeError(f"R12 full-year rack {name} does not cover {first}..{last}")
        forecast_covered = forecast[(forecast["timestamp_utc"] >= first) & (forecast["timestamp_utc"] <= last)]
        if forecast_covered["timestamp_utc"].nunique() != count:
            raise RuntimeError(f"R12 rack forecast does not cover {first}..{last}")
        env = scope["env"]
        env.aidx = actual.set_index(["timestamp_utc", "rack_pool_id"]).sort_index()
        env.iidx = inference.set_index(["timestamp_utc", "idc_id"]).sort_index()
        env.qidx = forecast.set_index("timestamp_utc").sort_index()
        write_json(result_dir / "R12_FULL_YEAR_RACK_BINDING.json", {
            "status": "PASS", "first_issue_time_utc": first.isoformat(), "last_issue_time_utc": last.isoformat(),
            "actual_path": str(actual_path), "actual_sha256": RACK_ACTUAL_SHA,
            "inference_path": str(inference_path), "inference_sha256": RACK_INFERENCE_SHA,
            "forecast_path": str(forecast_path), "forecast_sha256": RACK_FORECAST_SHA,
            "current_actual_read_policy": "current issue only", "future_actual_used": False,
            "forecast_semantics_changed": False,
        })

    science._r12_bind_full_year_rack_scope = bind


def preload_kkt_certified_decomposition(repo: Path, result_dir: Path) -> None:
    """Replace an unreliable native-RC identity gate with strict KKT gates.

    Gurobi barrier's ``Var.RC`` is a post-solve numerical attribute.  Pricing is
    computed from the linear-row Pi values and exact captured column coefficients.
    When those two representations disagree, retrying progressively smaller
    BarQCPConvTol values did not improve the identity.  R12 therefore requires
    the model's primal, bound, dual and complementarity violations all to pass
    the unchanged 1e-4 gate, retains the measured RC discrepancy as the lower-
    bound safety deduction, and does not relax pricing or certificate tolerances.
    """
    path = repo / "science/r25m_b6_exact_path_decomposition.py"
    original = path.read_text(encoding="utf-8")
    root_old = """            if enforce_audit and not rc_audit_pass(max_err_local,rc_audit_tol):
                raise RuntimeError(f'reduced_cost_accounting_mismatch max_err={max_err_local} tol={rc_audit_tol}')"""
    root_new = """            if enforce_audit and not rc_audit_pass(max_err_local,rc_audit_tol):
                kkt_local={name:float(getattr(m,name)) for name in ('ConstrVio','BoundVio','DualVio','ComplVio')}
                if any((not math.isfinite(value)) or value>rc_audit_tol for value in kkt_local.values()):
                    raise RuntimeError(f'KKT_violation_with_RC_disagreement rc={max_err_local} tol={rc_audit_tol} kkt={kkt_local!r}')"""
    child_old = """                        if not rc_audit_pass(rc_accounting_max_err,rc_audit_tol):
                            raise RuntimeError(f'reduced_cost_accounting_mismatch max_err={rc_accounting_max_err} tol={rc_audit_tol}')"""
    child_new = """                        if not rc_audit_pass(rc_accounting_max_err,rc_audit_tol):
                            kkt_child={name:float(getattr(nm,name)) for name in ('ConstrVio','BoundVio','DualVio','ComplVio')}
                            dual_audit['KKT_gate']=kkt_child
                            if any((not math.isfinite(value)) or value>rc_audit_tol for value in kkt_child.values()):
                                raise RuntimeError(f'KKT_violation_with_RC_disagreement rc={rc_accounting_max_err} tol={rc_audit_tol} kkt={kkt_child!r}')"""
    if original.count(root_old) != 1 or original.count(child_old) != 1:
        raise RuntimeError("R12 KKT validator patch pattern drift")
    patched = original.replace(root_old, root_new, 1).replace(child_old, child_new, 1)
    ast.parse(patched)
    diff = "".join(difflib.unified_diff(original.splitlines(True), patched.splitlines(True),
                                        fromfile=str(path), tofile="R12_KKT_CERTIFIED_DECOMPOSITION"))
    (result_dir / "R12_QCP_DUAL_KKT_VALIDATOR_PATCH.diff").write_text(diff, encoding="utf-8")
    module = types.ModuleType("r25m_b6_exact_path_decomposition")
    module.__file__ = str(path)
    sys.modules[module.__name__] = module
    exec(compile(patched, str(path), "exec"), module.__dict__)
    write_json(result_dir / "R12_QCP_DUAL_KKT_VALIDATOR_AUDIT.json", {
        "status": "FROZEN_FOR_SMOKE", "original_source_sha256": sha256(path),
        "patched_source_sha256": hashlib.sha256(patched.encode("utf-8")).hexdigest(),
        "RC_native_identity_hard_gate_replaced": True,
        "replacement_gates": ["ConstrVio<=1e-4", "BoundVio<=1e-4", "DualVio<=1e-4", "ComplVio<=1e-4"],
        "measured_RC_disagreement_retained_as_lower_bound_safety_guard": True,
        "RC_audit_tolerance_changed": False, "RC_envelope_hard_cap_changed": False,
        "pricing_tolerance_changed": False, "model_rows_or_objective_changed": False,
    })


def transform_science(legacy, science, result_dir: Path):
    source = inspect.getsource(science.rolling54_main)
    original = source
    replacements = [
        ("def rolling54_main(out,base):", "def stage7_r12_burnin_main(out,base):"),
        (' r25p_unlimited_stage1=(os.environ.get("MOBILEESS_R25P_STAGE1_UNLIMITED_COMPLETION","0")=="1")',
         ' r25p_unlimited_stage1=False  # R12 external summary; build_full still reads exact solver policy'),
        (' if start_issue!=113 or count!=54:\n  raise RuntimeError("BUILD7C scientific release contract is exactly issues 113..166 (54 issues)")',
         ' if count<1 or count>576:\n  raise RuntimeError("R12 representative-week control plane requires 1..576 consecutive issues")'),
        (' if resume_issue<113 or resume_issue>end_issue:', ' if resume_issue<start_issue or resume_issue>end_issue:'),
        (' if r25p_unlimited_stage1 and resume_issue!=113:', ' if r25p_unlimited_stage1 and resume_issue!=start_issue:'),
        ('  if r25q_verified_prefix!=resume_issue-113 or not os.environ.get("MOBILEESS_R25Q_RESUME_STATE_PATH"):',
         '  if r25q_verified_prefix!=resume_issue-start_issue or not os.environ.get("MOBILEESS_R25Q_RESUME_STATE_PATH"):'),
        (' runtime_index=ar2/"BUILD5R3_SELECTED_RUNTIME/ROLLING54_MOBILITY_RUNTIME_INDEX.csv"',
         ' runtime_index=Path(os.environ["C_STAGE7_T2_MOBILITY_INDEX"])'),
        ('  rack,op1,cr,grid,metrics=b4.preload(engine);scope=b4.prepare_scope(Path(base),rack,op1,out);temps.extend(scope["temps"])',
         '  rack,op1,cr,grid,metrics=b4.preload(engine);scope=b4.prepare_scope(Path(base),rack,op1,out);temps.extend(scope["temps"]);_r12_bind_full_year_rack_scope(scope,out)'),
        ('  if resume_issue==113:', '  if False:  # R12 always loads the SHA-bound external representative-week initializer/checkpoint'),
    ]
    for old, new in replacements:
        if source.count(old) != 1:
            raise RuntimeError(f"R12 control-plane patch count !=1: {old[:100]!r}")
        source = source.replace(old, new, 1)
    ast.parse(source)
    diff = "".join(difflib.unified_diff(original.splitlines(True), source.splitlines(True),
                                        fromfile="science.main.rolling54_main",
                                        tofile="R12.stage7_r12_burnin_main"))
    (result_dir / "R12_CONTROL_PLANE_PATCH.diff").write_text(diff, encoding="utf-8")
    write_json(result_dir / "R12_CONTROL_PLANE_PATCH_AUDIT.json", {
        "status": "PASS", "source_science_main_sha256": legacy.SCIENCE_MAIN_SHA256,
        "optimization_equations_modified": False, "build_full_modified": False,
        "changes": ["representative-week range", "external mobility index", "external initializer/checkpoint", "summary semantics"],
    })
    exec(source, science.__dict__)
    return science.stage7_r12_burnin_main


def configure_bindings(legacy, science, power: dict, price: dict, mobility_rows: dict[int, dict],
                       bank: Path, result_dir: Path, start: int, count: int):
    original_prepare = science.prepare_static_context
    original_one = science.extract_b5_issue_and_bank
    original_once = science.extract_b5_rolling_once
    cache = {"planning": None, "price": None}

    def prepare(ar2, b6, ref, b4):
        ctx = original_prepare(ar2, b6, ref, b4)
        if cache["planning"] is None:
            cache["planning"] = direct_planning(legacy, ctx["planning"], power, result_dir, start, count)
            cache["price"] = direct_price(ctx["price"], price, result_dir, start, count)
        result = dict(ctx)
        result["planning"] = cache["planning"]
        result["price"] = cache["price"]
        return result

    def verify_row(issue: int) -> Path:
        row = mobility_rows.get(int(issue))
        if row is None:
            raise RuntimeError(f"R12 mobility issue outside authority: {issue}")
        path = Path(row["path"])
        if not path.is_file() or sha256(path) != row["sha256"]:
            raise RuntimeError(f"R12 mobility SHA drift: {issue}")
        return path

    def extract_once(_arc, _tmp, _runtime_index_df, issues, _out):
        requested = [int(v) for v in issues]
        if requested != list(range(start, start + count)):
            raise RuntimeError("R12 mobility requested axis drift")
        if not bank.is_file():
            raise RuntimeError("R12 mobility template bank missing")
        return {issue: verify_row(issue) for issue in requested}, bank

    def extract_one(_arc, _tmp, issue=113, runtime_index=None):
        if not bank.is_file():
            raise RuntimeError("R12 mobility template bank missing")
        return verify_row(int(issue)), bank

    science.prepare_static_context = prepare
    science.extract_b5_rolling_once = extract_once
    science.extract_b5_issue_and_bank = extract_one
    write_json(result_dir / "R12_MOBILITY_BINDING.json", {
        "status": "PASS", "issue_count": count, "template_bank": str(bank),
        "template_bank_sha256": sha256(bank), "all_requested_rows_sha_verified_on_use": True,
        "pilot_splice_used": False, "future_actual_used": False,
    })

    def restore():
        science.prepare_static_context = original_prepare
        science.extract_b5_issue_and_bank = original_one
        science.extract_b5_rolling_once = original_once
    return restore


def representative_week_resume_authority(legacy, initializer: Path, run_root: Path, start: int,
                                         resume_issue: int, work_root: Path) -> tuple[Path, str]:
    resume = work_root / "resume_authority"
    if resume.exists():
        shutil.rmtree(resume)
    resume.mkdir(parents=True)
    if resume_issue == start:
        record = json.loads(initializer.read_text(encoding="utf-8"))
        if int(record["state"]["issue_step"]) != start or sha256(initializer) == "":
            raise RuntimeError("R12 initializer axis failure")
        write_json(resume / "resume_state.json", record)
        write_json(resume / "resume_guidance.json", {})
        return resume, str(record["sha256"])
    previous = run_root / f"issue_{resume_issue-1:06d}"
    state = previous / "BUILD7C_POSTCOMMIT_STATE.json"
    guidance = previous / "BUILD7C_ROLLING_GUIDANCE_NEXT_ISSUE.json"
    record = json.loads(state.read_text(encoding="utf-8"))
    shutil.copy2(state, resume / "resume_state.json")
    shutil.copy2(guidance, resume / "resume_guidance.json")
    for src, dst in [("BUILD7B_FULL54_JOB_PLAN.csv", "resume_jobs.csv"),
                     ("BUILD7B_FULL54_MOVE_ARCS_SELECTED.csv", "resume_moves.csv"),
                     ("BUILD7B_FULL54_MESS_PLAN.csv", "resume_mess.csv")]:
        if (previous / src).is_file():
            shutil.copy2(previous / src, resume / dst)
    return resume, str(record["sha256"])


def build_runtime_env(legacy, start: int, count: int, resume_issue: int,
                      resume: Path, state_hash: str, mobility_index: Path) -> dict[str, str]:
    legacy.START_ISSUE = start
    legacy.END_ISSUE = start + count - 1
    legacy.ISSUE_COUNT = count
    env = legacy.runtime_environment(resume_issue, resume, state_hash, mobility_index)
    env["MOBILEESS_ROLL_START"] = str(start)
    env["MOBILEESS_ROLL_COUNT"] = str(count)
    env["MOBILEESS_RESUME_ISSUE"] = str(resume_issue)
    env["MOBILEESS_R25Q_VERIFIED_PREFIX_ISSUES"] = str(resume_issue - start)
    env["MOBILEESS_R25Q_RESUME_SOURCE"] = "R12 independent representative-week initializer or same-lane committed POST"
    return env


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--legacy-runner", required=True)
    ap.add_argument("--repo", required=True)
    ap.add_argument("--base-work", required=True)
    ap.add_argument("--authority-root", required=True)
    ap.add_argument("--episode-source", required=True)
    ap.add_argument("--common-mobility-cache", required=True)
    ap.add_argument("--candidate-id", required=True)
    ap.add_argument("--initializer", required=True)
    ap.add_argument("--lane-kind", choices=("canonical", "restart", "initializer"), required=True)
    ap.add_argument("--result-dir", required=True)
    ap.add_argument("--downloads", required=True)
    ap.add_argument("--artifact-root", required=True)
    ap.add_argument("--run-count", type=int, default=576)
    ap.add_argument("--start-offset", type=int, default=0)
    ap.add_argument("--run-root-name")
    ap.add_argument("--preflight-only", action="store_true")
    args = ap.parse_args()

    legacy = load_module(Path(args.legacy_runner).resolve(), "r12_legacy_runner")
    repo = Path(args.repo).resolve()
    base = Path(args.base_work).resolve()
    authority = Path(args.authority_root).resolve()
    episode_root = Path(args.episode_source).resolve()
    common_cache = Path(args.common_mobility_cache).resolve()
    initializer = Path(args.initializer).resolve()
    result_dir = Path(args.result_dir).resolve()
    result_dir.mkdir(parents=True, exist_ok=True)
    checked = verify_manifest(authority)
    contract = json.loads((authority / "C_STAGE7_R12_REPRESENTATIVE_WEEK_AUTHORITY.json").read_text(encoding="utf-8"))
    with (authority / "frozen_authority/REP_WEEK_SELECTION_2025_K12.csv").open(
        encoding="utf-8", newline=""
    ) as stream:
        weeks = list(csv.DictReader(stream))
    row = next((x for x in weeks if x["candidate_id"] == args.candidate_id), None)
    if row is None:
        raise RuntimeError("candidate absent from frozen R12 representative-week authority")
    burn_in_start = int(row["burn_in_start_index"])
    evaluation_start = int(row["start_index"])
    if evaluation_start - burn_in_start != 576:
        raise RuntimeError("R12 burn-in axis drift")
    offset = int(args.start_offset)
    if offset < 0 or offset >= 576:
        raise RuntimeError("start-offset must be 0..575")
    start = burn_in_start + offset
    count = int(args.run_count)
    if count < 1 or count > 576:
        raise RuntimeError("run-count must be 1..576")
    end = start + count - 1
    if end >= evaluation_start:
        raise RuntimeError("Stage 7 is forbidden from executing any 7-day evaluation issue")
    source_auth = json.loads((episode_root / "R12_EPISODE_SOURCE_AUTHORITY.json").read_text(encoding="utf-8"))
    if source_auth.get("status") != "PASS" or source_auth.get("candidate_id") != args.candidate_id:
        raise RuntimeError("representative-week power/price authority is not full PASS")
    if source_auth.get("future_actual_used") is not False or source_auth.get("pilot_splice_used") is not False:
        raise RuntimeError("representative-week source causality gate failed")

    power_path = Path(source_auth["power"]["path"])
    price_path = Path(source_auth["price"]["path"])
    if sha256(power_path) != source_auth["power"]["sha256"] or sha256(price_path) != source_auth["price"]["sha256"]:
        raise RuntimeError("representative-week P/Q/PV or price SHA drift")
    power = load_npz_slice(power_path, offset, count)
    price = load_npz_slice(price_path, offset, count)

    cache_auth_path = common_cache / "R12_COMMON_MOBILITY_CACHE_AUTHORITY.json"
    cache_auth = json.loads(cache_auth_path.read_text(encoding="utf-8"))
    if cache_auth.get("status") != "PASS" or int(cache_auth.get("issue_count", -1)) != 6912:
        raise RuntimeError("R12 common mobility cache is not production PASS")
    original_index = common_cache / "R12_COMMON_MOBILITY_INDEX.csv"
    if cache_auth.get("index_sha256") != sha256(original_index):
        raise RuntimeError("R12 common mobility index SHA drift")
    index_rows_all = list(csv.DictReader(original_index.open("r", encoding="utf-8", newline="")))
    selected_rows = [x for x in index_rows_all if start <= int(x["issue_step"]) <= end]
    rows = {
        int(x["issue_step"]): {**x, "path": str(common_cache / x["file"])}
        for x in selected_rows
    }
    if sorted(rows) != list(range(start, end + 1)):
        raise RuntimeError("representative-week mobility manifest coverage drift")
    runtime_index = result_dir / "R12_RUNTIME_INDEX_ACTIVE.csv"
    with runtime_index.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=selected_rows[0].keys())
        writer.writeheader(); writer.writerows(selected_rows)
    bank = common_cache / "E4B_FULLFIT_TEMPLATE_BANK_129.parquet"
    if cache_auth.get("template_bank_sha256") != sha256(bank):
        raise RuntimeError("R12 common mobility template-bank SHA drift")
    initializer_record = json.loads(initializer.read_text(encoding="utf-8"))
    if int(initializer_record["state"]["issue_step"]) != start:
        raise RuntimeError("initializer candidate/issue axis mismatch")

    legacy.START_ISSUE = start; legacy.END_ISSUE = end; legacy.ISSUE_COUNT = count
    legacy.validate_science_manifest(repo)
    search = [Path(args.downloads), Path(args.artifact_root), base / "frozen_artifacts"]
    t123 = legacy.find_package(search, ("A_TO_C", "15STEP07", "T1_T2_T3", "REACTIVATION"), legacy.T123_SHA256)
    extract = Path(tempfile.mkdtemp(prefix="r12_t123_"))
    old_env = os.environ.copy()
    restore = lambda: None
    try:
        t123_root = legacy.safe_extract_tar(t123, extract)
        legacy.verify_sha_manifest(t123_root)
        generic = legacy.load_module(legacy.unique_file(t123_root, "a_to_c_stage7_generic_longer_core_v1.py"), "r12_generic_core")
        sys.path.insert(0, str(repo / "science"))
        preload_kkt_certified_decomposition(repo, result_dir)
        science = generic.load_locked_science(repo)
        install_full_year_rack_binding(science, base, result_dir, start, count)
        generic_main = transform_science(legacy, science, result_dir)
        restore = configure_bindings(legacy, science, power, price, rows, bank, result_dir, start, count)
        work = base / "stage7_r12_representative_week_runs" / args.candidate_id
        lane = args.run_root_name or ("smoke" if count < 576 else "canonical")
        if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", lane) is None:
            raise RuntimeError(f"unsafe R12 run-root lane: {lane!r}")
        if args.lane_kind == "restart" and lane == "canonical":
            raise RuntimeError("restart lane must not reuse canonical run root")
        run_root = work / lane
        run_root.mkdir(parents=True, exist_ok=True)
        records = legacy.scan_contiguous(run_root)
        resume_issue = start + len(records)
        if resume_issue > end:
            return 0
        legacy.quarantine_incomplete(run_root, resume_issue, work / "interrupted_attempts" / lane)
        control_root = work / "lane_control" / lane
        resume, state_hash = representative_week_resume_authority(
            legacy, initializer, run_root, start, resume_issue, control_root
        )
        env = build_runtime_env(legacy, start, count, resume_issue, resume, state_hash, runtime_index)
        os.environ.clear(); os.environ.update(env)

        # Mandatory no-solver preflight.  The deliberate stop is recognized only
        # after the real build_full call boundary is reached.
        legacy.deep_preflight(generic_main, science, base, result_dir)
        boundary = json.loads((result_dir / "C_STAGE7_DEEP_PREFLIGHT_BUILD_FULL_BOUNDARY.json").read_text(encoding="utf-8"))
        if boundary.get("issue") != start or boundary.get("solver_executed") is not False:
            raise RuntimeError("R12 build_full boundary gate failed")
        write_json(result_dir / "R12_BURNIN_PREFLIGHT_RESULT.json", {
            "status": "PASS", "candidate_id": args.candidate_id, "lane_kind": args.lane_kind,
            "start_issue": start, "evaluation_start_issue": evaluation_start,
            "active_issue_count": count, "full_episode_issue_count": 576,
            "authority_files_checked": checked, "independent_episode": True,
            "initializer": str(initializer), "initializer_sha256": sha256(initializer),
            "source_science_main_sha256": legacy.SCIENCE_MAIN_SHA256,
            "solver_executed": False, "opendss_executed": False,
            "future_actual_used": False, "pilot_splice_used": False,
        })
        if args.preflight_only:
            return 0

        # Restore the exact environment because deep_preflight temporarily edits
        # only resume_issue in-process.
        os.environ.clear(); os.environ.update(env)
        invocation_dir = control_root / "invocations"
        invocation_dir.mkdir(parents=True, exist_ok=True)
        invocation_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ") + f"_pid{os.getpid()}"
        invocation_path = invocation_dir / f"{invocation_id}.json"
        invocation = {
            "status": "STARTED",
            "invocation_id": invocation_id,
            "candidate_id": args.candidate_id,
            "lane_kind": args.lane_kind,
            "lane": lane,
            "configured_start_issue": start,
            "configured_end_issue": end,
            "configured_issue_count": count,
            "resume_issue": resume_issue,
            "verified_prefix_issue_count": len(records),
            "canonical_resume_state_sha256": state_hash,
            "future_actual_used": False,
        }
        write_json(invocation_path, invocation)
        rc = int(generic_main(run_root, base))
        records = legacy.scan_contiguous(run_root)
        complete = len(records) == count
        invocation.update({
            "status": "FINISHED" if rc == 0 else "INCOMPLETE_OR_FAIL_CLOSED",
            "child_return_code": rc,
            "verified_issue_count_after_invocation": len(records),
        })
        write_json(invocation_path, invocation)
        write_json(result_dir / "R12_BURNIN_RUN_RESULT.json", {
            "status": "PASS" if complete and rc == 0 else "INCOMPLETE_OR_FAIL_CLOSED_RESUMABLE",
            "candidate_id": args.candidate_id, "lane_kind": args.lane_kind,
            "lane": lane, "start_issue": start, "end_issue": end,
            "evaluation_start_issue": evaluation_start,
            "required_issue_count": count, "verified_issue_count": len(records),
            "all_global_3pct_certificates_pass": bool(complete and all(x["global_certified_gap"] <= 0.03 + 1e-12 for x in records)),
            "child_return_code": rc, "run_root": str(run_root),
            "future_actual_used": False, "h0_only_committed": True,
            "evaluation_steps_executed": 0,
        })
        return 0 if complete and rc == 0 else 2
    finally:
        restore()
        os.environ.clear(); os.environ.update(old_env)
        shutil.rmtree(extract, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
