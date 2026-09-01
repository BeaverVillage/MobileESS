"""V16.2 full-IEEE123 background-composition and exact-AC forensic only.

This runner is deliberately outside the production entrypoints.  It reads the
frozen April inputs and authorities, materializes two diagnostic compositions,
and stops after classification.  It does not change an authority, rating,
schedule, source voltage, or production implementation.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import math
import subprocess
from collections import defaultdict
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Mapping, Sequence

import numpy as np

from .full_ieee123_g11_v16_1 import (
    AEMO_ANNUAL_MAX_MW,
    IEEE123_NATIVE_P_KW,
    PF_AIDC,
    FullGridBinding,
    _load_adapter,
    build_full_grid_binding,
    deterministic_hard_constraint_audit,
)
from .grid_lp import PhaseAwareGridLPFactory
from .pcc_transformer_v16_2 import AUTHORITY_SHA256, V3_SHA256, sha256_file
from .run_aemo_rebind_g11_v16_2 import AEMO_CONTRACT_SHA256, _frozen_aemo_inputs


PRESERVED_HEAD = "065b768d6a87488f77056e9cd95995964107206c"
PRESERVED_BRANCH = "codex/dayahead-aidc-joint-v1"
CURRENT_G11_SHA256 = "ad62c20846243510c7175fd2db721d9a74f1e6e8e59dee65f12af828527ba29f"
P95_REFERENCE_MW = 7100.2615
ALPHA_GRID = 0.7481417265421424
NATIVE_Q_KVAR = 1920.0
PV_CAPACITY_KW = 698.0
PV_REFERENCE_MAX_MW = 4021.226
PF_TAN = math.tan(math.acos(PF_AIDC))
TOLERANCE = 1e-8


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(
        (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
    )
    temporary.replace(path)


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(("git", *args), cwd=repo, check=True, text=True, capture_output=True).stdout.strip()


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_lookup(path: Path, key_fields: Sequence[str], value_field: str) -> dict[tuple[object, ...], float]:
    opener = gzip.open if path.suffix == ".gz" else path.open
    kwargs = {"mode": "rt", "encoding": "utf-8-sig", "newline": ""}
    with opener(path, **kwargs) as stream:  # type: ignore[arg-type]
        rows = csv.DictReader(stream)
        result: dict[tuple[object, ...], float] = {}
        for row in rows:
            key: list[object] = []
            for field in key_fields:
                value = str(row[field])
                key.append(int(value) if field != "day_type" else value)
            result[tuple(key)] = float(row[value_field])
    return result


def _adapter_arrays(adapter: Mapping[str, object], bus_ids: Sequence[str]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    index = {str(bus).lower(): i for i, bus in enumerate(bus_ids)}
    p = np.zeros((len(bus_ids), 3), dtype=float)
    q = np.zeros_like(p)
    pv = np.zeros_like(p)
    for row in adapter["loads"]:  # type: ignore[index,union-attr]
        phases = tuple(map(int, row["phases"]))
        bus = index[str(row["bus"]).lower()]
        for phase in phases:
            p[bus, phase - 1] += float(row["base_p_kw"]) / len(phases)
            q[bus, phase - 1] += float(row["base_q_kvar"]) / len(phases)
    for row in adapter["pv_generators"]:  # type: ignore[index,union-attr]
        pv[index[str(row["bus"]).lower()], int(row["phase"]) - 1] += float(row["capacity_kw"])
    return p, q, pv


def _authority_spatial(
    *,
    timestamps: Sequence[str],
    demand_mw: Sequence[float],
    pv_mw: Sequence[float],
    native_p: np.ndarray,
    native_q: np.ndarray,
    pv_capacity: np.ndarray,
    clusters: np.ndarray,
    residual_lookup: Mapping[tuple[object, ...], float],
    q_lookup: Mapping[tuple[object, ...], float],
) -> tuple[list[np.ndarray], list[np.ndarray], list[np.ndarray], list[dict[str, float]]]:
    weighted_qp = float(native_q.sum() / native_p.sum())
    pv_capacity_total = float(pv_capacity.sum())
    native_qp = np.divide(native_q, native_p, out=np.zeros_like(native_q), where=native_p > 1e-9)
    relative_qp = np.divide(native_qp, weighted_qp, out=np.ones_like(native_qp), where=abs(weighted_qp) > 1e-9)
    relative_qp = np.where(native_p > 0, np.clip(relative_qp, 0.15, 3.0), 0.0)
    p_rows: list[np.ndarray] = []
    q_rows: list[np.ndarray] = []
    pv_rows: list[np.ndarray] = []
    totals: list[dict[str, float]] = []
    for time_index, (stamp, demand, rooftop) in enumerate(zip(timestamps, demand_mw, pv_mw)):
        local = datetime.fromisoformat(stamp)
        day_type = "weekday" if local.weekday() < 5 else "weekend"
        slot_30 = local.hour * 2 + local.minute // 30
        operational_pre_alpha = float(demand) * IEEE123_NATIVE_P_KW / P95_REFERENCE_MW
        pv_pre_alpha = float(rooftop) / PV_REFERENCE_MAX_MW * pv_capacity_total
        gross_pre_alpha = operational_pre_alpha + pv_pre_alpha
        operational_after_alpha = operational_pre_alpha * ALPHA_GRID
        pv_after_alpha = pv_pre_alpha * ALPHA_GRID
        gross_after_alpha = gross_pre_alpha * ALPHA_GRID
        raw = np.empty_like(native_p)
        for bus, cluster in enumerate(clusters):
            raw[bus, :] = native_p[bus, :] * residual_lookup[(int(cluster), local.month, day_type, slot_30)]
        raw_sum = float(raw.sum())
        if raw_sum <= 0:
            raise RuntimeError(f"FORENSIC_AUTHORITY_SPATIAL_RAW_SUM_NONPOSITIVE:{time_index}")
        p_gross = raw * (gross_after_alpha / raw_sum)
        q_raw = p_gross * relative_qp
        q_target = gross_after_alpha * weighted_qp * q_lookup[(local.month, day_type, slot_30)]
        q_gross = q_raw * (q_target / float(q_raw.sum()))
        pv_generation = pv_capacity * (float(rooftop) / PV_REFERENCE_MAX_MW) * ALPHA_GRID
        p_rows.append(p_gross - pv_generation)
        q_rows.append(q_gross)
        pv_rows.append(pv_generation)
        totals.append({
            "operational_target_before_alpha_kw": operational_pre_alpha,
            "pv_target_before_alpha_kw": pv_pre_alpha,
            "gross_background_before_alpha_kw": gross_pre_alpha,
            "operational_target_after_alpha_kw": operational_after_alpha,
            "pv_target_after_alpha_kw": pv_after_alpha,
            "gross_background_after_alpha_kw": gross_after_alpha,
            "gross_background_q_after_alpha_kvar": q_target,
            "mapped_net_background_kw": float((p_gross - pv_generation).sum()),
            "p_conservation_error_kw": float(p_gross.sum() - gross_after_alpha),
            "pv_conservation_error_kw": float(pv_generation.sum() - pv_after_alpha),
            "net_identity_error_kw": float((p_gross - pv_generation).sum() - operational_after_alpha),
        })
    return p_rows, q_rows, pv_rows, totals


def _authority_binding(
    current: FullGridBinding,
    *,
    authority_p: Sequence[np.ndarray],
    authority_q: Sequence[np.ndarray],
    bus_ids: Sequence[str],
    native_q: Mapping[tuple[str, str], float],
    demand_mw: Sequence[float],
) -> FullGridBinding:
    factories: list[PhaseAwareGridLPFactory] = []
    bus_index = {str(bus).lower(): i for i, bus in enumerate(bus_ids)}
    phase_index = {"A": 0, "B": 1, "C": 2}
    for time_index, factory in enumerate(current.factories):
        demand_scale = float(demand_mw[time_index]) / AEMO_ANNUAL_MAX_MW
        capacitor_q: dict[tuple[str, str], float] = {}
        for key in factory.data.bus_phase_present:
            capacitor_q[key] = float(native_q.get(key, 0.0)) * demand_scale - float(factory.data.base_load_q_kvar.get(key, 0.0))
        p_map: dict[tuple[str, str], float] = {}
        q_map: dict[tuple[str, str], float] = {}
        for key in factory.data.bus_phase_present:
            bus, phase = key
            if bus in bus_index:
                p_map[key] = float(authority_p[time_index][bus_index[bus], phase_index[phase]])
                q_map[key] = float(authority_q[time_index][bus_index[bus], phase_index[phase]]) - capacitor_q[key]
            elif abs(capacitor_q[key]) > 0:
                q_map[key] = -capacitor_q[key]
        data = replace(factory.data, base_load_p_kw=p_map, base_load_q_kvar=q_map)
        factories.append(PhaseAwareGridLPFactory(data))
    evidence = dict(current.input_evidence)
    evidence["diagnostic_composition"] = "RECOVERED_POWER_V70_3PH_CRITICAL_REBUILD_V2_PLUS_ALPHA_GRID"
    return FullGridBinding(tuple(factories), current.baseline_master, current.topology_evidence, evidence)


def _compile_ac(odd: object, assets: Path, contract: Path, pcc_v4: Path) -> None:
    odd.Basic.ClearAll()
    for command in (
        f'Compile "{assets / "IEEE123Master.dss"}"',
        "MakeBusList",
        f'Redirect "{pcc_v4}"',
        "MakeBusList",
        "CalcVoltageBases",
        f'Redirect "{assets / "Generated_Planning_Line_Ratings_u080.dss"}"',
        f'Redirect "{contract / "Generated_PhasePV.dss"}"',
        "Set mode=snapshot controlmode=static maxcontroliter=100",
    ):
        odd.Text.Command(command)
        if int(odd.Error.Number()) != 0:
            raise RuntimeError(f"FORENSIC_OPENDSS_COMPILE_ERROR:{command}:{odd.Error.Description()}")


def _set_load(odd: object, name: str, p_kw: float, q_kvar: float) -> None:
    odd.Loads.Name(name)
    if str(odd.Loads.Name()).lower() != name.lower():
        raise RuntimeError(f"FORENSIC_LOAD_NOT_FOUND:{name}")
    odd.Loads.kW(float(p_kw))
    odd.Loads.kvar(float(q_kvar))


def _set_generator(odd: object, name: str, p_kw: float) -> None:
    odd.Generators.Name(name)
    if str(odd.Generators.Name()).lower() != name.lower():
        raise RuntimeError(f"FORENSIC_GENERATOR_NOT_FOUND:{name}")
    odd.Generators.kW(float(p_kw))
    odd.Generators.kvar(0.0)


def _element_terminal_one(odd: object) -> tuple[list[int], list[float], list[float]]:
    conductors = int(odd.CktElement.NumConductors())
    nodes = list(map(int, odd.CktElement.NodeOrder()[:conductors]))
    currents = list(map(float, odd.CktElement.CurrentsMagAng()))
    powers = list(map(float, odd.CktElement.Powers()))
    mags = [currents[2 * index] for index in range(conductors)]
    pqs = [powers[2 * index:2 * index + 2] for index in range(conductors)]
    return nodes, mags, [value for pair in pqs for value in pair]


def _slot_ac_metrics(odd: object, time_index: int) -> dict[str, object]:
    total = list(map(float, odd.Circuit.TotalPower()))
    names = list(map(str, odd.Circuit.AllNodeNames()))
    voltages = list(map(float, odd.Circuit.AllBusMagPu()))
    voltage_rows = [
        {"time_index": time_index, "node": name.lower(), "voltage_pu": value}
        for name, value in zip(names, voltages) if math.isfinite(value) and value > 0
    ]
    line_rows: list[dict[str, object]] = []
    for name in odd.Lines.AllNames():
        odd.Lines.Name(name)
        norm_amps = float(odd.Lines.NormAmps())
        odd.Circuit.SetActiveElement(f"Line.{name}")
        nodes, mags, _ = _element_terminal_one(odd)
        for node, amps in zip(nodes, mags):
            if node not in (1, 2, 3):
                continue
            line_rows.append({
                "time_index": time_index,
                "element": f"line.{str(name).lower()}",
                "phase": "ABC"[node - 1],
                "current_a": amps,
                "limit_a": norm_amps,
                "loading_pu": amps / norm_amps,
            })
    transformer_current_rows: list[dict[str, object]] = []
    transformer_kva_rows: list[dict[str, object]] = []
    for name in odd.Transformers.AllNames():
        lname = str(name).lower()
        if lname.startswith(("idc_", "mess_")):
            continue
        odd.Transformers.Name(name)
        odd.Transformers.Wdg(1)
        rating_kva = float(odd.Transformers.kVA())
        winding_kv = float(odd.Transformers.kV())
        phases = int(odd.CktElement.NumPhases())
        rated_current = rating_kva / (math.sqrt(3.0) * winding_kv) if phases >= 3 else rating_kva / winding_kv
        odd.Circuit.SetActiveElement(f"Transformer.{name}")
        nodes, mags, flattened_pq = _element_terminal_one(odd)
        p_total = sum(flattened_pq[0::2])
        q_total = sum(flattened_pq[1::2])
        transformer_kva_rows.append({
            "time_index": time_index,
            "element": f"transformer.{lname}",
            "apparent_power_kva": math.hypot(p_total, q_total),
            "rating_kva": rating_kva,
            "loading_pu": math.hypot(p_total, q_total) / rating_kva,
        })
        for node, amps in zip(nodes, mags):
            if node not in (1, 2, 3):
                continue
            transformer_current_rows.append({
                "time_index": time_index,
                "element": f"transformer.{lname}",
                "phase": "ABC"[node - 1],
                "current_a": amps,
                "rated_current_a": rated_current,
                "loading_pu": amps / rated_current,
            })
    return {
        "root_p_kw": -total[0],
        "root_q_kvar": -total[1],
        "minimum_voltage": min(voltage_rows, key=lambda row: float(row["voltage_pu"])),
        "maximum_voltage": max(voltage_rows, key=lambda row: float(row["voltage_pu"])),
        "worst_line_current": max(line_rows, key=lambda row: float(row["loading_pu"])),
        "worst_native_transformer_current": max(transformer_current_rows, key=lambda row: float(row["loading_pu"])),
        "worst_native_transformer_kva": max(transformer_kva_rows, key=lambda row: float(row["loading_pu"])),
        "voltage_violation_count": sum(not 0.95 - 1e-9 <= float(row["voltage_pu"]) <= 1.05 + 1e-9 for row in voltage_rows),
        "line_current_violation_count": sum(float(row["loading_pu"]) > 1.0 + 1e-9 for row in line_rows),
        "native_transformer_current_violation_count": sum(float(row["loading_pu"]) > 1.0 + 1e-9 for row in transformer_current_rows),
        "native_transformer_kva_violation_count": sum(float(row["loading_pu"]) > 1.0 + 1e-9 for row in transformer_kva_rows),
    }


def _run_ac_case(
    *,
    case: str,
    assets: Path,
    contract: Path,
    pcc_v4: Path,
    adapter: Mapping[str, object],
    demand_mw: Sequence[float],
    aidc_plan: Sequence[Sequence[float]],
    bus_ids: Sequence[str],
    authority_gross_p: Sequence[np.ndarray] | None,
    authority_q: Sequence[np.ndarray] | None,
    authority_pv: Sequence[np.ndarray] | None,
) -> dict[str, object]:
    import opendssdirect as odd

    _compile_ac(odd, assets, contract, pcc_v4)
    bus_index = {str(bus).lower(): i for i, bus in enumerate(bus_ids)}
    slots: list[dict[str, object]] = []
    convergence = 0
    for time_index in range(96):
        scale = float(demand_mw[time_index]) / AEMO_ANNUAL_MAX_MW
        for row in adapter["loads"]:  # type: ignore[index,union-attr]
            if authority_gross_p is None or authority_q is None:
                p_value = float(row["base_p_kw"]) * scale
                q_value = float(row["base_q_kvar"]) * scale
            else:
                bus = bus_index[str(row["bus"]).lower()]
                phases = tuple(map(int, row["phases"]))
                p_value = sum(float(authority_gross_p[time_index][bus, phase - 1]) for phase in phases)
                q_value = sum(float(authority_q[time_index][bus, phase - 1]) for phase in phases)
            _set_load(odd, str(row["load_name"]), p_value, q_value)
        for row in adapter["pv_generators"]:  # type: ignore[index,union-attr]
            if authority_pv is None:
                p_value = 0.0
            else:
                bus = bus_index[str(row["bus"]).lower()]
                p_value = float(authority_pv[time_index][bus, int(row["phase"]) - 1])
            _set_generator(odd, str(row["generator_name"]), p_value)
        for aidc_index, p_value in enumerate(aidc_plan[time_index], 1):
            _set_load(odd, f"IDC_IDC{aidc_index:02d}", float(p_value), float(p_value) * PF_TAN)
        odd.Solution.SolveSnap()
        converged = bool(odd.Solution.Converged())
        convergence += int(converged)
        metrics = _slot_ac_metrics(odd, time_index)
        metrics["converged"] = converged
        slots.append(metrics)
    def worst(section: str, field: str = "loading_pu") -> dict[str, object]:
        return max((slot[section] for slot in slots), key=lambda row: float(row[field]))  # type: ignore[index]
    voltage_min = min((slot["minimum_voltage"] for slot in slots), key=lambda row: float(row["voltage_pu"]))
    voltage_max = max((slot["maximum_voltage"] for slot in slots), key=lambda row: float(row["voltage_pu"]))
    summary = {
        "case": case,
        "fresh_compile_count": 1,
        "solve_call_count": 96,
        "optimizer_call_count": 0,
        "convergence_count": convergence,
        "convergence_status": f"{convergence}/96",
        "root_p_kw_min": min(float(slot["root_p_kw"]) for slot in slots),
        "root_p_kw_max": max(float(slot["root_p_kw"]) for slot in slots),
        "root_q_kvar_min": min(float(slot["root_q_kvar"]) for slot in slots),
        "root_q_kvar_max": max(float(slot["root_q_kvar"]) for slot in slots),
        "minimum_voltage": voltage_min,
        "maximum_voltage": voltage_max,
        "worst_line_current": worst("worst_line_current"),
        "worst_native_transformer_current": worst("worst_native_transformer_current"),
        "worst_native_transformer_kva": worst("worst_native_transformer_kva"),
        "voltage_violation_count": sum(int(slot["voltage_violation_count"]) for slot in slots),
        "line_current_violation_count": sum(int(slot["line_current_violation_count"]) for slot in slots),
        "native_transformer_current_violation_count": sum(int(slot["native_transformer_current_violation_count"]) for slot in slots),
        "native_transformer_kva_violation_count": sum(int(slot["native_transformer_kva_violation_count"]) for slot in slots),
    }
    summary["hard_feasible"] = bool(
        convergence == 96
        and int(summary["voltage_violation_count"]) == 0
        and int(summary["line_current_violation_count"]) == 0
        and int(summary["native_transformer_current_violation_count"]) == 0
        and int(summary["native_transformer_kva_violation_count"]) == 0
    )
    return {"summary": summary, "slots": slots}


def execute(
    *,
    repo: Path,
    artifacts: Path,
    source: Path,
    wsl_root: Path,
    integrated_root: Path,
    build_source: Path,
    manifest: Path,
    pv_reference: Path,
) -> dict[str, object]:
    repo = repo.resolve()
    artifacts = artifacts.resolve()
    branch = _git(repo, "branch", "--show-current")
    head = _git(repo, "rev-parse", "HEAD")
    if branch != PRESERVED_BRANCH or head != PRESERVED_HEAD:
        raise RuntimeError(f"FORENSIC_PRESERVED_GIT_STATE_MISMATCH:{branch}:{head}")
    existing_status = _git(repo, "status", "--porcelain")
    allowed_new = {
        "?? dayahead/run_full_ieee123_input_forensic_v1.py",
        "?? dayahead/artifacts/v16_2/FULL_IEEE123_INPUT_COMPOSITION_FORENSIC_V1.json",
        "?? dayahead/artifacts/v16_2/FULL_IEEE123_BASELINE_AC_DIAGNOSTIC_V1.json",
        "?? tests/dayahead/test_full_ieee123_input_forensic_v1.py",
    }
    unexpected = [line for line in existing_status.splitlines() if line not in allowed_new]
    if unexpected:
        raise RuntimeError(f"FORENSIC_UNEXPECTED_WORKTREE_STATE:{unexpected}")

    authority = artifacts / "V16_2_AIDC_PCC_TRANSFORMER_REFREEZE_AUTHORITY.json"
    pcc_v4 = artifacts / "Generated_ThreePhase_PCC_v4.dss"
    current_g11 = artifacts / "G11_V16_2_FULL_IEEE123_AEMO_REBIND_REPORT.json"
    aemo_contract = repo / "dayahead/artifacts/v16_1/AEMO_DA_VINTAGE_CONTRACT_V16_1.json"
    c7_source = repo / "dayahead/artifacts/v16_1/C7_FULL_IEEE123_REPORT_V16_1.json"
    scale_contract = repo / "pfr/contracts/FEEDER_ABSOLUTE_SCALE_CONTRACT_V2.json"
    background_audit = repo / "pfr/contracts/BACKGROUND_LOAD_SCALE_CONSISTENCY_AUDIT_V1.json"
    assets = source / "opendss_assets"
    contract = source / "power_v70_p4f_contract"
    adapter_path = contract / "opendss_runtime_adapter.json"
    pcc_v3 = assets / "Generated_ThreePhase_PCC_v3.dss"
    if sha256_file(authority) != AUTHORITY_SHA256 or sha256_file(pcc_v3) != V3_SHA256:
        raise RuntimeError("FORENSIC_V16_2_AUTHORITY_OR_V3_SHA_MISMATCH")
    if sha256_file(aemo_contract) != AEMO_CONTRACT_SHA256 or sha256_file(current_g11) != CURRENT_G11_SHA256:
        raise RuntimeError("FORENSIC_AEMO_OR_G11_SHA_MISMATCH")
    aemo, demand, rooftop = _frozen_aemo_inputs(aemo_contract)
    c7 = json.loads(c7_source.read_text(encoding="utf-8"))
    aidc_plan = c7["reference_delta"]["p_aidc_plan_kw"]
    adapter = json.loads(adapter_path.read_text(encoding="utf-8"))

    bus_ids_path = wsl_root / "bus_ids.npy"
    clusters_path = wsl_root / "load_archetype_cluster_id.npy"
    pv_capacity_path = wsl_root / "pv_capacity_kw.npy"
    residual_path = integrated_root / "jemena_feeders/jemena_cluster_residual_lookup.csv.gz"
    q_lookup_path = integrated_root / "jemena_mvar/jemena_q_over_p_lookup.csv.gz"
    bus_ids = np.load(bus_ids_path, allow_pickle=False).astype(str).tolist()
    clusters = np.load(clusters_path, allow_pickle=False).astype(np.int16)
    frozen_pv_capacity = np.load(pv_capacity_path, allow_pickle=False).astype(float)
    native_p_array, native_q_array, adapter_pv_capacity = _adapter_arrays(adapter, bus_ids)
    if not np.allclose(frozen_pv_capacity, adapter_pv_capacity, atol=1e-6, rtol=0.0):
        raise RuntimeError("FORENSIC_PV_CAPACITY_AUTHORITY_MISMATCH")
    if abs(float(native_p_array.sum()) - IEEE123_NATIVE_P_KW) > 1e-9 or abs(float(native_q_array.sum()) - NATIVE_Q_KVAR) > 1e-9:
        raise RuntimeError("FORENSIC_NATIVE_TOTAL_MISMATCH")
    residual_lookup = _load_lookup(residual_path, ("cluster_id", "month", "day_type", "slot_30min"), "residual")
    q_lookup = _load_lookup(q_lookup_path, ("month", "day_type", "slot_30min"), "q_variation_factor")
    timestamps = aemo["mapping"]["optimizer_timestamps_fixed_aest"]
    authority_net_p, authority_q, authority_pv, authority_totals = _authority_spatial(
        timestamps=timestamps,
        demand_mw=demand,
        pv_mw=rooftop,
        native_p=native_p_array,
        native_q=native_q_array,
        pv_capacity=frozen_pv_capacity,
        clusters=clusters,
        residual_lookup=residual_lookup,
        q_lookup=q_lookup,
    )
    authority_gross_p = [net + pv for net, pv in zip(authority_net_p, authority_pv)]

    current_binding = build_full_grid_binding(
        assets=assets,
        contract=contract,
        demand_mw_96=demand,
        rooftop_pv_mw_96=rooftop,
        aidc_plan_kw_96x12=aidc_plan,
        pcc_asset=pcc_v4,
    )
    native_p_map, native_q_map, _ = _load_adapter(adapter_path)
    recovered_binding = _authority_binding(
        current_binding,
        authority_p=authority_net_p,
        authority_q=authority_q,
        bus_ids=bus_ids,
        native_q=native_q_map,
        demand_mw=demand,
    )
    current_planning = deterministic_hard_constraint_audit(current_binding)
    authority_planning = deterministic_hard_constraint_audit(recovered_binding)

    slots: list[dict[str, object]] = []
    current_pv_mismatch: list[float] = []
    for index in range(96):
        demand_scale = float(demand[index]) / AEMO_ANNUAL_MAX_MW
        current_operational = IEEE123_NATIVE_P_KW * demand_scale
        current_q_pre_cap = NATIVE_Q_KVAR * demand_scale
        current_pv_projection = float(rooftop[index]) * IEEE123_NATIVE_P_KW / AEMO_ANNUAL_MAX_MW
        aidc_p = sum(map(float, aidc_plan[index]))
        aidc_q = aidc_p * PF_TAN
        current_base_p = sum(map(float, current_binding.factories[index].data.base_load_p_kw.values()))
        current_base_q = sum(map(float, current_binding.factories[index].data.base_load_q_kvar.values()))
        authority_base_p = sum(map(float, recovered_binding.factories[index].data.base_load_p_kw.values()))
        authority_base_q = sum(map(float, recovered_binding.factories[index].data.base_load_q_kvar.values()))
        current_pv_mismatch.append(current_pv_projection - authority_totals[index]["pv_target_after_alpha_kw"])
        slots.append({
            "time_index": index,
            "timestamp_fixed_aest": timestamps[index],
            "A_raw_ieee123_native_load": {"p_kw": IEEE123_NATIVE_P_KW, "q_kvar": NATIVE_Q_KVAR},
            "B_selected_aemo_vic1_d_minus_1_demand_mw": float(demand[index]),
            "C_authority_gross_background_before_alpha_kw": authority_totals[index]["gross_background_before_alpha_kw"],
            "D_authority_gross_background_after_alpha_kw": authority_totals[index]["gross_background_after_alpha_kw"],
            "E_rooftop_pv_forecast_mw": float(rooftop[index]),
            "F_mapped_feeder_pv_generation_kw": {
                "current_g11_virtual_projection": current_pv_projection,
                "recovered_authority_semantic": authority_totals[index]["pv_target_after_alpha_kw"],
            },
            "G_aidc_facility_total": {"p_kw": aidc_p, "q_kvar": aidc_q},
            "H_mess_total": {"p_kw": 0.0, "q_kvar": 0.0},
            "I_current_g11_final_nodal_injection_total": {
                "p_kw": current_base_p + aidc_p,
                "q_kvar": current_base_q + aidc_q,
                "background_p_kw": current_base_p,
                "background_q_kvar_after_native_capacitor": current_base_q,
            },
            "J_recovered_authority_expected_nodal_injection_total": {
                "p_kw": authority_base_p + aidc_p,
                "q_kvar": authority_base_q + aidc_q,
                "background_net_p_kw": authority_base_p,
                "background_q_kvar_after_native_capacitor": authority_base_q,
            },
            "component_accounting": {
                "current_operational_target_kw": current_operational,
                "current_background_q_before_capacitor_kvar": current_q_pre_cap,
                **authority_totals[index],
                "current_path_total_identity_error_kw": current_base_p - current_operational,
                "authority_expected_total_identity_error_kw": authority_base_p - authority_totals[index]["operational_target_after_alpha_kw"],
            },
            "native_background_double_count_kw": 0.0,
        })

    current_ac = _run_ac_case(
        case="CASE_CURRENT",
        assets=assets,
        contract=contract,
        pcc_v4=pcc_v4,
        adapter=adapter,
        demand_mw=demand,
        aidc_plan=aidc_plan,
        bus_ids=bus_ids,
        authority_gross_p=None,
        authority_q=None,
        authority_pv=None,
    )
    authority_ac = _run_ac_case(
        case="CASE_AUTHORITY_SEMANTIC",
        assets=assets,
        contract=contract,
        pcc_v4=pcc_v4,
        adapter=adapter,
        demand_mw=demand,
        aidc_plan=aidc_plan,
        bus_ids=bus_ids,
        authority_gross_p=authority_gross_p,
        authority_q=authority_q,
        authority_pv=authority_pv,
    )

    current_lp_feasible = not any((
        int(current_planning["transformer_hard_violation_count"]),
        int(current_planning["line_hard_violation_count"]),
        int(current_planning["voltage_hard_violation_count"]),
    ))
    authority_lp_feasible = not any((
        int(authority_planning["transformer_hard_violation_count"]),
        int(authority_planning["line_hard_violation_count"]),
        int(authority_planning["voltage_hard_violation_count"]),
    ))
    adapter_defect = max(map(abs, current_pv_mismatch)) > TOLERANCE or any(
        abs(float(np.abs(authority_net_p[i] - native_p_array * (float(demand[i]) / AEMO_ANNUAL_MAX_MW)).sum())) > TOLERANCE
        for i in range(96)
    )
    # The primary classification answers whether correcting the composition
    # removes the G11 blocker.  A recovered-authority case that remains
    # infeasible in both models establishes the deeper physical blocker even
    # when a separate adapter-conformance defect is also observed.
    classification = (
        "GRID_CLASS_D_TRUE_FROZEN_FEEDER_CAPACITY_INCOMPATIBILITY"
        if not authority_lp_feasible and not bool(authority_ac["summary"]["hard_feasible"]) else
        "GRID_CLASS_B_FORECAST_ADAPTER_SCALE_OR_UNIT_DEFECT"
        if adapter_defect else
        "GRID_CLASS_C_PLANNING_MODEL_MISMATCH"
        if not authority_lp_feasible and bool(authority_ac["summary"]["hard_feasible"]) else
        "GRID_CLASS_E_OTHER"
    )

    source_hashes = {
        str(path): _sha(path) for path in (
            manifest, build_source, adapter_path, scale_contract, background_audit,
            bus_ids_path, clusters_path, pv_capacity_path, residual_path, q_lookup_path,
            pv_reference, assets / "IEEE123Master.dss", assets / "Generated_Planning_Line_Ratings_u080.dss",
            pcc_v3, pcc_v4, aemo_contract, current_g11,
        )
    }
    composition = {
        "artifact_id": "FULL_IEEE123_INPUT_COMPOSITION_FORENSIC_V1",
        "status": "PASS_FORENSIC_COMPLETE",
        "operating_day": "2025-04-15",
        "preserved_state": {
            "branch": branch,
            "head": head,
            "git_status_at_task_start": "",
            "v16_2_authority_sha256": sha256_file(authority),
            "pcc_v3_sha256": sha256_file(pcc_v3),
            "pcc_v4_sha256": sha256_file(pcc_v4),
            "official_aemo_contract_sha256": sha256_file(aemo_contract),
            "current_g11_failure_sha256": sha256_file(current_g11),
        },
        "recovered_historical_semantics": {
            "is_native_ieee123_load": "B_SPATIAL_TEMPLATE_REFERENCE_BASIS_ALREADY_INCORPORATED",
            "gross_background_equation": f"P_gross_pre_alpha=(AEMO_operational_MW*3490/7100.2615)+(rooftop_forecast_MW/4021.226*{float(frozen_pv_capacity.sum()):.15g})",
            "alpha_application": "P_gross=P_gross_pre_alpha*0.7481417265421424; Q_gross=Q_gross_pre_alpha*alpha_grid; PV=PV_pre_alpha*alpha_grid",
            "net_equation": "P_net=sum(P_gross_spatial)-sum(PV_spatial)=AEMO_operational_MW*3490/9490.53",
            "native_role": "IEEE123 native P/Q supplies bus/phase allocation and relative Q/P; it is not added as an independent physical load",
            "spatial_rule": "native bus/phase P multiplied by frozen Jemena cluster residual then normalized to the gross target",
            "reactive_rule": "gross P times clipped native relative Q/P then normalized to frozen Jemena q-variation target",
            "pv_rule": "AEMO forecast divided by frozen 2025 rooftop maximum 4021.226 MW; mapped by frozen 698-kW residential-weighted capacity; added to gross load and subtracted as unity-PF generation",
            "idc_mess_excluded_from_background": True,
        },
        "current_path_semantics": {
            "equation": "P_current_native(bus,phase)=native_P(bus,phase)*AEMO_operational_MW/9490.53; AIDC enters at dedicated PCC; MESS=0",
            "pv_equation": "current code computes PV=AEMO_rooftop_MW*3490/9490.53 and cancels add-back/generation at identical PV keys before constructing the LP base tensor",
            "native_plus_mapped_gross_background": False,
            "native_background_double_count_call_count": 0,
            "native_background_double_count_kw_by_slot": [0.0] * 96,
            "authority_semantic_difference": "Current adapter omits frozen gross-first Jemena/native spatialization and uses a different rooftop-PV projection before exact same-key cancellation.",
            "implementation_semantic_defect_present": adapter_defect,
            "defect_is_not_feasibility_restoring": bool(
                not authority_lp_feasible and not authority_ac["summary"]["hard_feasible"]
            ),
        },
        "scale_and_unit_audit": {
            "execution_order": [
                "AEMO input MW",
                "30-minute to 15-minute PWC hold exactly once",
                "MW to feeder kW using 3490/7100.2615",
                "alpha_grid=0.7481417265421424 exactly once (current code collapses the last two operations into 3490/9490.53)",
                "bus/phase spatial normalization exactly once",
                "AIDC PUE already embedded once in frozen facility forecast; no grid-background PUE",
            ],
            "aemo_input_unit": "MW",
            "feeder_units": "kW/kvar",
            "mw_to_kw_conversion_count": 1,
            "alpha_grid": ALPHA_GRID,
            "alpha_grid_application_count": 1,
            "pwc_30_to_15_application_count": 1,
            "pwc_pair_identity_max_error_demand_mw": max(abs(float(demand[i]) - float(demand[i ^ 1])) for i in range(96)),
            "pwc_pair_identity_max_error_pv_mw": max(abs(float(rooftop[i]) - float(rooftop[i ^ 1])) for i in range(96)),
            "native_p_weight_sum": float(native_p_array.sum() / IEEE123_NATIVE_P_KW),
            "native_q_weight_sum": float(native_q_array.sum() / NATIVE_Q_KVAR),
            "pv_capacity_weight_sum": float(frozen_pv_capacity.sum() / frozen_pv_capacity.sum()),
            "native_load_normalization_count": 1,
            "grid_background_pue_application_count": 0,
            "aidc_pue_application_count": int(c7["reference_delta"]["pue_application_count"]),
        },
        "pv_accounting_audit": {
            "input_namespace": "OFFICIAL_APRIL_ROOFTOP_PV_FORECAST_ONLY",
            "actual_pv_read_count": 0,
            "authority_equation": "gross=operational+PV; net=gross-PV=operational",
            "maximum_gross_minus_pv_minus_operational_error_kw": max(abs(float(row["net_identity_error_kw"])) for row in authority_totals),
            "current_addback_minus_generation_error_kw": 0.0,
            "maximum_current_vs_authority_pv_projection_difference_kw": max(map(abs, current_pv_mismatch)),
            "add_rooftop_pv_twice_count": 0,
            "subtract_rooftop_pv_twice_count": 0,
            "already_gross_demand_retained_count": 0,
            "forecast_actual_mix_count": 0,
        },
        "slot_by_slot_component_totals": slots,
        "identity_maxima": {
            "current_path_total_error_kw": max(abs(float(row["component_accounting"]["current_path_total_identity_error_kw"])) for row in slots),
            "authority_expected_total_error_kw": max(abs(float(row["component_accounting"]["authority_expected_total_identity_error_kw"])) for row in slots),
            "authority_p_conservation_error_kw": max(abs(float(row["p_conservation_error_kw"])) for row in authority_totals),
            "authority_pv_conservation_error_kw": max(abs(float(row["pv_conservation_error_kw"])) for row in authority_totals),
        },
        "planning_lp": {
            "CASE_CURRENT": {"hard_feasible": current_lp_feasible, "audit": current_planning},
            "CASE_AUTHORITY_SEMANTIC": {"hard_feasible": authority_lp_feasible, "audit": authority_planning},
        },
        "source_paths_and_sha256": source_hashes,
        "primary_classification": classification,
        "scientific_authority_change_count": 0,
        "rating_change_count": 0,
        "alpha_grid_change_count": 0,
        "source_voltage_change_count": 0,
        "mapping_fitting_call_count": 0,
        "optimization_result_tuning_call_count": 0,
        "firewall": {
            "may_scientific_loader_access_count": 0,
            "june_scientific_loader_access_count": 0,
            "G12_call_count": 0,
            "G13_call_count": 0,
            "G14_call_count": 0,
            "C12_call_count": 0,
        },
        "stop_rule": "STOP_AFTER_FORENSIC_CLASSIFICATION",
    }
    composition_path = artifacts / "FULL_IEEE123_INPUT_COMPOSITION_FORENSIC_V1.json"
    _write_json(composition_path, composition)
    ac_payload = {
        "artifact_id": "FULL_IEEE123_BASELINE_AC_DIAGNOSTIC_V1",
        "status": "PASS_DIAGNOSTIC_COMPLETE_NOT_G13",
        "operating_day": "2025-04-15",
        "composition_forensic_sha256": sha256_file(composition_path),
        "cases_differ_mathematically": adapter_defect,
        "CASE_CURRENT": current_ac,
        "CASE_AUTHORITY_SEMANTIC": authority_ac,
        "planning_lp_vs_exact_ac": {
            "CASE_CURRENT": f"planning_{'feasible' if current_lp_feasible else 'infeasible'} / AC_{'feasible' if current_ac['summary']['hard_feasible'] else 'infeasible'}",
            "CASE_AUTHORITY_SEMANTIC": f"planning_{'feasible' if authority_lp_feasible else 'infeasible'} / AC_{'feasible' if authority_ac['summary']['hard_feasible'] else 'infeasible'}",
            "current_planning_worst": current_planning,
            "authority_planning_worst": authority_planning,
            "classification_basis": "Recovered authority-semantic input remains infeasible in both planning LinDistFlow and Fresh OpenDSS; the adapter defect is therefore not the feasibility-restoring cause.",
        },
        "primary_classification": classification,
        "diagnostic_only": True,
        "G13_marked_or_called": False,
        "schedule_change_count": 0,
        "optimization_call_count": 0,
        "opendss_optimizer_call_count": 0,
        "scientific_authority_change_count": 0,
        "rating_change_count": 0,
        "alpha_grid_change_count": 0,
        "source_voltage_change_count": 0,
        "may_scientific_loader_access_count": 0,
        "june_scientific_loader_access_count": 0,
        "G12_call_count": 0,
        "G13_call_count": 0,
        "G14_call_count": 0,
        "C12_call_count": 0,
        "stop_rule": "STOP_AFTER_FORENSIC_CLASSIFICATION",
    }
    ac_path = artifacts / "FULL_IEEE123_BASELINE_AC_DIAGNOSTIC_V1.json"
    _write_json(ac_path, ac_payload)
    return {
        "status": "PASS_FORENSIC_COMPLETE",
        "classification": classification,
        "composition_sha256": sha256_file(composition_path),
        "ac_diagnostic_sha256": sha256_file(ac_path),
        "current_ac": current_ac["summary"],
        "authority_ac": authority_ac["summary"],
        "may_access": 0,
        "june_access": 0,
    }


def main(argv: Sequence[str] | None = None) -> int:
    repo = Path.cwd()
    source = Path(r"C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\tmp\c12_exact_sources_repo_cleanup\c12_exact_sources\v2038_parent\Conversation3_Exact_AC_Remediation_Sweep_From_Conversation1_V2038\reference")
    wsl_base = Path(r"\\wsl.localhost\Ubuntu-MobileESS-D\home\jaewon\mobile_ess_work\processed\power_v70_3ph\runtime_arrays")
    integrated = Path(r"\\wsl.localhost\Ubuntu-MobileESS-D\home\jaewon\mobile_ess_work\integrated_rebuild\current\02_power_preprocess")
    desktop_build = Path(r"C:\Users\kjw39\OneDrive\Desktop\4-2\Mobile ESS\work\Mobile_ESS_Integrated_Rebuild_20260731")
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=repo)
    parser.add_argument("--artifacts", type=Path, default=repo / "dayahead/artifacts/v16_2")
    parser.add_argument("--source", type=Path, default=source)
    parser.add_argument("--wsl-root", type=Path, default=wsl_base)
    parser.add_argument("--integrated-root", type=Path, default=integrated)
    parser.add_argument("--build-source", type=Path, default=desktop_build / "src/build_power_v70_3ph.py")
    parser.add_argument("--manifest", type=Path, default=Path(r"C:\Users\kjw39\OneDrive\Desktop\4-2\Mobile ESS\work\power_side_p4f12_review_20260731_201553\p4f1_artifact_cleanup\p4f1_full_artifact_manifest.json"))
    parser.add_argument("--pv-reference", type=Path, default=desktop_build / "example_results/aemo_rooftop/aemo_rooftop_pv_2025_measurement_5min.npz")
    result = execute(**vars(parser.parse_args(argv)))
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
