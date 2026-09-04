"""Vectorized Apr-01--20 calibration and Apr-21--30 frozen validation."""

from __future__ import annotations

import csv
import json
import os
from pathlib import Path
from typing import Mapping, Sequence

import numpy as np

from dayahead.v34.correction import CorrectionCandidates, StaticCorrection

from .contracts import CALIBRATION_DAYS, VALIDATION_DAYS
from .storage import atomic_json, canonical_sha256, sha256_file


CALIBRATION_CASES = ("B1", "B3")


def load_residual_arrays(
    cache_root: Path,
    phase: str,
    days: Sequence[str],
    cases: Sequence[str] = CALIBRATION_CASES,
) -> dict[str, object]:
    planning_rows, fresh_rows, schedules, labels = [], [], [], []
    node_names: tuple[str, ...] | None = None
    node_phases: tuple[str, ...] | None = None
    for day in days:
        for case in cases:
            root = cache_root / phase / day / case
            result = json.loads((root / "CASE_RESULT.json").read_text(encoding="utf-8"))
            with np.load(root / "PLANNING_GRID.npz", allow_pickle=False) as planning, \
                    np.load(root / "fresh/OPENDSS_PHASE_ARRAYS.npz", allow_pickle=False) as fresh:
                planning_v = np.asarray(planning["voltage_pu"], dtype=float)
                fresh_v = np.asarray(fresh["voltage_pu"], dtype=float)
                names = tuple(map(str, fresh["node_names"]))
                phases = tuple(map(str, fresh["node_phases"]))
            if planning_v.shape != fresh_v.shape or planning_v.shape[0] != 96:
                raise RuntimeError("V35_RESIDUAL_PLANNING_FRESH_AXIS")
            if node_names is None:
                node_names, node_phases = names, phases
            if names != node_names or phases != node_phases:
                raise RuntimeError("V35_RESIDUAL_NODE_PHASE_AXIS_DRIFT")
            schedule = str(result["combined_schedule_sha256"])
            if result["fresh"]["schedule_sha256"] != schedule:
                raise RuntimeError("V35_RESIDUAL_SCHEDULE_SHA_IDENTITY")
            planning_rows.append(planning_v); fresh_rows.append(fresh_v)
            schedules.append(schedule); labels.append((day, case))
    if node_names is None or node_phases is None:
        raise RuntimeError("V35_EMPTY_RESIDUAL_COHORT")
    planning_array = np.asarray(planning_rows)
    fresh_array = np.asarray(fresh_rows)
    if not np.isfinite(planning_array).all() or not np.isfinite(fresh_array).all():
        raise RuntimeError("V35_RESIDUAL_NONFINITE")
    return {
        "planning": planning_array,
        "fresh": fresh_array,
        "signed": fresh_array - planning_array,
        "node_names": node_names,
        "node_phases": node_phases,
        "schedules": tuple(schedules),
        "labels": tuple(labels),
    }


def calibrate_vectorized(residuals: Mapping[str, object]) -> CorrectionCandidates:
    signed = np.asarray(residuals["signed"], dtype=float)
    names = tuple(map(str, residuals["node_names"]))
    phases = tuple(map(str, residuals["node_phases"]))
    up = np.maximum(signed, 0.0)
    low = np.maximum(-signed, 0.0)
    global_up = float(up.max()); global_low = float(low.max())
    m1 = StaticCorrection("M1", {"GLOBAL": global_up}, {"GLOBAL": global_low}, 0)
    m2_up, m2_low = {}, {}
    m3_up, m3_low = {}, {}
    for index, (node, phase) in enumerate(zip(names, phases, strict=True)):
        key = f"{node}|{phase}"
        m2_up[key] = float(up[:, :, index].max())
        m2_low[key] = float(low[:, :, index].max())
        for block in range(4):
            block_key = f"{node}|{phase}|{block}"
            window = slice(24 * block, 24 * (block + 1))
            m3_up[block_key] = float(up[:, window, index].max())
            m3_low[block_key] = float(low[:, window, index].max())
    return CorrectionCandidates(
        m1,
        StaticCorrection("M2", m2_up, m2_low, 0),
        StaticCorrection("M3", m3_up, m3_low, 0),
    )


def residual_summary(residuals: Mapping[str, object]) -> dict[str, object]:
    signed = np.asarray(residuals["signed"], dtype=float)
    up = np.maximum(signed, 0.0).ravel()
    low = np.maximum(-signed, 0.0).ravel()
    absolute = np.abs(signed).ravel()
    return {
        "artifact_id": "V35_APR01_20_RESIDUAL_SUMMARY_V1",
        "calibration_days": list(CALIBRATION_DAYS),
        "cases": list(CALIBRATION_CASES),
        "matched_cell_count": int(signed.size),
        "E_UP": {"P95": float(np.quantile(up, .95)), "P99": float(np.quantile(up, .99)), "max": float(up.max())},
        "E_LOW": {"P95": float(np.quantile(low, .95)), "P99": float(np.quantile(low, .99)), "max": float(low.max())},
        "E_ABS": {"mean": float(absolute.mean()), "P95": float(np.quantile(absolute, .95)), "P99": float(np.quantile(absolute, .99)), "max": float(absolute.max())},
        "schedule_SHA_identity": True,
        "Actual_residual_reads": 0,
    }


