"""Frozen V16.2 authority-semantic Day-Ahead grid-background adapter."""

from __future__ import annotations

import csv
import gzip
import hashlib
import math
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Mapping, Sequence

import numpy as np


P95_REFERENCE_MW = 7100.2615
ANNUAL_MAX_REFERENCE_MW = 9490.53
ALPHA_GRID = 0.7481417265421424
IEEE123_NATIVE_P_KW = 3490.0
IEEE123_NATIVE_Q_KVAR = 1920.0
PV_REFERENCE_MAX_MW = 4021.226
PV_CAPACITY_EXPECTED_KW = 698.000002861023

EXPECTED_SHA256 = {
    "manifest": "7780cc3cd19a7f1dcf8e2d6a35d2872f7742bee200873b69a6c806df557624b5",
    "build_source": "aa81880e956e03a3195a316eae95687088772f5c2171abed7e215e1bab083a82",
    "runtime_adapter": "5637dc95ab3ea62611b278e0b5f1aefe49befd4bf90bafb7a478fe83e0c43036",
    "bus_ids": "7cad8bec82a1efd0bf55f3d566f1f2faff5b2be4bd058d957481a858fac771f4",
    "clusters": "27cbb7e41785d14c79635de662093442561c54162614f14418a6b961f5691f92",
    "pv_capacity": "2d39c325249c12045bed10825bfaa345d708883e6d7eba2954f6c36181464636",
    "residual_lookup": "159242ca2c198954c32a145a1776bf5dbc15eb896666c83dc93a2c444ca5e1ae",
    "q_lookup": "32143c7717e1cf37947d6d390bf7d7b518e7fbd852d719fa456e2b9a054f3e60",
    "pv_reference": "fe1b9c1c35249173edbe488a49d2271888cd745efb1b2bb03e526c3b5a429a97",
    "scale_contract": "5fd67c25b7e3df89a19cba6bcaab348f2e0a3f72f85ac47e34c4b7935307e650",
}


@dataclass(frozen=True)
class BackgroundSourcePaths:
    manifest: Path
    build_source: Path
    runtime_adapter: Path
    bus_ids: Path
    clusters: Path
    pv_capacity: Path
    residual_lookup: Path
    q_lookup: Path
    pv_reference: Path
    scale_contract: Path


@dataclass(frozen=True)
class AuthorityBackgroundBinding:
    net_p_kw_96: tuple[Mapping[tuple[str, str], float], ...]
    gross_q_kvar_96: tuple[Mapping[tuple[str, str], float], ...]
    gross_p_kw_96: tuple[Mapping[tuple[str, str], float], ...]
    pv_generation_kw_96: tuple[Mapping[tuple[str, str], float], ...]
    evidence: Mapping[str, object]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verify_sources(paths: BackgroundSourcePaths) -> dict[str, dict[str, object]]:
    records: dict[str, dict[str, object]] = {}
    for name, expected in EXPECTED_SHA256.items():
        path = getattr(paths, name)
        actual = _sha256(path)
        if actual != expected:
            raise RuntimeError(f"V16_2_BACKGROUND_SOURCE_SHA_MISMATCH:{name}:{actual}")
        records[name] = {"path": str(path.resolve()), "sha256": actual, "status": "PASS"}
    return records


def _lookup(path: Path, key_fields: Sequence[str], value_field: str) -> dict[tuple[object, ...], float]:
    with gzip.open(path, "rt", encoding="utf-8-sig", newline="") as stream:
        rows = csv.DictReader(stream)
        result: dict[tuple[object, ...], float] = {}
        for row in rows:
            key = tuple(
                str(row[field]) if field == "day_type" else int(row[field])
                for field in key_fields
            )
            result[key] = float(row[value_field])
    return result


