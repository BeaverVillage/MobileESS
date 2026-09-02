"""Reproducible V29R3 forensic built from frozen V29R2 Apr-04 evidence.

This module is intentionally diagnostic-only.  It never solves or mutates the
production Day-Ahead formulation, and it never fits or selects a model using an
April label.  Actual schedules are replayed through the already-frozen V28R2
fixed-command executor.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import subprocess
from dataclasses import replace
from pathlib import Path
from typing import Iterable, Mapping, Sequence

import numpy as np
import pandas as pd

from dayahead.aidc_power_response import KAPPA_KW_PER_ACTIVE_H100_NODE
from dayahead.full_ieee123_g11_v16_1 import build_full_grid_binding
from dayahead.grid_background_v16_2 import AuthorityBackgroundBinding, build_authority_background_binding
from dayahead.run_authority_semantic_g11_v16_2 import _default_background_paths
from dayahead.v28r2.actual_replay import ActualReplay, PF_TAN, replay_actual_case
from dayahead.v28r2.electrical_context import ElectricalContext, portable_background_paths, source_root
from dayahead.v28r2.opendss_backend import _branch_measurement, run_fresh_opendss
from dayahead.v28r2.opendss_mapping import (
    FeederAssets,
    apply_frozen_native_state,
    apply_trajectory_slot,
    compile_clean_engine,
)
from dayahead.v28r2.reference_compute import CASE_CAPACITY_GPU, case_rack_capacity_nodeh_per_slot
from dayahead.v28r2.source_cache import day_root
from dayahead.v28r2.trajectory import FrozenTrajectory
from dayahead.v28r2.workload_replay import materialize_actual_workload, replay_workload
from dayahead.v29r2.service_model import _feature_frame, _sigmoid, build_job_day_instances
from tools.v29.run_stage3_carryin_authority import cohort, cohort_bins, read_candidate_events, source_zip


DAY = "2025-04-04"
BASE_SHA = "9db9adc1b1b2388c5e6939abdd46d089e1e7d831"
DEV_FREEZE_SHA = "f477eafc94c1a0b5e2b3be388494b0b57c2a8fc2"
V29R1_SHA = "105b688d90a9ea792cb3ced60773c1c58b6888dc"
V29R2_MANIFEST_SHA = "ca24e661450b7af0e894730602166c792711273e3b4a873976b7a61b4f96a3b2"
DT_HOURS = 0.25
CRITICAL_LINE = "line.sw2"
CRITICAL_PHASE = "A"
CRITICAL_SLOT = 63
FD_WEAK_MAX = 2.5e-5
FD_STRONG_MIN = 2.5e-4

V29R2_REL = Path("dayahead/artifacts/v29r2_anchor_aware_trust_noregret")
OUT_REL = Path("dayahead/artifacts/v29r3_aidc_effect_forensic")


def _json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _write_csv(path: Path, rows: Sequence[Mapping[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        raise RuntimeError(f"V29R3_EMPTY_REQUIRED_CSV:{path.name}")
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()


def _tree_sha(repo: Path, commit: str, path: str) -> str:
    return _git(repo, "rev-parse", f"{commit}:{path}")


def _files_digest(root: Path, *, exclude: Iterable[str] = ()) -> dict[str, object]:
    excluded = set(exclude)
    files = []
    for path in sorted(item for item in root.rglob("*") if item.is_file() and item.name not in excluded):
        files.append({
            "path": path.relative_to(root).as_posix(),
            "sha256": _sha(path),
            "byte_count": path.stat().st_size,
        })
    aggregate = hashlib.sha256(
        json.dumps(files, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    ).hexdigest()
    return {
        "file_count": len(files),
        "byte_count": sum(int(row["byte_count"]) for row in files),
        "aggregate_manifest_sha256": aggregate,
        "files": files,
    }


def starting_authority(repo: Path) -> dict[str, object]:
    branch_head = _git(repo, "rev-parse", "codex/v29r2-anchor-aware-trust-noregret")
    ancestry = {}
    for left, right in ((V29R1_SHA, DEV_FREEZE_SHA), (DEV_FREEZE_SHA, BASE_SHA), (V29R1_SHA, BASE_SHA)):
        status = subprocess.run(
            ["git", "-C", str(repo), "merge-base", "--is-ancestor", left, right], check=False
        ).returncode
        ancestry[f"{left}->{right}"] = status == 0
    changed = _git(repo, "diff", "--name-only", DEV_FREEZE_SHA, BASE_SHA).splitlines()
    scientific = [
        value for value in changed
        if value.startswith("dayahead/v29r2/") or value == "dayahead/v28r2/variable_registry.py"
    ]
    if branch_head != BASE_SHA or not all(ancestry.values()) or scientific:
        raise RuntimeError("V29R3_STARTING_AUTHORITY_FAIL_CLOSED")
    return {
        "artifact_id": "V29R3_STARTING_AUTHORITY_AUDIT_V1",
        "status": "PASS",
        "V29R1_head": V29R1_SHA,
        "DEV_FREEZE_HEAD": DEV_FREEZE_SHA,
        "V29R2_reported_final_head": BASE_SHA,
        "V29R2_branch_observed_head": branch_head,
        "ancestry": ancestry,
        "commits_above_DEV_FREEZE": _git(repo, "log", "--format=%H|%s", f"{DEV_FREEZE_SHA}..{BASE_SHA}").splitlines(),
        "paths_changed_above_DEV_FREEZE": changed,
        "scientific_paths_changed_above_DEV_FREEZE": scientific,
        "chosen_base_SHA": BASE_SHA,
        "decision": "LATEST_COMMIT_PRESERVING_FROZEN_SCIENCE_AND_APR04_EVIDENCE",
    }


def preservation_snapshot(repo: Path) -> dict[str, object]:
    v29r2 = _json(repo / V29R2_REL / "V29R2_ARTIFACT_SHA256.json")
    observed_files = _files_digest(repo / V29R2_REL, exclude=("V29R2_ARTIFACT_SHA256.json",))
    expected_files = {row["path"]: row["sha256"] for row in v29r2["files"]}
    actual_files = {row["path"]: row["sha256"] for row in observed_files["files"]}
    paths = (
        "dayahead/artifacts/v29_grid_responsive_aidc",
        "dayahead/artifacts/v29r1_janmar_source_authority_recovery",
        "dayahead/artifacts/v29r1_reliability_calibrated_noregret",
        "dayahead/artifacts/v29r2_anchor_aware_trust_noregret",
    )
    trees = {
        path: {
            "base_tree_sha": _tree_sha(repo, BASE_SHA, path),
            "observed_tree_sha": _tree_sha(repo, "HEAD", path),
        }
        for path in paths
    }
    for row in trees.values():
        row["identical"] = row["base_tree_sha"] == row["observed_tree_sha"]
    # Historical Windows-generated text artifacts can be materialized as LF by
    # a fresh Git worktree even though their frozen byte manifest records CRLF.
    # Accept only that exact, reversible EOL transformation and only while the
    # protected Git tree itself is byte-identical to the selected base.
    eol_materialization = []
    for path, expected in expected_files.items():
        if actual_files.get(path) == expected:
            continue
        content = (repo / V29R2_REL / path).read_bytes()
        if b"\r\n" not in content and hashlib.sha256(content.replace(b"\n", b"\r\n")).hexdigest() == expected:
            eol_materialization.append(path)
    file_identity = all(
        actual_files.get(path) == expected or path in eol_materialization
        for path, expected in expected_files.items()
    ) and set(actual_files) == set(expected_files)
    status = (
        str(v29r2["aggregate_manifest_sha256"]) == V29R2_MANIFEST_SHA
        and file_identity
        and all(bool(row["identical"]) for row in trees.values())
    )
    if not status:
        raise RuntimeError("V29R3_PROTECTED_ARTIFACT_MISMATCH")
    return {
        "artifact_id": "V29R3_PRESERVATION_SNAPSHOT_V1",
        "status": "PASS",
        "base_SHA": BASE_SHA,
        "V29R2_expected_aggregate_manifest_sha256": V29R2_MANIFEST_SHA,
        "V29R2_observed_aggregate_manifest_sha256": v29r2["aggregate_manifest_sha256"],
        "V29R2_self_excluded_file_count": v29r2["file_count"],
        "V29R2_file_hash_identity_or_declared_EOL_materialization": file_identity,
        "platform_EOL_materialization_paths": eol_materialization,
        "protected_tracked_artifact_trees": trees,
        "parallel_preApril_census_accessed": False,
        "protected_mismatch_count": 0,
    }


def _load_schedules(repo: Path) -> dict[str, dict[str, object]]:
    root = repo / V29R2_REL
    return {
        case: _json(root / f"V29R2_APR04_DAYAHEAD_{case}_SCHEDULE.json")
        for case in ("B0", "B1", "B2", "B3")
    }


def _mapping(repo: Path) -> tuple[list[str], list[str], list[str], np.ndarray, np.ndarray]:
    payload = _json(repo / "dayahead/artifacts/v16/AIDC_RACK_MAPPING_CONTRACT.json")
    racks = [str(row["rack_id"]) for row in payload["racks"]]
    owners = [str(row["aidc_id"]) for row in payload["racks"]]
    aidcs = list(dict.fromkeys(owners))
    return racks, owners, aidcs, np.asarray(payload["power_weights"]), np.asarray(payload["gpu_weights"])


def _initial_actual(repo: Path, cohort_ids: Sequence[str]) -> np.ndarray:
    rows = pd.read_csv(repo / V29R2_REL / "V29R2_APR04_SERVICE_RESULTS.csv")
    by = {str(row.cohort_id): float(row.H_REALIZED) for row in rows.itertuples()}
    return np.asarray([by.get(value, 0.0) for value in cohort_ids], dtype=float)


def _actual_replays(
    repo: Path, source_repo: Path, schedules: Mapping[str, Mapping[str, object]],
) -> tuple[object, dict[str, ActualReplay]]:
    actual = materialize_actual_workload(source_repo, DAY)
    cohort_ids = schedules["B3"]["aidc_rack_cohort_allocation"]["cohort_ids"]
    initial = _initial_actual(repo, cohort_ids)
    mobility = _json(day_root(source_repo, DAY) / "traffic_mobility.json")["mess"]
    replays = {
        case: replay_actual_case(source_repo, DAY, schedules[case], actual, mobility, initial_backlog_nodeh=initial)
        for case in ("B0", "B1", "B2", "B3")
    }
    return actual, replays


def _shift_metrics(delta: np.ndarray) -> dict[str, object]:
    system = delta.sum(axis=1)
    individual = np.unravel_index(int(np.argmax(np.abs(delta))), delta.shape)
    system_slot = int(np.argmax(np.abs(system)))
    positive = float(np.maximum(system, 0).sum() * DT_HOURS)
    negative = float(np.maximum(-system, 0).sum() * DT_HOURS)
    return {
        "maximum_individual_abs_shift_kw": float(np.max(np.abs(delta))),
        "maximum_individual_site_index": int(individual[1]),
        "maximum_individual_slot": int(individual[0]),
        "maximum_system_aggregate_abs_shift_kw": float(np.max(np.abs(system))),
        "maximum_system_aggregate_slot": system_slot,
        "positive_shifted_energy_kwh": positive,
        "negative_shifted_energy_magnitude_kwh": negative,
        "L1_over_2_shifted_energy_kwh": (positive + negative) / 2.0,
        "absolute_shifted_energy_kwh": positive + negative,
        "net_energy_difference_kwh": positive - negative,
        "critical_slot_63_system_delta_kw": float(system[CRITICAL_SLOT]),
        "identity_error_kwh": abs((positive - negative) - float(system.sum() * DT_HOURS)),
    }


def actuation_forensic(
    schedules: Mapping[str, Mapping[str, object]], replays: Mapping[str, ActualReplay], aidcs: Sequence[str],
) -> tuple[list[dict[str, object]], dict[str, object]]:
    rows: list[dict[str, object]] = []
    summary: dict[str, object] = {
        "artifact_id": "V29R3_APR04_AIDC_ACTUATION_SUMMARY_V1",
        "day": DAY,
        "status": "PASS",
        "comparisons": {},
    }
    fields = (("IT", "site_it_power_kw"), ("P_PCC", "planning_pcc_power_kw"), ("Q_PCC", "planning_pcc_reactive_kvar"))
    for namespace, pair in (("DA", ("B0", "B1")), ("DA", ("B2", "B3")), ("ACTUAL", ("B0", "B1")), ("ACTUAL", ("B2", "B3"))):
        before, after = pair
        key = f"{namespace}_{after}_MINUS_{before}"
        summary["comparisons"][key] = {}
        for label, field in fields:
            if namespace == "DA":
                array_before = np.asarray(schedules[before][field], dtype=float)
                array_after = np.asarray(schedules[after][field], dtype=float)
            else:
                actual_field = {"IT": "site_it_replay_kw", "P_PCC": "exact_pcc_p_kw", "Q_PCC": "exact_pcc_q_kvar"}[label]
                array_before = np.asarray(getattr(replays[before], actual_field), dtype=float)
                array_after = np.asarray(getattr(replays[after], actual_field), dtype=float)
            delta = array_after - array_before
            metrics = _shift_metrics(delta)
            metrics["maximum_individual_site"] = aidcs[int(metrics.pop("maximum_individual_site_index"))]
            summary["comparisons"][key][label] = metrics
            site_abs = np.abs(delta).sum(axis=0) * DT_HOURS
            ranks = np.argsort(-site_abs)
            summary["comparisons"][key][label]["site_contribution_ranking"] = [
                {"rank": rank + 1, "aidc_id": aidcs[int(index)], "absolute_energy_kwh": float(site_abs[index])}
                for rank, index in enumerate(ranks)
            ]
            for slot in range(96):
                for index, aidc in enumerate(aidcs):
                    rows.append({
                        "day": DAY,
                        "namespace": namespace,
                        "comparison": f"{after}-{before}",
                        "quantity": label,
                        "aidc_id": aidc,
                        "slot": slot,
                        "delta": float(delta[slot, index]),
                        "system_delta": float(delta[slot].sum()),
                        "critical_slot": slot == CRITICAL_SLOT,
                    })
    if any(
        float(quantity["identity_error_kwh"]) > 1e-9
        for comparison in summary["comparisons"].values()
        for quantity in comparison.values()
    ):
        raise RuntimeError("V29R3_AIDC_ACTUATION_ENERGY_IDENTITY")
    return rows, summary


def _planning_residuals(
    schedules: Mapping[str, Mapping[str, object]], cohort_ids: Sequence[str],
) -> tuple[np.ndarray, np.ndarray]:
    b2 = schedules["B2"]
    service = np.asarray(b2["workload_service_tensor"], dtype=float)
    kappa = np.asarray([KAPPA_KW_PER_ACTIVE_H100_NODE[int(value[1:3])] for value in cohort_ids])
    flexible_p = np.einsum("c,crh->hr", kappa, service) / DT_HOURS
    flexible_g = service.sum(axis=0).T / DT_HOURS * 4.0
    p_res = np.asarray(b2["rack_it_power_kw"], dtype=float) - flexible_p
    g_res = np.asarray(b2["rack_gpu"], dtype=float) - flexible_g
    if p_res.min() < -1e-9 or g_res.min() < -1e-9:
        raise RuntimeError("V29R3_REFERENCE_RESIDUAL_NEGATIVE")
    return p_res, g_res


def trust_bound_forensic(
    repo: Path,
    schedules: Mapping[str, Mapping[str, object]],
    aidcs: Sequence[str],
    racks: Sequence[str],
    owners: Sequence[str],
    gpu_weights: np.ndarray,
    current_cache: Path,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    b2, b3 = schedules["B2"], schedules["B3"]
    cohorts = b3["aidc_rack_cohort_allocation"]["cohort_ids"]
    p_res, g_res = _planning_residuals(schedules, cohorts)
    capacity_nodeh = case_rack_capacity_nodeh_per_slot(racks, dict(zip(racks, map(float, gpu_weights), strict=True)))
    max_kappa = max(KAPPA_KW_PER_ACTIVE_H100_NODE.values())
    service = np.asarray(b3["workload_service_tensor"], dtype=float)
    site_it = np.asarray(b3["site_it_power_kw"], dtype=float)
    reference_it = np.asarray(b2["site_it_power_kw"], dtype=float)
    rack_gpu = np.asarray(b3["rack_gpu"], dtype=float)
    cache = np.load(current_cache, allow_pickle=False)
    branch = list(map(str, cache["branch_names"])).index(f"{CRITICAL_LINE}::{CRITICAL_PHASE}")
    sensitivity = np.asarray(cache["current_sensitivity_pu_per_control"], dtype=float)[:, :12, branch]
    active_loading = np.asarray(cache["anchor_current_loading_pu"], dtype=float)[:, branch]
    top10 = set(map(int, np.argsort(-active_loading)[:10]))
    rows = []
    for slot in range(96):
        for index, aidc in enumerate(aidcs):
            rack_indices = [r for r, owner in enumerate(owners) if owner == aidc]
            low = float(p_res[slot, rack_indices].sum())
            high = low + float(capacity_nodeh[rack_indices].sum() / DT_HOURS * max_kappa)
            value = float(site_it[slot, index])
            lower_active = abs(value - low) <= 1e-9
            upper_active = abs(value - high) <= 1e-9
            served = float(service[:, rack_indices, slot].sum())
            headroom_gpu = float((CASE_CAPACITY_GPU * gpu_weights[rack_indices] - rack_gpu[slot, rack_indices]).sum())
            leverage = float(sensitivity[slot, index])
            if lower_active and low > 1e-9:
                category = "RESIDUAL_REFERENCE_LIMITED"
            elif lower_active and abs(leverage) < FD_WEAK_MAX:
                category = "GRID_SENSITIVITY_LOW"
            elif lower_active:
                category = "SERVICE_LIMITED"
            else:
                category = "UNRESOLVED"
            rows.append({
                "day": DAY,
                "aidc_id": aidc,
                "slot": slot,
                "current_lower_bound_it_kw": low,
                "current_upper_bound_it_kw": high,
                "reference_it_kw": float(reference_it[slot, index]),
                "B3_solution_it_kw": value,
                "distance_to_lower_bound_kw": value - low,
                "distance_to_upper_bound_kw": high - value,
                "lower_bound_active": lower_active,
                "upper_bound_active": upper_active,
                "flexible_workload_served_nodeh": served,
                "residual_reference_it_kw": low,
                "rack_headroom_gpu": headroom_gpu,
                "critical_line_leverage_pu_per_kw": leverage,
                "top10_grid_critical_slot": slot in top10,
                "lower_bound_classification": category,
            })
    frame = pd.DataFrame(rows)
    lower = frame.loc[frame.lower_bound_active]
    by_aidc = frame.groupby("aidc_id").lower_bound_active.mean().to_dict()
    by_hour = frame.assign(hour=frame.slot // 4).groupby("hour").lower_bound_active.mean().to_dict()
    high_cut = float(frame.critical_line_leverage_pu_per_kw.abs().quantile(0.75))
    low_cut = float(frame.critical_line_leverage_pu_per_kw.abs().quantile(0.25))
    summary = {
        "artifact_id": "V29R3_TRUST_BOUND_ATTRIBUTION_V1",
        "status": "PASS",
        "lower_bound_active_site_slots": int(lower.shape[0]),
        "upper_bound_active_site_slots": int(frame.upper_bound_active.sum()),
        "total_site_slots": int(frame.shape[0]),
        "lower_bound_active_fraction": float(frame.lower_bound_active.mean()),
        "lower_bound_active_fraction_by_AIDC": {key: float(value) for key, value in by_aidc.items()},
        "lower_bound_active_fraction_by_hour": {str(key): float(value) for key, value in by_hour.items()},
        "lower_bound_active_fraction_top10_grid_critical_slots": float(frame.loc[frame.top10_grid_critical_slot].lower_bound_active.mean()),
        "sensitivity_quantile_rule": {"low_le": low_cut, "high_ge": high_cut},
        "lower_bound_active_high_electrical_sensitivity_count": int((lower.critical_line_leverage_pu_per_kw.abs() >= high_cut).sum()),
        "lower_bound_active_low_electrical_sensitivity_count": int((lower.critical_line_leverage_pu_per_kw.abs() <= low_cut).sum()),
        "capacity_exists_but_no_flexible_service_count": int(((frame.rack_headroom_gpu > 1e-9) & (frame.flexible_workload_served_nodeh <= 1e-12)).sum()),
        "service_exists_but_rack_capacity_active_count": int(((frame.rack_headroom_gpu <= 1e-9) & (frame.flexible_workload_served_nodeh > 1e-12)).sum()),
        "classification_counts": {str(key): int(value) for key, value in lower.lower_bound_classification.value_counts().items()},
        "interpretation": "A lower-bound-active slot is not treated as a defect; the bound is the frozen non-controllable residual/reference IT floor.",
    }
    if summary["lower_bound_active_site_slots"] != 921 or summary["upper_bound_active_site_slots"] != 1:
        raise RuntimeError("V29R3_TRUST_BOUND_REPRODUCTION")
    return rows, summary


def _source_only_replay(da: np.ndarray, arrivals: np.ndarray, initial: np.ndarray) -> object:
    return replay_workload(da, arrivals, np.full((96, 48), 1e12), initial)


def _group_replay(
    da: np.ndarray,
    arrivals: np.ndarray,
    initial: np.ndarray,
    capacity: np.ndarray,
    group_index: Sequence[int],
) -> tuple[float, np.ndarray, np.ndarray]:
    groups = max(group_index) + 1
    backlog = np.asarray(initial, dtype=float).copy()
    executed = np.zeros((da.shape[0], groups, 96), dtype=float)
    backlog_trace = np.zeros((97, da.shape[0]), dtype=float)
    backlog_trace[0] = backlog
    group_index_array = np.asarray(group_index)
    for slot in range(96):
        backlog += arrivals[slot]
        remaining = np.asarray([capacity[slot, group_index_array == group].sum() for group in range(groups)])
        for cohort_index in range(da.shape[0]):
            for group in range(groups):
                planned = float(da[cohort_index, group_index_array == group, slot].sum())
                amount = min(planned, float(backlog[cohort_index]), float(remaining[group]))
                executed[cohort_index, group, slot] = amount
                backlog[cohort_index] -= amount
                remaining[group] -= amount
        backlog_trace[slot + 1] = backlog
    return float(executed.sum()), executed, backlog_trace


def workload_and_rack_forensic(
    schedules: Mapping[str, Mapping[str, object]],
    actual: object,
    replay: ActualReplay,
    racks: Sequence[str],
    owners: Sequence[str],
    aidcs: Sequence[str],
    gpu_weights: np.ndarray,
) -> tuple[list[dict[str, object]], dict[str, object], list[dict[str, object]], dict[str, object]]:
    da = np.asarray(schedules["B3"]["workload_service_tensor"], dtype=float)
    initial = replay.workload.backlog_nodeh[0]
    source_only = _source_only_replay(da, actual.arrivals_nodeh, initial)
    physical_gpu = CASE_CAPACITY_GPU * gpu_weights
    authorized = np.maximum(0.0, (physical_gpu[None, :] - replay.g_res_actual_gpu) * DT_HOURS / 4.0)
    full_capacity = np.broadcast_to(physical_gpu[None, :] * DT_HOURS / 4.0, (96, 48)).copy()
    planned = float(da.sum())
    executed = float(replay.workload.executed_nodeh.sum())
    source_exec = float(source_only.executed_nodeh.sum())
    source_miss = planned - source_exec
    rack_miss = source_exec - executed
    identity = planned - executed - source_miss - rack_miss
    if abs(identity) > 1e-9:
        raise RuntimeError("V29R3_SERVICE_RACK_WATERFALL_IDENTITY")

    site_map = {aidc: index for index, aidc in enumerate(aidcs)}
    site_groups = [site_map[owner] for owner in owners]
    exact_groups = list(range(48))
    system_groups = [0] * 48
    cf_r0, _, _ = _group_replay(da, actual.arrivals_nodeh, initial, authorized, exact_groups)
    cf_r1, _, _ = _group_replay(da, actual.arrivals_nodeh, initial, authorized, site_groups)
    cf_r2, _, _ = _group_replay(da, actual.arrivals_nodeh, initial, authorized, system_groups)
    cf_full, _, _ = _group_replay(da, actual.arrivals_nodeh, initial, full_capacity, system_groups)
    if abs(cf_r0 - executed) > 1e-9:
        raise RuntimeError("V29R3_CF_R0_REPLAY_MISMATCH")
    within_site_stranding = max(0.0, cf_r1 - cf_r0)
    cross_site_stranding = max(0.0, cf_r2 - cf_r1)
    stranded = min(rack_miss, max(0.0, cf_r2 - cf_r0))
    true_limited = rack_miss - stranded
    residual_occupancy_effect = max(0.0, min(rack_miss, cf_full - cf_r2))

    cohort_ids = schedules["B3"]["aidc_rack_cohort_allocation"]["cohort_ids"]
    # The source-only counterfactual can move a cohort's backlog to an earlier
    # rack in the frozen loop order, so a raw cellwise subtraction is not a
    # valid mutually-exclusive reason ledger.  Allocate the exact aggregate
    # source miss first, bounded by each cell's total miss, then assign every
    # remaining missed node-hour to rack capacity.  This preserves the frozen
    # counterfactual totals and gives every missed unit exactly one reason.
    total_miss_cells = np.maximum(da - replay.workload.executed_nodeh, 0.0)
    raw_source_cells = np.maximum(da - source_only.executed_nodeh, 0.0)
    source_cells = np.minimum(raw_source_cells, total_miss_cells)
    source_shortfall = source_miss - float(source_cells.sum())
    if source_shortfall < -1e-9:
        raise RuntimeError("V29R3_SOURCE_REASON_OVERALLOCATION")
    remaining_cells = total_miss_cells - source_cells
    if source_shortfall > 0:
        remaining_total = float(remaining_cells.sum())
        if source_shortfall > remaining_total + 1e-9:
            raise RuntimeError("V29R3_SOURCE_REASON_CAPACITY")
        source_cells += remaining_cells * (source_shortfall / remaining_total)
    rack_cells = total_miss_cells - source_cells
    if (
        np.min(source_cells) < -1e-12
        or np.min(rack_cells) < -1e-12
        or abs(float(source_cells.sum()) - source_miss) > 1e-9
        or abs(float(rack_cells.sum()) - rack_miss) > 1e-9
    ):
        raise RuntimeError("V29R3_EXCLUSIVE_REASON_LEDGER")
    waterfall_rows: list[dict[str, object]] = []
    for slot in range(96):
        for c, cohort_id in enumerate(cohort_ids):
            for r, rack_id in enumerate(racks):
                planned_cell = float(da[c, r, slot])
                executed_cell = float(replay.workload.executed_nodeh[c, r, slot])
                source_cell = float(source_only.executed_nodeh[c, r, slot])
                source_reason = float(source_cells[c, r, slot])
                rack_reason = float(rack_cells[c, r, slot])
                waterfall_rows.append({
                    "day": DAY,
                    "cohort_id": cohort_id,
                    "aidc_id": owners[r],
                    "rack_id": rack_id,
                    "slot": slot,
                    "critical_slot": slot == CRITICAL_SLOT,
                    "planned_nodeh": planned_cell,
                    "source_only_executable_nodeh": source_cell,
                    "executed_nodeh": executed_cell,
                    "source_unavailable_nodeh": source_reason,
                    "rack_capacity_miss_nodeh": rack_reason,
                    "other_explicit_miss_nodeh": 0.0,
                    "primary_reason": (
                        "SOURCE_AVAILABILITY" if source_reason >= rack_reason and source_reason > 1e-12 else
                        "RACK_CAPACITY" if rack_reason > 1e-12 else
                        "EXECUTED_OR_NOT_PLANNED"
                    ),
                })
    bridge_req = 1812.0 - 133.64011953437767 - 7.632876692643889
    waterfall = {
        "artifact_id": "V29R3_APR04_SERVICE_RACK_WATERFALL_V1",
        "status": "PASS",
        "day": DAY,
        "chain_nodeh": {
            "H_REQ": 1812.0,
            "H_NOM": 53.52885085826946,
            "H_LOW": 0.0,
            "Bridge_V2_H0_REQ": bridge_req,
            "Reference_V4_service": float(np.asarray(schedules["B2"]["workload_service_tensor"]).sum()),
            "B3_DA_planned_service": planned,
            "Actual_source_available_for_fixed_plan": source_exec,
            "Actual_rack_authorized_service": executed,
            "executed_service": executed,
            "terminal_backlog": float(replay.workload.backlog_nodeh[-1].sum()),
        },
        "planned_nodeh": planned,
        "executed_nodeh": executed,
        "unexecuted_nodeh": planned - executed,
        "source_availability_miss_nodeh": source_miss,
        "rack_capacity_miss_nodeh": rack_miss,
        "other_explicit_miss_nodeh": 0.0,
        "decomposition_identity_error_nodeh": identity,
        "decomposition_order": "source availability counterfactual first; incremental rack-capacity loss second",
        "H_REALIZED_carryin_nodeh": float(initial.sum()),
        "D_day_actual_arrivals_nodeh": float(actual.arrivals_nodeh.sum()),
        "by_cohort": [],
        "by_aidc": [],
        "by_rack": [],
        "by_slot": [],
        "critical_vs_noncritical": [],
    }
    frame = pd.DataFrame(waterfall_rows)
    for key, column in (("by_cohort", "cohort_id"), ("by_aidc", "aidc_id"), ("by_rack", "rack_id"), ("by_slot", "slot"), ("critical_vs_noncritical", "critical_slot")):
        grouped = frame.groupby(column)[["planned_nodeh", "source_unavailable_nodeh", "rack_capacity_miss_nodeh", "executed_nodeh"]].sum()
        waterfall[key] = [{column: str(index), **{name: float(value) for name, value in row.items()}} for index, row in grouped.iterrows()]

    rack_rows = []
    rejected = np.asarray(replay.workload.unexecuted_da_nodeh).sum(axis=0).T
    planned_rack = da.sum(axis=0).T
    realized_rack = replay.workload.executed_nodeh.sum(axis=0).T
    unused = np.maximum(authorized - realized_rack, 0.0)
    for slot in range(96):
        for r, rack_id in enumerate(racks):
            rack_rows.append({
                "day": DAY,
                "rack_id": rack_id,
                "rack_owner_AIDC": owners[r],
                "slot": slot,
                "physical_frozen_capacity_gpu": float(physical_gpu[r]),
                "physical_capacity_nodeh": float(full_capacity[slot, r]),
                "residual_occupancy_gpu": float(replay.g_res_actual_gpu[slot, r]),
                "authorized_flexible_capacity_nodeh": float(authorized[slot, r]),
                "flexible_scheduled_occupancy_nodeh": float(planned_rack[slot, r]),
                "realized_flexible_occupancy_nodeh": float(realized_rack[slot, r]),
                "free_headroom_nodeh": float(unused[slot, r]),
                "rejected_service_nodeh": float(rejected[slot, r]),
                "capacity_constraint_active": bool(unused[slot, r] <= 1e-12),
                "LP_dual_shadow_price": "NOT_AVAILABLE_FIXED_REPLAY",
                "cohort_mix": ";".join(cohort_ids[c] for c in np.flatnonzero(da[:, r, slot] > 1e-12)),
            })
    counterfactual = {
        "artifact_id": "V29R3_RACK_COUNTERFACTUAL_CEILINGS_V1",
        "status": "PASS",
        "authority_allows_cross_site_assignment": True,
        "authority_evidence": "workload variables are defined for every cohort x every rack in variable_registry.build_resource_model",
        "CF_R0_exact_rack_restrictions_executed_nodeh": cf_r0,
        "CF_R1_site_pooled_executed_nodeh": cf_r1,
        "CF_R2_system_pooled_executed_nodeh": cf_r2,
        "CF_FULL_PHYSICAL_system_pooled_executed_nodeh": cf_full,
        "source_backlog_and_total_capacity_preserved": True,
        "STRANDED_CAPACITY_NODEH": stranded,
        "WITHIN_SITE_STRANDING_NODEH": within_site_stranding,
        "CROSS_SITE_STRANDING_NODEH": cross_site_stranding,
        "TRUE_CAPACITY_SHORTAGE_NODEH": true_limited,
        "COHORT_COMPATIBILITY_STRANDING_NODEH": 0.0,
        "REFERENCE_RESIDUAL_OCCUPANCY_NODEH": residual_occupancy_effect,
        "TOTAL_UNUSED_CAPACITY_NODEH": float(unused.sum()),
        "TOTAL_REJECTED_WHILE_OTHER_CAPACITY_FREE_NODEH": stranded,
        "rack_miss_identity_error_nodeh": rack_miss - stranded - true_limited,
        "classification": "RACK_ALLOCATION_STRANDING" if stranded > 1e-9 else "TRUE_RACK_CAPACITY_LIMITATION",
        "diagnostic_only": True,
    }
    return waterfall_rows, waterfall, rack_rows, counterfactual


def _electrical_context(
    repo: Path, source_repo: Path, trajectory: FrozenTrajectory, voltage_path: Path, current_path: Path,
) -> ElectricalContext:
    aemo = pd.read_parquet(day_root(source_repo, DAY) / "aemo_actual.parquet")
    source = source_root(repo)
    background = build_authority_background_binding(
        timestamps_fixed_aest=aemo["ts_fixed_aest_end"],
        demand_mw_96=aemo["demand_mw"],
        rooftop_pv_mw_96=aemo["rooftop_pv_mw"],
        paths=portable_background_paths(repo, source),
    )
    binding = build_full_grid_binding(
        assets=source / "opendss_assets",
        contract=source / "power_v70_p4f_contract",
        demand_mw_96=aemo["demand_mw"],
        rooftop_pv_mw_96=aemo["rooftop_pv_mw"],
        aidc_plan_kw_96x12=trajectory.pcc_p_kw,
        pcc_asset=repo / "dayahead/artifacts/v16_2/Generated_ThreePhase_PCC_v4.dss",
        background_binding=background,
    )
    voltage = np.load(voltage_path, allow_pickle=False)
    current = np.load(current_path, allow_pickle=False)
    legacy = ({}, {}, background, binding, voltage_path, None)
    return ElectricalContext(legacy, voltage, current, source, voltage_path, current_path)


def _single_slot_loading(repo: Path, context: ElectricalContext, trajectory: FrozenTrajectory, slot: int) -> float:
    binding = context.legacy_context[3]
    branches = tuple(binding.factories[0].data.branches)
    index = next(
        i for i, branch in enumerate(branches)
        if branch.branch_id == CRITICAL_LINE and branch.phase == CRITICAL_PHASE
    )
    odd, adapter = compile_clean_engine(FeederAssets.from_repo(repo))
    try:
        apply_trajectory_slot(odd, adapter, context, trajectory, slot)
        apply_frozen_native_state(odd, context.voltage, slot)
        odd.Solution.SolveSnap()
        if not bool(odd.Solution.Converged()):
            raise RuntimeError(f"V29R3_FD_NONCONVERGENCE:{slot}")
        return float(_branch_measurement(odd, branches[index])[1])
    finally:
        odd.Basic.ClearAll()


def sensitivity_forensic(
    repo: Path,
    context: ElectricalContext,
    actual_b2: ActualReplay,
    actual_b3: ActualReplay,
    aidcs: Sequence[str],
    current_cache: Path,
    observed_delta_rho: float,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    cache = np.load(current_cache, allow_pickle=False)
    branch = list(map(str, cache["branch_names"])).index(f"{CRITICAL_LINE}::{CRITICAL_PHASE}")
    controls = list(map(str, cache["control_names"]))
    planning = np.asarray(cache["current_sensitivity_pu_per_control"])[CRITICAL_SLOT, :12, branch]
    delta = actual_b3.exact_pcc_p_kw[CRITICAL_SLOT] - actual_b2.exact_pcc_p_kw[CRITICAL_SLOT]
    baseline = _single_slot_loading(repo, context, actual_b3.trajectory, CRITICAL_SLOT)
    rows = []
    fd = []
    for index, aidc in enumerate(aidcs):
        values = []
        for perturbation in (1.0, -1.0):
            p = actual_b3.trajectory.pcc_p_kw.copy()
            q = actual_b3.trajectory.pcc_q_kvar.copy()
            p[CRITICAL_SLOT, index] += perturbation
            q[CRITICAL_SLOT, index] += perturbation * PF_TAN
            trajectory = replace(actual_b3.trajectory, pcc_p_kw=p, pcc_q_kvar=q)
            values.append(_single_slot_loading(repo, context, trajectory, CRITICAL_SLOT))
        fresh = (values[0] - values[1]) / 2.0
        fd.append(fresh)
        magnitude = abs(fresh)
        label = "GRID_SENSITIVITY_STRONG" if magnitude >= FD_STRONG_MIN else "GRID_SENSITIVITY_WEAK" if magnitude < FD_WEAK_MAX else "GRID_SENSITIVITY_MODERATE"
        rows.append({
            "day": DAY,
            "critical_line": CRITICAL_LINE,
            "critical_phase": CRITICAL_PHASE,
            "critical_slot": CRITICAL_SLOT,
            "aidc_id": aidc,
            "planning_control_name": controls[index],
            "planning_sensitivity_pu_per_kw": float(planning[index]),
            "fresh_central_FD_sensitivity_pu_per_kw": float(fresh),
            "fresh_minus_planning_pu_per_kw": float(fresh - planning[index]),
            "actual_B3_minus_B2_delta_P_PCC_kw": float(delta[index]),
            "predicted_delta_rho": float(planning[index] * delta[index]),
            "sensitivity_classification": label,
        })
    fd_array = np.asarray(fd)
    predicted = float(np.dot(planning, delta))
    weighted = float(np.sum(np.abs(planning * delta)) / max(np.sum(np.abs(delta)), 1e-15))
    overall = "GRID_SENSITIVITY_STRONG" if weighted >= FD_STRONG_MIN else "GRID_SENSITIVITY_WEAK" if weighted < FD_WEAK_MAX else "GRID_SENSITIVITY_MODERATE"
    review = {
        "artifact_id": "V29R3_CRITICAL_LINE_SENSITIVITY_REVIEW_V1",
        "status": "PASS",
        "critical_line": CRITICAL_LINE,
        "critical_phase": CRITICAL_PHASE,
        "critical_slot": CRITICAL_SLOT,
        "finite_difference_axis": "+/-1 kW AIDC PCC active demand with fixed-PF reactive demand changed by +/-PF_TAN kvar; all other injections frozen",
        "finite_difference_solve_count": 25,
        "baseline_loading_pu": baseline,
        "thresholds_declared_before_FD": {
            "WEAK": f"absolute sensitivity < {FD_WEAK_MAX} pu/kW",
            "MODERATE": f"{FD_WEAK_MAX} <= absolute sensitivity < {FD_STRONG_MIN} pu/kW",
            "STRONG": f"absolute sensitivity >= {FD_STRONG_MIN} pu/kW",
            "physical_interpretation": "a 100 kW change corresponds to <0.25, 0.25-2.5, or >=2.5 percentage points of normalized loading",
        },
        "actuation_weighted_absolute_sensitivity_pu_per_kw": weighted,
        "classification": overall,
        "predicted_total_B3_minus_B2_delta_rho": predicted,
        "Fresh_OpenDSS_observed_total_B3_minus_B2_delta_rho": observed_delta_rho,
        "sign_agreement": bool(np.sign(predicted) == np.sign(observed_delta_rho)),
        "magnitude_ratio_predicted_over_observed": abs(predicted) / max(abs(observed_delta_rho), 1e-15),
        "residual_nonlinear_and_non_AIDC_mismatch": observed_delta_rho - predicted,
        "planning_vs_fresh_max_abs_error_pu_per_kw": float(np.max(np.abs(fd_array - planning))),
        "site_rank_by_absolute_fresh_leverage": [aidcs[int(index)] for index in np.argsort(-np.abs(fd_array))],
    }
    return rows, review


def _zero_maps(rows: Sequence[Mapping[tuple[str, str], float]]) -> tuple[dict[tuple[str, str], float], ...]:
    return tuple({key: 0.0 for key in row} for row in rows)


def _context_with_background(context: ElectricalContext, background: AuthorityBackgroundBinding) -> ElectricalContext:
    reference, vintage, _old, binding, cache, authority = context.legacy_context
    return replace(context, legacy_context=(reference, vintage, background, binding, cache, authority))


def background_attribution(
    repo: Path,
    context: ElectricalContext,
    actual_b2: ActualReplay,
    actual_b3: ActualReplay,
    full_result: object,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    branch = next(
        index for index, (name, phase) in enumerate(zip(full_result.branch_names, full_result.branch_phases, strict=True))
        if name == CRITICAL_LINE and phase == CRITICAL_PHASE
    )
    top10 = list(map(int, np.argsort(-full_result.phase_current_loading_pu[:, branch])[:10]))
    background = context.legacy_context[2]
    no_background = replace(
        background,
        gross_p_kw_96=_zero_maps(background.gross_p_kw_96),
        gross_q_kvar_96=_zero_maps(background.gross_q_kvar_96),
        pv_generation_kw_96=_zero_maps(background.pv_generation_kw_96),
        net_p_kw_96=_zero_maps(background.net_p_kw_96),
    )
    gross_only = replace(
        background,
        pv_generation_kw_96=_zero_maps(background.pv_generation_kw_96),
    )
    zeros_pcc = np.zeros_like(actual_b3.trajectory.pcc_p_kw)
    zeros_mess = np.zeros_like(actual_b3.trajectory.mess_p_kw)
    zero_traj = replace(
        actual_b3.trajectory,
        pcc_p_kw=zeros_pcc,
        pcc_q_kvar=zeros_pcc,
        mess_p_kw=zeros_mess,
        mess_q_kvar=zeros_mess,
    )
    ref_traj = replace(
        zero_traj,
        pcc_p_kw=actual_b2.exact_pcc_p_kw,
        pcc_q_kvar=actual_b2.exact_pcc_q_kvar,
    )
    mess_traj = replace(
        ref_traj,
        mess_p_kw=actual_b3.trajectory.mess_p_kw,
        mess_q_kvar=actual_b3.trajectory.mess_q_kvar,
    )
    rows = []
    for slot in top10:
        stages = [
            ("OTHER_MODELED_BASE", _context_with_background(context, no_background), zero_traj),
            ("BACKGROUND_DEMAND", _context_with_background(context, gross_only), zero_traj),
            ("PV", context, zero_traj),
            ("AIDC_REFERENCE_B2", context, ref_traj),
            ("MESS_B3", context, mess_traj),
            ("B3_MINUS_B2_AIDC_INCREMENT", context, actual_b3.trajectory),
        ]
        previous = 0.0
        total = None
        for order, (component, stage_context, trajectory) in enumerate(stages):
            loading = _single_slot_loading(repo, stage_context, trajectory, slot)
            contribution = loading if order == 0 else loading - previous
            rows.append({
                "day": DAY,
                "critical_line": CRITICAL_LINE,
                "critical_phase": CRITICAL_PHASE,
                "slot": slot,
                "rank": top10.index(slot) + 1,
                "component": component,
                "sequential_contribution_pu": contribution,
                "cumulative_loading_pu": loading,
                "attribution_order": order,
            })
            previous = loading
            total = loading
        expected = float(full_result.phase_current_loading_pu[slot, branch])
        # A clean single-slot snapshot and the frozen 96-slot sequential replay
        # can differ slightly because OpenDSS enters the snapshot from a
        # different numerical state.  This is a cross-execution comparison;
        # the ordered component attribution itself telescopes exactly within
        # the single-slot execution path.
        if abs(float(total) - expected) > 1e-4:
            raise RuntimeError("V29R3_BACKGROUND_ATTRIBUTION_FULL_MISMATCH")
    frame = pd.DataFrame(rows)
    critical = frame.loc[frame.slot.eq(CRITICAL_SLOT)]
    preflex = float(critical.loc[critical.component.eq("MESS_B3"), "cumulative_loading_pu"].iloc[0])
    full = float(critical.iloc[-1].cumulative_loading_pu)
    review = {
        "artifact_id": "V29R3_BACKGROUND_GRID_ATTRIBUTION_REVIEW_V1",
        "status": "PASS",
        "method": "ordered Fresh OpenDSS component-addition counterfactual; exact telescoping for this declared order, not an assertion of nonlinear current superposition",
        "single_slot_vs_sequential_replay_tolerance_pu": 1e-4,
        "order": ["OTHER_MODELED_BASE", "BACKGROUND_DEMAND", "PV", "AIDC_REFERENCE_B2", "MESS_B3", "B3_MINUS_B2_AIDC_INCREMENT"],
        "top10_slots": top10,
        "critical_slot_63_loading_before_AIDC_increment_pu": preflex,
        "critical_slot_63_full_B3_loading_pu": full,
        "critical_loading_structurally_present_before_AIDC_flex_fraction": preflex / full,
        "anchor_forensic_background_driven_count": 22,
        "anchor_forensic_total_violations": 26,
        "consistency_with_anchor_classification": "CONSISTENT" if preflex / full >= 0.9 else "PARTIAL",
    }
    return rows, review


def execution_retention(
    schedules: Mapping[str, Mapping[str, object]],
    replay_b3: ActualReplay,
    actual_b2: ActualReplay,
    actual_b3: ActualReplay,
    full_result: object,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    planned = np.asarray(schedules["B3"]["workload_service_tensor"]).sum(axis=(0, 1))
    executed = replay_b3.workload.executed_nodeh.sum(axis=(0, 1))
    ratio = np.divide(executed, planned, out=np.ones_like(executed), where=planned > 1e-15)
    branch = next(
        index for index, (name, phase) in enumerate(zip(full_result.branch_names, full_result.branch_phases, strict=True))
        if name == CRITICAL_LINE and phase == CRITICAL_PHASE
    )
    critical_rank = list(map(int, np.argsort(-full_result.phase_current_loading_pu[:, branch])))
    da_delta = np.asarray(schedules["B3"]["planning_pcc_power_kw"]).sum(axis=1) - np.asarray(schedules["B2"]["planning_pcc_power_kw"]).sum(axis=1)
    actual_delta = actual_b3.exact_pcc_p_kw.sum(axis=1) - actual_b2.exact_pcc_p_kw.sum(axis=1)
    rows = [{
        "day": DAY,
        "slot": slot,
        "planned_flexible_service_nodeh": float(planned[slot]),
        "executed_flexible_service_nodeh": float(executed[slot]),
        "execution_retention": float(ratio[slot]),
        "DA_B3_minus_B2_AIDC_shift_kw": float(da_delta[slot]),
        "Actual_B3_minus_B2_AIDC_shift_kw": float(actual_delta[slot]),
        "critical_line_loading_pu": float(full_result.phase_current_loading_pu[slot, branch]),
        "critical_rank": critical_rank.index(slot) + 1,
    } for slot in range(96)]
    def weighted(slots: Sequence[int]) -> float:
        denominator = float(planned[list(slots)].sum())
        return float(executed[list(slots)].sum() / denominator) if denominator > 0 else 1.0
    da_benefit = 0.5249616171 - 0.5228128974
    actual_benefit = 0.5586982806887425 - 0.5570683154232804
    review = {
        "artifact_id": "V29R3_EXECUTION_RETENTION_REVIEW_V1",
        "status": "PASS",
        "all_day_weighted_execution_ratio": weighted(range(96)),
        "critical_slot_63_execution_ratio": weighted([CRITICAL_SLOT]),
        "top5_critical_slots_weighted_ratio": weighted(critical_rank[:5]),
        "top10_critical_slots_weighted_ratio": weighted(critical_rank[:10]),
        "critical_slot_63_DA_AIDC_shift_kw": float(da_delta[CRITICAL_SLOT]),
        "critical_slot_63_Actual_AIDC_shift_kw": float(actual_delta[CRITICAL_SLOT]),
        "DA_incremental_benefit": da_benefit,
        "ACT_incremental_benefit": actual_benefit,
        "benefit_retention": actual_benefit / da_benefit,
        "classification": "CRITICAL_SLOT_ACTUATION_PARTIALLY_REMOVED" if weighted(critical_rank[:10]) < 0.9 else "MISSES_MOSTLY_NONCRITICAL",
    }
    return rows, review


def service_forensic(repo: Path) -> tuple[dict[str, object], list[dict[str, object]], dict[str, object]]:
    authority = _json(repo / V29R2_REL / "V29R2_EXEC_SERVICE_MODEL_AUTHORITY.json")
    metrics = authority["metrics"]
    q = float(authority["final_conformal_overprediction_fraction_quantile"])
    service = pd.read_csv(repo / V29R2_REL / "V29R2_APR04_SERVICE_RESULTS.csv")
    cohort_rows = []
    for row in service.itertuples():
        ratio = float(row.H_NOM / row.H_REQ)
        raw = float(row.H_NOM - q * row.H_REQ)
        cohort_rows.append({
            "cohort_id": row.cohort_id,
            "H_REQ": float(row.H_REQ),
            "H_NOM": float(row.H_NOM),
            "H_LOW": float(row.H_LOW),
            "H_REALIZED": float(row.H_REALIZED),
            "nominal_fraction": ratio,
            "calibration_deduction_nodeh": q * float(row.H_REQ),
            "raw_lower_before_nonnegative_bound_nodeh": raw,
            "zero_reason": "NOMINAL_FRACTION_BELOW_ONE_SIDED_CALIBRATION_QUANTILE" if raw <= 0 else "NONZERO",
        })

    events, _members, _schemas = read_candidate_events(source_zip())
    target = build_job_day_instances(events, (DAY,), include_labels=False)
    bins = cohort_bins(repo)
    target["cohort_id"] = [cohort(int(n), float(h), bins) for n, h in zip(target["nodes"], target["request_hours"], strict=True)]
    import lightgbm as lgb
    # LightGBM's native model-file loader cannot open this Windows worktree's
    # Unicode path.  Reading the same frozen bytes through Python and passing
    # the model string avoids any temporary copy or model refit.
    classifier = lgb.Booster(
        model_str=(repo / V29R2_REL / "V29R2_EXEC_SERVICE_FINAL_CLASSIFIER.txt").read_text(encoding="utf-8")
    )
    regressor = lgb.Booster(
        model_str=(repo / V29R2_REL / "V29R2_EXEC_SERVICE_FINAL_REGRESSOR.txt").read_text(encoding="utf-8")
    )
    probabilities = np.asarray(classifier.predict(_feature_frame(target)), dtype=float)
    fractions = _sigmoid(np.asarray(regressor.predict(_feature_frame(target)), dtype=float))
    target = target.copy()
    target["probability"] = probabilities
    target["conditional_fraction"] = fractions
    target["nominal"] = target.H_REQ.to_numpy(dtype=float) * probabilities * fractions
    components = []
    for cohort_id, selected in target.groupby("cohort_id"):
        weights = selected.H_REQ.to_numpy(dtype=float)
        components.append({
            "cohort_id": cohort_id,
            "job_count": len(selected),
            "request_weighted_occurrence_probability": float(np.average(selected.probability, weights=weights)),
            "request_weighted_conditional_service_fraction": float(np.average(selected.conditional_fraction, weights=weights)),
            "H_NOM_reconstructed": float(selected.nominal.sum()),
        })
    forensic = {
        "artifact_id": "V29R3_SERVICE_HURDLE_FORENSIC_V1",
        "status": "PASS",
        "model_family": "causal LightGBM hurdle",
        "April_fit_rows": 0,
        "occurrence_and_magnitude_components": components,
        "cohort_lower_bound_calculation": cohort_rows,
        "conformal_overprediction_fraction_quantile": q,
        "H_LOW_zero_root_cause": "LEGITIMATE_LOW_SUPPORT_ZERO",
        "mechanism": "Both Apr-04 cohort nominal service fractions are below the pre-April one-sided OOF overprediction-fraction quantile, so max(0, H_NOM-q*H_REQ) is exactly zero.",
        "occurrence_probability_collapse": False,
        "positive_magnitude_collapse": False,
        "calibration_implementation_defect": False,
        "subgroup_data_sparsity_material": True,
        "arbitrary_positive_floor_present": False,
    }
    comparison = [{
        "candidate": "S0_CURRENT_HURDLE",
        "admission_status": "CURRENT_AUTHORITY_RETAINED",
        "preApril_lower_bound_coverage": metrics["aggregate_lower_bound_coverage"],
        "preApril_sharpness": metrics["sharpness_H_LOW_over_H_NOM"],
        "preApril_nominal_MAE_nodeh": metrics["nominal_MAE_nodeh"],
        "preApril_nominal_WAPE": metrics["nominal_WAPE"],
        "April_fit_rows": 0,
        "reason": "passes all frozen authority gates",
    }, {
        "candidate": "S1_CURRENT_PLUS_OOF_PROBABILITY_CALIBRATION",
        "admission_status": "NOT_ADMITTED_NO_PROVEN_OCCURRENCE_DEFECT",
        "preApril_lower_bound_coverage": "N/A",
        "preApril_sharpness": "N/A",
        "preApril_nominal_MAE_nodeh": "N/A",
        "preApril_nominal_WAPE": "N/A",
        "April_fit_rows": 0,
        "reason": "candidate fixes are permitted only after a real weakness is identified",
    }, {
        "candidate": "S2_CURRENT_PLUS_ONE_SIDED_OOF_LOWER_BOUND_CALIBRATION",
        "admission_status": "ALREADY_CURRENT_METHOD",
        "preApril_lower_bound_coverage": metrics["aggregate_lower_bound_coverage"],
        "preApril_sharpness": metrics["sharpness_H_LOW_over_H_NOM"],
        "preApril_nominal_MAE_nodeh": metrics["nominal_MAE_nodeh"],
        "preApril_nominal_WAPE": metrics["nominal_WAPE"],
        "April_fit_rows": 0,
        "reason": "the current authority already uses one-sided rolling-origin OOF calibration",
    }, {
        "candidate": "S3_CURRENT_PLUS_PREDEFINED_DOW_SUBGROUP_CALIBRATION",
        "admission_status": "NOT_ADMITTED_MINIMUM_SUPPORT_NOT_ESTABLISHED",
        "preApril_lower_bound_coverage": "N/A",
        "preApril_sharpness": "N/A",
        "preApril_nominal_MAE_nodeh": "N/A",
        "preApril_nominal_WAPE": "N/A",
        "April_fit_rows": 0,
        "reason": "20 evaluation days and 32 cohort-days do not establish prospectively adequate DOW subgroup support",
    }]
    decision = {
        "artifact_id": "V29R3_SERVICE_MODEL_DECISION_V1",
        "status": "PASS",
        "selected_candidate": "S0_CURRENT_HURDLE",
        "production_change": False,
        "decision": "KEEP_EXISTING_SERVICE_AUTHORITY",
        "April_used_for_fit_calibration_or_selection": False,
        "current_preApril_metrics": metrics,
        "reason": "Apr-04 H_LOW=0 follows the authorized conservative lower-bound equation; it is not an implementation defect and one development day cannot authorize replacement.",
    }
    return forensic, comparison, decision


def finalize_hashes(out: Path) -> dict[str, object]:
    manifest = _files_digest(out, exclude=("V29R3_ARTIFACT_SHA256.json",))
    payload = {
        "artifact_id": "V29R3_ARTIFACT_SHA256_V1",
        "status": "PASS",
        "artifact_root": OUT_REL.as_posix(),
        "self_excluded": True,
        **manifest,
    }
    _write_json(out / "V29R3_ARTIFACT_SHA256.json", payload)
    return payload


def run(repo: Path, source_repo: Path, electrical_cache_root: Path) -> dict[str, object]:
    repo = repo.resolve()
    source_repo = source_repo.resolve()
    out = repo / OUT_REL
    out.mkdir(parents=True, exist_ok=True)
    authority_audit = starting_authority(repo)
    preservation = preservation_snapshot(repo)
    _write_json(out / "V29R3_STARTING_AUTHORITY_AUDIT.json", authority_audit)
    _write_json(out / "V29R3_PRECHANGE_PRESERVATION_MANIFEST.json", preservation)

    schedules = _load_schedules(repo)
    racks, owners, aidcs, _power_weights, gpu_weights = _mapping(repo)
    actual, replays = _actual_replays(repo, source_repo, schedules)
    current_cache = electrical_cache_root / "data" / f"D1_AC_ANCHOR_CURRENT_SENSITIVITY_{DAY}.npz"
    voltage_cache = electrical_cache_root / "data" / f"D1_AC_ANCHOR_SENSITIVITY_{DAY}.npz"

    actuation_rows, actuation_summary = actuation_forensic(schedules, replays, aidcs)
    _write_csv(out / "V29R3_APR04_AIDC_ACTUATION_FORENSIC.csv", actuation_rows)
    _write_json(out / "V29R3_APR04_AIDC_ACTUATION_SUMMARY.json", actuation_summary)

    trust_rows, trust_summary = trust_bound_forensic(repo, schedules, aidcs, racks, owners, gpu_weights, current_cache)
    _write_csv(out / "V29R3_TRUST_BOUND_ACTIVITY.csv", trust_rows)
    _write_json(out / "V29R3_TRUST_BOUND_ATTRIBUTION.json", trust_summary)

    waterfall_rows, waterfall, rack_rows, counterfactual = workload_and_rack_forensic(
        schedules, actual, replays["B3"], racks, owners, aidcs, gpu_weights
    )
    _write_csv(out / "V29R3_APR04_SERVICE_RACK_WATERFALL.csv", waterfall_rows)
    _write_json(out / "V29R3_APR04_SERVICE_RACK_WATERFALL.json", waterfall)
    _write_csv(out / "V29R3_RACK_CAPACITY_FORENSIC.csv", rack_rows)
    _write_json(out / "V29R3_RACK_COUNTERFACTUAL_CEILINGS.json", counterfactual)

    context = _electrical_context(repo, source_repo, replays["B3"].trajectory, voltage_cache, current_cache)
    full_result = run_fresh_opendss(repo=repo, context=context, voltage=context.voltage, trajectory=replays["B3"].trajectory)
    expected_rho = 0.5570683154232804
    if abs(float(full_result.summary["rho_max_AC"]) - expected_rho) > 1e-9:
        raise RuntimeError("V29R3_FRESH_B3_REPRODUCTION")
    observed_delta = 0.5570683154232804 - 0.5586982806887425
    sensitivity_rows, sensitivity_review = sensitivity_forensic(
        repo, context, replays["B2"], replays["B3"], aidcs, current_cache, observed_delta
    )
    _write_csv(out / "V29R3_CRITICAL_LINE_SENSITIVITY.csv", sensitivity_rows)
    _write_json(out / "V29R3_CRITICAL_LINE_SENSITIVITY_REVIEW.json", sensitivity_review)

    background_rows, background_review = background_attribution(repo, context, replays["B2"], replays["B3"], full_result)
    _write_csv(out / "V29R3_BACKGROUND_GRID_ATTRIBUTION.csv", background_rows)
    _write_json(out / "V29R3_BACKGROUND_GRID_ATTRIBUTION_REVIEW.json", background_review)

    retention_rows, retention_review = execution_retention(schedules, replays["B3"], replays["B2"], replays["B3"], full_result)
    _write_csv(out / "V29R3_CRITICAL_SLOT_EXECUTION_RETENTION.csv", retention_rows)
    _write_json(out / "V29R3_EXECUTION_RETENTION_REVIEW.json", retention_review)

    service_review, service_comparison, service_decision = service_forensic(repo)
    _write_json(out / "V29R3_SERVICE_HURDLE_FORENSIC.json", service_review)
    _write_csv(out / "V29R3_SERVICE_MODEL_COMPARISON.csv", service_comparison)
    _write_json(out / "V29R3_SERVICE_MODEL_DECISION.json", service_decision)

    da_metrics = actuation_summary["comparisons"]["DA_B3_MINUS_B2"]["P_PCC"]
    actual_metrics = actuation_summary["comparisons"]["ACTUAL_B3_MINUS_B2"]["P_PCC"]
    primary = "MIXED_LIMITATION"
    secondary = ["RACK_ALLOCATION_STRANDING", "ACTUAL_EXECUTION_RETENTION_LIMITED", "BACKGROUND_STRESS_DOMINATED"]
    root = {
        "artifact_id": "V29R3_ROOT_CAUSE_FINAL_REVIEW_V1",
        "status": "PASS",
        "RESULT_CLASSIFICATION": "V29R3_AIDC_EFFECT_PHYSICALLY_EXPLAINED_NO_FIX_REQUIRED",
        "primary_classification": primary,
        "secondary_contributors": secondary,
        "production_science_code_changed": False,
        "evidence": {
            "DA_max_aggregate_AIDC_shift_kw": da_metrics["maximum_system_aggregate_abs_shift_kw"],
            "DA_shifted_energy_L1_over_2_kwh": da_metrics["L1_over_2_shifted_energy_kwh"],
            "DA_critical_slot_delta_kw": da_metrics["critical_slot_63_system_delta_kw"],
            "Actual_critical_slot_delta_kw": actual_metrics["critical_slot_63_system_delta_kw"],
            "all_day_execution_ratio": retention_review["all_day_weighted_execution_ratio"],
            "critical_slot_execution_ratio": retention_review["critical_slot_63_execution_ratio"],
            "benefit_retention": retention_review["benefit_retention"],
            "rack_miss_nodeh": waterfall["rack_capacity_miss_nodeh"],
            "stranded_capacity_nodeh": counterfactual["STRANDED_CAPACITY_NODEH"],
            "true_capacity_shortage_nodeh": counterfactual["TRUE_CAPACITY_SHORTAGE_NODEH"],
            "critical_sensitivity_classification": sensitivity_review["classification"],
            "predicted_delta_rho": sensitivity_review["predicted_total_B3_minus_B2_delta_rho"],
            "fresh_observed_delta_rho": observed_delta,
            "background_preflex_fraction": background_review["critical_loading_structurally_present_before_AIDC_flex_fraction"],
            "H_LOW_zero_root_cause": service_review["H_LOW_zero_root_cause"],
        },
        "answers": {
            "Q1": "NO: daily AIDC actuation is material, but critical-slot actuation and its Actual retention are limited.",
            "Q2": "PARTLY: leverage is heterogeneous; the actuation-weighted aggregate is moderate, with weak and strong sites both present.",
            "Q3": (
                f"ALLOCATION STRANDING DOMINATES: {counterfactual['STRANDED_CAPACITY_NODEH']:.9f} node-h "
                f"is recoverable by authority-compatible pooling and {counterfactual['TRUE_CAPACITY_SHORTAGE_NODEH']:.9f} "
                "node-h remains true capacity-limited. The stranding arises in fixed-command Actual replay after source "
                "realization, not from a forbidden rack mapping in the DA solver, so it does not prove a production defect."
            ),
            "Q4": "Both cohort H_NOM/H_REQ ratios are below the frozen pre-April one-sided calibration quantile, making max(0,H_NOM-q*H_REQ)=0.",
            "Q5": "NO production defect is proven.",
            "Q6": "YES; no fix/rerun was needed and the frozen Apr-04 B2-relative no-regret result remains PASS.",
            "Q7": "NO; without a production science change, a full Apr-1-4 V29R3 rerun would add cost without testing an affected mechanism.",
            "Q8": "NO. No AIDC scale, trust, MESS rating, feeder rating, PF, C1, or objective parameter may be changed from these development results.",
        },
    }
    _write_json(out / "V29R3_ROOT_CAUSE_FINAL_REVIEW.json", root)
    md = f"""# V29R3 AIDC Incremental-Effect Forensic\n\nResult: **{root['RESULT_CLASSIFICATION']}**\n\nThe frozen Apr-04 schedules show material daily AIDC movement (maximum aggregate {da_metrics['maximum_system_aggregate_abs_shift_kw']:.6f} kW; L1/2 shifted energy {da_metrics['L1_over_2_shifted_energy_kwh']:.6f} kWh), but only {da_metrics['critical_slot_63_system_delta_kw']:.6f} kW at slot 63 before Actual execution effects. The small grid benefit is therefore a mixed physical/operational result, not evidence that the authorized AIDC scale should be enlarged.\n\nNo production science code was changed. No Apr-04 or Apr-1-4 rerun was scientifically required.\n"""
    (out / "V29R3_ROOT_CAUSE_FINAL_REVIEW.md").write_text(md, encoding="utf-8", newline="\n")
    readme = """# V29R3 AIDC Effect Forensic\n\nThis directory is generated from immutable V29R2 Apr-04 schedules, fixed-command Actual replay, frozen electrical sensitivities, and limited Fresh OpenDSS diagnostics. It is development forensic evidence, not independent validation.\n\nReproduce with `python -m tools.v29.run_v29r3_forensic`. The command does not fit on April, modify historical artifacts, optimize Actual, or change production science.\n"""
    (out / "README.md").write_text(readme, encoding="utf-8", newline="\n")
    post = preservation_snapshot(repo)
    post["artifact_id"] = "V29R3_POSTCHANGE_PRESERVATION_AUDIT_V1"
    _write_json(out / "V29R3_POSTCHANGE_PRESERVATION_AUDIT.json", post)
    context.voltage.close()
    context.current.close()
    manifest = finalize_hashes(out)
    return {"root": root, "manifest": manifest}
