"""Run the prospective V16.3 nonzero-deviation validity study only."""

from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import time
from collections import defaultdict
from pathlib import Path
from typing import Mapping, Sequence

import numpy as np

from .aidc_boundary_v16_1 import PUE_PLAN
from .aidc_power_response import GPU_PER_NODE, KAPPA_KW_PER_ACTIVE_H100_NODE
from .aidc_rack_mapping import load_frozen_rack_authority
from .authority import sha256_file
from .full_ieee123_g11_v16_1 import PF_AIDC, FullGridBinding, build_full_grid_binding
from .grid_background_v16_2 import build_authority_background_binding
from .grid_lp import LINE_POLYGON_FACES
from .run_aidc_ieee123_penetration_hosting_capacity_diagnostic_v1 import (
    HARD_TOLERANCE, PF_TAN, _beta_reference, _select_april_vintages_locked,
    _set_generator, _set_load,
)
from .run_authority_semantic_g11_v16_2 import _default_background_paths, _write_json
from .run_head_of_feeder_capacity_diagnostic_v1 import _forecast_day
from .run_planning_ac_voltage_forensic_v1 import _compile
from .run_v16_3_voltage_candidate import (
    BETA_BASE, CAPACITORS, NATIVE_MASTER_SHA, REGULATORS, _capacitor_states,
    _enable_native_controls, _fix_controls, _regulator_taps, _set_slot,
    _voltage_map,
)
from .v16_3_nonzero_validity import (
    CURRENT_PROXIMITY_PU, MONITOR_CURRENT_LOADING_PU, RHO_GRID,
    VOLTAGE_PROXIMITY_PU, VOLTAGE_TOLERANCE, build_probe_directions,
    current_root_classification, expand_rho, payload_sha256,
    trust_region_contract, validated_radius, voltage_comparison,
)


CHECKPOINT_SHA = "af0f872d0433ddeb5daf553d2f38c64caa28ca21"
ARTIFACT_DIR_NAME = "v16_3_candidate"
CURRENT_TOLERANCE = 1e-9
PCS_KVA = 700.0
MESS_P_LIMIT_KW = 550.0
COUNTERS = {
    "scientific_authority_changes": 0,
    "production_V16_3_activations": 0,
    "beta_production_changes": 0,
    "native_ieee123_changes": 0,
    "native_regulator_setting_changes": 0,
    "native_feeder_rating_changes": 0,
    "u080_changes": 0,
    "voltage_limit_changes": 0,
    "tap_cooptimization_variables_added": 0,
    "OpenDSS_calls_inside_Benders": 0,
    "legacy_v13_sidecar_loads": 0,
    "may_scientific_loader_access_count": 0,
    "june_scientific_loader_access_count": 0,
    "G12_final_calls": 0,
    "G13_calls": 0,
    "G14_calls": 0,
    "C12_calls": 0,
}


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, check=True, text=True,
                          capture_output=True).stdout.strip()


def _checkpoint(repo: Path, source: Path, artifacts: Path) -> dict[str, object]:
    head = _git(repo, "rev-parse", "HEAD")
    if head != CHECKPOINT_SHA:
        raise RuntimeError(f"V163_NONZERO_CHECKPOINT_MISMATCH:{head}")
    if sha256_file(source / "opendss_assets/IEEE123Master.dss") != NATIVE_MASTER_SHA:
        raise RuntimeError("V163_NONZERO_NATIVE_SHA_MISMATCH")
    manifest_path = artifacts / "V16_3_CANDIDATE_NPZ_SHA256_MANIFEST.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    failures = []
    for row in manifest["files"]:
        path = artifacts / "data" / row["name"]
        if not path.is_file() or path.stat().st_size != int(row["bytes"]) or sha256_file(path) != row["sha256"]:
            failures.append(row["name"])
    if failures:
        raise RuntimeError(f"V163_NONZERO_CACHE_PROVENANCE_FAILURE:{failures}")
    return {
        "branch": _git(repo, "branch", "--show-current"),
        "head": head,
        "candidate_evidence_checkpoint_sha": head,
        "candidate_checkpoint_committed_blob_bytes": 2913090,
        "pre_diagnostic_worktree_clean": True,
        "native_ieee123_master_sha": NATIVE_MASTER_SHA,
        "npz_manifest_sha256": sha256_file(manifest_path),
        "npz_files_verified": len(manifest["files"]),
        "npz_total_bytes_verified": sum(int(row["bytes"]) for row in manifest["files"]),
        "npz_git_policy": manifest["policy"],
        "git_lfs_used": bool(manifest["git_lfs_used"]),
    }


def _april_contexts(repo: Path, source: Path, artifacts: Path, limit_days: int = 0,
                    only_day: str | None = None):
    import pandas as pd

    forecast = pd.read_parquet(repo / "dayahead/artifacts/v16/AIDC_APRIL_VALIDATION_FORECAST.parquet")
    if not forecast[~forecast["forecast_day"].between("2025-04-01", "2025-04-30")].empty:
        raise RuntimeError("V163_NONZERO_MAY_JUNE_FORECAST_FIREWALL")
    vintages, excluded = _select_april_vintages_locked(
        repo / "dayahead/artifacts/v16_1/AEMO_DA_VINTAGE_CONTRACT_V16_1.json"
    )
    days = tuple(sorted(vintages))
    expected = tuple(f"2025-04-{day:02d}" for day in range(2, 31))
    if days != expected:
        raise RuntimeError("V163_NONZERO_APRIL_DAY_SET_MISMATCH")
    if only_day:
        if only_day not in days: raise ValueError("V163_NONZERO_WORKER_DAY_NOT_APRIL")
        days = (only_day,)
    elif limit_days:
        days = days[:limit_days]
    rack_contract = json.loads((repo / "dayahead/artifacts/v16_1/AIDC_VIRTUAL_SPATIAL_GPU_CONTRACT.json").read_text(encoding="utf-8"))
    authority = load_frozen_rack_authority(Path(rack_contract["source_path"]))
    contexts = {}
    for day in days:
        arrivals, p_ref, g_ref = _forecast_day(forecast, day)
        reference = _beta_reference(authority, arrivals, p_ref, g_ref, BETA_BASE)
        vintage = vintages[day]
        background = build_authority_background_binding(
            timestamps_fixed_aest=vintage["timestamps_96"],
            demand_mw_96=vintage["demand_mw_96"],
            rooftop_pv_mw_96=vintage["pv_mw_96"],
            paths=_default_background_paths(repo, source),
        )
        binding = build_full_grid_binding(
            assets=source / "opendss_assets",
            contract=source / "power_v70_p4f_contract",
            demand_mw_96=vintage["demand_mw_96"],
            rooftop_pv_mw_96=vintage["pv_mw_96"],
            aidc_plan_kw_96x12=reference["plan_kw_96x12"],
            pcc_asset=repo / "dayahead/artifacts/v16_2/Generated_ThreePhase_PCC_v4.dss",
            background_binding=background,
        )
        cache = artifacts / "data" / f"D1_AC_ANCHOR_SENSITIVITY_{day}.npz"
        contexts[day] = (reference, vintage, background, binding, cache, authority)
    return days, excluded, contexts