def _adapter_arrays(adapter: Mapping[str, object], bus_ids: Sequence[str]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    index = {str(bus).lower(): row for row, bus in enumerate(bus_ids)}
    p = np.zeros((len(bus_ids), 3), dtype=float)
    q = np.zeros_like(p)
    pv = np.zeros_like(p)
    for record in adapter["loads"]:  # type: ignore[index,union-attr]
        phases = tuple(map(int, record["phases"]))
        bus = index[str(record["bus"]).lower()]
        for phase in phases:
            p[bus, phase - 1] += float(record["base_p_kw"]) / len(phases)
            q[bus, phase - 1] += float(record["base_q_kvar"]) / len(phases)
    for record in adapter["pv_generators"]:  # type: ignore[index,union-attr]
        bus = index[str(record["bus"]).lower()]
        pv[bus, int(record["phase"]) - 1] += float(record["capacity_kw"])
    return p, q, pv


def _map(bus_ids: Sequence[str], values: np.ndarray) -> dict[tuple[str, str], float]:
    phases = ("A", "B", "C")
    return {
        (str(bus).lower(), phases[phase]): float(values[row, phase])
        for row, bus in enumerate(bus_ids)
        for phase in range(3)
        if abs(float(values[row, phase])) > 0.0
    }


def build_authority_background_binding(
    *,
    timestamps_fixed_aest: Sequence[str],
    demand_mw_96: Sequence[float],
    rooftop_pv_mw_96: Sequence[float],
    paths: BackgroundSourcePaths,
) -> AuthorityBackgroundBinding:
    if not (len(timestamps_fixed_aest) == len(demand_mw_96) == len(rooftop_pv_mw_96) == 96):
        raise ValueError("V16_2_BACKGROUND_DIRECT96_REQUIRED")
    sources = _verify_sources(paths)
    import json

    adapter = json.loads(paths.runtime_adapter.read_text(encoding="utf-8"))
    bus_ids = np.load(paths.bus_ids, allow_pickle=False).astype(str).tolist()
    clusters = np.load(paths.clusters, allow_pickle=False).astype(np.int16)
    pv_capacity = np.load(paths.pv_capacity, allow_pickle=False).astype(float)
    native_p, native_q, adapter_pv = _adapter_arrays(adapter, bus_ids)
    if clusters.shape != (len(bus_ids),) or pv_capacity.shape != native_p.shape:
        raise RuntimeError("V16_2_BACKGROUND_FROZEN_ARRAY_SHAPE_MISMATCH")
    if not np.allclose(pv_capacity, adapter_pv, atol=1e-6, rtol=0.0):
        raise RuntimeError("V16_2_BACKGROUND_PV_MAPPING_MISMATCH")
    if abs(float(native_p.sum()) - IEEE123_NATIVE_P_KW) > 1e-9:
        raise RuntimeError("V16_2_BACKGROUND_NATIVE_P_TOTAL_MISMATCH")
    if abs(float(native_q.sum()) - IEEE123_NATIVE_Q_KVAR) > 1e-9:
        raise RuntimeError("V16_2_BACKGROUND_NATIVE_Q_TOTAL_MISMATCH")
    if abs(float(pv_capacity.sum()) - PV_CAPACITY_EXPECTED_KW) > 1e-9:
        raise RuntimeError("V16_2_BACKGROUND_PV_CAPACITY_TOTAL_MISMATCH")
    residual = _lookup(paths.residual_lookup, ("cluster_id", "month", "day_type", "slot_30min"), "residual")
    q_variation = _lookup(paths.q_lookup, ("month", "day_type", "slot_30min"), "q_variation_factor")
    weighted_qp = float(native_q.sum() / native_p.sum())
    native_qp = np.divide(native_q, native_p, out=np.zeros_like(native_q), where=native_p > 1e-9)
    relative_qp = np.divide(native_qp, weighted_qp, out=np.ones_like(native_qp), where=abs(weighted_qp) > 1e-9)
    relative_qp = np.where(native_p > 0, np.clip(relative_qp, 0.15, 3.0), 0.0)
    gross_rows: list[Mapping[tuple[str, str], float]] = []
    q_rows: list[Mapping[tuple[str, str], float]] = []
    pv_rows: list[Mapping[tuple[str, str], float]] = []
    net_rows: list[Mapping[tuple[str, str], float]] = []
    slot_totals: list[dict[str, float]] = []
    for index, (stamp, demand, rooftop) in enumerate(zip(timestamps_fixed_aest, demand_mw_96, rooftop_pv_mw_96)):
        local = datetime.fromisoformat(str(stamp))
        day_type = "weekday" if local.weekday() < 5 else "weekend"
        slot_30 = local.hour * 2 + local.minute // 30
        operational_pre_alpha = float(demand) * IEEE123_NATIVE_P_KW / P95_REFERENCE_MW
        pv_pre_alpha = float(rooftop) / PV_REFERENCE_MAX_MW * float(pv_capacity.sum())
        gross_pre_alpha = operational_pre_alpha + pv_pre_alpha
        gross_target = ALPHA_GRID * gross_pre_alpha
        pv_target = ALPHA_GRID * pv_pre_alpha
        operational_target = ALPHA_GRID * operational_pre_alpha
        raw = np.empty_like(native_p)
        for bus, cluster in enumerate(clusters):
            raw[bus, :] = native_p[bus, :] * residual[(int(cluster), local.month, day_type, slot_30)]
        gross = raw * (gross_target / float(raw.sum()))
        q_raw = gross * relative_qp
        q_target = gross_target * weighted_qp * q_variation[(local.month, day_type, slot_30)]
        q = q_raw * (q_target / float(q_raw.sum()))
        pv = pv_capacity * (float(rooftop) / PV_REFERENCE_MAX_MW) * ALPHA_GRID
        net = gross - pv
        gross_rows.append(_map(bus_ids, gross))
        q_rows.append(_map(bus_ids, q))
        pv_rows.append(_map(bus_ids, pv))
        net_rows.append(_map(bus_ids, net))
        slot_totals.append({
            "time_index": index,
            "gross_pre_alpha_kw": gross_pre_alpha,
            "gross_after_alpha_kw": gross_target,
            "pv_after_alpha_kw": pv_target,
            "operational_after_alpha_kw": operational_target,
            "gross_mapping_error_kw": float(gross.sum() - gross_target),
            "pv_mapping_error_kw": float(pv.sum() - pv_target),
            "net_identity_error_kw": float(net.sum() - operational_target),
            "q_mapping_error_kvar": float(q.sum() - q_target),
        })
    maxima = {
        key: max(abs(float(row[key])) for row in slot_totals)
        for key in ("gross_mapping_error_kw", "pv_mapping_error_kw", "net_identity_error_kw", "q_mapping_error_kvar")
    }
    if max(maxima.values()) > 1e-8:
        raise RuntimeError(f"V16_2_BACKGROUND_IDENTITY_TOLERANCE_FAIL:{maxima}")
    if not math.isclose(P95_REFERENCE_MW / ANNUAL_MAX_REFERENCE_MW, ALPHA_GRID, abs_tol=1e-15):
        raise RuntimeError("V16_2_ALPHA_GRID_AUTHORITY_MISMATCH")
    return AuthorityBackgroundBinding(
        tuple(net_rows), tuple(q_rows), tuple(gross_rows), tuple(pv_rows),
        {
            "authority_id": "GRID_BACKGROUND_MAPPING_CONTRACT_V16_2_BINDING",
            "status": "PASS",
            "is_native_ieee123_load": "B_SPATIAL_TEMPLATE_REFERENCE_BASIS_ALREADY_INCORPORATED",
            "formula": "gross=alpha_grid*((AEMO_MW*3490/7100.2615)+(PV_MW/4021.226*698.000002861023)); net=gross-PV",
            "alpha_grid": ALPHA_GRID,
            "alpha_grid_application_count": 1,
            "pwc_30_to_15_application_count": 1,
            "native_background_double_count_call_count": 0,
            "mapping_fitting_call_count": 0,
            "pv_capacity_kw": float(pv_capacity.sum()),
            "source_paths_and_sha256": sources,
            "identity_maxima": maxima,
            "slot_totals": slot_totals,
            "may_scientific_loader_access_count": 0,
            "june_scientific_loader_access_count": 0,
        },
    )
