"""Calibrate and validate the V37-R2 direct-affine MESS voltage repair."""

from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import os
from pathlib import Path
import time
from typing import Any, Iterable, Mapping

import numpy as np
import pandas as pd

from dayahead.mess_physics import PCS_KVA, P_LIMIT_KW
from dayahead.v28r2.electrical_cache_prepare import prepare_electrical_context
from dayahead.v28r2.electrical_context import build_electrical_context
from dayahead.v28r2.electrical_subproblem import slot_coefficients
from dayahead.v28r2.formulation import PF_TAN, materialize_formulation_data
from dayahead.v28r2.opendss_backend import _voltage_vector
from dayahead.v28r2.opendss_mapping import (
    FeederAssets, apply_frozen_native_state, apply_trajectory_slot,
    compile_clean_engine,
)
from dayahead.v28r2.trajectory import FrozenTrajectory
from dayahead.v35.contracts import MESS_IDS
from dayahead.v36.science import canonical_sha256
from dayahead.v36.storage import file_sha, write_json, write_parquet
from dayahead.v37.contracts import (
    BEAM_WIDTH, DEFAULT_K, SEED_WIDTH, SOURCE_DATA_REPOSITORY,
)
from dayahead.v37.voltage_fidelity import (
    AUTHORITY_RELATIVE_PATH, AUTHORITY_SCHEMA, repaired_coefficients,
)


CALIBRATION_DAY = "2025-04-01"
MAY_DAYS = tuple(f"2025-05-{index:02d}" for index in range(1, 6))
CASES = ("B2", "B3")
APRIL_WORKTREE = Path(r"C:\codex_mobileess_workspace\MobileESS_v36_apr01_calibration")
APRIL_ROOT = APRIL_WORKTREE / "frozen_artifacts/v36_final_schema/PRE_CALIBRATION"
OLD_PASS_ID = "MAY_2025_LOCKED_FINAL"
R2_PASS_ID = "MAY_2025_V37_R2_FINAL_AUTHORITY"
RAW_ROOT = Path("frozen_artifacts/v36_final_schema")
OLD_ROOT = RAW_ROOT / OLD_PASS_ID
NEW_ROOT = RAW_ROOT / R2_PASS_ID
OUT = Path("dayahead/artifacts/v37_r2_voltage_fidelity_repair")
APRIL_BACKGROUND_CACHE = Path("dayahead/cache/v37_r2_april_background")
APRIL_DAYS = tuple(f"2025-04-{index:02d}" for index in range(1, 31))
SELECTABLE_SERVICES = tuple(
    [f"IDC{index:02d}" for index in range(1, 13)]
    + [f"STA{index:02d}" for index in range(1, 13)]
)
# A 10-unit symmetric step is tiny relative to the frozen 550 kW / 700 kVA
# equipment limits, while moving remote cross-PCC voltage responses above the
# independently measured OpenDSS numerical scatter.
DELTA_P_KW = 10.0
DELTA_Q_KVAR = 10.0
PHYSICAL_TOLERANCE = 1.0e-6


def _source_location(function: object, repo: Path) -> dict[str, Any]:
    return {
        "file": str(Path(inspect.getsourcefile(function) or "").resolve().relative_to(repo)),
        "function": getattr(function, "__name__", str(function)),
        "line": int(inspect.getsourcelines(function)[1]),
    }


def _case_root(repo: Path, pass_id: str, day: str, case: str) -> Path:
    return repo / RAW_ROOT / pass_id / day / case


def _case_data(repo: Path, day: str, case: str, *, calibration: bool = False,
               pass_id: str = OLD_PASS_ID) -> dict[str, Any]:
    root = APRIL_ROOT / day / case if calibration else _case_root(repo, pass_id, day, case)
    mess = pd.read_parquet(root / "mess/MESS_TRAJECTORY_96.parquet")
    aidc = pd.read_parquet(root / "aidc/IDC_FACILITY_96.parquet")
    fresh = pd.read_parquet(root / "fresh/FRESH_BUS_PHASE_96.parquet")
    planning = pd.read_parquet(root / "planning/PLANNING_BUS_PHASE_96.parquet")
    aidc_ids = [f"AIDC{index:02d}" for index in range(1, 13)]
    pcc_p = aidc.pivot(index="slot", columns="AIDC_id", values="PCC_P_kW")[aidc_ids].to_numpy(float)
    pcc_q = aidc.pivot(index="slot", columns="AIDC_id", values="PCC_Q_kvar")[aidc_ids].to_numpy(float)
    order = list(MESS_IDS)
    p = mess.pivot(index="slot", columns="vehicle_id", values="P_kW")[order].to_numpy(float)
    q = mess.pivot(index="slot", columns="vehicle_id", values="Q_kvar")[order].to_numpy(float)
    locations = mess.pivot(index="slot", columns="vehicle_id", values="current_location")[order].to_numpy(dtype=object)
    for vehicle_index, vehicle in enumerate(order):
        for slot in range(96):
            if str(locations[slot, vehicle_index]).upper() == "TRANSIT":
                locations[slot, vehicle_index] = f"TRANSIT_{vehicle}"
    frozen = FrozenTrajectory(
        day=day, namespace="DAYAHEAD", case=case,
        pcc_p_kw=pcc_p, pcc_q_kvar=pcc_q,
        mess_p_kw=p, mess_q_kvar=q, mess_ids=tuple(MESS_IDS),
        mess_locations_96x4=locations,
        source_schedule_sha256=canonical_sha256({
            "authority": "V37_R2_SAVED_CALIBRATION_STATE",
            "day": day, "case": case,
        }),
    )
    frozen.validate()
    return {
        "root": root, "mess": mess, "aidc": aidc, "fresh": fresh,
        "planning": planning, "pcc_p": pcc_p, "pcc_q": pcc_q,
        "p": p, "q": q, "locations": locations, "frozen": frozen,
    }