def write_residual_csv(path: Path, residuals: Mapping[str, object]) -> str:
    planning = np.asarray(residuals["planning"], dtype=float)
    fresh = np.asarray(residuals["fresh"], dtype=float)
    names = tuple(map(str, residuals["node_names"]))
    phases = tuple(map(str, residuals["node_phases"]))
    labels = tuple(residuals["labels"])
    schedules = tuple(map(str, residuals["schedules"]))
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    fields = ("day", "case", "slot", "node", "phase", "schedule_SHA", "V_PLAN", "V_FRESH", "E_SIGNED", "E_UP", "E_LOW", "E_ABS")
    count = 0
    with temporary.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for sample, ((day, case), schedule) in enumerate(zip(labels, schedules, strict=True)):
            for slot in range(96):
                for index, (node, phase) in enumerate(zip(names, phases, strict=True)):
                    plan = float(planning[sample, slot, index]); actual = float(fresh[sample, slot, index])
                    signed = actual - plan
                    writer.writerow({
                        "day": day, "case": case, "slot": slot, "node": node, "phase": phase,
                        "schedule_SHA": schedule, "V_PLAN": plan, "V_FRESH": actual,
                        "E_SIGNED": signed, "E_UP": max(0.0, signed),
                        "E_LOW": max(0.0, -signed), "E_ABS": abs(signed),
                    })
                    count += 1
        stream.flush(); os.fsync(stream.fileno())
    os.replace(temporary, path)
    expected = len(labels) * 96 * len(names)
    with path.open(encoding="utf-8", newline="") as stream:
        reloaded_count = sum(1 for _ in stream) - 1
    if count != expected or reloaded_count != expected:
        raise RuntimeError("V35_RESIDUAL_CSV_RELOAD_ROW_COUNT")
    return sha256_file(path)


def _correction_arrays(candidate: StaticCorrection, names: Sequence[str], phases: Sequence[str]) -> tuple[np.ndarray, np.ndarray]:
    up = np.zeros((96, len(names))); low = np.zeros_like(up)
    for slot in range(96):
        for index, (node, phase) in enumerate(zip(names, phases, strict=True)):
            up[slot, index], low[slot, index] = candidate.value_for(node, phase, slot)
    return up, low


def prospective_coverage(candidate: StaticCorrection, residuals: Mapping[str, object]) -> dict[str, object]:
    signed = np.asarray(residuals["signed"], dtype=float)
    up_residual = np.maximum(signed, 0.0); low_residual = np.maximum(-signed, 0.0)
    up, low = _correction_arrays(candidate, residuals["node_names"], residuals["node_phases"])

    def one(indices: Sequence[int]) -> dict[str, object]:
        upper = np.maximum(0.0, up_residual[np.asarray(indices)] - up[None, :, :])
        lower = np.maximum(0.0, low_residual[np.asarray(indices)] - low[None, :, :])
        return {
            "upper_exceedance_count": int(np.count_nonzero(upper > 0.0)),
            "lower_exceedance_count": int(np.count_nonzero(lower > 0.0)),
            "worst_upper_exceedance": float(upper.max()),
            "worst_lower_exceedance": float(lower.max()),
            "mean_applied_correction": float((up.mean() + low.mean())),
            "P95_applied_correction": float(np.quantile(up + low, .95)),
            "max_applied_correction": float((up + low).max()),
            "fallback_count": candidate.fallback_count,
        }

    combined = one(range(len(residuals["labels"])))
    by_case = {}
    for case in CALIBRATION_CASES:
        indices = [index for index, (_day, label_case) in enumerate(residuals["labels"]) if label_case == case]
        by_case[case] = one(indices)
    return {
        "family": candidate.family,
        **combined,
        "covering": combined["upper_exceedance_count"] == 0 and combined["lower_exceedance_count"] == 0,
        "by_case": by_case,
        "candidate_sha256_before_validation": candidate.canonical_sha256,
    }


def select_family(candidates: CorrectionCandidates, residuals: Mapping[str, object]):
    ordered = (candidates.m1, candidates.m2, candidates.m3)
    before = {item.family: item.canonical_sha256 for item in ordered}
    reports = {item.family: prospective_coverage(item, residuals) for item in ordered}
    covering = [item for item in ordered if reports[item.family]["covering"]]
    if not covering:
        return None, reports, "STATIC_AC_FIDELITY_CORRECTION_INSUFFICIENT"
    simplest = covering[0]
    selected = simplest
    reason = "SIMPLEST_COVERING_FAMILY"
    baseline = float(reports[simplest.family]["mean_applied_correction"])
    if baseline > 0:
        for item in covering[1:]:
            if float(reports[item.family]["mean_applied_correction"]) <= .75 * baseline:
                selected = item
                reason = "MORE_COMPLEX_COVERING_FAMILY_AT_LEAST_25_PERCENT_LESS_MEAN_CORRECTION"
                break
    if before != {item.family: item.canonical_sha256 for item in ordered}:
        raise RuntimeError("V35_PROSPECTIVE_VALIDATION_MUTATED_FROZEN_NUMBERS")
    return selected, reports, reason


def candidate_artifact(candidate: StaticCorrection) -> dict[str, object]:
    return {
        "artifact_id": f"V35_{candidate.family}_STATIC_AC_CORRECTION_V1",
        "status": "FROZEN_FROM_APR01_20",
        "correction": candidate.payload(),
        "correction_sha256": candidate.canonical_sha256,
    }

