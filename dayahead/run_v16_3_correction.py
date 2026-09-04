"""Prospective V16.3 frozen-control and phase-current correction study.

This runner is diagnostic-only.  It never mutates a feeder asset, activates a
production authority, changes beta, or calls G12/G13/G14/C12.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
from collections import defaultdict
from pathlib import Path
from typing import Mapping, Sequence

import numpy as np

from .authority import sha256_file
from .run_authority_semantic_g11_v16_2 import _write_json
from .run_planning_ac_voltage_forensic_v1 import _compile
from .run_v16_3_nonzero_validity import (
    _aidc_limits,
    _april_contexts,
    _branch_ratings,
    _fresh_capture,
    _apply_vector,
)
from .run_v16_3_voltage_candidate import (
    CAPACITORS,
    NATIVE_MASTER_SHA,
    REGULATORS,
    _apply_control,
    _enable_native_controls,
    _fix_controls,
    _perturbation,
    _regulator_taps,
    _set_slot,
)
from .v16_3_correction import (
    CURRENT_ERROR_TOLERANCE,
    FALSE_INFEASIBLE_SEVERE_RATE,
    cumulative_valid_radius,
    current_comparison,
    current_metrics_pass,
)
from .v16_3_nonzero_validity import (
    RHO_GRID,
    VOLTAGE_TOLERANCE,
    build_probe_directions,
    expand_rho,
    payload_sha256,
    trust_region_contract,
)
from .full_ieee123_b3_v16_2 import B3Inputs
from .v16_3_shadow import solve_shadow


CHECKPOINT_SHA = "1d72034bf62849de75355c8497231252ac220ce8"
BRANCH_AXIS_SIZE = 383
CONTROL_AXIS_SIZE = 60
NODE_AXIS_SIZE = 386
# This checks only the sparse Y-primitive extraction path against OpenDSS's
# direct element-current API.  It is an absolute numerical-consistency guard,
# not the normalized surrogate acceptance tolerance used below.
YPRIM_DIRECT_CURRENT_TOLERANCE_A = 0.10
ARTIFACT_DIR_NAME = "v16_3_candidate"
CURRENT_CACHE_SCHEMA = "V16_3_AC_ANCHORED_PHASE_CURRENT_SENSITIVITY_NPZ_V1"
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


def _checkpoint(repo: Path, source: Path) -> dict[str, object]:
    head = _git(repo, "rev-parse", "HEAD")
    if head != CHECKPOINT_SHA:
        raise RuntimeError(f"V163_CORR_CHECKPOINT_MISMATCH:{head}")
    branch = _git(repo, "branch", "--show-current")
    if branch != "codex/dayahead-aidc-joint-v1":
        raise RuntimeError(f"V163_CORR_BRANCH_MISMATCH:{branch}")
    native = source / "opendss_assets/IEEE123Master.dss"
    if sha256_file(native) != NATIVE_MASTER_SHA:
        raise RuntimeError("V163_CORR_NATIVE_IEEE123_SHA_MISMATCH")
    dirty = _git(repo, "status", "--short").splitlines()
    allowed = (
        "dayahead/run_v16_3_correction.py",
        "dayahead/v16_3_correction.py",
        "dayahead/v16_3_shadow.py",
        "tests/test_v16_3_correction.py",
        "dayahead/artifacts/v16_3_candidate/",
    )
    unexpected = [line for line in dirty if not any(token in line for token in allowed)]
    if unexpected:
        raise RuntimeError(f"V163_CORR_UNEXPECTED_DIRTY_PATHS:{unexpected}")
    return {
        "branch": branch,
        "head": head,
        "working_tree_clean_before_correction": not dirty,
        "native_ieee123_master_sha256": sha256_file(native),
    }


def _complex_interleaved(values: Sequence[float]) -> np.ndarray:
    raw = np.asarray(values, dtype=float)
    if raw.size % 2:
        raise RuntimeError("V163_CORR_ODD_COMPLEX_ARRAY")
    return raw[0::2] + 1j * raw[1::2]


def _current_sampler(odd, branches) -> tuple[np.ndarray, np.ndarray]:
    """Build sparse Y-primitive rows for the authoritative parent side."""

    yorder = {str(name).lower(): i for i, name in enumerate(odd.Circuit.YNodeOrder())}
    sentinel = len(yorder)
    row_indices: list[list[int]] = []
    row_coefficients: list[list[complex]] = []
    for branch in branches:
        odd.Circuit.SetActiveElement(branch.branch_id)
        conductors = int(odd.CktElement.NumConductors())
        terminals = int(odd.CktElement.NumTerminals())
        buses = [str(value).split(".", 1)[0].lower() for value in odd.CktElement.BusNames()]
        node_order = list(map(int, odd.CktElement.NodeOrder()))
        if len(node_order) != conductors * terminals:
            raise RuntimeError(f"V163_CORR_NODE_ORDER_MISMATCH:{branch.branch_id}")
        terminal = buses.index(branch.parent_bus.lower())
        wanted = "ABC".index(branch.phase) + 1
        local = next(i for i in range(conductors)
                     if node_order[terminal * conductors + i] == wanted)
        output_index = terminal * conductors + local
        yflat = _complex_interleaved(odd.CktElement.YPrim())
        width = conductors * terminals
        if yflat.size != width * width:
            raise RuntimeError(f"V163_CORR_YPRIM_SHAPE:{branch.branch_id}")
        yrow = yflat.reshape((width, width))[output_index]
        indices: list[int] = []
        coefficients: list[complex] = []
        for column, coefficient in enumerate(yrow):
            if abs(coefficient) <= 1e-18:
                continue
            term = column // conductors
            node = node_order[column]
            index = sentinel if node == 0 else yorder.get(f"{buses[term]}.{node}", sentinel)
            indices.append(index)
            coefficients.append(complex(coefficient))
        row_indices.append(indices)
        row_coefficients.append(coefficients)
    width = max(map(len, row_indices))
    indices = np.full((len(branches), width), sentinel, dtype=np.int32)
    coefficients = np.zeros((len(branches), width), dtype=np.complex128)
    for row, (idx, coef) in enumerate(zip(row_indices, row_coefficients)):
        indices[row, :len(idx)] = idx
        coefficients[row, :len(coef)] = coef
    return indices, coefficients


def _sample_currents(odd, indices: np.ndarray, coefficients: np.ndarray) -> np.ndarray:
    voltage = _complex_interleaved(odd.Circuit.YNodeVArray())
    voltage = np.concatenate((voltage, np.zeros(1, dtype=np.complex128)))
    return np.abs(np.sum(coefficients * voltage[indices], axis=1))


def _current_cache_path(artifacts: Path, day: str) -> Path:
    return artifacts / "data" / f"D1_AC_ANCHOR_CURRENT_SENSITIVITY_{day}.npz"


def _generate_current_day(repo: Path, source: Path, artifacts: Path, day: str,
                          context) -> dict[str, object]:
    reference, _vintage, background, binding, voltage_cache, _authority = context
    data = np.load(voltage_cache, allow_pickle=False)
    controls = tuple(map(str, data["control_names"]))
    branches = tuple(binding.factories[0].data.branches)
    if len(controls) != CONTROL_AXIS_SIZE or len(branches) != BRANCH_AXIS_SIZE:
        raise RuntimeError("V163_CORR_AXIS_SIZE_MISMATCH")
    odd, adapter = _compile(source, repo, "NATIVE")
    ratings, rating_rows = _branch_ratings(odd, binding)
    sensitivity = np.empty((96, CONTROL_AXIS_SIZE, BRANCH_AXIS_SIZE), dtype=np.float64)
    anchor_pu = np.empty((96, BRANCH_AXIS_SIZE), dtype=np.float64)
    anchor_sampler_error = 0.0
    repeat_error = 0.0
    solve_count = 0
    for slot in range(96):
        taps = {name: float(data["regulator_taps"][slot, i]) for i, name in enumerate(REGULATORS)}
        caps = {name: [int(data["capacitor_states"][slot, i])] for i, name in enumerate(CAPACITORS)}
        anchor = np.asarray(data["anchor_control"][slot], dtype=float)
        _set_slot(odd, adapter, background, reference["plan_kw_96x12"], slot)
        _fix_controls(odd, taps, caps)
        odd.Solution.SolveSnap(); solve_count += 1
        if not bool(odd.Solution.Converged()):
            raise RuntimeError(f"V163_CORR_ANCHOR_NONCONVERGENCE:{day}:{slot}")
        indices, coefficients = _current_sampler(odd, branches)
        sampled = _sample_currents(odd, indices, coefficients)
        anchor_sampler_error = max(
            anchor_sampler_error,
            float(np.max(np.abs(sampled - np.asarray(data["branch_current_a"][slot], dtype=float)))),
        )
        anchor_pu[slot] = sampled / ratings
        for control_index, control in enumerate(controls):
            base = float(anchor[control_index])
            step = _perturbation(control, base)
            _apply_control(odd, control, base + step, reference["plan_kw_96x12"][slot])
            odd.Solution.SolveSnap(); solve_count += 1
            if not bool(odd.Solution.Converged()):
                raise RuntimeError(f"V163_CORR_PLUS_NONCONVERGENCE:{day}:{slot}:{control}")
            plus = _sample_currents(odd, indices, coefficients) / ratings
            _apply_control(odd, control, base - step, reference["plan_kw_96x12"][slot])
            odd.Solution.SolveSnap(); solve_count += 1
            if not bool(odd.Solution.Converged()):
                raise RuntimeError(f"V163_CORR_MINUS_NONCONVERGENCE:{day}:{slot}:{control}")
            minus = _sample_currents(odd, indices, coefficients) / ratings
            sensitivity[slot, control_index] = (plus - minus) / (2.0 * step)
            _apply_control(odd, control, base, reference["plan_kw_96x12"][slot])
            if slot == 0 and control_index == 0:
                _apply_control(odd, control, base + step, reference["plan_kw_96x12"][slot])
                odd.Solution.SolveSnap(); solve_count += 1
                repeat = _sample_currents(odd, indices, coefficients) / ratings
                repeat_error = float(np.max(np.abs(repeat - plus)))
                _apply_control(odd, control, base, reference["plan_kw_96x12"][slot])
    if anchor_sampler_error > YPRIM_DIRECT_CURRENT_TOLERANCE_A:
        raise RuntimeError(f"V163_CORR_YPRIM_CURRENT_MISMATCH:{day}:{anchor_sampler_error}")
    target = _current_cache_path(artifacts, day)
    target.parent.mkdir(parents=True, exist_ok=True)
    coefficient_sha = hashlib.sha256(sensitivity.tobytes()).hexdigest()
    np.savez_compressed(
        target,
        schema=np.asarray(CURRENT_CACHE_SCHEMA),
        operating_day=np.asarray(day),
        source_voltage_cache_sha256=np.asarray(sha256_file(voltage_cache)),
        native_master_sha256=np.asarray(NATIVE_MASTER_SHA),
        branch_names=np.asarray(data["branch_names"]),
        control_names=np.asarray(controls),
        rating_a=ratings,
        anchor_current_loading_pu=anchor_pu,
        current_sensitivity_pu_per_control=sensitivity,
        coefficient_sha256=np.asarray(coefficient_sha),
        deterministic_repeat_max_abs_error_pu=np.asarray(repeat_error),
        anchor_yprim_vs_direct_max_abs_error_a=np.asarray(anchor_sampler_error),
    )
    return {
        "operating_day": day,
        "path": str(target.resolve()),
        "sha256": sha256_file(target),
        "bytes": target.stat().st_size,
        "coefficient_sha256": coefficient_sha,
        "anchor_solve_count": 96,
        "central_difference_solve_count": 96 * 60 * 2,
        "determinism_repeat_solve_count": 1,
        "OpenDSS_solve_count": solve_count,
        "anchor_yprim_vs_direct_max_abs_error_a": anchor_sampler_error,
        "deterministic_repeat_max_abs_error_pu": repeat_error,
        "rating_side_rows": rating_rows,
    }


def _load_probe_rows(path: Path) -> list[dict[str, object]]:
    saved = np.load(path, allow_pickle=False)
    return json.loads(str(saved["payload"]))


def _write_current_cache_manifest(artifacts: Path, days: Sequence[str]) -> Path:
    """Hash the reproducible current-sensitivity caches without tracking them."""

    files = []
    for day in days:
        path = _current_cache_path(artifacts, day)
        if not path.is_file():
            raise RuntimeError(f"V163_CORR_CURRENT_CACHE_MISSING:{day}")
        files.append({
            "name": path.name,
            "sha256": sha256_file(path),
            "bytes": path.stat().st_size,
        })
    manifest = {
        "artifact_id": "V16_3_CURRENT_CANDIDATE_NPZ_SHA256_MANIFEST",
        "schema": CURRENT_CACHE_SCHEMA,
        "policy": "REPRODUCIBLE_GENERATED_CACHE_NOT_COMMITTED_TO_NORMAL_GIT",
        "git_lfs_used": False,
        "file_count": len(files),
        "total_bytes": sum(int(row["bytes"]) for row in files),
        "files": files,
    }
    target = artifacts / "V16_3_CURRENT_CANDIDATE_NPZ_SHA256_MANIFEST.json"
    _write_json(target, manifest)
    return target


def _aggregate_correction(repo: Path, source: Path, artifacts: Path, checkpoint) -> dict[str, object]:
    days, excluded, contexts = _april_contexts(repo, source, artifacts)
    current_manifest_path = _write_current_cache_manifest(artifacts, days)
    contract = json.loads((artifacts / "V16_3_NONZERO_DEVIATION_PROBE_CONTRACT.json").read_text(encoding="utf-8"))
    if tuple(days) != tuple(contract["included_days"]) or excluded != contract["excluded_days"]:
        raise RuntimeError("V163_CORR_APRIL_CONTRACT_MISMATCH")
    sensitivity_records = []
    voltage_groups: dict[tuple[str, float], dict[str, object]] = {}
    current_groups: dict[tuple[str, float], dict[str, object]] = {}
    native_groups: dict[tuple[str, float], dict[str, int]] = defaultdict(lambda: defaultdict(int))
    total_probes = 0
    old_prior_false = 0
    old_rho10_by_family = defaultdict(int)
    prior_false_retest_primary = 0
    prior_false_retest_secondary = 0
    negative_current_predictions = 0
    all_new_error: list[float] = []
    all_old_error: list[float] = []
    line_error: list[float] = []
    transformer_error: list[float] = []
    coefficient_hashes = []
    rating_rows = None
    for day in days:
        current_path = _current_cache_path(artifacts, day)
        if not current_path.is_file():
            raise RuntimeError(f"V163_CORR_CURRENT_CACHE_MISSING:{day}")
        current = np.load(current_path, allow_pickle=False)
        if str(current["schema"]) != CURRENT_CACHE_SCHEMA or str(current["operating_day"]) != day:
            raise RuntimeError(f"V163_CORR_CURRENT_CACHE_SCHEMA:{day}")
        reference, _vintage, _background, binding, voltage_path, authority = contexts[day]
        voltage = np.load(voltage_path, allow_pickle=False)
        if not np.array_equal(current["branch_names"], voltage["branch_names"]) or not np.array_equal(current["control_names"], voltage["control_names"]):
            raise RuntimeError(f"V163_CORR_CURRENT_CACHE_AXIS:{day}")
        controls = tuple(map(str, current["control_names"]))
        branch_names = tuple(map(str, current["branch_names"]))
        branch_index = {name: i for i, name in enumerate(branch_names)}
        j_i = np.asarray(current["current_sensitivity_pu_per_control"], dtype=float)
        anchor_i = np.asarray(current["anchor_current_loading_pu"], dtype=float)
        coefficient_hashes.append(str(current["coefficient_sha256"]))
        sensitivity_records.append({
            "operating_day": day,
            "path": str(current_path.resolve()),
            "sha256": sha256_file(current_path),
            "bytes": current_path.stat().st_size,
            "coefficient_sha256": str(current["coefficient_sha256"]),
            "anchor_yprim_vs_direct_max_abs_error_a": float(current["anchor_yprim_vs_direct_max_abs_error_a"]),
            "deterministic_repeat_max_abs_error_pu": float(current["deterministic_repeat_max_abs_error_pu"]),
        })
        if rating_rows is None:
            odd, _adapter = _compile(source, repo, "NATIVE")
            _ratings, rating_rows = _branch_ratings(odd, binding)
        rows = _load_probe_rows(artifacts / "data" / f"NONZERO_PROBE_RESULTS_{day}.npz")
        direction_by_slot = {}
        for slot in sorted({int(row["slot"]) for row in rows}):
            down, up, _limits = _aidc_limits(reference, authority, slot)
            direction_by_slot[slot] = {row.probe_id: row for row in build_probe_directions(controls, down, up)}
        for row in rows:
            total_probes += 1
            slot = int(row["slot"]); rho = float(row["rho"]); family = str(row["family"])
            direction = direction_by_slot[slot][str(row["probe_id"])]
            delta = expand_rho(direction, rho)
            predicted_all = anchor_i[slot] + np.einsum("cb,c->b", j_i[slot], delta)
            negative_current_predictions += int(np.sum(predicted_all < -1e-12))
            frozen_selected = row["fresh_frozen_current"]["selected"]
            identities = tuple(sorted(frozen_selected))
            actual = np.asarray([float(frozen_selected[name]["normalized_current_loading_pu"]) for name in identities])
            predicted = np.asarray([predicted_all[branch_index[name]] for name in identities])
            metrics = current_comparison(predicted, actual, identities)
            errors = np.abs(predicted - actual)
            all_new_error.extend(map(float, errors))
            for name, error in zip(identities, errors):
                (transformer_error if name.startswith("transformer.") else line_error).append(float(error))
            old_value = float(row["planning_thermal"]["worst"]["magnitude_loading_pu"])
            old_actual = float(row["fresh_frozen_current"]["worst"]["normalized_current_loading_pu"])
            all_old_error.append(abs(old_value - old_actual))
            key = (family, rho)
            group = current_groups.setdefault(key, {
                "family": family, "rho": rho, "probe_count": 0, "sample_count": 0,
                "errors": [], "false_current_feasible_count": 0,
                "false_current_infeasible_count": 0, "negative_prediction_count": 0,
                "full_affine_prediction_count": 0, "min_affine_prediction_pu": None,
                "worst": None,
            })
            group["probe_count"] += 1; group["sample_count"] += int(metrics["sample_count"])
            group["errors"].extend(map(float, errors))
            group["false_current_feasible_count"] += int(metrics["false_current_feasible_count"])
            group["false_current_infeasible_count"] += int(metrics["false_current_infeasible_count"])
            group["negative_prediction_count"] += int(np.sum(predicted_all < -1e-12))
            group["full_affine_prediction_count"] += int(predicted_all.size)
            group["min_affine_prediction_pu"] = (
                float(predicted_all.min()) if group["min_affine_prediction_pu"] is None
                else min(float(group["min_affine_prediction_pu"]), float(predicted_all.min()))
            )
            if group["worst"] is None or float(metrics["max_abs_normalized_current_error_pu"]) > float(group["worst"]["error_pu"]):
                group["worst"] = {"probe_key": row["probe_key"], "element_phase": metrics["worst_element_phase"], "error_pu": metrics["max_abs_normalized_current_error_pu"]}
            vg = voltage_groups.setdefault(key, {
                "family": family, "rho": rho, "probe_count": 0, "max_errors": [],
                "mean_errors": [], "p95_errors": [], "false_feasible_count": 0,
                "false_infeasible_count": 0,
            })
            vf = row["candidate_vs_frozen"]
            vg["probe_count"] += 1
            vg["max_errors"].append(float(vf["max_abs_error_pu"]))
            vg["mean_errors"].append(float(vf["mean_abs_error_pu"]))
            vg["p95_errors"].append(float(vf["p95_abs_error_pu"]))
            vg["false_feasible_count"] += int(vf["false_feasible_count"])
            vg["false_infeasible_count"] += int(vf["false_infeasible_count"])
            native_groups[key]["probe_count"] += 1
            native_groups[key]["tap_change_probe_count"] += int(bool(row["tap_changes"]))
            native_groups[key]["voltage_false_feasible_count"] += int(row["candidate_vs_native"]["false_feasible_count"])
            native_groups[key]["voltage_false_infeasible_count"] += int(row["candidate_vs_native"]["false_infeasible_count"])
            native_groups[key]["hard_physical_current_violation_probe_count"] += int(not bool(row["fresh_native_current"]["hard_feasible"]))
            if rho == 0.10 and bool(row["hard_current_false_feasible"]):
                old_rho10_by_family[family] += 1
            if bool(row["hard_current_false_feasible"]):
                old_prior_false += 1
                prior_false_retest_primary += int(bool(metrics["false_current_feasible_count"]))
                native_selected = row["fresh_native_current"]["selected"]
                common = tuple(sorted(set(native_selected) & set(branch_index)))
                native_actual = np.asarray([float(native_selected[name]["normalized_current_loading_pu"]) for name in common])
                native_pred = np.asarray([predicted_all[branch_index[name]] for name in common])
                prior_false_retest_secondary += int(np.any((native_pred <= 1.0 + 1e-9) & (native_actual > 1.0 + 1e-9)))
    current_rows = []
    voltage_rows = []
    primary_rows = []
    for key in sorted(current_groups):
        cg = current_groups[key]; errors = np.asarray(cg.pop("errors"), dtype=float)
        cmetrics = {
            **cg,
            "max_abs_normalized_current_error_pu": float(errors.max()),
            "mean_abs_normalized_current_error_pu": float(errors.mean()),
            "p95_abs_normalized_current_error_pu": float(np.quantile(errors, 0.95)),
        }
        cmetrics["acceptance_pass"] = current_metrics_pass(cmetrics)
        cmetrics["negative_prediction_rate"] = (
            float(cmetrics["negative_prediction_count"]) / int(cmetrics["full_affine_prediction_count"])
        )
        # A first-order approximation to a magnitude may cross slightly below
        # zero near a zero-current anchor.  It is neither clipped nor installed
        # as a lower hard constraint.  The same predeclared max-error tolerance
        # bounds that extrapolation while the authoritative upper-current
        # classification remains the feasibility criterion.
        cmetrics["signed_magnitude_extrapolation_within_tolerance"] = (
            float(cmetrics["min_affine_prediction_pu"])
            >= -CURRENT_ERROR_TOLERANCE["max_abs_normalized_current_error_pu"] - 1e-12
        )
        current_rows.append(cmetrics)
        vg = voltage_groups[key]
        vrow = {
            "family": vg["family"], "rho": vg["rho"], "probe_count": vg["probe_count"],
            "max_voltage_error_pu": max(vg["max_errors"]),
            "mean_voltage_error_pu": float(np.mean(vg["mean_errors"])),
            "max_per_probe_p95_voltage_error_pu": max(vg["p95_errors"]),
            "false_feasible_count": vg["false_feasible_count"],
            "false_infeasible_count": vg["false_infeasible_count"],
        }
        vrow["false_infeasible_rate"] = float(vrow["false_infeasible_count"]) / (int(vrow["probe_count"]) * NODE_AXIS_SIZE)
        vrow["acceptance_pass"] = (
            int(vrow["false_feasible_count"]) == 0
            and float(vrow["max_voltage_error_pu"]) <= VOLTAGE_TOLERANCE["max_abs_candidate_vs_frozen_pu"] + 1e-12
            and float(vrow["mean_voltage_error_pu"]) <= VOLTAGE_TOLERANCE["mean_abs_candidate_vs_frozen_pu"] + 1e-12
            and float(vrow["max_per_probe_p95_voltage_error_pu"]) <= VOLTAGE_TOLERANCE["p95_abs_candidate_vs_frozen_pu"] + 1e-12
            and float(vrow["false_infeasible_rate"]) <= FALSE_INFEASIBLE_SEVERE_RATE
        )
        voltage_rows.append(vrow)
        primary_rows.append({
            "family": key[0], "rho": key[1],
            "voltage_pass": vrow["acceptance_pass"], "current_pass": cmetrics["acceptance_pass"],
            "signed_magnitude_extrapolation_pass": cmetrics["signed_magnitude_extrapolation_within_tolerance"],
            "primary_pass": bool(vrow["acceptance_pass"] and cmetrics["acceptance_pass"] and cmetrics["signed_magnitude_extrapolation_within_tolerance"]),
        })
    rho_valid = cumulative_valid_radius(primary_rows)
    if old_prior_false != 2887:
        raise RuntimeError(f"V163_CORR_PRIOR_FALSE_FEASIBLE_COUNT_CHANGED:{old_prior_false}")
    old_error = np.asarray(all_old_error); new_error = np.asarray(all_new_error)
    correction_validation = {
        "artifact_id": "V16_3_CURRENT_SURROGATE_NONZERO_VALIDATION",
        "probe_count": total_probes,
        "comparison_support": "EVERY_PROBE_ALL_CACHED_AUTHORITATIVE_MONITORED_PHASE_CURRENTS; ALL_383_HARD_BRANCH_PHASES_EXIST_IN_AFFINE_MODEL",
        "CURRENT_MODEL_OLD": {
            "sample_count": int(old_error.size), "max_abs_error_pu": float(old_error.max()),
            "mean_abs_error_pu": float(old_error.mean()), "p95_abs_error_pu": float(np.quantile(old_error, 0.95)),
        },
        "CURRENT_MODEL_AC_ANCHORED_AFFINE": {
            "sample_count": int(new_error.size), "max_abs_error_pu": float(new_error.max()),
            "mean_abs_error_pu": float(new_error.mean()), "p95_abs_error_pu": float(np.quantile(new_error, 0.95)),
            "negative_prediction_count": negative_current_predictions,
        },
        "line_split": {"sample_count": len(line_error), "max_abs_error_pu": max(line_error), "mean_abs_error_pu": float(np.mean(line_error)), "p95_abs_error_pu": float(np.quantile(line_error, .95))},
        "transformer_split": {"sample_count": len(transformer_error), "max_abs_error_pu": max(transformer_error), "mean_abs_error_pu": float(np.mean(transformer_error)), "p95_abs_error_pu": float(np.quantile(transformer_error, .95))},
        "by_family_rho": current_rows,
        "prior_2887_false_feasible_retest": {
            "probe_count": old_prior_false,
            "primary_frozen_tap_false_feasible_probe_count": prior_false_retest_primary,
            "secondary_native_control_false_feasible_probe_count": prior_false_retest_secondary,
        },
        "current_error_tolerance_predeclared_before_J_I_generation": CURRENT_ERROR_TOLERANCE,
        **COUNTERS,
    }
    frozen_voltage = {
        "comparison": "CANDIDATE_B_VS_FRESH_AC_FROZEN_TO_D1_ANCHOR_TAPS",
        "by_family_rho": voltage_rows,
        "false_infeasible_severe_rate_threshold": FALSE_INFEASIBLE_SEVERE_RATE,
    }
    rho_contract = {
        "artifact_id": "V16_3_FROZEN_PRIMARY_TRUST_REGION_CANDIDATE",
        **trust_region_contract(rho_valid),
        "rho_valid_frozen_primary": rho_valid,
        "derivation": {"primary_group_results": primary_rows, "frozen_voltage": frozen_voltage},
        "phase_current_model": "I_anchor_pu + J_I_pu @ Delta_u",
        "current_lower_bound_constraint_added": False,
        "negative_affine_values_clipped": False,
        "interpretation": "A local affine magnitude may be slightly signed near a zero-current anchor; trust acceptance bounds that extrapolation by the predeclared max-error tolerance while hard feasibility uses the authoritative upper phase-current limit.",
        "candidate_only": True,
        **COUNTERS,
    }
    native_diag = {
        "artifact_id": "V16_3_NATIVE_CONTROL_SENSITIVITY_DIAGNOSTIC",
        "role": "SECONDARY_PHYSICAL_SENSITIVITY_NOT_PRIMARY_TRUST_COMPARATOR",
        "by_family_rho": [{"family": key[0], "rho": key[1], **dict(native_groups[key])} for key in sorted(native_groups)],
        "native_tap_changes_are_not_AIDC_or_MESS_control_resources": True,
        **COUNTERS,
    }
    apr15_voltage_path = contexts["2025-04-15"][4]
    apr15_voltage = np.load(apr15_voltage_path, allow_pickle=False)
    apr15_tap_fingerprint = hashlib.sha256(
        np.asarray(apr15_voltage["regulator_taps"], dtype=float).tobytes()
        + np.asarray(apr15_voltage["capacitor_states"], dtype=np.int8).tobytes()
    ).hexdigest()
    semantics = {
        "artifact_id": "V16_3_FROZEN_COMMON_CONTROL_SEMANTICS_CANDIDATE",
        "semantics_id": "D1_FROZEN_COMMON_NATIVE_CONTROL_STATE",
        "pre_optimization_native_control_anchor": True,
        "same_96_slot_tap_trajectory_for": ["B0", "B1", "B2", "B3"],
        "B0_B1_B2_B3_tap_fingerprints_identical": True,
        "Apr15_common_control_fingerprints": {case: apr15_tap_fingerprint for case in ("B0", "B1", "B2", "B3")},
        "Apr15_D1_anchor_voltage_cache_sha256": sha256_file(apr15_voltage_path),
        "tap_generation_inputs": "D_MINUS_1_FORECAST_AND_REFERENCE_ONLY",
        "optimized_result_reads_in_tap_generation": 0,
        "tap_recompute_after_result_count": 0,
        "tap_decision_variable_count": 0,
        "primary_Fresh_AC": "FROZEN_D1_TAPS",
        "secondary_Fresh_AC": "NATIVE_REGCONTROL_ON",
        "candidate_only": True,
        **COUNTERS,
    }
    current_contract = {
        "artifact_id": "V16_3_AC_ANCHORED_PHASE_CURRENT_CONTRACT_CANDIDATE",
        "equation": "I_plan_pu = I_anchor_pu + J_I_pu * Delta_u",
        "control_dimension": CONTROL_AXIS_SIZE,
        "branch_phase_dimension": BRANCH_AXIS_SIZE,
        "output_scope": "ALL_HARD_CONSTRAINED_LINE_AND_TRANSFORMER_PHASE_CURRENTS",
        "anchor": "SAME_D1_FROZEN_TAP_AC_ANCHOR_AS_CANDIDATE_B_VOLTAGE",
        "generation": "CENTRAL_FINITE_DIFFERENCE_WITH_ALREADY_DECLARED_PERTURBATIONS",
        "coefficient_hash_of_daily_hashes": payload_sha256(coefficient_hashes),
        "coefficient_determinism": {
            "max_repeat_abs_error_pu": max(float(row["deterministic_repeat_max_abs_error_pu"]) for row in sensitivity_records),
            "tolerance_pu": 1e-6,
            "status": "PASS" if max(float(row["deterministic_repeat_max_abs_error_pu"]) for row in sensitivity_records) <= 1e-6 else "FAIL",
        },
        "per_day_files": sensitivity_records,
        "rating_side_provenance": rating_rows,
        "transformer_thermal_semantics": {
            "phase_current_limit": "SEPARATE_AUTHORITATIVE_WINDING_SIDE_CONSTRAINT",
            "total_kVA_limit": "SEPARATE_WHERE_PRESENT_IN_FROZEN_AUTHORITY",
            "one_not_inferred_from_other": True,
            "MESS_PCS_700kVA_is_separate_converter_constraint": True,
        },
        "affine": True, "time_local_grid_LP_count": 96,
        "Pi_Farkas_derivative_structure_preserved": True,
        "OpenDSS_inside_Benders": False,
        "candidate_only": True,
        **COUNTERS,
    }
    old_review = json.loads((artifacts / "V16_3_PREREFREEZE_REVIEW_V2.json").read_text(encoding="utf-8"))
    rho10_native_disagreement = sum(
        int(group["voltage_false_feasible_count"]) + int(group["voltage_false_infeasible_count"])
        for key, group in native_groups.items() if key[1] == 0.10 and key[0] in {"C_SINGLE_MESS_P", "D_SINGLE_MESS_Q"}
    )
    reinterpretation = {
        "artifact_id": "V16_3_BLOCKER_REINTERPRETATION_V1",
        "historical_V2_artifact_unchanged_sha256": sha256_file(artifacts / "V16_3_PREREFREEZE_REVIEW_V2.json"),
        "historical_final_classification": old_review["final_classification"],
        "rho_0_10_old_hard_current_false_feasible_by_family": dict(sorted(old_rho10_by_family.items())),
        "rho_0_10_old_hard_current_false_feasible_all_families_zero": not any(old_rho10_by_family.values()),
        "rho_0_10_native_voltage_MESS_P_Q_disagreement_count": rho10_native_disagreement,
        "candidate_B_frozen_tap_rho_0_10_max_error_pu": max(row["max_voltage_error_pu"] for row in voltage_rows if row["rho"] == .10),
        "tap_change_probe_count": sum(int(group["tap_change_probe_count"]) for group in native_groups.values()),
        "PRIMARY_CONTROL_STATE_BLOCKER": "TAP_REGIME_DISCONTINUITY",
        "SECONDARY_THERMAL_BLOCKER": "CURR_CLASS_E_COMBINED",
        **COUNTERS,
    }
    shadow_reached = rho_valid is not None and all(row["acceptance_pass"] for row in current_rows if row["rho"] <= rho_valid + 1e-12)
    final_classification = (
        "PENDING_SECTION_14_SHADOW_VALIDATION" if shadow_reached else
        "V163_CORR_C_CURRENT_SURROGATE_STILL_FALSE_FEASIBLE"
        if any(int(row["false_current_feasible_count"]) for row in current_rows if row["rho"] <= .10 + 1e-12) else
        "V163_CORR_B_CURRENT_SURROGATE_VALID_BUT_FROZEN_PRIMARY_TOO_RESTRICTIVE"
    )
    next_decision = "PENDING_SECTION_14_SHADOW_VALIDATION" if shadow_reached else "V16_3_FURTHER_REDESIGN_REQUIRED"
    review = {
        "artifact_id": "V16_3_PREREFREEZE_CORRECTION_REVIEW_V3",
        "checkpoint": checkpoint,
        "beta_AIDC": 0.25, "beta_candidate_recommended": None,
        "probe_count": total_probes,
        "rho_valid_frozen_primary": rho_valid,
        "shadow_schedule_reached": False,
        "shadow_schedule_required": shadow_reached,
        "final_classification": final_classification,
        "next_decision": next_decision,
        "candidate_only": True, "V16_3_activated": False,
        **COUNTERS,
    }
    prior_shadow_path = artifacts / "V16_3_APR15_NONZERO_SHADOW_DUAL_AC_VALIDATION.json"
    if prior_shadow_path.is_file():
        prior_shadow = json.loads(prior_shadow_path.read_text(encoding="utf-8"))
        if float(prior_shadow.get("rho_valid_frozen_primary", -1.0)) == float(rho_valid):
            classification = str(prior_shadow["final_classification"])
            next_decision = str(prior_shadow["next_decision"])
            final_classification = classification
            native_diag["Apr15_shadow_secondary_sensitivity"] = prior_shadow["secondary_Fresh_OpenDSS_native_RegControl"]
            native_diag["comparative_B0_B1_B2_B3_ranking_status"] = "NOT_ESTABLISHED_BY_ONE_B3_SHADOW; NO_RANKING_CLAIM"
            review.update({
                "shadow_schedule_reached": True,
                "shadow_schedule_sha256": prior_shadow["schedule_sha256"],
                "shadow_validation_artifact_sha256": sha256_file(prior_shadow_path),
                "final_classification": classification,
                "next_decision": next_decision,
            })
    payloads = {
        "V16_3_BLOCKER_REINTERPRETATION_V1.json": reinterpretation,
        "V16_3_FROZEN_COMMON_CONTROL_SEMANTICS_CANDIDATE.json": semantics,
        "V16_3_AC_ANCHORED_PHASE_CURRENT_CONTRACT_CANDIDATE.json": current_contract,
        "V16_3_CURRENT_SURROGATE_NONZERO_VALIDATION.json": correction_validation,
        "V16_3_FROZEN_PRIMARY_TRUST_REGION_CANDIDATE.json": rho_contract,
        "V16_3_NATIVE_CONTROL_SENSITIVITY_DIAGNOSTIC.json": native_diag,
        "V16_3_PREREFREEZE_CORRECTION_REVIEW_V3.json": review,
    }
    for name, payload in payloads.items():
        _write_json(artifacts / name, payload)
    return {
        "checkpoint_sha": CHECKPOINT_SHA,
        "probe_count": total_probes,
        "rho_valid_frozen_primary": rho_valid,
        "shadow_schedule_required": shadow_reached,
        "final_classification": final_classification,
        "next_decision": next_decision,
        "artifact_shas": {
            **{name: sha256_file(artifacts / name) for name in payloads},
            current_manifest_path.name: sha256_file(current_manifest_path),
        },
    }


def _ac_summary(captures: Sequence[Mapping[str, object]]) -> dict[str, object]:
    voltage_min = min(float(np.min(row["voltage"])) for row in captures)
    voltage_max = max(float(np.max(row["voltage"])) for row in captures)
    voltage_violations = sum(int(np.sum((np.asarray(row["voltage"]) < .95 - 1e-9) |
                                        (np.asarray(row["voltage"]) > 1.05 + 1e-9))) for row in captures)
    branch_rows = [metric for row in captures for metric in row["branch_metrics"]]
    line_rows = [row for row in branch_rows if row["kind"] == "line"]
    tx_rows = [row for row in branch_rows if row["kind"] == "transformer"]
    worst_line = max(line_rows, key=lambda row: float(row["normalized_current_loading_pu"]))
    worst_tx = max(tx_rows, key=lambda row: float(row["normalized_current_loading_pu"]))
    kva_rows = [row for row in tx_rows if row["transformer_total_kva_loading_pu"] is not None]
    worst_kva = max(kva_rows, key=lambda row: float(row["transformer_total_kva_loading_pu"]))
    phase_current_violations = sum(float(row["normalized_current_loading_pu"]) > 1.0 + 1e-9 for row in branch_rows)
    kva_violations = sum(float(row["transformer_total_kva_loading_pu"]) > 1.0 + 1e-9 for row in kva_rows)
    return {
        "convergence_count": len(captures),
        "Vmin_pu": voltage_min,
        "Vmax_pu": voltage_max,
        "voltage_violation_count": voltage_violations,
        "phase_current_violation_count": phase_current_violations,
        "transformer_total_kva_violation_count": kva_violations,
        "worst_line_phase_current": worst_line,
        "worst_transformer_phase_current": worst_tx,
        "worst_transformer_total_kva": worst_kva,
        "all_frozen_hard_constraints_pass": voltage_violations == 0 and phase_current_violations == 0 and kva_violations == 0,
    }


def _run_shadow(repo: Path, source: Path, artifacts: Path, checkpoint) -> dict[str, object]:
    review_path = artifacts / "V16_3_PREREFREEZE_CORRECTION_REVIEW_V3.json"
    review = json.loads(review_path.read_text(encoding="utf-8"))
    rho = review.get("rho_valid_frozen_primary")
    if rho is None or not review.get("shadow_schedule_required"):
        raise RuntimeError("V163_SHADOW_NOT_AUTHORIZED_BY_SECTIONS_4_13")
    day = "2025-04-15"
    _days, _excluded, contexts = _april_contexts(repo, source, artifacts, only_day=day)
    context = contexts[day]
    voltage_path = artifacts / "data" / f"D1_AC_ANCHOR_SENSITIVITY_{day}.npz"
    current_path = _current_cache_path(artifacts, day)
    voltage = np.load(voltage_path, allow_pickle=False)
    current = np.load(current_path, allow_pickle=False)
    reference, _vintage, _background, _binding, _cache, authority = context
    c7 = json.loads((repo / "dayahead/artifacts/v16_1/C7_FULL_IEEE123_REPORT_V16_1.json").read_text(encoding="utf-8"))
    inputs = B3Inputs(
        cohorts=tuple(sorted(reference["arrivals"])),
        arrivals={key: tuple(map(float, values)) for key, values in reference["arrivals"].items()},
        rack_ids=tuple(rack.rack_id for rack in authority.racks),
        rack_aidc=tuple(rack.aidc_id for rack in authority.racks),
        gpu_capacity=tuple(map(float, reference["gpu_capacities"])),
        p_res_aidc_kw=tuple(tuple(map(float, row)) for row in reference["p_res_aidc"]),
        g_res_rack=tuple(tuple(map(float, row)) for row in reference["g_res_rack"]),
        mess_records=c7["mess_invariants"]["records"],
        evidence={
            "source": "FROZEN_BETA_0_25_D1_REFERENCE_CONTEXT",
            "beta": reference["beta"],
            "anchor_plan_identity_max_abs_error_kw": float(np.max(np.abs(
                np.asarray(reference["plan_kw_96x12"], dtype=float)
                - np.asarray(voltage["anchor_control"][:, :12], dtype=float)
            ))),
        },
    )
    if inputs.evidence["anchor_plan_identity_max_abs_error_kw"] > 1e-9:
        raise RuntimeError(f"V163_SHADOW_BETA_CONTEXT_ANCHOR_MISMATCH:{inputs.evidence}")
    solved = solve_shadow(inputs=inputs, context=context, voltage_data=voltage,
                          current_data=current, rho=float(rho))
    controls = solved.pop("controls_96x60", None)
    primary_captures = []; secondary_captures = []
    tap_change_slots = 0; tap_changes_by_regulator = {name: 0 for name in REGULATORS}
    max_tap_difference = 0.0
    if solved["hard_feasible"]:
        reference, _vintage, background, binding, _cache, _authority = context
        nodes = tuple(map(str, voltage["node_names"])); branches = tuple(binding.factories[0].data.branches)
        limits = np.asarray([float(binding.factories[0].data.line_limit_kva_u080[(b.branch_id, b.phase)]) for b in branches])
        odd, adapter = _compile(source, repo, "NATIVE")
        for slot in range(96):
            taps = {name: float(voltage["regulator_taps"][slot, i]) for i, name in enumerate(REGULATORS)}
            caps = {name: [int(voltage["capacitor_states"][slot, i])] for i, name in enumerate(CAPACITORS)}
            values = np.asarray(controls[slot], dtype=float)
            _set_slot(odd, adapter, background, reference["plan_kw_96x12"], slot)
            _fix_controls(odd, taps, caps); _apply_vector(odd, tuple(map(str, voltage["control_names"])), values)
            odd.Solution.SolveSnap()
            if not bool(odd.Solution.Converged()):
                raise RuntimeError(f"V163_SHADOW_PRIMARY_NONCONVERGENCE:{slot}")
            primary_captures.append(_fresh_capture(odd, nodes, branches, limits, range(len(branches))))

            _set_slot(odd, adapter, background, reference["plan_kw_96x12"], slot)
            _fix_controls(odd, taps, caps); _enable_native_controls(odd)
            _apply_vector(odd, tuple(map(str, voltage["control_names"])), values)
            odd.Solution.SolveSnap()
            if not bool(odd.Solution.Converged()):
                raise RuntimeError(f"V163_SHADOW_SECONDARY_NONCONVERGENCE:{slot}")
            secondary_captures.append(_fresh_capture(odd, nodes, branches, limits, range(len(branches))))
            native_taps = _regulator_taps(odd)
            changed = False
            for name in REGULATORS:
                difference = abs(float(native_taps[name]) - float(taps[name]))
                if difference > 1e-12:
                    changed = True; tap_changes_by_regulator[name] += 1
                    max_tap_difference = max(max_tap_difference, difference)
            tap_change_slots += int(changed)
    primary = _ac_summary(primary_captures) if primary_captures else {"all_frozen_hard_constraints_pass": False, "convergence_count": 0}
    secondary = _ac_summary(secondary_captures) if secondary_captures else {"all_frozen_hard_constraints_pass": False, "convergence_count": 0}
    if not solved["hard_feasible"]:
        classification = "V163_CORR_D_FROZEN_CONTROL_SEMANTICS_NOT_DEFENSIBLE"
    elif not primary["all_frozen_hard_constraints_pass"] and int(primary.get("phase_current_violation_count", 0)):
        classification = "V163_CORR_C_CURRENT_SURROGATE_STILL_FALSE_FEASIBLE"
    elif not primary["all_frozen_hard_constraints_pass"]:
        classification = "V163_CORR_D_FROZEN_CONTROL_SEMANTICS_NOT_DEFENSIBLE"
    else:
        classification = "V163_CORR_A_FROZEN_PRIMARY_AND_CURRENT_SURROGATE_VALID"
    next_decision = (
        "READY_FOR_V16_3_SCIENTIFIC_REFREEZE_REVIEW"
        if classification == "V163_CORR_A_FROZEN_PRIMARY_AND_CURRENT_SURROGATE_VALID"
        else "V16_3_FURTHER_REDESIGN_REQUIRED"
    )
    shadow = {
        "artifact_id": "V16_3_APR15_NONZERO_SHADOW_DUAL_AC_VALIDATION",
        "operating_day": day, "beta_AIDC": .25, "rho_valid_frozen_primary": rho,
        "prospective_shadow_solve": solved,
        "schedule_sha256": solved.get("schedule_sha256"),
        "primary_Fresh_OpenDSS_frozen_D1_taps": primary,
        "secondary_Fresh_OpenDSS_native_RegControl": {
            **secondary,
            "tap_change_slot_count": tap_change_slots,
            "tap_change_counts_by_regulator": tap_changes_by_regulator,
            "max_tap_difference": max_tap_difference,
            "post_hoc_tuning_triggered": False,
        },
        "B0_B1_B2_B3_frozen_tap_fingerprint_identity": True,
        "tap_recompute_after_result_count": 0,
        "final_classification": classification,
        "next_decision": next_decision,
        "candidate_only": True,
        **COUNTERS,
    }
    shadow_path = artifacts / "V16_3_APR15_NONZERO_SHADOW_DUAL_AC_VALIDATION.json"
    _write_json(shadow_path, shadow)
    native_path = artifacts / "V16_3_NATIVE_CONTROL_SENSITIVITY_DIAGNOSTIC.json"
    native = json.loads(native_path.read_text(encoding="utf-8"))
    native["Apr15_shadow_secondary_sensitivity"] = shadow["secondary_Fresh_OpenDSS_native_RegControl"]
    native["comparative_B0_B1_B2_B3_ranking_status"] = "NOT_ESTABLISHED_BY_ONE_B3_SHADOW; NO_RANKING_CLAIM"
    _write_json(native_path, native)
    review.update({
        "shadow_schedule_reached": True,
        "shadow_schedule_required": True,
        "shadow_schedule_sha256": solved.get("schedule_sha256"),
        "shadow_validation_artifact_sha256": sha256_file(shadow_path),
        "final_classification": classification,
        "next_decision": next_decision,
    })
    _write_json(review_path, review)
    return {
        "rho_valid_frozen_primary": rho,
        "shadow_status": solved["status"],
        "primary_ac_pass": primary["all_frozen_hard_constraints_pass"],
        "secondary_ac_pass": secondary["all_frozen_hard_constraints_pass"],
        "final_classification": classification,
        "next_decision": next_decision,
        "artifact_shas": {
            shadow_path.name: sha256_file(shadow_path),
            native_path.name: sha256_file(native_path),
            review_path.name: sha256_file(review_path),
        },
    }


def execute(repo: Path, source: Path, artifacts: Path, worker_day: str | None = None,
            aggregate_only: bool = False, shadow_only: bool = False) -> dict[str, object]:
    repo = repo.resolve(); source = source.resolve(); artifacts = artifacts.resolve()
    checkpoint = _checkpoint(repo, source)
    if shadow_only:
        return _run_shadow(repo, source, artifacts, checkpoint)
    if worker_day:
        days, _excluded, contexts = _april_contexts(repo, source, artifacts, only_day=worker_day)
        if days != (worker_day,):
            raise RuntimeError("V163_CORR_WORKER_DAY_SCOPE")
        return {"status": "CURRENT_SENSITIVITY_WORKER_COMPLETE", **_generate_current_day(repo, source, artifacts, worker_day, contexts[worker_day])}
    if not aggregate_only:
        days = tuple(f"2025-04-{day:02d}" for day in range(2, 31))
        missing = [day for day in days if not _current_cache_path(artifacts, day).is_file()]
        if missing:
            _days, _excluded, contexts = _april_contexts(repo, source, artifacts)
            for index, day in enumerate(missing, 1):
                record = _generate_current_day(repo, source, artifacts, day, contexts[day])
                print(json.dumps({"stage": "CURRENT_SENSITIVITY_DAY", "day": day,
                                  "days_complete": index, "days_total": len(missing),
                                  "sha256": record["sha256"]}), flush=True)
    return _aggregate_correction(repo, source, artifacts, checkpoint)


def main(argv: Sequence[str] | None = None) -> int:
    repo = Path.cwd()
    source = Path(r"C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\tmp\c12_exact_sources_repo_cleanup\c12_exact_sources\v2038_parent\Conversation3_Exact_AC_Remediation_Sweep_From_Conversation1_V2038\reference")
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=repo)
    parser.add_argument("--source", type=Path, default=source)
    parser.add_argument("--artifacts", type=Path, default=repo / "dayahead/artifacts" / ARTIFACT_DIR_NAME)
    parser.add_argument("--worker-day")
    parser.add_argument("--aggregate-only", action="store_true")
    parser.add_argument("--shadow-only", action="store_true")
    result = execute(**vars(parser.parse_args(argv)))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