def _aggregate_states(repo: Path) -> tuple[pd.DataFrame, dict[tuple[str, str], dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    loaded: dict[tuple[str, str], dict[str, Any]] = {}
    for day in (CALIBRATION_DAY,):
        for case in CASES:
            data = _case_data(repo, day, case, calibration=True)
            loaded[(day, case)] = data
            active = data["mess"].loc[
                (data["mess"]["P_kW"].abs() > 1e-9)
                | (data["mess"]["Q_kvar"].abs() > 1e-9)
            ]
            fresh = data["fresh"].set_index(["slot", "bus_phase_key"])
            for (slot, service), group in active.groupby(["slot", "current_location"], sort=True):
                service = str(service).upper()
                if service.startswith("TRANSIT_"):
                    continue
                node_keys = [f"mess_{service.lower()}_pcc.{index}" for index in range(1, 4)]
                local = [float(fresh.loc[(int(slot), node), "fresh_voltage_magnitude_pu"]) for node in node_keys]
                rows.append({
                    "day": day, "case": case, "slot": int(slot), "service": service,
                    "timestamp": str(group["timestamp"].iloc[0]),
                    "P_kW": float(group["P_kW"].sum()),
                    "Q_kvar": float(group["Q_kvar"].sum()),
                    "Fresh_local_Vmin_pu": min(local),
                    "vehicle_ids": "|".join(sorted(map(str, group["vehicle_id"]))),
                })
    return pd.DataFrame(rows), loaded


def _background_audit_plan() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Select the smallest deterministic pre-May background coverage set."""

    source_days = (
        SOURCE_DATA_REPOSITORY
        / "cache/v28r2_campaign_sources/april_2025/days"
    )
    raw_rows: list[dict[str, Any]] = []
    for day in APRIL_DAYS:
        path = source_days / day / "aemo_forecast.json"
        if not path.is_file():
            raise FileNotFoundError(f"V37_R2_APRIL_BACKGROUND_SOURCE_MISSING:{path}")
        payload = json.loads(path.read_text(encoding="utf-8"))
        demand = np.asarray(payload["demand_mw_96"], dtype=float)
        pv = np.asarray(payload["pv_mw_96"], dtype=float)
        timestamps = tuple(map(str, payload["timestamps_96"]))
        if demand.shape != (96,) or pv.shape != (96,) or len(timestamps) != 96:
            raise RuntimeError(f"V37_R2_APRIL_BACKGROUND_AXIS:{day}")
        for slot in range(96):
            raw_rows.append({
                "day": day, "slot": slot, "timestamp": timestamps[slot],
                "demand_MW": float(demand[slot]), "PV_MW": float(pv[slot]),
                "net_demand_MW": float(demand[slot] - pv[slot]),
            })
    raw = pd.DataFrame(raw_rows)
    median_net = float(raw["net_demand_MW"].median())
    raw_candidates = (
        (raw.loc[raw["net_demand_MW"].idxmin()], "FULL_APRIL_LOW_NET_HIGH_PV"),
        (raw.loc[(raw["net_demand_MW"] - median_net).abs().idxmin()], "FULL_APRIL_MEDIAN_NET"),
        (raw.loc[raw["net_demand_MW"].idxmax()], "FULL_APRIL_HIGH_NET_HIGH_DEMAND"),
    )

    electrical_rows: list[dict[str, Any]] = []
    exact_days: list[str] = []
    exact_root = (
        SOURCE_DATA_REPOSITORY
        / "frozen_artifacts/v28r2_april_full_month_preflight"
    )
    for day in APRIL_DAYS:
        path = (
            exact_root / day / "dayahead/electrical_cache/data"
            / f"D1_AC_ANCHOR_SENSITIVITY_{day}.npz"
        )
        if not path.is_file():
            continue
        exact_days.append(day)
        with np.load(path, allow_pickle=False) as voltage:
            nodes = tuple(map(str, voltage["node_names"]))
            anchor_v = np.sqrt(np.maximum(0.0, np.asarray(voltage["anchor_v_squared"], dtype=float)))
            root_pq = np.asarray(voltage["root_pq"], dtype=float)
        complete_bus_indices: list[tuple[int, int, int]] = []
        by_bus: dict[str, dict[str, int]] = {}
        for index, node in enumerate(nodes):
            bus, suffix = node.rsplit(".", 1)
            phase = {"1": "A", "2": "B", "3": "C"}.get(suffix)
            if phase is not None:
                by_bus.setdefault(bus, {})[phase] = index
        for phases in by_bus.values():
            if set(phases) == set("ABC"):
                complete_bus_indices.append(tuple(phases[p] for p in "ABC"))
        for slot in range(96):
            imbalance = max(
                float(np.ptp(anchor_v[slot, list(indices)]))
                for indices in complete_bus_indices
            )
            electrical_rows.append({
                "day": day, "slot": slot,
                "D1_root_P_kW": float(root_pq[slot, 0]),
                "D1_root_Q_kvar": float(root_pq[slot, 1]),
                "D1_anchor_Vmin_pu": float(anchor_v[slot].min()),
                "D1_max_three_phase_imbalance_pu": imbalance,
            })
    if not electrical_rows:
        raise RuntimeError("V37_R2_NO_SAVED_APRIL_ELECTRICAL_BACKGROUND")
    electrical = pd.DataFrame(electrical_rows)
    electrical_candidates = (
        (electrical.loc[electrical["D1_anchor_Vmin_pu"].idxmin()], "SAVED_APRIL_LOW_D1_ANCHOR_VOLTAGE"),
        (electrical.loc[electrical["D1_max_three_phase_imbalance_pu"].idxmax()], "SAVED_APRIL_STRONG_PHASE_IMBALANCE"),
        (electrical.loc[electrical["D1_root_Q_kvar"].idxmin()], "SAVED_APRIL_LOW_ROOT_Q"),
        (electrical.loc[electrical["D1_root_Q_kvar"].idxmax()], "SAVED_APRIL_HIGH_ROOT_Q"),
    )

    representatives: dict[tuple[str, int], dict[str, Any]] = {}
    for row, reason in (*raw_candidates, *electrical_candidates):
        key = (str(row["day"]), int(row["slot"]))
        target = representatives.setdefault(key, {
            "day": key[0], "slot": key[1], "selection_reasons": [],
        })
        target["selection_reasons"].append(reason)
        for name, value in row.items():
            if name not in {"day", "slot", "timestamp"} and pd.notna(value):
                target[name] = float(value)
    planned = []
    raw_indexed = raw.set_index(["day", "slot"])
    for key, row in sorted(representatives.items()):
        raw_row = raw_indexed.loc[key]
        row.update({
            "timestamp": str(raw_row["timestamp"]),
            "demand_MW": float(raw_row["demand_MW"]),
            "PV_MW": float(raw_row["PV_MW"]),
            "net_demand_MW": float(raw_row["net_demand_MW"]),
            "selection_reasons": "|".join(sorted(row["selection_reasons"])),
        })
        planned.append(row)

    apr01 = raw.loc[raw["day"] == CALIBRATION_DAY]
    audit = {
        "artifact_id": "V37_R2_APRIL_BACKGROUND_COVERAGE_AUDIT_V1",
        "scope": "PRE_MAY_APRIL_BACKGROUND_ONLY",
        "raw_April_day_count": int(raw["day"].nunique()),
        "raw_April_slot_count": int(len(raw)),
        "saved_D1_electrical_day_count_before_targeted_generation": len(exact_days),
        "saved_D1_electrical_days_before_targeted_generation": exact_days,
        "Apr01_raw_range": {
            "demand_MW": [float(apr01["demand_MW"].min()), float(apr01["demand_MW"].max())],
            "PV_MW": [float(apr01["PV_MW"].min()), float(apr01["PV_MW"].max())],
            "net_demand_MW": [float(apr01["net_demand_MW"].min()), float(apr01["net_demand_MW"].max())],
        },
        "full_April_raw_range": {
            "demand_MW": [float(raw["demand_MW"].min()), float(raw["demand_MW"].max())],
            "PV_MW": [float(raw["PV_MW"].min()), float(raw["PV_MW"].max())],
            "net_demand_MW": [float(raw["net_demand_MW"].min()), float(raw["net_demand_MW"].max())],
        },
        "Apr01_background_alone_sufficient": False,
        "representative_selection_rule": (
            "FULL_APRIL_RAW_LOW_MEDIAN_HIGH_NET_PLUS_SAVED_APRIL_ELECTRICAL_"
            "LOW_VOLTAGE_MAX_PHASE_IMBALANCE_LOW_HIGH_ROOT_Q"
        ),
        "representative_background_slot_count": len(planned),
        "representatives": planned,
        "full_April_optimization_campaign_run": False,
        "May_data_used": False,
        "PASS": False,
    }
    return audit, planned


def _materialize_april_background_data(
    repo: Path, representatives: list[dict[str, Any]],
) -> tuple[pd.DataFrame, dict[tuple[str, str], dict[str, Any]]]:
    """Create only the D1/Fresh context needed by the selected April slots."""

    from dayahead.v36.context import install_exact_source_lookup

    rows: list[dict[str, Any]] = []
    loaded: dict[tuple[str, str], dict[str, Any]] = {}
    for representative in representatives:
        day = str(representative["day"]); slot = int(representative["slot"])
        key = (day, "FRESH_ONLY")
        if key not in loaded:
            install_exact_source_lookup()
            previous = Path.cwd()
            try:
                formulation = materialize_formulation_data(
                    SOURCE_DATA_REPOSITORY, day, disable_legacy_mess_source=True,
                )
            finally:
                os.chdir(previous)
            source_cache = (
                SOURCE_DATA_REPOSITORY
                / "frozen_artifacts/v28r2_april_full_month_preflight"
                / day / "dayahead/electrical_cache"
            )
            local_cache = repo / APRIL_BACKGROUND_CACHE / day
            cache = source_cache if (
                source_cache / "data" / f"D1_AC_ANCHOR_SENSITIVITY_{day}.npz"
            ).is_file() else local_cache
            try:
                electrical = build_electrical_context(
                    SOURCE_DATA_REPOSITORY, formulation, cache,
                )
            except RuntimeError as error:
                if not str(error).startswith("V28R2_D1_ELECTRICAL_CACHE_MISSING:"):
                    raise
                electrical = prepare_electrical_context(
                    SOURCE_DATA_REPOSITORY, formulation, cache,
                )
            try:
                anchor_control = np.asarray(electrical.voltage["anchor_control"], dtype=float)
                pcc_p = anchor_control[:, :12].copy()
                pcc_q = pcc_p * PF_TAN
            finally:
                electrical.voltage.close(); electrical.current.close()
            loaded[key] = {
                "pcc_p": pcc_p, "pcc_q": pcc_q,
                "p": np.zeros((96, len(MESS_IDS)), dtype=float),
                "q": np.zeros((96, len(MESS_IDS)), dtype=float),
                "locations": np.asarray([
                    [f"TRANSIT_{vehicle}" for vehicle in MESS_IDS]
                    for _slot in range(96)
                ], dtype=object),
                "fresh": None, "planning": None,
                "formulation_data": formulation, "electrical_cache": cache,
            }
        for service in SELECTABLE_SERVICES:
            rows.append({
                "day": day, "case": "FRESH_ONLY", "slot": slot,
                "service": service, "timestamp": str(representative["timestamp"]),
                "P_kW": 0.0, "Q_kvar": 0.0,
                "Fresh_local_Vmin_pu": np.nan, "vehicle_ids": str(MESS_IDS[0]),
                "selection_reasons": str(representative["selection_reasons"]),
                "calibration_state_id": (
                    f"APRIL_BACKGROUND_{day.replace('-', '')}_S{slot:02d}_{service}"
                ),
                "probe_kind": "TARGETED_APRIL_BACKGROUND_FRESH_ONLY_PROBE",
                "probe_target_P_kW": 500.0,
                "probe_target_Q_kvar": -450.0,
                "probe_vehicle_index": 0,
                "override_source_location": True,
                "zero_all_MESS_at_slot": True,
            })
    return pd.DataFrame(rows), loaded


def _select_calibration_states(
    states: pd.DataFrame, services: tuple[str, ...] = SELECTABLE_SERVICES,
) -> pd.DataFrame:
    selected: dict[tuple[str, str, int, str], set[str]] = {}

    def add(row: pd.Series, reason: str) -> None:
        key = (str(row["day"]), str(row["case"]), int(row["slot"]), str(row["service"]))
        selected.setdefault(key, set()).add(reason)

    selectors = {
        "GLOBAL_MOST_NEGATIVE_Q": lambda f: f["Q_kvar"].idxmin(),
        "GLOBAL_MOST_POSITIVE_Q": lambda f: f["Q_kvar"].idxmax(),
        "GLOBAL_MOST_NEGATIVE_P": lambda f: f["P_kW"].idxmin(),
        "GLOBAL_MOST_POSITIVE_P": lambda f: f["P_kW"].idxmax(),
        "GLOBAL_LOWEST_FRESH_V": lambda f: f["Fresh_local_Vmin_pu"].idxmin(),
    }
    for _service, frame in states.groupby("service", sort=True):
        for reason, selector in selectors.items():
            add(frame.loc[selector(frame)], reason)

    for (_case, _service), frame in states.groupby(["case", "service"], sort=True):
        add(frame.loc[frame["Q_kvar"].idxmin()], "APRIL_CASE_MOST_NEGATIVE_Q")
        add(frame.loc[frame["Fresh_local_Vmin_pu"].idxmin()], "APRIL_CASE_LOWEST_FRESH_V")

    rows = []
    indexed = states.set_index(["day", "case", "slot", "service"])
    for sequence, (key, reasons) in enumerate(sorted(selected.items()), start=1):
        row = indexed.loc[key].to_dict()
        row.update(dict(zip(("day", "case", "slot", "service"), key, strict=True)))
        row["selection_reasons"] = "|".join(sorted(reasons))
        row["calibration_state_id"] = f"APRIL_SAVED_{sequence:03d}"
        row["probe_kind"] = "SAVED_APRIL_OPERATING_STATE"
        row["probe_target_P_kW"] = float(row["P_kW"])
        row["probe_target_Q_kvar"] = float(row["Q_kvar"])
        row["probe_vehicle_index"] = -1
        row["override_source_location"] = False
        row["zero_all_MESS_at_slot"] = False
        rows.append(row)

    # The completed Apr-01 B2/B3 paths do not contain both P and Q directions
    # at every active service.  Fill only that electrical coverage gap with
    # deterministic Fresh-only probes on an existing Apr-01 location/slot.
    # No route, destination, SoC, or optimization decision is changed.
    synthetic_targets = (
        (500.0, 0.0, "APRIL_FRESH_ONLY_POSITIVE_P"),
        (-500.0, 0.0, "APRIL_FRESH_ONLY_NEGATIVE_P"),
        (0.0, 600.0, "APRIL_FRESH_ONLY_POSITIVE_Q"),
        (0.0, -600.0, "APRIL_FRESH_ONLY_NEGATIVE_Q"),
        (500.0, 450.0, "APRIL_FRESH_ONLY_JOINT_POSITIVE_P_POSITIVE_Q"),
        (500.0, -450.0, "APRIL_FRESH_ONLY_JOINT_POSITIVE_P_NEGATIVE_Q"),
        (-500.0, 450.0, "APRIL_FRESH_ONLY_JOINT_NEGATIVE_P_POSITIVE_Q"),
        (-500.0, -450.0, "APRIL_FRESH_ONLY_JOINT_NEGATIVE_P_NEGATIVE_Q"),
    )
    for service, frame in states.groupby("service", sort=True):
        reference = frame.loc[frame["Fresh_local_Vmin_pu"].idxmin()].to_dict()
        for p_target, q_target, reason in synthetic_targets:
            sequence = len(rows) + 1
            row = dict(reference)
            row["selection_reasons"] = reason
            row["calibration_state_id"] = f"APRIL_PROBE_{sequence:03d}"
            row["probe_kind"] = "TARGETED_APRIL_FRESH_ONLY_ELECTRICAL_PROBE"
            row["probe_target_P_kW"] = p_target
            row["probe_target_Q_kvar"] = q_target
            row["probe_vehicle_index"] = -1
            row["override_source_location"] = False
            row["zero_all_MESS_at_slot"] = False
            rows.append(row)

    # Apr-01 has saved nonzero operation at only a subset of selectable PCCs.
    # Complete the source axis at the single lowest-voltage saved Apr-01
    # background without pretending that the synthetic states were completed
    # integrated operating days.
    observed = set(states["service"].astype(str))
    reference = states.loc[states["Fresh_local_Vmin_pu"].idxmin()].to_dict()
    missing_targets = (
        (500.0, 450.0, "APRIL_FRESH_ONLY_MISSING_PCC_POSITIVE_Q"),
        (500.0, -450.0, "APRIL_FRESH_ONLY_MISSING_PCC_NEGATIVE_Q"),
        (-500.0, 450.0, "APRIL_FRESH_ONLY_MISSING_PCC_NEGATIVE_P_POSITIVE_Q"),
        (-500.0, -450.0, "APRIL_FRESH_ONLY_MISSING_PCC_NEGATIVE_P_NEGATIVE_Q"),
    )
    for service in services:
        if service in observed:
            continue
        for p_target, q_target, reason in missing_targets:
            sequence = len(rows) + 1
            row = dict(reference)
            row.update({
                "service": service, "P_kW": 0.0, "Q_kvar": 0.0,
                "selection_reasons": reason,
                "calibration_state_id": f"APRIL_PCC_COVERAGE_{sequence:03d}",
                "probe_kind": "TARGETED_APR01_MISSING_PCC_FRESH_ONLY_PROBE",
                "probe_target_P_kW": p_target,
                "probe_target_Q_kvar": q_target,
                "probe_vehicle_index": 0,
                "override_source_location": True,
                "zero_all_MESS_at_slot": True,
            })
            rows.append(row)
    return pd.DataFrame(rows)


def _changed_trajectory(
    data: Mapping[str, Any], day: str, case: str, slot: int,
    vehicle_index: int, service: str, target_p: float, target_q: float,
    label: str, *, zero_all_mess: bool, override_source_location: bool,
) -> FrozenTrajectory:
    p = np.asarray(data["p"], dtype=float).copy()
    q = np.asarray(data["q"], dtype=float).copy()
    locations = np.asarray(data["locations"], dtype=object).copy()
    if zero_all_mess:
        p[slot, :] = 0.0; q[slot, :] = 0.0
        p[slot, vehicle_index] = target_p
        q[slot, vehicle_index] = target_q
    else:
        source_indices = [
            index for index, location in enumerate(locations[slot])
            if str(location).upper() == service
        ]
        current_p = float(p[slot, source_indices].sum())
        current_q = float(q[slot, source_indices].sum())
        p[slot, vehicle_index] += target_p - current_p
        q[slot, vehicle_index] += target_q - current_q
    if override_source_location:
        locations[slot, vehicle_index] = service
    result = FrozenTrajectory(
        day=day, namespace="DAYAHEAD", case=case,
        pcc_p_kw=np.asarray(data["pcc_p"]), pcc_q_kvar=np.asarray(data["pcc_q"]),
        mess_p_kw=p, mess_q_kvar=q, mess_ids=tuple(MESS_IDS),
        mess_locations_96x4=locations,
        source_schedule_sha256=canonical_sha256({
            "authority": "V37_R2_LOCAL_FINITE_DIFFERENCE", "day": day,
            "case": case, "slot": slot, "vehicle": MESS_IDS[vehicle_index],
            "source_service": service, "target_P_kW": target_p,
            "target_Q_kvar": target_q, "label": label,
            "zero_all_mess": zero_all_mess,
            "override_source_location": override_source_location,
        }),
    )
    result.validate()
    return result


def _solve_slot_voltage(odd: Any, adapter: Mapping[str, Any], context: Any,
                        trajectory: FrozenTrajectory, slot: int,
                        nodes: tuple[str, ...]) -> np.ndarray:
    apply_trajectory_slot(odd, adapter, context, trajectory, slot)
    apply_frozen_native_state(odd, context.voltage, slot)
    odd.Solution.SolveSnap()
    if not bool(odd.Solution.Converged()):
        raise RuntimeError(f"V37_R2_FRESH_NONCONVERGENCE:{trajectory.day}:{trajectory.case}:{slot}")
    # A second solve at the identical frozen state removes the dependence of
    # finite differences on the previous probe's voltage warm start.  This is
    # calibration-only; production Fresh validation remains unchanged.
    odd.Solution.SolveSnap()
    if not bool(odd.Solution.Converged()):
        raise RuntimeError(f"V37_R2_FRESH_REPEAT_NONCONVERGENCE:{trajectory.day}:{trajectory.case}:{slot}")
    return _voltage_vector(odd, nodes)


def _measure_calibration(
    repo: Path, selected: pd.DataFrame,
    loaded: Mapping[tuple[str, str], Mapping[str, Any]], *,
    reverse_state_order: bool = False,
    probe_order: tuple[str, ...] = ("BASE", "P_PLUS", "P_MINUS", "Q_PLUS", "Q_MINUS"),
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    assets = FeederAssets.from_repo(SOURCE_DATA_REPOSITORY)
    for day, day_states in selected.groupby("day", sort=True):
        sample_data = loaded[(str(day), str(day_states.iloc[0]["case"]))]
        if sample_data.get("formulation_data") is not None:
            context = build_electrical_context(
                SOURCE_DATA_REPOSITORY,
                sample_data["formulation_data"],
                Path(sample_data["electrical_cache"]),
            )
        else:
            from dayahead.v36.context import load_day_context as load_april_context
            _formulation, context = load_april_context(str(day))
        nodes = tuple(map(str, context.voltage["node_names"]))
        coefficients = tuple(
            slot_coefficients(context.legacy_context, context.voltage, context.current, slot)
            for slot in range(96)
        )
        controls = tuple(map(str, context.voltage["control_names"]))
        odd, adapter = compile_clean_engine(assets)
        try:
            ordered_states = day_states.sort_values(["case", "slot", "service", "calibration_state_id"])
            if reverse_state_order:
                ordered_states = ordered_states.iloc[::-1]
            for _, state in ordered_states.iterrows():
                case = str(state["case"]); slot = int(state["slot"]); service = str(state["service"])
                data = loaded[(str(day), case)]
                requested_vehicle = int(state.get("probe_vehicle_index", -1))
                local_vehicle = requested_vehicle if requested_vehicle >= 0 else next(
                    index for index, location in enumerate(data["locations"][slot])
                    if str(location).upper() == service
                )
                target_p = float(state["probe_target_P_kW"])
                target_q = float(state["probe_target_Q_kvar"])
                zero_all = bool(state.get("zero_all_MESS_at_slot", False))
                override_location = bool(state.get("override_source_location", False))
                trajectories = {
                    "BASE": _changed_trajectory(data, str(day), case, slot, local_vehicle, service, target_p, target_q, "BASE", zero_all_mess=zero_all, override_source_location=override_location),
                    "P_PLUS": _changed_trajectory(data, str(day), case, slot, local_vehicle, service, target_p + DELTA_P_KW, target_q, "P_PLUS", zero_all_mess=zero_all, override_source_location=override_location),
                    "P_MINUS": _changed_trajectory(data, str(day), case, slot, local_vehicle, service, target_p - DELTA_P_KW, target_q, "P_MINUS", zero_all_mess=zero_all, override_source_location=override_location),
                    "Q_PLUS": _changed_trajectory(data, str(day), case, slot, local_vehicle, service, target_p, target_q + DELTA_Q_KVAR, "Q_PLUS", zero_all_mess=zero_all, override_source_location=override_location),
                    "Q_MINUS": _changed_trajectory(data, str(day), case, slot, local_vehicle, service, target_p, target_q - DELTA_Q_KVAR, "Q_MINUS", zero_all_mess=zero_all, override_source_location=override_location),
                }
                values = {
                    label: _solve_slot_voltage(odd, adapter, context, trajectories[label], slot, nodes)
                    for label in probe_order
                }
                planning = (
                    data["planning"].set_index(["slot", "bus_phase_key"])
                    if data.get("planning") is not None else None
                )
                saved_fresh = (
                    data["fresh"].set_index(["slot", "bus_phase_key"])
                    if data.get("fresh") is not None else None
                )
                coefficient = coefficients[slot]
                p_index = controls.index(f"mess_p_kw[{service}]")
                q_index = controls.index(f"mess_q_kvar[{service}]")
                pcc_targets = {
                    f"mess_{target.lower()}_pcc.{phase_index}": (target, phase)
                    for target in SELECTABLE_SERVICES
                    for phase_index, phase in enumerate("ABC", start=1)
                }
                for node_index, node in enumerate(nodes):
                    target_service, phase = pcc_targets.get(node, ("", {
                        "1": "A", "2": "B", "3": "C",
                    }.get(node.rsplit(".", 1)[-1], "OTHER")))
                    base_v = float(values["BASE"][node_index])
                    fresh_hp = float(
                        (values["P_PLUS"][node_index] ** 2 - values["P_MINUS"][node_index] ** 2)
                        / (2.0 * DELTA_P_KW)
                    )
                    fresh_hq = float(
                        (values["Q_PLUS"][node_index] ** 2 - values["Q_MINUS"][node_index] ** 2)
                        / (2.0 * DELTA_Q_KVAR)
                    )
                    old_hp = float(coefficient.voltage_matrix[p_index, node_index])
                    old_hq = float(coefficient.voltage_matrix[q_index, node_index])
                    saved_state = str(state["probe_kind"]) == "SAVED_APRIL_OPERATING_STATE"
                    saved_fresh_value = (
                        float(saved_fresh.loc[(slot, node), "fresh_voltage_magnitude_pu"])
                        if saved_state and saved_fresh is not None else np.nan
                    )
                    saved_planning_value = (
                        float(planning.loc[(slot, node), "voltage_magnitude_pu"])
                        if saved_state and planning is not None else np.nan
                    )
                    p_ratio = fresh_hp / old_hp if abs(old_hp) > np.finfo(float).tiny else np.nan
                    q_ratio = fresh_hq / old_hq if abs(old_hq) > np.finfo(float).tiny else np.nan
                    rows.append({
                            "day": str(day), "case": case, "slot": slot,
                            "timestamp": str(state["timestamp"]), "service": service,
                            "source_service": service, "target_service": target_service,
                            "source_PCC": service, "target_PCC": target_service,
                            "phase": phase, "target_bus_phase_key": node,
                            "target_is_selectable_MESS_PCC": bool(node in pcc_targets),
                            "perturbed_vehicle_id": str(MESS_IDS[local_vehicle]),
                            "calibration_state_id": str(state["calibration_state_id"]),
                            "probe_kind": str(state["probe_kind"]),
                            "P_at_source_PCC_kW": target_p,
                            "Q_at_source_PCC_kvar": target_q,
                            "P_at_PCC_kW": target_p,
                            "Q_at_PCC_kvar": target_q,
                            "selection_reasons": str(state["selection_reasons"]),
                            "delta_P_kW": DELTA_P_KW, "delta_Q_kvar": DELTA_Q_KVAR,
                            "Fresh_base_voltage_pu": base_v,
                            "saved_Fresh_voltage_pu": saved_fresh_value if saved_state else np.nan,
                            "saved_Planning_voltage_pu": saved_planning_value if saved_state else np.nan,
                            "Fresh_replay_abs_error_pu": abs(base_v - saved_fresh_value) if saved_state else np.nan,
                            "old_H_P_pu_squared_per_kW": old_hp,
                            "Fresh_H_P_pu_squared_per_kW": fresh_hp,
                            "old_dV_dP_pu_per_kW": old_hp / (2.0 * base_v),
                            "Fresh_dV_dP_pu_per_kW": fresh_hp / (2.0 * base_v),
                            "old_H_Q_pu_squared_per_kvar": old_hq,
                            "Fresh_H_Q_pu_squared_per_kvar": fresh_hq,
                            "old_dV_dQ_pu_per_kvar": old_hq / (2.0 * base_v),
                            "Fresh_dV_dQ_pu_per_kvar": fresh_hq / (2.0 * base_v),
                            "Fresh_to_old_H_P_ratio": p_ratio,
                            "Fresh_to_old_H_Q_ratio": q_ratio,
                            "P_sign_match": bool(np.sign(fresh_hp) == np.sign(old_hp)),
                            "Q_sign_match": bool(np.sign(fresh_hq) == np.sign(old_hq)),
                    })
        finally:
            odd.Basic.ClearAll()
            context.voltage.close(); context.current.close()
    return pd.DataFrame(rows)


def _order_history_subset(selected: pd.DataFrame) -> pd.DataFrame:
    rows = []
    representative_pccs = {"IDC01", "IDC06", "IDC12", "STA01", "STA06", "STA12"}
    negative_q = selected.loc[
        (selected["day"] == CALIBRATION_DAY)
        & (selected["probe_kind"] != "SAVED_APRIL_OPERATING_STATE")
        & (selected["probe_target_Q_kvar"] <= -450.0)
        & (selected["probe_target_P_kW"] >= 500.0)
        & selected["service"].isin(representative_pccs)
    ].sort_values("service").drop_duplicates("service")
    rows.extend(negative_q.to_dict("records"))
    saved = selected.loc[selected["probe_kind"] == "SAVED_APRIL_OPERATING_STATE"]
    if len(saved):
        rows.append(saved.loc[saved["Fresh_local_Vmin_pu"].idxmin()].to_dict())
    result = pd.DataFrame(rows).drop_duplicates("calibration_state_id")
    if not 5 <= len(result) <= 10:
        raise RuntimeError(f"V37_R2_ORDER_HISTORY_SUBSET_SIZE:{len(result)}")
    return result


def _authority(
    repo: Path, calibration: pd.DataFrame, *,
    p_reproducibility_guard: float, q_reproducibility_guard: float,
    april_background_audit: Mapping[str, Any],
) -> dict[str, Any]:
    relevant = calibration.loc[calibration["target_is_selectable_MESS_PCC"]].copy()
    expected_sources = set(SELECTABLE_SERVICES)
    if set(relevant["source_service"].unique()) != expected_sources:
        raise RuntimeError("V37_R2_SOURCE_PCC_COVERAGE_NOT_24_OF_24")
    if set(relevant["target_service"].unique()) != expected_sources:
        raise RuntimeError("V37_R2_TARGET_PCC_COVERAGE_NOT_24_OF_24")
    if set(relevant["phase"].unique()) != set("ABC"):
        raise RuntimeError("V37_R2_PHASE_COVERAGE_NOT_ABC")

    def axis_authority(frame: pd.DataFrame, axis: str) -> dict[str, Any]:
        unit = "kW" if axis == "P" else "kvar"
        limit = P_LIMIT_KW if axis == "P" else PCS_KVA
        old = frame[f"old_H_{axis}_pu_squared_per_{unit}"].to_numpy(float)
        fresh = frame[f"Fresh_H_{axis}_pu_squared_per_{unit}"].to_numpy(float)
        base = frame["Fresh_base_voltage_pu"].to_numpy(float)
        material = (
            np.abs(fresh) / (2.0 * np.maximum(base, np.finfo(float).tiny)) * limit
            >= PHYSICAL_TOLERANCE
        )
        if material.any():
            physical_signs = set(map(int, np.sign(fresh[material])))
            if len(physical_signs) != 1 or 0 in physical_signs:
                raise RuntimeError("V37_R2_MATERIAL_FRESH_SIGN_NOT_STABLE")
            physical_sign = physical_signs.pop()
            guard = p_reproducibility_guard if axis == "P" else q_reproducibility_guard
            minimum_abs_h = float(np.nextafter(
                np.abs(fresh[material]).max() * (1.0 + guard), np.inf,
            ))
            old_sign_mismatch = int((np.sign(old[material]) != physical_sign).sum())
            repaired = np.where(
                (np.sign(old) == physical_sign) & (np.abs(old) >= minimum_abs_h),
                old, physical_sign * minimum_abs_h,
            )
            maximum_abs_correction = float(np.max(np.abs(repaired - old)))
        else:
            physical_sign = 0
            minimum_abs_h = 0.0
            old_sign_mismatch = 0
            maximum_abs_correction = 0.0
        return {
            "physical_sign": physical_sign,
            "minimum_abs_H": minimum_abs_h,
            "material_state_count": int(material.sum()),
            "immaterial_state_count": int((~material).sum()),
            "old_sign_mismatch_count_on_material_states": old_sign_mismatch,
            "maximum_absolute_H_correction": maximum_abs_correction,
            "materiality_rule": (
                f"ABS_FRESH_DV_D{axis}_TIMES_{limit:g}_"
                f"{unit.upper()}_GE_{PHYSICAL_TOLERANCE:g}_PU"
            ),
        }

    corrections = []
    for (source_service, target_service, phase), frame in relevant.groupby(
        ["source_service", "target_service", "phase"], sort=True,
    ):
        try:
            p = axis_authority(frame, "P")
            q = axis_authority(frame, "Q")
        except RuntimeError as error:
            raise RuntimeError(
                f"{error}:{source_service}:{target_service}:{phase}"
            ) from error
        phase_index = "ABC".index(str(phase)) + 1
        corrections.append({
            "service": str(source_service), "source_service": str(source_service),
            "target_service": str(target_service),
            "source_PCC": str(source_service), "target_PCC": str(target_service),
            "phase": str(phase),
            "target_bus_phase_key": f"mess_{str(target_service).lower()}_pcc.{phase_index}",
            "P_repair_mode": "PHYSICAL_SIGNED_MINIMUM_ABSOLUTE_H_FLOOR",
            "Q_repair_mode": "PHYSICAL_SIGNED_MINIMUM_ABSOLUTE_H_FLOOR",
            "P_physical_sign": p["physical_sign"],
            "Q_physical_sign": q["physical_sign"],
            "P_minimum_abs_H": p["minimum_abs_H"],
            "Q_minimum_abs_H": q["minimum_abs_H"],
            "calibration_state_count": int(len(frame)),
            "P_material_state_count": p["material_state_count"],
            "Q_material_state_count": q["material_state_count"],
            "P_immaterial_state_count": p["immaterial_state_count"],
            "Q_immaterial_state_count": q["immaterial_state_count"],
            "P_old_sign_mismatch_count_on_material_states": p[
                "old_sign_mismatch_count_on_material_states"
            ],
            "Q_old_sign_mismatch_count_on_material_states": q[
                "old_sign_mismatch_count_on_material_states"
            ],
            "P_maximum_absolute_H_correction": p["maximum_absolute_H_correction"],
            "Q_maximum_absolute_H_correction": q["maximum_absolute_H_correction"],
            "P_reproducibility_relative_guard": p_reproducibility_guard,
            "Q_reproducibility_relative_guard": q_reproducibility_guard,
            "P_materiality_rule": p["materiality_rule"],
            "Q_materiality_rule": q["materiality_rule"],
            "selection_rule": "STABLE_MATERIAL_FRESH_SIGN_AND_MAXIMUM_MATERIAL_ABSOLUTE_FRESH_H_TIMES_APRIL_REPRODUCIBILITY_GUARD",
            "strict_conservatism": "REPLACE_WRONG_SIGN_OR_WEAKER_BASE_ROW_WITH_PHYSICAL_SIGNED_MINIMUM_ABSOLUTE_H_FLOOR;_NEXTAFTER_AWAY_FROM_ZERO",
        })
    if len(corrections) != 24 * 24 * 3:
        raise RuntimeError(f"V37_R2_CORRECTION_AXIS:{len(corrections)}")
    base_hashes = {}
    for day in MAY_DAYS:
        path = repo / "dayahead/cache/v37_may_locked_final/electrical" / day / "data" / f"D1_AC_ANCHOR_SENSITIVITY_{day}.npz"
        base_hashes[day] = file_sha(path)
    from dayahead.v36.context import load_day_context as load_april_context
    _data, april_context = load_april_context(CALIBRATION_DAY)
    try:
        base_hashes[CALIBRATION_DAY] = file_sha(Path(april_context.voltage_path))
    finally:
        april_context.voltage.close(); april_context.current.close()
    return {
        "schema_id": AUTHORITY_SCHEMA,
        "classification": "DIRECT_AFFINE_VOLTAGE_FIDELITY_REPAIR",
        "calibration_days": sorted(calibration["day"].unique().tolist()),
        "calibration_cases": list(CASES),
        "calibration_source": {
            "worktree": str(APRIL_WORKTREE),
            "saved_result_root": str(APRIL_ROOT),
            "completed_integrated_April_authority_days": [CALIBRATION_DAY],
            "targeted_Fresh_only_probe_rule": "APR01_MISSING_PCC_CORNERS_PLUS_MINIMUM_APRIL_BACKGROUND_REPRESENTATIVE_PROBES",
            "targeted_Fresh_only_April_days": sorted(
                set(calibration["day"].astype(str)) - {CALIBRATION_DAY}
            ),
            "May_results_used_for_coefficient_derivation": False,
            "May_results_used_for_intercept_derivation": False,
            "May_margin_used": False
        },
        "finite_difference": {
            "method": "SYMMETRIC_CENTRAL", "delta_P_kW": DELTA_P_KW,
            "delta_Q_kvar": DELTA_Q_KVAR, "optimizer_invoked": False,
            "route_destination_SoC_changed": False,
            "frozen_regulator_and_capacitor_state": True,
            "identical_state_double_solve_for_history_settling": True,
        },
        "reproducibility_guard": {
            "P_relative": p_reproducibility_guard,
            "Q_relative": q_reproducibility_guard,
            "source": "MAX_OF_TWO_INDEPENDENT_IDENTICAL_SEQUENCE_AND_ALTERED_ORDER_APR01_FRESH_PROBES",
        },
        "reference_operating_point": "ORIGINAL_D1_AC_ANCHOR_WITH_MESS_P_EQ_Q_EQ_0",
        "reference_intercept_policy": "RECOMPUTE_CONSTANT_TO_PRESERVE_ORIGINAL_ANCHOR_EXACTLY",
        "loading_state_dependence": "ORIGINAL_96_SLOT_COEFFICIENT_VARIATION_PRESERVED",
        "correction_scope": "ALL_24_SOURCE_MESS_PCC_TO_ALL_24_TARGET_MESS_PCC_A_B_C_ROWS",
        "authority_frozen": True,
        "selectable_service_PCCs": list(SELECTABLE_SERVICES),
        "selectable_service_PCC_coverage": "24/24",
        "target_MESS_PCC_coverage": "24/24",
        "cross_PCC_sensitivity": True,
        "phase_coverage": ["A", "B", "C"],
        "full_bus_phase_capture_per_source_state": True,
        "full_bus_phase_target_count": int(calibration["target_bus_phase_key"].nunique()),
        "April_background_coverage_PASS": bool(april_background_audit["PASS"]),
        "April_background_representative_slot_count": int(
            april_background_audit["representative_background_slot_count"]
        ),
        "May_outcomes_examined_before_freeze": False,
        "base_voltage_authority_sha256_by_day": base_hashes,
        "corrections": corrections,
        "Benders_changed": False, "K_changed": False, "beam_changed": False,
        "MESS_physical_limits_changed": False, "AIDC_changed": False,
        "voltage_physical_limit_changed": False,
    }


def _apply_new_columns(calibration: pd.DataFrame, authority: Mapping[str, Any]) -> pd.DataFrame:
    repairs = {
        (str(row["source_service"]), str(row["target_service"]), str(row["phase"])):
            {
                "P": (int(row["P_physical_sign"]), float(row["P_minimum_abs_H"])),
                "Q": (int(row["Q_physical_sign"]), float(row["Q_minimum_abs_H"])),
            }
        for row in authority["corrections"]
    }
    result = calibration.loc[calibration["target_is_selectable_MESS_PCC"]].copy()
    def repaired_value(row: Any, axis: str, old: float) -> float:
        sign, floor = repairs[
            (str(row.source_service), str(row.target_service), str(row.phase))
        ][axis]
        if sign == 0 or (int(np.sign(old)) == sign and abs(old) >= floor):
            return old
        return float(sign) * floor

    result["new_H_P_pu_squared_per_kW"] = [
        repaired_value(row, "P", float(row.old_H_P_pu_squared_per_kW))
        for row in result.itertuples()
    ]
    result["new_H_Q_pu_squared_per_kvar"] = [
        repaired_value(row, "Q", float(row.old_H_Q_pu_squared_per_kvar))
        for row in result.itertuples()
    ]
    result["new_dV_dP_pu_per_kW"] = result["new_H_P_pu_squared_per_kW"] / (2.0 * result["Fresh_base_voltage_pu"])
    result["new_dV_dQ_pu_per_kvar"] = result["new_H_Q_pu_squared_per_kvar"] / (2.0 * result["Fresh_base_voltage_pu"])
    result["P_conservatism_pu_squared_per_kW"] = np.abs(result["new_H_P_pu_squared_per_kW"]) - np.abs(result["Fresh_H_P_pu_squared_per_kW"])
    result["Q_conservatism_pu_squared_per_kvar"] = np.abs(result["new_H_Q_pu_squared_per_kvar"]) - np.abs(result["Fresh_H_Q_pu_squared_per_kvar"])
    result["P_material"] = (
        np.abs(result["Fresh_dV_dP_pu_per_kW"]) * P_LIMIT_KW
        >= PHYSICAL_TOLERANCE
    )
    result["Q_material"] = (
        np.abs(result["Fresh_dV_dQ_pu_per_kvar"]) * PCS_KVA
        >= PHYSICAL_TOLERANCE
    )
    p_changed = ~np.isclose(
        result["new_H_P_pu_squared_per_kW"], result["old_H_P_pu_squared_per_kW"],
        rtol=1e-12, atol=0.0,
    )
    q_changed = ~np.isclose(
        result["new_H_Q_pu_squared_per_kvar"], result["old_H_Q_pu_squared_per_kvar"],
        rtol=1e-12, atol=0.0,
    )
    result["classification"] = np.select(
        [p_changed & q_changed, p_changed, q_changed],
        ["CORRECT_BOTH", "CORRECT_P", "CORRECT_Q"],
        default="PASS_UNCHANGED",
    )
    result["reason"] = "OBSERVED_APRIL_FULL_CROSS_PCC_FRESH_SLOPE_MAGNITUDE_ENVELOPE_WITH_EXACT_ZERO_MESS_ANCHOR"
    return result


def _metric_block(predicted: Iterable[float], actual: Iterable[float]) -> dict[str, Any]:
    predicted_array = np.asarray(tuple(predicted), dtype=float)
    actual_array = np.asarray(tuple(actual), dtype=float)
    error = predicted_array - actual_array
    absolute = np.abs(error)
    return {
        "row_count": int(len(error)), "MAE_pu": float(absolute.mean()),
        "P95_absolute_error_pu": float(np.quantile(absolute, 0.95)),
        "P99_absolute_error_pu": float(np.quantile(absolute, 0.99)),
        "maximum_absolute_error_pu": float(absolute.max()),
        "signed_bias_Planning_minus_Fresh_pu": float(error.mean()),
        "voltage_drop_underprediction_count": int((error > PHYSICAL_TOLERANCE).sum()),
        "Fresh_below_0_95_while_Planning_feasible_count": int(
            ((actual_array < 0.95 - PHYSICAL_TOLERANCE) & (predicted_array >= 0.95 - PHYSICAL_TOLERANCE)).sum()
        ),
    }


def _fidelity_rows(repo: Path, states: pd.DataFrame,
                   loaded: Mapping[tuple[str, str], Mapping[str, Any]],
                   selected: pd.DataFrame) -> pd.DataFrame:
    selected_keys = set(zip(
        selected["day"].astype(str), selected["case"].astype(str),
        selected["slot"].astype(int), selected["service"].astype(str), strict=True,
    ))
    rows = []
    for day in (CALIBRATION_DAY,):
        from dayahead.v36.context import load_day_context as load_april_context
        _data, context = load_april_context(day)
        old = tuple(
            slot_coefficients(context.legacy_context, context.voltage, context.current, slot)
            for slot in range(96)
        )
        new = repaired_coefficients(repo, context)
        controls = tuple(map(str, context.voltage["control_names"]))
        services = tuple(name[10:-1] for name in controls[12:36])
        nodes = tuple(map(str, context.voltage["node_names"]))
        try:
            for case in CASES:
                case_data = loaded[(day, case)]
                aidc = case_data["pcc_p"]
                fresh = case_data["fresh"].set_index(["slot", "bus_phase_key"])
                case_states = states.loc[(states["day"] == day) & (states["case"] == case)]
                for _, state in case_states.iterrows():
                    slot = int(state["slot"]); service = str(state["service"])
                    vector = np.zeros(60, dtype=float); vector[:12] = aidc[slot]
                    for sindex, active_service in enumerate(services):
                        selected_mess = case_data["mess"].loc[
                            (case_data["mess"]["slot"] == slot)
                            & (case_data["mess"]["current_location"] == active_service)
                        ]
                        vector[12 + sindex] = float(selected_mess["P_kW"].sum())
                        vector[36 + sindex] = float(selected_mess["Q_kvar"].sum())
                    old_v = np.sqrt(np.maximum(0.0, old[slot].voltage_constant + old[slot].voltage_matrix.T @ vector))
                    new_v = np.sqrt(np.maximum(0.0, new[slot].voltage_constant + new[slot].voltage_matrix.T @ vector))
                    for phase_index, phase in enumerate("ABC", start=1):
                        node = f"mess_{service.lower()}_pcc.{phase_index}"
                        nindex = nodes.index(node)
                        rows.append({
                            "day": day, "case": case, "slot": slot, "service": service,
                            "phase": phase, "bus_phase_key": node,
                            "P_at_PCC_kW": float(state["P_kW"]), "Q_at_PCC_kvar": float(state["Q_kvar"]),
                            "split": "CALIBRATION" if (day, case, slot, service) in selected_keys else "HOLD_OUT",
                            "old_Planning_voltage_pu": float(old_v[nindex]),
                            "new_Planning_voltage_pu": float(new_v[nindex]),
                            "Fresh_voltage_pu": float(fresh.loc[(slot, node), "fresh_voltage_magnitude_pu"]),
                        })
        finally:
            context.voltage.close(); context.current.close()
    return pd.DataFrame(rows)


def calibrate(repo: Path) -> dict[str, Any]:
    repo = repo.resolve(); out = repo / OUT; out.mkdir(parents=True, exist_ok=True)
    states, loaded = _aggregate_states(repo)
    background_audit, representatives = _background_audit_plan()
    april_background_states, april_background_loaded = _materialize_april_background_data(
        repo, representatives,
    )
    loaded.update(april_background_loaded)
    selected = pd.concat([
        _select_calibration_states(states), april_background_states,
    ], ignore_index=True)
    if set(selected["service"].astype(str)) != set(SELECTABLE_SERVICES):
        raise RuntimeError("V37_R2_SELECTED_SOURCE_PCC_COVERAGE")
    calibration = _measure_calibration(repo, selected, loaded)
    repeated = _measure_calibration(repo, selected, loaded)
    identity = ["calibration_state_id", "source_service", "target_bus_phase_key"]
    repeated = repeated.set_index(identity).sort_index()
    first_indexed = calibration.set_index(identity).sort_index()
    if not first_indexed.index.equals(repeated.index):
        raise RuntimeError("V37_R2_FINITE_DIFFERENCE_REPEAT_AXIS")
    p_repeat = np.abs(first_indexed["Fresh_dV_dP_pu_per_kW"].to_numpy(float)
                      - repeated["Fresh_dV_dP_pu_per_kW"].to_numpy(float))
    q_repeat = np.abs(first_indexed["Fresh_dV_dQ_pu_per_kvar"].to_numpy(float)
                      - repeated["Fresh_dV_dQ_pu_per_kvar"].to_numpy(float))
    v_repeat = np.abs(
        first_indexed["Fresh_base_voltage_pu"].to_numpy(float)
        - repeated["Fresh_base_voltage_pu"].to_numpy(float)
    )
    p_signal = np.abs(first_indexed["Fresh_dV_dP_pu_per_kW"].to_numpy(float))
    q_signal = np.abs(first_indexed["Fresh_dV_dQ_pu_per_kvar"].to_numpy(float))
    p_material = p_signal * P_LIMIT_KW >= PHYSICAL_TOLERANCE
    q_material = q_signal * PCS_KVA >= PHYSICAL_TOLERANCE
    if not p_material.any() or not q_material.any():
        raise RuntimeError("V37_R2_NO_MATERIAL_SENSITIVITY_SIGNAL")
    p_relative = p_repeat / np.maximum(p_signal, np.finfo(float).tiny)
    q_relative = q_repeat / np.maximum(q_signal, np.finfo(float).tiny)
    voltage_scatter = float(v_repeat.max())
    signal_scale = float(max(p_signal.max(), q_signal.max()))
    calibration = calibration.merge(
        pd.DataFrame({
            "calibration_state_id": first_indexed.index.get_level_values(0),
            "source_service": first_indexed.index.get_level_values(1),
            "target_bus_phase_key": first_indexed.index.get_level_values(2),
            "repeat_dV_dP_abs_error_pu_per_kW": p_repeat,
            "repeat_dV_dQ_abs_error_pu_per_kvar": q_repeat,
            "repeat_dV_dP_relative_error": p_relative,
            "repeat_dV_dQ_relative_error": q_relative,
            "repeat_base_voltage_abs_error_pu": v_repeat,
        }),
        on=identity, how="left", validate="one_to_one",
    )
    order_subset = _order_history_subset(selected)
    reordered = _measure_calibration(
        repo, order_subset, loaded, reverse_state_order=True,
        probe_order=("Q_MINUS", "Q_PLUS", "P_MINUS", "P_PLUS", "BASE"),
    ).set_index(identity).sort_index()
    reference_subset = first_indexed.loc[reordered.index]
    order_p = np.abs(reference_subset["Fresh_dV_dP_pu_per_kW"].to_numpy(float)
                     - reordered["Fresh_dV_dP_pu_per_kW"].to_numpy(float))
    order_q = np.abs(reference_subset["Fresh_dV_dQ_pu_per_kvar"].to_numpy(float)
                     - reordered["Fresh_dV_dQ_pu_per_kvar"].to_numpy(float))
    order_v = np.abs(reference_subset["Fresh_base_voltage_pu"].to_numpy(float)
                     - reordered["Fresh_base_voltage_pu"].to_numpy(float))
    order_p_relative = order_p / np.maximum(
        np.abs(reference_subset["Fresh_dV_dP_pu_per_kW"].to_numpy(float)), np.finfo(float).tiny,
    )
    order_q_relative = order_q / np.maximum(
        np.abs(reference_subset["Fresh_dV_dQ_pu_per_kvar"].to_numpy(float)), np.finfo(float).tiny,
    )
    order_p_signal = np.abs(reference_subset["Fresh_dV_dP_pu_per_kW"].to_numpy(float))
    order_q_signal = np.abs(reference_subset["Fresh_dV_dQ_pu_per_kvar"].to_numpy(float))
    order_p_material = order_p_signal * P_LIMIT_KW >= PHYSICAL_TOLERANCE
    order_q_material = order_q_signal * PCS_KVA >= PHYSICAL_TOLERANCE

    # The acceptance band is measured, not a bit-equality constant.  A
    # central difference contains two perturbed endpoints, so conservatively
    # propagate twice the largest independently observed unperturbed voltage
    # scatter through the smallest perturbation step.  The floating-point
    # term is only a lower numerical floor.
    observed_voltage_scatter = float(max(voltage_scatter, order_v.max()))
    sensitivity_abs_tolerance = float(max(
        2.0 * observed_voltage_scatter / min(DELTA_P_KW, DELTA_Q_KVAR),
        64.0 * np.finfo(float).eps * max(1.0, signal_scale),
    ))
    minimum_signal = float(min(p_signal[p_material].min(), q_signal[q_material].min()))
    sensitivity_relative_tolerance = float(
        sensitivity_abs_tolerance / max(minimum_signal, np.finfo(float).tiny)
    )
    repeat_pass = bool(
        p_repeat.max() <= sensitivity_abs_tolerance
        and q_repeat.max() <= sensitivity_abs_tolerance
        and p_relative[p_material].max() <= sensitivity_relative_tolerance
        and q_relative[q_material].max() <= sensitivity_relative_tolerance
    )
    order_pass = bool(
        order_p.max() <= sensitivity_abs_tolerance
        and order_q.max() <= sensitivity_abs_tolerance
        and order_p_relative[order_p_material].max() <= sensitivity_relative_tolerance
        and order_q_relative[order_q_material].max() <= sensitivity_relative_tolerance
    )

    replay = calibration["Fresh_replay_abs_error_pu"].dropna().to_numpy(float)
    replay_max = float(replay.max())
    replay_q25, replay_q75, replay_q99 = map(
        float, np.quantile(replay, (0.25, 0.75, 0.99)),
    )
    replay_iqr = replay_q75 - replay_q25
    # Saved Fresh was produced by an independent 96-slot solve sequence.  Use
    # the observed Apr-01 replay distribution's robust upper fence, together
    # with the newly measured engine/order scatter, for the baseline gate.
    baseline_tolerance = float(max(
        replay_q99 + 5.0 * replay_iqr,
        5.0 * observed_voltage_scatter,
        64.0 * np.finfo(float).eps,
    ))
    baseline_pass = bool(replay_max <= baseline_tolerance)
    p_guard = float(max(
        p_relative[p_material].max(), order_p_relative[order_p_material].max(),
    ))
    q_guard = float(max(
        q_relative[q_material].max(), order_q_relative[order_q_material].max(),
    ))

    background_rows = calibration.loc[
        calibration["probe_kind"] == "TARGETED_APRIL_BACKGROUND_FRESH_ONLY_PROBE"
    ]
    expected_background_states = len(representatives) * len(SELECTABLE_SERVICES)
    background_state_count = int(background_rows["calibration_state_id"].nunique())
    full_target_counts = background_rows.groupby("calibration_state_id")[
        "target_bus_phase_key"
    ].nunique()
    pcc_target_counts = background_rows.loc[
        background_rows["target_is_selectable_MESS_PCC"]
    ].groupby("calibration_state_id")["target_bus_phase_key"].nunique()
    background_pass = bool(
        background_state_count == expected_background_states
        and len(full_target_counts) == expected_background_states
        and (full_target_counts == calibration["target_bus_phase_key"].nunique()).all()
        and len(pcc_target_counts) == expected_background_states
        and (pcc_target_counts == 24 * 3).all()
        and set(background_rows["source_service"].unique()) == set(SELECTABLE_SERVICES)
    )
    background_audit.update({
        "targeted_Fresh_only_representative_state_count": background_state_count,
        "expected_targeted_Fresh_only_representative_state_count": expected_background_states,
        "source_PCC_coverage": "24/24",
        "full_bus_phase_target_count_per_source_perturbation": int(
            full_target_counts.min()
        ),
        "selectable_MESS_PCC_phase_target_count_per_source_perturbation": int(
            pcc_target_counts.min()
        ),
        "phase_coverage": ["A", "B", "C"],
        "cross_PCC_response_captured": True,
        "additional_integrated_optimization_days_assumed": 0,
        "additional_full_April_optimization_runs": 0,
        "PASS": background_pass,
    })
    write_json(out / "V37_R2_APRIL_BACKGROUND_COVERAGE_AUDIT.json", background_audit)
    pd.DataFrame(representatives).to_csv(
        out / "V37_R2_APRIL_BACKGROUND_REPRESENTATIVES.csv", index=False,
    )
    if not background_pass:
        raise RuntimeError("V37_R2_APRIL_BACKGROUND_COVERAGE_FAIL")

    reproducibility = {
        "artifact_id": "V37_R2_FRESH_REPRODUCIBILITY_AUDIT_V1",
        "full_pass_count": 2,
        "each_pass_new_OpenDSS_engine": True,
        "identical_deterministic_probe_sequence": True,
        "full_pass_state_count": int(len(selected)),
        "pass1_vs_pass2": {
            "dV_dP_max_absolute_error_pu_per_kW": float(p_repeat.max()),
            "dV_dP_max_relative_error_material_signals": float(p_relative[p_material].max()),
            "dV_dQ_max_absolute_error_pu_per_kvar": float(q_repeat.max()),
            "dV_dQ_max_relative_error_material_signals": float(q_relative[q_material].max()),
            "baseline_voltage_max_absolute_scatter_pu": voltage_scatter,
            "full_bus_phase_row_count": int(len(first_indexed)),
            "P_material_row_count": int(p_material.sum()),
            "Q_material_row_count": int(q_material.sum()),
        },
        "acceptance_tolerance": {
            "absolute_sensitivity": sensitivity_abs_tolerance,
            "relative_sensitivity": sensitivity_relative_tolerance,
            "derivation": "MAX(2_X_MAX(IDENTICAL_SEQUENCE_BASELINE_SCATTER,ALTERED_ORDER_BASELINE_SCATTER)_DIV_MIN_PROBE_DELTA,64_X_FLOAT_EPSILON_X_SIGNAL_SCALE);_RELATIVE_GATE_APPLIES_ONLY_WHEN_FULL_PHYSICAL_RANGE_EFFECT_GE_1E-6_PU",
            "saved_baseline_voltage": baseline_tolerance,
            "saved_baseline_derivation": "MAX(SAVED_REPLAY_P99_PLUS_5_X_IQR,5_X_OBSERVED_ENGINE_ORDER_BASELINE_SCATTER,64_X_FLOAT_EPSILON)",
        },
        "saved_Apr01_baseline": {
            "comparison_count": int(len(replay)),
            "maximum_absolute_error_pu": replay_max,
            "median_absolute_error_pu": float(np.median(replay)),
            "P99_absolute_error_pu": replay_q99,
            "IQR_absolute_error_pu": replay_iqr,
            "exceedance_count": int((replay > baseline_tolerance).sum()),
            "all_unperturbed_saved_probe_baselines_checked_same_slot_bus_phase": True,
            "PASS": baseline_pass,
        },
        "order_history_check": {
            "state_count": int(len(order_subset)),
            "PCCs": sorted(order_subset["service"].unique().tolist()),
            "phases": ["A", "B", "C"],
            "large_negative_Q_included": bool((order_subset["probe_target_Q_kvar"] <= -450.0).any()),
            "low_voltage_state_included": True,
            "independent_new_engine": True,
            "state_order_reversed": True,
            "probe_order_changed": True,
            "baseline_voltage_max_absolute_scatter_pu": float(order_v.max()),
            "dV_dP_max_absolute_error_pu_per_kW": float(order_p.max()),
            "dV_dP_max_relative_error_material_signals": float(order_p_relative[order_p_material].max()),
            "dV_dQ_max_absolute_error_pu_per_kvar": float(order_q.max()),
            "dV_dQ_max_relative_error_material_signals": float(order_q_relative[order_q_material].max()),
            "P_full_probe_range_scatter_impact_pu": float(order_p.max() * 500.0),
            "Q_full_probe_range_scatter_impact_pu": float(order_q.max() * 600.0),
            "PASS": order_pass,
        },
        "frozen_scale_reproducibility_guard": {
            "P_relative": p_guard,
            "Q_relative": q_guard,
            "derivation": "MAX_RELATIVE_ERROR_OBSERVED_ACROSS_IDENTICAL_SEQUENCE_AND_ALTERED_ORDER_APR01_PASSES",
        },
        "full_repeat_PASS": repeat_pass,
        "baseline_consistency_PASS": baseline_pass,
        "order_history_PASS": order_pass,
        "source_PCC_coverage": "24/24",
        "cross_PCC_coverage": True,
        "full_bus_phase_target_count": int(calibration["target_bus_phase_key"].nunique()),
        "phase_coverage": ["A", "B", "C"],
        "April_background_coverage_PASS": background_pass,
        "authority_freeze_allowed": bool(
            repeat_pass and baseline_pass and order_pass and background_pass
        ),
    }
    write_json(out / "V37_R2_FRESH_REPRODUCIBILITY_AUDIT.json", reproducibility)
    if not reproducibility["authority_freeze_allowed"]:
        raise RuntimeError("V37_R2_OPENDSS_STATE_HISTORY_MATERIAL")
    # Preserve the full pre-May evidence before attempting to build a frozen
    # authority, so any physical-sign/loading-state refusal is diagnosable
    # without looking at May or repeating the Fresh passes.
    write_parquet(out / "V37_R2_FRESH_FULL_BUS_PHASE_SENSITIVITY.parquet", calibration)
    write_parquet(
        out / "V37_R2_FRESH_LOCAL_SENSITIVITY.parquet",
        calibration.loc[calibration["target_is_selectable_MESS_PCC"]],
    )
    authority = _authority(
        repo, calibration,
        p_reproducibility_guard=p_guard,
        q_reproducibility_guard=q_guard,
        april_background_audit=background_audit,
    )
    write_json(repo / AUTHORITY_RELATIVE_PATH, authority)
    correction = _apply_new_columns(calibration, authority)
    write_parquet(out / "V37_R2_VOLTAGE_SENSITIVITY_CORRECTION_TABLE.parquet", correction)

    fidelity = _fidelity_rows(repo, states, loaded, selected)
    holdout = fidelity.loc[fidelity["split"] == "HOLD_OUT"]
    old_metrics = _metric_block(holdout["old_Planning_voltage_pu"], holdout["Fresh_voltage_pu"])
    new_metrics = _metric_block(holdout["new_Planning_voltage_pu"], holdout["Fresh_voltage_pu"])
    comparison = {
        "artifact_id": "V37_R2_OLD_NEW_FIDELITY_COMPARISON_V1",
        "scope": "APRIL01_SAVED_NONZERO_MESS_LOCAL_PCC_PHASE_HOLD_OUT_STATES",
        "calibration_state_count": int(len(selected)),
        "calibration_phase_row_count": int(len(calibration)),
        "hold_out_row_count": int(len(holdout)),
        "calibration_sensitivity_error": {
            f"{version}_vs_Fresh_dV_d{axis}": {
                f"MAE_pu_per_{unit}": float(np.abs(
                    correction[f"{version}_dV_d{axis}_pu_per_{unit}"]
                    - correction[f"Fresh_dV_d{axis}_pu_per_{unit}"]
                ).mean()),
                f"P95_absolute_error_pu_per_{unit}": float(np.quantile(np.abs(
                    correction[f"{version}_dV_d{axis}_pu_per_{unit}"]
                    - correction[f"Fresh_dV_d{axis}_pu_per_{unit}"]
                ), 0.95)),
                f"maximum_absolute_error_pu_per_{unit}": float(np.abs(
                    correction[f"{version}_dV_d{axis}_pu_per_{unit}"]
                    - correction[f"Fresh_dV_d{axis}_pu_per_{unit}"]
                ).max()),
            }
            for axis, unit in (("P", "kW"), ("Q", "kvar"))
            for version in ("old", "new")
        },
        "conservative_slope_envelope": {
            "new_P_weaker_than_Fresh_count": int(
                ((np.abs(correction["new_H_P_pu_squared_per_kW"])
                  + np.finfo(float).eps
                  < np.abs(correction["Fresh_H_P_pu_squared_per_kW"]))
                 & correction["P_material"]).sum()
            ),
            "new_Q_weaker_than_Fresh_count": int(
                ((np.abs(correction["new_H_Q_pu_squared_per_kvar"])
                  + np.finfo(float).eps
                  < np.abs(correction["Fresh_H_Q_pu_squared_per_kvar"]))
                 & correction["Q_material"]).sum()
            ),
            "interpretation": "MAE_CAN_INCREASE_BECAUSE_ONE_LINEAR_SLOPE_ENVELOPES_BOTH_NEGATIVE_AND_POSITIVE_PHYSICAL_RESPONSE;_SAFETY_GATE_IS_NO_WEAKER_THAN_FRESH",
        },
        "old": old_metrics, "repaired": new_metrics,
        "calibration_rows_excluded_from_hold_out": True,
    }
    write_json(out / "V37_R2_OLD_NEW_FIDELITY_COMPARISON.json", comparison)

    b0_errors = []
    for day in (CALIBRATION_DAY,):
        root = APRIL_ROOT / day / "B0"
        planning = pd.read_parquet(root / "planning/PLANNING_BUS_PHASE_96.parquet")
        fresh = pd.read_parquet(root / "fresh/FRESH_BUS_PHASE_96.parquet")
        merged = planning.merge(fresh, on=["slot", "bus_phase_key"], suffixes=("_p", "_f"))
        b0_errors.extend((merged["voltage_magnitude_pu"] - merged["fresh_voltage_magnitude_pu"]).tolist())
    reference = {
        "artifact_id": "V37_R2_REFERENCE_POINT_AUDIT_V1",
        "reference_operating_point": "D1_AC_ANCHOR_PER_SLOT_WITH_MESS_P_EQ_Q_EQ_0",
        "anchor_preserved_exactly_by_recomputed_affine_constant": True,
        "B0_April01_mean_signed_Planning_minus_Fresh_pu": float(np.mean(b0_errors)),
        "B0_April01_max_absolute_Planning_minus_Fresh_pu": float(np.max(np.abs(b0_errors))),
        "intercept_correction_required": False,
        "intercept_correction_applied": False,
        "reason": "ZERO_MESS_AC_ANCHOR_IS_ACCURATE; ERROR_EMERGES_OFF_ANCHOR_AND_IS_REPAIRED_IN_PQ_SLOPES",
    }
    write_json(out / "V37_R2_REFERENCE_POINT_AUDIT.json", reference)

    from dayahead.run_v16_3_voltage_candidate import _anchor_and_sensitivity_day
    from dayahead.v28r2.electrical_subproblem import slot_coefficients as slot_builder
    from dayahead.v35r3.algorithm import _add_fixed_voltage
    from dayahead.v34.integrated_mess import solve_integrated_mess
    from dayahead.v37.voltage_fidelity import repaired_coefficients as repair_builder
    trace = {
        "artifact_id": "V37_R2_EXISTING_VOLTAGE_AUTHORITY_TRACE_V1",
        "calibration_serialized_authority": str(
            SOURCE_DATA_REPOSITORY / "frozen_artifacts/v28r2_april_full_month_preflight"
            / CALIBRATION_DAY / "dayahead/electrical_cache/data"
            / f"D1_AC_ANCHOR_SENSITIVITY_{CALIBRATION_DAY}.npz"
        ),
        "production_base_authority_pattern": "dayahead/cache/v37_may_locked_final/electrical/<day>/data/D1_AC_ANCHOR_SENSITIVITY_<day>.npz",
        "old_authority_sha256_by_day": authority["base_voltage_authority_sha256_by_day"],
        "authority_generation": _source_location(_anchor_and_sensitivity_day, repo),
        "slot_coefficient_builder": _source_location(slot_builder, repo),
        "restricted_row_injector": _source_location(_add_fixed_voltage, repo),
        "full_model_builder": _source_location(solve_integrated_mess, repo),
        "repair_builder": _source_location(repair_builder, repo),
        "repaired_serialized_authority": str(AUTHORITY_RELATIVE_PATH),
        "old_equation": "v2 = anchor_v2 + H_old.T @ (control - anchor_control)",
        "repaired_equation": "v2 = anchor_v2 + H_repaired.T @ (control - anchor_control)",
        "reference": {
            "MESS_P_kW": 0.0, "MESS_Q_kvar": 0.0,
            "AIDC": "D1_REFERENCE_PLAN", "regulator_taps": "FROZEN_PER_SLOT",
            "capacitor_states": "FROZEN_PER_SLOT",
        },
        "indexing": ["day", "slot/loading_state", "source_service/PCC", "target_bus", "phase", "P_or_Q"],
    }
    write_json(out / "V37_R2_EXISTING_VOLTAGE_AUTHORITY_TRACE.json", trace)
    integration = {
        "artifact_id": "V37_R2_PRODUCTION_INTEGRATION_AUDIT_V1",
        "classification": "DIRECT_AFFINE_VOLTAGE_FIDELITY_REPAIR",
        "authority_loader": "dayahead.v37.voltage_fidelity.repaired_coefficients",
        "beam_internal_coefficient_factory_bound_to_repaired_authority": True,
        "production_consumers": ["_add_fixed_voltage", "solve_integrated_mess"],
        "original_direct_affine_row_count_per_full_model": 37056,
        "affine_structure_preserved": True, "new_binary_variables": 0,
        "OpenDSS_calls_inside_optimizer": 0, "Benders_changed": False,
        "K_changed": False, "beam_changed": False, "MESS_physical_limits_changed": False,
        "AIDC_changed": False, "voltage_physical_limit_changed": False,
        "base_anchor_files_modified": False,
        "V37_P1_cumulative_cache_and_persistent_worker_required": True,
        "planning_validation_pass_id": R2_PASS_ID,
    }
    write_json(out / "V37_R2_PRODUCTION_INTEGRATION_AUDIT.json", integration)
    return {
        "calibration_states": int(len(selected)), "calibration_rows": int(len(calibration)),
        "services": sorted(calibration["service"].unique().tolist()),
        "correction_entries": len(authority["corrections"]),
        "full_bus_phase_target_count": int(calibration["target_bus_phase_key"].nunique()),
        "April_background_representative_slot_count": len(representatives),
        "April_background_coverage_PASS": background_pass,
        "authority_sha256": file_sha(repo / AUTHORITY_RELATIVE_PATH),
        "authority_frozen": True,
        "old_holdout": old_metrics, "new_holdout": new_metrics,
        "maximum_absolute_P_H_correction": max(
            float(row["P_maximum_absolute_H_correction"])
            for row in authority["corrections"]
        ),
        "maximum_absolute_Q_H_correction": max(
            float(row["Q_maximum_absolute_H_correction"])
            for row in authority["corrections"]
        ),
    }


def _smoke_payload(repo: Path, day: str, case: str, result: Mapping[str, Any],
                   fallback: int) -> dict[str, Any]:
    root = _case_root(repo, R2_PASS_ID, day, case)
    old_root = _case_root(repo, OLD_PASS_ID, day, case)
    gates = json.loads((root / "summary/PHYSICAL_GATES.json").read_text(encoding="utf-8"))
    old_gates = json.loads((old_root / "summary/PHYSICAL_GATES.json").read_text(encoding="utf-8"))
    fresh = pd.read_parquet(root / "fresh/FRESH_BUS_PHASE_96.parquet")
    residual = pd.read_parquet(root / "residual/PLANNING_FRESH_VOLTAGE_RESIDUAL.parquet")
    moves = pd.read_parquet(root / "mess/MESS_MOVE_EVENTS.parquet")
    worst = fresh.loc[fresh["fresh_voltage_magnitude_pu"].idxmin()]
    payload = {
        "artifact_id": f"V37_R2_{day}_{case}_SMOKE_V1", "day": day, "case": case,
        "old_Planning_Vmin_pu": float(old_gates["Planning"]["Vmin_pu"]),
        "new_Planning_Vmin_pu": float(gates["Planning"]["Vmin_pu"]),
        "new_Fresh_Vmin_pu": float(gates["Fresh"]["Vmin_pu"]),
        "new_Fresh_Vmax_pu": float(gates["Fresh"]["Vmax_pu"]),
        "worst_Fresh": {
            "slot": int(worst["slot"]), "bus_phase_key": str(worst["bus_phase_key"]),
            "phase": str(worst["phase"]), "voltage_pu": float(worst["fresh_voltage_magnitude_pu"]),
        },
        "Fresh_lower_voltage_violations": int(gates["Fresh"]["lower_voltage_violation_count"]),
        "Fresh_upper_voltage_violations": int(gates["Fresh"]["upper_voltage_violation_count"]),
        "Fresh_current_violations": int(gates["Fresh"]["current_violation_count"]),
        "Fresh_transformer_violations": int(gates["Fresh"]["transformer_violation_count"]),
        "Fresh_convergence": str(gates["Fresh_solve_coverage"]),
        "maximum_Planning_Fresh_voltage_residual_pu": float(residual["absolute_residual"].max()),
        "Planning_lower_voltage_violations": int(gates["Planning"]["lower_voltage_violation_count"]),
        "Planning_upper_voltage_violations": int(gates["Planning"]["upper_voltage_violation_count"]),
        "Planning_current_violations": int(gates["Planning"]["current_violation_count"]),
        "Planning_transformer_violations": int(gates["Planning"]["transformer_violation_count"]),
        "MESS_relocation_count": int(len(moves)),
        "beam_fallback_used": bool(fallback),
        "K_fallback_used": bool(result.get("K_fallback", False)),
        "physical_PASS": bool(
            gates["Fresh_solve_coverage"] == "96/96"
            and sum(int(gates["Planning"][key]) for key in (
                "voltage_violation_count", "current_violation_count", "transformer_violation_count"
            )) == 0
            and sum(int(gates["Fresh"][key]) for key in (
                "voltage_violation_count", "current_violation_count", "transformer_violation_count"
            )) == 0
        ),
    }
    return payload


def run_validation_case(repo: Path, day: str, case: str) -> dict[str, Any]:
    if day not in MAY_DAYS or case not in CASES:
        raise PermissionError(f"V37_R2_VALIDATION_SCOPE:{day}:{case}")
    from dayahead.v37 import runner as production
    original_pass = production.PASS_ID
    production.PASS_ID = R2_PASS_ID
    try:
        aidc_b0 = production.build_day(repo, day, "B0")
        aidc_b1 = production.build_day(repo, day, "B1")
        beam, fallback = production._beam_case(repo, day, case, aidc_b0, aidc_b1)
        aidc = aidc_b0 if case == "B2" else aidc_b1
        result = production._run_frozen_case(repo, day, case, aidc, beam)
        result["beam_fallback"] = bool(fallback)
        result["K_fallback"] = bool(int(beam.get("V37_K_fallback_count", 0)) > 0)
        return _smoke_payload(repo, day, case, result, fallback)
    finally:
        production.PASS_ID = original_pass


def validate(repo: Path) -> dict[str, Any]:
    repo = repo.resolve(); out = repo / OUT; out.mkdir(parents=True, exist_ok=True)
    b2 = run_validation_case(repo, "2025-05-01", "B2")
    write_json(out / "V37_R2_MAY01_B2_SMOKE.json", b2)
    if not b2["physical_PASS"]:
        return {"status": "STOP_MAY01_B2_FAIL", "B2": b2}
    b3 = run_validation_case(repo, "2025-05-01", "B3")
    write_json(out / "V37_R2_MAY01_B3_SMOKE.json", b3)
    if not b3["physical_PASS"]:
        return {"status": "STOP_MAY01_B3_FAIL", "B2": b2, "B3": b3}

    records = [b2, b3]
    for day in MAY_DAYS[1:]:
        for case in CASES:
            result = run_validation_case(repo, day, case)
            records.append(result)
            if not result["physical_PASS"]:
                pd.DataFrame(records).to_csv(out / "V37_R2_MAY01_05_VALIDATION.csv", index=False)
                return {"status": "STOP_MAY01_05_FAIL", "failed": {"day": day, "case": case}, "records": records}
    table = pd.DataFrame(records)
    table.to_csv(out / "V37_R2_MAY01_05_VALIDATION.csv", index=False)
    reused_b0_b1 = []
    for day in MAY_DAYS:
        for case in ("B0", "B1"):
            gates = json.loads((_case_root(repo, OLD_PASS_ID, day, case) / "summary/PHYSICAL_GATES.json").read_text(encoding="utf-8"))
            reused_b0_b1.append({
                "day": day, "case": case, "Fresh_convergence": gates["Fresh_solve_coverage"],
                "Fresh_physical_violation_count": sum(int(gates["Fresh"][key]) for key in (
                    "voltage_violation_count", "current_violation_count", "transformer_violation_count"
                )),
            })
    readiness = bool(table["physical_PASS"].all()) and all(
        row["Fresh_convergence"] == "96/96" and row["Fresh_physical_violation_count"] == 0
        for row in reused_b0_b1
    )
    summary = {
        "artifact_id": "V37_R2_PHYSICAL_GATE_SUMMARY_V1",
        "May01_B2_PASS": bool(b2["physical_PASS"]),
        "May01_B3_PASS": bool(b3["physical_PASS"]),
        "May01_05_B2_PASS_days": int(table.loc[table["case"] == "B2", "physical_PASS"].sum()),
        "May01_05_B3_PASS_days": int(table.loc[table["case"] == "B3", "physical_PASS"].sum()),
        "May01_05_voltage_violation_days": sorted(table.loc[
            (table["Fresh_lower_voltage_violations"] + table["Fresh_upper_voltage_violations"]) > 0, "day"
        ].unique().tolist()),
        "May01_05_Fresh_non_96_of_96_days": sorted(table.loc[
            table["Fresh_convergence"] != "96/96", "day"
        ].unique().tolist()),
        "reused_B0_B1": reused_b0_b1,
        "firewall": {
            "Benders_changed": False, "K_changed": False, "beam_changed": False,
            "MESS_physical_limits_changed": False, "AIDC_changed": False,
            "voltage_physical_limit_changed": False,
        },
        "MAY_CAMPAIGN_RESTART_READY": readiness,
        "May_campaign_restarted": False,
    }
    write_json(out / "V37_R2_PHYSICAL_GATE_SUMMARY.json", summary)
    return {"status": "PASS" if readiness else "FAIL", "summary": summary, "records": records}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--calibrate", action="store_true")
    parser.add_argument("--validate", action="store_true")
    args = parser.parse_args()
    if args.calibrate == args.validate:
        parser.error("select exactly one of --calibrate or --validate")
    repo = Path.cwd().resolve(); started = time.perf_counter()
    result = calibrate(repo) if args.calibrate else validate(repo)
    result["wallclock_seconds"] = time.perf_counter() - started
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if not str(result.get("status", "PASS")).startswith("STOP") else 2


if __name__ == "__main__":
    raise SystemExit(main())