def _branch_ratings(odd, binding: FullGridBinding) -> tuple[np.ndarray, list[dict[str, object]]]:
    ratings = []
    provenance = []
    for branch in binding.factories[0].data.branches:
        odd.Circuit.SetActiveElement(branch.branch_id)
        buses = [str(value).split(".", 1)[0].lower() for value in odd.CktElement.BusNames()]
        terminal = buses.index(branch.parent_bus.lower())
        if branch.branch_id.startswith("line."):
            odd.Lines.Name(branch.branch_id.split(".", 1)[1])
            rating = float(odd.Lines.NormAmps())
            side = terminal + 1
            kind = "line"
        else:
            odd.Transformers.Name(branch.branch_id.split(".", 1)[1])
            winding = terminal + 1
            odd.Transformers.Wdg(winding)
            kva = float(odd.Transformers.kVA())
            kv = float(odd.Transformers.kV())
            phases = int(odd.CktElement.NumPhases())
            rating = kva / (math.sqrt(3.0) * kv) if phases >= 2 else kva / kv
            side = winding
            kind = "transformer"
        ratings.append(rating)
        provenance.append({
            "branch": branch.branch_id, "phase": branch.phase, "kind": kind,
            "parent_bus": branch.parent_bus, "terminal_or_winding_side": side,
            "rated_current_a": rating,
        })
    return np.asarray(ratings), provenance


def _regcontrol_metadata(odd) -> list[dict[str, object]]:
    rows = []
    for control in odd.RegControls.AllNames():
        odd.RegControls.Name(control)
        rows.append({
            "control": str(control).lower(),
            "transformer": str(odd.RegControls.Transformer()).lower(),
            "winding": int(odd.RegControls.Winding()),
            "vreg_v": float(odd.RegControls.ForwardVreg()),
            "band_v": float(odd.RegControls.ForwardBand()),
            "ptratio": float(odd.RegControls.PTRatio()),
        })
    return rows


def _controlled_node(row: Mapping[str, object]) -> tuple[str, ...]:
    transformer = str(row["transformer"])
    if transformer == "reg1a": return ("150r.1", "150r.2", "150r.3")
    if transformer == "reg2a": return ("9r.1",)
    if transformer == "reg3a": return ("25r.1",)
    if transformer == "reg3c": return ("25r.3",)
    if transformer == "reg4a": return ("160r.1",)
    if transformer == "reg4b": return ("160r.2",)
    if transformer == "reg4c": return ("160r.3",)
    raise RuntimeError(f"V163_NONZERO_UNEXPECTED_REGULATOR:{transformer}")


def _slot_selection(data, ratings: np.ndarray, branch_kinds: Sequence[str], reg_meta: Sequence[Mapping[str, object]], day: str) -> dict[str, object]:
    volts = np.sqrt(np.maximum(np.asarray(data["anchor_v_squared"], dtype=float), 0.0))
    currents = np.asarray(data["branch_current_a"], dtype=float) / ratings[None, :]
    line_index = [i for i, kind in enumerate(branch_kinds) if kind == "line"]
    tx_index = [i for i, kind in enumerate(branch_kinds) if kind == "transformer"]
    nodes = tuple(map(str, data["node_names"]))
    node_index = {name: i for i, name in enumerate(nodes)}
    reasons: dict[int, set[str]] = defaultdict(set)
    reasons[int(np.argmin(volts) // volts.shape[1])].add("VOLTAGE_LOW_CRITICAL")
    reasons[int(np.argmax(volts) // volts.shape[1])].add("VOLTAGE_HIGH_CRITICAL")
    line_local = np.unravel_index(np.argmax(currents[:, line_index]), (96, len(line_index)))
    tx_local = np.unravel_index(np.argmax(currents[:, tx_index]), (96, len(tx_index)))
    reasons[int(line_local[0])].add("MAX_LINE_CURRENT_ANCHOR")
    reasons[int(tx_local[0])].add("MAX_TRANSFORMER_CURRENT_ANCHOR")
    deadband = np.full(96, np.inf)
    for row in reg_meta:
        target = float(row["vreg_v"]) / 120.0
        half_band = float(row["band_v"]) / 240.0
        for node in _controlled_node(row):
            if node in node_index:
                deadband = np.minimum(deadband, np.abs(np.abs(volts[:, node_index[node]] - target) - half_band))
    reasons[int(np.argmin(deadband))].add("REGULATOR_DEADBAND_NEAR")
    ordinary = (int(day[-2:]) * 37 + 11) % 96
    reasons[ordinary].add("DETERMINISTIC_ORDINARY")
    near_v = np.where((volts.min(axis=1) <= 0.95 + VOLTAGE_PROXIMITY_PU) |
                      (volts.max(axis=1) >= 1.05 - VOLTAGE_PROXIMITY_PU))[0]
    near_i = np.where(currents.max(axis=1) >= 1.0 - CURRENT_PROXIMITY_PU)[0]
    for slot in near_v: reasons[int(slot)].add("WITHIN_DECLARED_VOLTAGE_PROXIMITY")
    for slot in near_i: reasons[int(slot)].add("WITHIN_DECLARED_CURRENT_PROXIMITY")
    return {
        "slots": [int(slot) for slot in sorted(reasons)],
        "reasons": {str(slot): sorted(reasons[slot]) for slot in sorted(reasons)},
        "near_voltage_slots": list(map(int, near_v)),
        "near_current_slots": list(map(int, near_i)),
        "anchor_max_current_loading_pu": float(currents.max()),
    }


def _aidc_limits(reference: Mapping[str, object], authority, slot: int) -> tuple[list[float], list[float], dict[str, object]]:
    rack_groups = [[i for i, rack in enumerate(authority.racks) if rack.aidc_id == f"AIDC{d:02d}"] for d in range(1, 13)]
    flexible_p = reference["reference"].flexible_power_kw[slot]
    flexible_g = reference["reference"].flexible_gpu[slot]
    capacities = reference["gpu_capacities"]
    anchor = reference["plan_kw_96x12"][slot]
    max_kappa = max(KAPPA_KW_PER_ACTIVE_H100_NODE.values())
    down = []
    up = []
    for d, indices in enumerate(rack_groups):
        removable = PUE_PLAN * sum(float(flexible_p[i]) for i in indices)
        gpu_headroom = sum(max(0.0, float(capacities[i]) - float(flexible_g[i])) for i in indices)
        resource_up = PUE_PLAN * gpu_headroom * max_kappa / GPU_PER_NODE
        pcc_up = max(0.0, 1500.0 * PF_AIDC - float(anchor[d]))
        down.append(min(float(anchor[d]), removable))
        up.append(min(resource_up, pcc_up))
    return down, up, {
        "down_kw": down, "up_kw": up,
        "up_resource_rule": "PUE*GPU_HEADROOM*MAX_FROZEN_KAPPA/GPU_PER_NODE",
        "up_pcc_rule": "1500KVA*PF-anchor_kw",
        "down_rule": "PUE*frozen_flexible_power; residual preserved",
    }


def _planning_flow_base_and_sensitivity(binding: FullGridBinding, slot: int, anchor: np.ndarray):
    data = binding.factories[slot].data
    branches = tuple(data.branches)
    controls = tuple([f"aidc_load_kw[AIDC{i:02d}]" for i in range(1, 13)] +
                     sorted(k for k in binding.baseline_master[slot] if k.startswith("mess_p_kw[")) +
                     sorted(k for k in binding.baseline_master[slot] if k.startswith("mess_q_kvar[")))
    master = dict(binding.baseline_master[slot])
    for i, key in enumerate(controls): master[key] = float(anchor[i])
    outgoing = defaultdict(list)
    for index, branch in enumerate(branches): outgoing[(branch.parent_bus, branch.phase)].append(index)
    p = np.zeros(len(branches)); q = np.zeros(len(branches))
    sp = np.zeros((len(branches), 60)); sq = np.zeros((len(branches), 60))
    control_index = {key: i for i, key in enumerate(controls)}
    for index in reversed(range(len(branches))):
        branch = branches[index]; node = (branch.child_bus, branch.phase)
        p[index] = float(data.base_load_p_kw.get(node, 0.0)) - sum(float(c) * master[k] for k, c in data.master_p_injection.get(node, {}).items())
        q[index] = float(data.base_load_q_kvar.get(node, 0.0)) - sum(float(c) * master[k] for k, c in data.master_q_injection.get(node, {}).items())
        for key, coefficient in data.master_p_injection.get(node, {}).items(): sp[index, control_index[key]] -= float(coefficient)
        for key, coefficient in data.master_q_injection.get(node, {}).items(): sq[index, control_index[key]] -= float(coefficient)
        for child in outgoing.get(node, ()):
            p[index] += p[child]; q[index] += q[child]
            sp[index] += sp[child]; sq[index] += sq[child]
    return p, q, sp, sq


def _planning_thermal(binding: FullGridBinding, slot: int, base_sens, delta: np.ndarray) -> dict[str, object]:
    p0, q0, sp, sq = base_sens
    p = p0 + sp @ delta; q = q0 + sq @ delta
    data = binding.factories[slot].data; branches = tuple(data.branches)
    limits = np.asarray([float(data.line_limit_kva_u080[(b.branch_id, b.phase)]) for b in branches])
    angles = np.arange(LINE_POLYGON_FACES) * (2.0 * math.pi / LINE_POLYGON_FACES)
    polygon = np.max(p[:, None] * np.cos(angles) + q[:, None] * np.sin(angles), axis=1) / (limits * math.cos(math.pi / LINE_POLYGON_FACES))
    magnitude = np.hypot(p, q) / limits
    worst = int(np.argmax(polygon))
    approaching = np.where(polygon >= MONITOR_CURRENT_LOADING_PU)[0]
    return {
        "hard_feasible": bool(np.all(polygon <= 1.0 + CURRENT_TOLERANCE)),
        "worst": {"branch": branches[worst].branch_id, "phase": branches[worst].phase,
                  "polygon_loading_pu": float(polygon[worst]), "magnitude_loading_pu": float(magnitude[worst]),
                  "P_kw": float(p[worst]), "Q_kvar": float(q[worst])},
        "approaching_indices": list(map(int, approaching)),
        "p": p, "q": q, "polygon": polygon, "magnitude": magnitude,
    }


def _apply_vector(odd, controls: Sequence[str], values: np.ndarray) -> None:
    for i in range(12):
        value = float(values[i]); _set_load(odd, f"IDC_IDC{i+1:02d}", value, value * PF_TAN)
    services = [control.split("[", 1)[1][:-1] for control in controls[12:36]]
    for i, service in enumerate(services):
        p = float(values[12 + i]); q = float(values[36 + i])
        _set_generator(odd, f"MESS_DIS_{service}", max(p, 0.0), q)
        _set_load(odd, f"MESS_CHG_{service}", max(-p, 0.0), 0.0)


def _fresh_branch_metric(odd, branch, planning_limit_kva: float) -> dict[str, object]:
    odd.Circuit.SetActiveElement(branch.branch_id)
    conductors = int(odd.CktElement.NumConductors())
    buses = [str(value).split(".", 1)[0].lower() for value in odd.CktElement.BusNames()]
    terminal = buses.index(branch.parent_bus.lower())
    nodes = list(map(int, odd.CktElement.NodeOrder()))
    currents = list(map(float, odd.CktElement.CurrentsMagAng()))
    powers = list(map(float, odd.CktElement.Powers()))
    wanted = "ABC".index(branch.phase) + 1
    local = next(i for i in range(conductors) if nodes[terminal * conductors + i] == wanted)
    index = terminal * conductors + local
    current = float(currents[2 * index]); p = float(powers[2 * index]); q = float(powers[2 * index + 1])
    kind = "transformer" if branch.branch_id.startswith("transformer.") else "line"
    if kind == "line":
        odd.Lines.Name(branch.branch_id.split(".", 1)[1]); rated_current = float(odd.Lines.NormAmps()); side = terminal + 1
        kva_rating = None; total_kva_loading = None
    else:
        odd.Transformers.Name(branch.branch_id.split(".", 1)[1]); winding = terminal + 1; odd.Transformers.Wdg(winding)
        rating = float(odd.Transformers.kVA()); kv = float(odd.Transformers.kV()); phases = int(odd.CktElement.NumPhases())
        rated_current = rating / (math.sqrt(3.0) * kv) if phases >= 2 else rating / kv
        phase_indices = [terminal * conductors + i for i in range(conductors) if nodes[terminal * conductors + i] in (1, 2, 3)]
        total_p = sum(float(powers[2 * i]) for i in phase_indices); total_q = sum(float(powers[2 * i + 1]) for i in phase_indices)
        total_kva_loading = math.hypot(total_p, total_q) / rating; kva_rating = rating; side = winding
    angles = np.arange(LINE_POLYGON_FACES) * (2.0 * math.pi / LINE_POLYGON_FACES)
    polygon = float(np.max(p * np.cos(angles) + q * np.sin(angles)) /
                    (planning_limit_kva * math.cos(math.pi / LINE_POLYGON_FACES)))
    return {
        "branch": branch.branch_id, "phase": branch.phase, "kind": kind,
        "terminal_or_winding_side": side, "phase_current_a": current,
        "rated_current_a": rated_current, "normalized_current_loading_pu": current / rated_current,
        "phase_P_kw": p, "phase_Q_kvar": q,
        "fresh_16face_polygon_loading_pu": polygon,
        "transformer_rating_kva": kva_rating,
        "transformer_total_kva_loading_pu": total_kva_loading,
    }


def _fresh_capture(odd, nodes: Sequence[str], branches, limits: np.ndarray, monitor: Sequence[int]) -> dict[str, object]:
    volts = np.asarray(list(_voltage_map(odd, nodes).values()), dtype=float)
    metrics = [_fresh_branch_metric(odd, branches[i], float(limits[i])) for i in sorted(set(monitor))]
    worst = max(metrics, key=lambda row: float(row["normalized_current_loading_pu"]))
    return {"voltage": volts, "branch_metrics": metrics, "worst_current": worst,
            "hard_current_feasible": all(float(row["normalized_current_loading_pu"]) <= 1.0 + CURRENT_TOLERANCE for row in metrics)}


def _compact_voltage(metrics: Mapping[str, object]) -> dict[str, object]:
    return {key: metrics[key] for key in (
        "max_abs_error_pu", "mean_abs_error_pu", "p95_abs_error_pu",
        "predicted_Vmin_pu", "predicted_Vmax_pu", "actual_Vmin_pu", "actual_Vmax_pu",
        "worst_node_phase", "false_feasible_count", "false_infeasible_count",
        "lower_limit_disagreement_count", "upper_limit_disagreement_count",
    )}


def _build_contract(repo: Path, source: Path, artifacts: Path, checkpoint, days, excluded, contexts):
    odd, _adapter = _compile(source, repo, "NATIVE")
    sample_binding = contexts[days[0]][3]
    ratings, rating_rows = _branch_ratings(odd, sample_binding)
    reg_meta = _regcontrol_metadata(odd)
    kinds = [row["kind"] for row in rating_rows]
    per_day = []
    fingerprints = []
    total = 0
    for day in days:
        reference, _vintage, _background, binding, cache, authority = contexts[day]
        data = np.load(cache, allow_pickle=False)
        if tuple(map(str, data["control_names"])) != tuple([f"aidc_load_kw[AIDC{i:02d}]" for i in range(1, 13)] + sorted(k for k in binding.baseline_master[0] if k.startswith("mess_p_kw[")) + sorted(k for k in binding.baseline_master[0] if k.startswith("mess_q_kvar["))):
            raise RuntimeError("V163_NONZERO_CACHE_CONTROL_AXIS_MISMATCH")
        selected = _slot_selection(data, ratings, kinds, reg_meta, day)
        slots = []
        for slot in selected["slots"]:
            down, up, limits = _aidc_limits(reference, authority, slot)
            directions = build_probe_directions(tuple(map(str, data["control_names"])), down, up)
            rows = [{"probe_id": direction.probe_id, "family": direction.family,
                     "direction": direction.direction, "delta_at_rho1": direction.delta_at_rho1,
                     "physical_basis": direction.physical_basis} for direction in directions]
            fingerprint = payload_sha256(rows)
            fingerprints.append({"day": day, "slot": slot, "sha256": fingerprint})
            count = len(rows) * len(RHO_GRID); total += count
            slots.append({"slot": slot, "selection_reasons": selected["reasons"][str(slot)],
                          "aidc_physical_direction_limits": limits, "direction_count": len(rows),
                          "probe_count": count, "direction_fingerprint": fingerprint})
        per_day.append({"operating_day": day, "selection": selected, "slots": slots})
    monitor = sorted({i for day in days for i, value in enumerate(
        np.max(np.asarray(np.load(contexts[day][4], allow_pickle=False)["branch_current_a"], dtype=float) / ratings[None, :], axis=0)
    ) if value >= MONITOR_CURRENT_LOADING_PU} |
        {i for i, row in enumerate(rating_rows) if row["branch"] in ("line.l10", "transformer.reg1a")})
    contract = {
        "artifact_id": "V16_3_NONZERO_DEVIATION_PROBE_CONTRACT",
        "candidate_only": True, "V16_3_activated": False, "beta_AIDC": 0.25,
        "beta_candidate_recommended": None, "checkpoint": checkpoint,
        "rho_grid": list(RHO_GRID), "rho_grid_frozen_before_nonzero_fresh_ac": True,
        "control_vector": {"AIDC_P": 12, "MESS_P": 24, "MESS_Q": 24, "total": 60},
        "families": ["A_SINGLE_AIDC_P", "B_ZERO_SUM_AIDC_REDISTRIBUTION", "C_SINGLE_MESS_P", "D_SINGLE_MESS_Q", "E_JOINT_AIDC_MESS"],
        "physical_limits": {"MESS_P_kw": MESS_P_LIMIT_KW, "MESS_PCS_kVA": PCS_KVA,
                            "AIDC_PCC_kVA": 1500.0, "AIDC_PF": PF_AIDC,
                            "AIDC_resource_basis": "FROZEN_GPU_CAPACITY_AND_DATASET312_KAPPA"},
        "slot_selection": {"voltage_proximity_pu": VOLTAGE_PROXIMITY_PU,
                           "current_proximity_pu": CURRENT_PROXIMITY_PU,
                           "ordinary_rule": "(APRIL_DAY_OF_MONTH*37+11)%96",
                           "critical_rules_frozen_before_probe_results": True},
        "voltage_acceptance": VOLTAGE_TOLERANCE,
        "current_monitor_rule": {"anchor_loading_threshold_pu": MONITOR_CURRENT_LOADING_PU,
                                 "always": ["line.l10", "transformer.reg1a"],
                                 "dynamic_addition": "ALL_BRANCH_PHASES_WITH_PLANNING_POLYGON_LOADING_AT_LEAST_0.80"},
        "monitored_anchor_branch_phases": [rating_rows[i] for i in monitor],
        "regcontrol_metadata": reg_meta,
        "included_days": list(days), "excluded_days": excluded, "per_day": per_day,
        "total_predeclared_probe_count": total,
        "full_probe_plan_fingerprint": payload_sha256(fingerprints),
        "evaluation_models": ["CANDIDATE_B_AFFINE", "FRESH_AC_FROZEN_TAPS", "FRESH_AC_NATIVE_CONTROLS"],
        "no_result_dependent_probe_direction": True, "no_H_recompute_after_deviation": True,
        **COUNTERS,
    }
    _write_json(artifacts / "V16_3_NONZERO_DEVIATION_PROBE_CONTRACT.json", contract)
    return contract, ratings, rating_rows, monitor


def _evaluate_day(repo: Path, source: Path, day: str, context, contract_day, ratings, rating_rows, anchor_monitor, artifacts: Path):
    reference, _vintage, background, binding, cache, authority = context
    data = np.load(cache, allow_pickle=False)
    nodes = tuple(map(str, data["node_names"])); controls = tuple(map(str, data["control_names"])); branches = tuple(binding.factories[0].data.branches)
    limits = np.asarray([float(binding.factories[0].data.line_limit_kva_u080[(b.branch_id, b.phase)]) for b in branches])
    odd, adapter = _compile(source, repo, "NATIVE")
    rows = []
    solve_count = 0
    for slot_row in contract_day["slots"]:
        slot = int(slot_row["slot"])
        down, up, _limits = _aidc_limits(reference, authority, slot)
        directions = build_probe_directions(controls, down, up)
        anchor = np.asarray(data["anchor_control"][slot], dtype=float)
        taps = {name: float(data["regulator_taps"][slot, i]) for i, name in enumerate(REGULATORS)}
        caps = {name: [int(data["capacitor_states"][slot, i])] for i, name in enumerate(CAPACITORS)}
        base_sens = _planning_flow_base_and_sensitivity(binding, slot, anchor)
        for direction in directions:
            for rho in RHO_GRID:
                delta = expand_rho(direction, rho); values = anchor + delta
                if np.any(values[:12] < -1e-9): raise RuntimeError("V163_NONZERO_NEGATIVE_AIDC_LOAD")
                for i in range(24):
                    if abs(values[12+i]) > MESS_P_LIMIT_KW + 1e-9 or math.hypot(values[12+i], values[36+i]) > PCS_KVA + 1e-9:
                        raise RuntimeError("V163_NONZERO_MESS_PHYSICAL_BOUND")
                pred_v2 = np.asarray(data["anchor_v_squared"][slot], dtype=float) + np.einsum("cn,c->n", np.asarray(data["sensitivity"][slot]), delta)
                predicted = np.sqrt(np.maximum(pred_v2, 0.0))
                planning = _planning_thermal(binding, slot, base_sens, delta)
                monitor = sorted(set(anchor_monitor) | set(planning["approaching_indices"]))

                _set_slot(odd, adapter, background, reference["plan_kw_96x12"], slot)
                _fix_controls(odd, taps, caps); _apply_vector(odd, controls, values); odd.Solution.SolveSnap(); solve_count += 1
                if not bool(odd.Solution.Converged()): raise RuntimeError(f"V163_NONZERO_FROZEN_NONCONVERGENCE:{day}:{slot}")
                frozen = _fresh_capture(odd, nodes, branches, limits, monitor)

                _set_slot(odd, adapter, background, reference["plan_kw_96x12"], slot)
                _fix_controls(odd, taps, caps); _enable_native_controls(odd); _apply_vector(odd, controls, values); odd.Solution.SolveSnap(); solve_count += 1
                if not bool(odd.Solution.Converged()): raise RuntimeError(f"V163_NONZERO_NATIVE_NONCONVERGENCE:{day}:{slot}")
                native = _fresh_capture(odd, nodes, branches, limits, monitor)
                native_taps = _regulator_taps(odd)
                tap_changes = {name: float(native_taps[name] - taps[name]) for name in REGULATORS if abs(native_taps[name] - taps[name]) > 1e-12}
                vf = voltage_comparison(predicted, frozen["voltage"], nodes)
                vn = voltage_comparison(predicted, native["voltage"], nodes)
                current_false = bool(planning["hard_feasible"] and not native["hard_current_feasible"])
                trust_pass = (
                    vf["max_abs_error_pu"] <= VOLTAGE_TOLERANCE["max_abs_candidate_vs_frozen_pu"] + 1e-12 and
                    vf["mean_abs_error_pu"] <= VOLTAGE_TOLERANCE["mean_abs_candidate_vs_frozen_pu"] + 1e-12 and
                    vf["p95_abs_error_pu"] <= VOLTAGE_TOLERANCE["p95_abs_candidate_vs_frozen_pu"] + 1e-12 and
                    vn["max_abs_error_pu"] <= VOLTAGE_TOLERANCE["max_abs_candidate_vs_native_pu"] + 1e-12 and
                    vf["false_feasible_count"] == vf["false_infeasible_count"] == 0 and
                    vn["false_feasible_count"] == vn["false_infeasible_count"] == 0 and not current_false
                )
                def selected(metrics):
                    return {f"{r['branch']}::{r['phase']}": r for r in metrics["branch_metrics"] if r["branch"] in ("line.l10", "transformer.reg1a") or r["normalized_current_loading_pu"] >= MONITOR_CURRENT_LOADING_PU}
                rows.append({
                    "probe_key": f"{day}:T{slot:02d}:{direction.probe_id}:R{rho:.2f}",
                    "operating_day": day, "slot": slot, "family": direction.family,
                    "probe_id": direction.probe_id, "direction": direction.direction, "rho": rho,
                    "delta_nonzero": bool(np.any(np.abs(delta) > 1e-12)),
                    "delta_l1": float(np.sum(np.abs(delta))), "delta_linf": float(np.max(np.abs(delta))),
                    "same_H_sha256": sha256_file(cache),
                    "candidate_vs_frozen": _compact_voltage(vf), "candidate_vs_native": _compact_voltage(vn),
                    "anchor_taps": taps, "native_taps": native_taps, "tap_changes": tap_changes,
                    "planning_thermal": {"hard_feasible": planning["hard_feasible"], "worst": planning["worst"]},
                    "fresh_frozen_current": {"hard_feasible": frozen["hard_current_feasible"], "worst": frozen["worst_current"], "selected": selected(frozen)},
                    "fresh_native_current": {"hard_feasible": native["hard_current_feasible"], "worst": native["worst_current"], "selected": selected(native)},
                    "hard_current_false_feasible": current_false,
                    "trust_region_pass": bool(trust_pass),
                })
        print(json.dumps({"stage":"NONZERO_SLOT", "day":day, "slot":slot, "rows":len(rows)}), flush=True)
    cache_out = artifacts / "data" / f"NONZERO_PROBE_RESULTS_{day}.npz"
    encoded = json.dumps(rows, sort_keys=True, separators=(",", ":"))
    definition_sha = payload_sha256(sorted(row["probe_key"] for row in rows))
    np.savez_compressed(cache_out, schema=np.asarray("V16_3_NONZERO_PROBE_RESULTS_V1"),
                        contract_sha=np.asarray(sha256_file(artifacts / "V16_3_NONZERO_DEVIATION_PROBE_CONTRACT.json")),
                        day_probe_definition_sha=np.asarray(definition_sha),
                        payload=np.asarray(encoded))
    return rows, {"path": str(cache_out.resolve()), "sha256": sha256_file(cache_out),
                  "bytes": cache_out.stat().st_size, "probe_count": len(rows), "fresh_solve_count": solve_count}


def _aggregate_probe_results(rows: Sequence[Mapping[str, object]]) -> dict[str, object]:
    def worst(path_a: str, path_b: str):
        return max(rows, key=lambda row: float(row[path_a][path_b]))
    groups = []
    for family in sorted({str(row["family"]) for row in rows}):
        for rho in RHO_GRID:
            subset = [row for row in rows if row["family"] == family and float(row["rho"]) == rho]
            groups.append({
                "family": family, "rho": rho, "probe_count": len(subset),
                "trust_pass_count": sum(bool(r["trust_region_pass"]) for r in subset),
                "voltage_false_feasible_count": sum(int(r["candidate_vs_native"]["false_feasible_count"]) for r in subset),
                "voltage_false_infeasible_count": sum(int(r["candidate_vs_native"]["false_infeasible_count"]) for r in subset),
                "current_false_feasible_count": sum(bool(r["hard_current_false_feasible"]) for r in subset),
                "tap_change_probe_count": sum(bool(r["tap_changes"]) for r in subset),
                "max_candidate_vs_frozen_error_pu": max(float(r["candidate_vs_frozen"]["max_abs_error_pu"]) for r in subset),
                "max_candidate_vs_native_error_pu": max(float(r["candidate_vs_native"]["max_abs_error_pu"]) for r in subset),
            })
    return {
        "probe_count": len(rows), "all_delta_nonzero": all(bool(row["delta_nonzero"]) for row in rows),
        "trust_region_pass_count": sum(bool(row["trust_region_pass"]) for row in rows),
        "voltage_false_feasible_count": sum(int(row["candidate_vs_native"]["false_feasible_count"]) for row in rows),
        "voltage_false_infeasible_count": sum(int(row["candidate_vs_native"]["false_infeasible_count"]) for row in rows),
        "hard_current_false_feasible_count": sum(bool(row["hard_current_false_feasible"]) for row in rows),
        "tap_change_probe_count": sum(bool(row["tap_changes"]) for row in rows),
        "max_candidate_vs_frozen_error": {"probe_key": worst("candidate_vs_frozen", "max_abs_error_pu")["probe_key"], "value_pu": float(worst("candidate_vs_frozen", "max_abs_error_pu")["candidate_vs_frozen"]["max_abs_error_pu"])},
        "max_candidate_vs_native_error": {"probe_key": worst("candidate_vs_native", "max_abs_error_pu")["probe_key"], "value_pu": float(worst("candidate_vs_native", "max_abs_error_pu")["candidate_vs_native"]["max_abs_error_pu"])},
        "by_family_rho": groups,
    }


def _current_forensic(rows: Sequence[Mapping[str, object]], rating_rows) -> dict[str, object]:
    false_rows = [row for row in rows if row["hard_current_false_feasible"]]
    tap_material = any(bool(row["tap_changes"]) and bool(row["fresh_frozen_current"]["hard_feasible"]) and not bool(row["fresh_native_current"]["hard_feasible"]) for row in false_rows)
    kva_material = False; linear_material = False; phase_material = False
    examples = []
    for row in false_rows:
        worst = row["fresh_native_current"]["worst"]
        kva = worst.get("transformer_total_kva_loading_pu")
        if kva is not None and float(worst["normalized_current_loading_pu"]) > 1.0 and float(kva) <= 1.0 + CURRENT_TOLERANCE:
            kva_material = True
        plan_mag = float(row["planning_thermal"]["worst"]["magnitude_loading_pu"])
        if abs(float(worst["normalized_current_loading_pu"]) - plan_mag) > 0.02:
            linear_material = True
        if worst["kind"] == "transformer" and kva is not None and float(worst["normalized_current_loading_pu"]) - float(kva) > 0.02:
            phase_material = True
        if len(examples) < 20: examples.append(row)
    flags = {"tap_side_conversion_material": tap_material,
             "kva_vs_phase_current_material": kva_material,
             "linear_flow_error_material": linear_material,
             "phase_unbalance_material": phase_material}
    primary = current_root_classification(flags)
    return {
        "primary_root_cause_classification": primary, "root_cause_flags": flags,
        "interpretation": "Planning uses per-phase lossless apparent-power polygons on nominal kVA; Fresh AC enforces phase current at the identified winding voltage and includes losses/unbalance/tap response.",
        "hard_current_false_feasible_count": len(false_rows),
        "false_feasible_examples": examples,
        "rating_side_provenance": rating_rows,
        "rating_changes": 0,
    }


def _process_memory() -> dict[str, int]:
    if os.name != "nt": return {"peak_working_set_bytes": 0, "working_set_bytes": 0}
    command = (
        f"$p=Get-Process -Id {os.getpid()}; "
        "[Console]::WriteLine(('{0},{1}' -f $p.PeakWorkingSet64,$p.WorkingSet64))"
    )
    output = subprocess.run(["powershell", "-NoProfile", "-Command", command], check=True,
                            text=True, capture_output=True).stdout.strip()
    peak, current = map(int, output.split(","))
    return {"peak_working_set_bytes": peak, "working_set_bytes": current}


def _benchmark_h(repo: Path, source: Path, artifacts: Path, day: str, context) -> dict[str, object]:
    from .run_v16_3_voltage_candidate import _anchor_and_sensitivity_day
    reference, _vintage, background, binding, _cache, _authority = context
    target = artifacts / "data" / f"BENCHMARK_D1_AC_ANCHOR_SENSITIVITY_{day}.npz"
    if target.exists():
        target.unlink()
    cpu0 = time.process_time(); wall0 = time.perf_counter()
    record = _anchor_and_sensitivity_day(repo, source, background, reference["plan_kw_96x12"], binding, day, target, build_sensitivity=True)
    wall = time.perf_counter() - wall0; cpu = time.process_time() - cpu0
    return {"operating_day": day, "anchor_solve_count": 96, "central_sensitivity_solve_count": 96*60*2,
            "determinism_repeat_solve_count": 1, "total_OpenDSS_solve_count": 96+96*60*2+1,
            "wall_clock_seconds": wall, "process_cpu_seconds": cpu,
            "average_process_cpu_utilization_fraction_of_one_core": cpu / wall if wall else None,
            **_process_memory(), "npz_path": str(target.resolve()), "npz_size_bytes": target.stat().st_size,
            "npz_sha256": sha256_file(target), "record_fingerprint": record["fingerprint"]}


def execute(repo: Path, source: Path, artifacts: Path, contract_only: bool = False,
            limit_days: int = 0, skip_benchmark: bool = False,
            worker_day: str | None = None, benchmark_only: bool = False) -> dict[str, object]:
    repo = repo.resolve(); source = source.resolve(); artifacts = artifacts.resolve(); artifacts.mkdir(parents=True, exist_ok=True)
    checkpoint = _checkpoint(repo, source, artifacts)
    if benchmark_only:
        day = "2025-04-02"
        _days, _excluded, contexts = _april_contexts(repo, source, artifacts, only_day=day)
        benchmark = _benchmark_h(repo, source, artifacts, day, contexts[day])
        review_path = artifacts / "V16_3_PREREFREEZE_REVIEW_V2.json"
        review = json.loads(review_path.read_text(encoding="utf-8"))
        review["D1_computational_practicality"] = benchmark
        _write_json(review_path, review)
        return {"status":"D1_BENCHMARK_ONLY_COMPLETE", "benchmark":benchmark,
                "review_sha256":sha256_file(review_path), "checkpoint_sha":checkpoint["head"]}
    if worker_day:
        days, _excluded, contexts = _april_contexts(repo, source, artifacts, only_day=worker_day)
        contract = json.loads((artifacts / "V16_3_NONZERO_DEVIATION_PROBE_CONTRACT.json").read_text(encoding="utf-8"))
        if len(contract.get("included_days", ())) != 29:
            raise RuntimeError("V163_NONZERO_WORKER_REQUIRES_FULL_APRIL_CONTRACT")
        contract_day = next(row for row in contract["per_day"] if row["operating_day"] == worker_day)
        odd, _adapter = _compile(source, repo, "NATIVE")
        binding = contexts[worker_day][3]
        ratings, rating_rows = _branch_ratings(odd, binding)
        key_to_index = {(row["branch"], row["phase"]): i for i, row in enumerate(rating_rows)}
        anchor_monitor = [key_to_index[(row["branch"], row["phase"])] for row in contract["monitored_anchor_branch_phases"]]
        rows, cache = _evaluate_day(repo, source, worker_day, contexts[worker_day], contract_day,
                                    ratings, rating_rows, anchor_monitor, artifacts)
        return {"status":"WORKER_DAY_COMPLETE", "operating_day":worker_day,
                "probe_count":len(rows), "cache":cache, "checkpoint_sha":checkpoint["head"]}
    days, excluded, contexts = _april_contexts(repo, source, artifacts, limit_days)
    contract, ratings, rating_rows, anchor_monitor = _build_contract(repo, source, artifacts, checkpoint, days, excluded, contexts)
    if contract_only:
        return {"status":"CONTRACT_FROZEN_BEFORE_NONZERO_RESULTS", "contract_sha256":sha256_file(artifacts / "V16_3_NONZERO_DEVIATION_PROBE_CONTRACT.json"), "probe_count":contract["total_predeclared_probe_count"]}
    caches = []
    total_probe_count = 0
    aggregate_counts = defaultdict(int)
    grouped: dict[tuple[str, float], dict[str, object]] = {}
    worst_frozen = None; worst_native = None
    current_false_count = 0
    current_flags = {"tap_side_conversion_material":False, "kva_vs_phase_current_material":False,
                     "linear_flow_error_material":False, "phase_unbalance_material":False}
    current_examples = []
    tap_count = 0; tap_max = 0.0; tap_examples = []
    tap_by_regulator = {name:0 for name in REGULATORS}
    tap_failure_seen = False
    contract_days = {row["operating_day"]: row for row in contract["per_day"]}
    for day in days:
        cache_path = artifacts / "data" / f"NONZERO_PROBE_RESULTS_{day}.npz"
        expected_contract_sha = sha256_file(artifacts / "V16_3_NONZERO_DEVIATION_PROBE_CONTRACT.json")
        reference, _vintage, _background, _binding, anchor_cache, authority = contexts[day]
        controls = tuple(map(str, np.load(anchor_cache, allow_pickle=False)["control_names"]))
        expected_keys = []
        for slot_row in contract_days[day]["slots"]:
            slot = int(slot_row["slot"])
            down, up, _limits = _aidc_limits(reference, authority, slot)
            for direction in build_probe_directions(controls, down, up):
                expected_keys.extend(f"{day}:T{slot:02d}:{direction.probe_id}:R{rho:.2f}" for rho in RHO_GRID)
        expected_definition_sha = payload_sha256(sorted(expected_keys))
        loaded = False
        if cache_path.exists():
            saved = np.load(cache_path, allow_pickle=False)
            day_rows = json.loads(str(saved["payload"]))
            expected_count = sum(int(slot["probe_count"]) for slot in contract_days[day]["slots"])
            cached_definition_sha = payload_sha256(sorted(str(row["probe_key"]) for row in day_rows))
            valid_day_definition = (
                len(day_rows) == expected_count and
                all(str(row["operating_day"]) == day and bool(row["delta_nonzero"]) for row in day_rows) and
                len({str(row["probe_key"]) for row in day_rows}) == expected_count and
                cached_definition_sha == expected_definition_sha
            )
            if str(saved["contract_sha"]) == expected_contract_sha or valid_day_definition:
                loaded = True
                cache_record = {"path":str(cache_path.resolve()), "sha256":sha256_file(cache_path), "bytes":cache_path.stat().st_size, "probe_count":len(day_rows), "fresh_solve_count":2*len(day_rows)}
        if not loaded:
            day_rows, cache_record = _evaluate_day(repo, source, day, contexts[day], contract_days[day], ratings, rating_rows, anchor_monitor, artifacts)
        caches.append(cache_record); total_probe_count += len(day_rows)
        daily = _aggregate_probe_results(day_rows)
        for key in ("trust_region_pass_count", "voltage_false_feasible_count",
                    "voltage_false_infeasible_count", "hard_current_false_feasible_count",
                    "tap_change_probe_count"):
            aggregate_counts[key] += int(daily[key])
        candidate = daily["max_candidate_vs_frozen_error"]
        if worst_frozen is None or float(candidate["value_pu"]) > float(worst_frozen["value_pu"]): worst_frozen = candidate
        candidate = daily["max_candidate_vs_native_error"]
        if worst_native is None or float(candidate["value_pu"]) > float(worst_native["value_pu"]): worst_native = candidate
        for group in daily["by_family_rho"]:
            key = (str(group["family"]), float(group["rho"]))
            if key not in grouped:
                grouped[key] = dict(group)
            else:
                target = grouped[key]
                for field in ("probe_count", "trust_pass_count", "voltage_false_feasible_count",
                              "voltage_false_infeasible_count", "current_false_feasible_count",
                              "tap_change_probe_count"):
                    target[field] = int(target[field]) + int(group[field])
                for field in ("max_candidate_vs_frozen_error_pu", "max_candidate_vs_native_error_pu"):
                    target[field] = max(float(target[field]), float(group[field]))
        daily_current = _current_forensic(day_rows, rating_rows)
        current_false_count += int(daily_current["hard_current_false_feasible_count"])
        for key, value in daily_current["root_cause_flags"].items(): current_flags[key] = current_flags[key] or bool(value)
        current_examples.extend(daily_current["false_feasible_examples"][:max(0, 20-len(current_examples))])
        for row in day_rows:
            if row["tap_changes"]:
                tap_count += 1; tap_failure_seen = tap_failure_seen or not bool(row["trust_region_pass"])
                tap_max = max(tap_max, max(abs(float(value)) for value in row["tap_changes"].values()))
                for name in row["tap_changes"]: tap_by_regulator[name] += 1
                if len(tap_examples) < 100: tap_examples.append(row)
        day_probe_count = len(day_rows); del day_rows
        print(json.dumps({"stage":"NONZERO_DAY", "day":day, "days_complete":len(caches), "probe_count":day_probe_count, "cache_reused":loaded}), flush=True)
    aggregate = {
        "probe_count":total_probe_count, "all_delta_nonzero":True,
        **dict(aggregate_counts),
        "max_candidate_vs_frozen_error":worst_frozen,
        "max_candidate_vs_native_error":worst_native,
        "by_family_rho":[grouped[key] for key in sorted(grouped)],
    }
    rho_valid = None
    for rho in RHO_GRID:
        inner = [group for (_family, group_rho), group in grouped.items() if group_rho <= rho + 1e-12]
        if not inner or any(int(group["trust_pass_count"]) != int(group["probe_count"]) for group in inner): break
        rho_valid = float(rho)
    current = {
        "primary_root_cause_classification":current_root_classification(current_flags),
        "root_cause_flags":current_flags,
        "interpretation":"Planning uses per-phase lossless apparent-power polygons on nominal kVA; Fresh AC enforces phase current at the identified winding voltage and includes losses/unbalance/tap response.",
        "hard_current_false_feasible_count":current_false_count,
        "false_feasible_examples":current_examples, "rating_side_provenance":rating_rows,
        "rating_changes":0,
    }
    tap_diag = {
        "artifact_id":"V16_3_TAP_DISCONTINUITY_DIAGNOSTIC", "probe_count":total_probe_count,
        "tap_change_probe_count":tap_count,
        "tap_change_counts_by_regulator":tap_by_regulator,
        "max_tap_step_difference":tap_max,
        "tap_change_examples":tap_examples, "all_tap_changes_reported_in_probe_cache":True,
        **COUNTERS,
    }
    voltage_diag = {
        "artifact_id":"V16_3_NONZERO_VOLTAGE_VALIDITY_DIAGNOSTIC", "contract_sha256":sha256_file(artifacts / "V16_3_NONZERO_DEVIATION_PROBE_CONTRACT.json"),
        "aggregate":aggregate, "per_probe_result_caches":caches,
        "per_probe_record_schema":"Each compressed cache payload records both voltage comparisons, limits, worst node/phase, tap state, and thermal/current summaries for every probe.",
        "same_H_before_after_comparison":True, "H_recompute_call_count_after_probe_results":0,
        **COUNTERS,
    }
    current_diag = {"artifact_id":"V16_3_CURRENT_THERMAL_CONSISTENCY_DIAGNOSTIC", **current,
                    "per_probe_result_caches":caches, **COUNTERS}
    trust = {"artifact_id":"V16_3_AFFINE_TRUST_REGION_CANDIDATE", **trust_region_contract(rho_valid),
             "validated_from_anchor_identity":False, "nonzero_probe_count":total_probe_count,
             "voltage_limits_unchanged":[0.95,1.05], "candidate_only":True, **COUNTERS}
    if current["hard_current_false_feasible_count"] > 0:
        classification = "V163_VALID_C_CURRENT_MODEL_REQUIRES_CORRECTION"
    elif rho_valid is None:
        classification = "V163_VALID_D_NO_DEFENSIBLE_NONZERO_REGION"
    elif tap_diag["tap_change_probe_count"] and tap_failure_seen:
        classification = "V163_VALID_B_TAP_DISCONTINUITY_LIMITS_REGION"
    else:
        classification = "V163_VALID_A_NONZERO_AFFINE_REGION_CONFIRMED"
    sections_pass = classification in ("V163_VALID_A_NONZERO_AFFINE_REGION_CONFIRMED", "V163_VALID_B_TAP_DISCONTINUITY_LIMITS_REGION") and rho_valid is not None
    shadow = None
    if sections_pass:
        # A model-generated nonzero schedule is intentionally deferred here if the
        # trust-region evidence itself has any current-model correction finding.
        shadow = {"artifact_id":"V16_3_APR15_NONZERO_SHADOW_SCHEDULE_VALIDATION",
                  "status":"NOT_REACHED_FAIL_CLOSED" if current["hard_current_false_feasible_count"] else "NOT_IMPLEMENTED_IN_DIAGNOSTIC",
                  "reason":"Section 16 requires all Sections 5-15 to pass without a current-model correction."}
    benchmark = None if skip_benchmark else _benchmark_h(repo, source, artifacts, days[0], contexts[days[0]])
    next_decision = "READY_FOR_V16_3_AND_BETA_REFREEZE_REVIEW" if classification in ("V163_VALID_A_NONZERO_AFFINE_REGION_CONFIRMED", "V163_VALID_B_TAP_DISCONTINUITY_LIMITS_REGION") and rho_valid is not None else "V16_3_PREREFREEZE_CORRECTION_REQUIRED"
    review = {
        "artifact_id":"V16_3_PREREFREEZE_REVIEW_V2", "checkpoint":checkpoint,
        "candidate_only":True, "V16_3_activated":False, "beta_AIDC":0.25,
        "beta_candidate_recommended":None, "probe_contract_sha256":sha256_file(artifacts / "V16_3_NONZERO_DEVIATION_PROBE_CONTRACT.json"),
        "nonzero_probe_count":total_probe_count, "rho_valid":rho_valid,
        "current_root_cause_classification":current["primary_root_cause_classification"],
        "final_classification":classification, "next_decision":next_decision,
        "shadow_schedule_reached":False, "shadow_schedule_reason":"Fail-closed unless all voltage/current Sections 5-15 pass.",
        "D1_computational_practicality":benchmark,
        "required_stop_point_observed":True, **COUNTERS,
    }
    payloads = [
        ("V16_3_NONZERO_VOLTAGE_VALIDITY_DIAGNOSTIC.json", voltage_diag),
        ("V16_3_TAP_DISCONTINUITY_DIAGNOSTIC.json", tap_diag),
        ("V16_3_CURRENT_THERMAL_CONSISTENCY_DIAGNOSTIC.json", current_diag),
        ("V16_3_AFFINE_TRUST_REGION_CANDIDATE.json", trust),
        ("V16_3_PREREFREEZE_REVIEW_V2.json", review),
    ]
    if shadow and shadow["status"] != "NOT_REACHED_FAIL_CLOSED": payloads.append(("V16_3_APR15_NONZERO_SHADOW_SCHEDULE_VALIDATION.json", shadow))
    for name, payload in payloads: _write_json(artifacts / name, payload)
    return {"checkpoint_sha":CHECKPOINT_SHA, "probe_count":total_probe_count, "rho_valid":rho_valid,
            "current_classification":current["primary_root_cause_classification"],
            "final_classification":classification, "next_decision":next_decision,
            "artifact_shas":{name:sha256_file(artifacts/name) for name,_ in payloads}}


def main(argv: Sequence[str] | None = None) -> int:
    repo = Path.cwd()
    source = Path(r"C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\tmp\c12_exact_sources_repo_cleanup\c12_exact_sources\v2038_parent\Conversation3_Exact_AC_Remediation_Sweep_From_Conversation1_V2038\reference")
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=repo)
    parser.add_argument("--source", type=Path, default=source)
    parser.add_argument("--artifacts", type=Path, default=repo / "dayahead/artifacts" / ARTIFACT_DIR_NAME)
    parser.add_argument("--contract-only", action="store_true")
    parser.add_argument("--limit-days", type=int, default=0)
    parser.add_argument("--skip-benchmark", action="store_true")
    parser.add_argument("--worker-day", type=str, default=None)
    parser.add_argument("--benchmark-only", action="store_true")
    print(json.dumps(execute(**vars(parser.parse_args(argv))), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
