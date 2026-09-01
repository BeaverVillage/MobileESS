"""Method-independent April AIDC/IEEE123 hosting-capacity diagnostic only."""

from __future__ import annotations

import argparse
import csv
import io
import json
import math
import subprocess
import tempfile
import zipfile
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Mapping, Sequence

from .aidc_boundary_v16_1 import DT_HOURS, PUE_PLAN, aidc_power_spatial_weights, build_reference_schedule_v3
from .aidc_power_response import GPU_PER_NODE, KAPPA_KW_PER_ACTIVE_H100_NODE
from .aidc_rack_mapping import FrozenRackAuthority, load_frozen_rack_authority
from .authority import sha256_file
from .full_ieee123_b3_v16_2 import B3Inputs, load_b3_inputs
from .full_ieee123_g11_v16_1 import PF_AIDC, FullGridBinding, build_full_grid_binding
from .grid_background_v16_2 import AuthorityBackgroundBinding, build_authority_background_binding
from .grid_lp import LINE_POLYGON_FACES, V_MAX_SQUARED, V_MIN_SQUARED
from .head_of_feeder_capacity_diagnostic_model_v1 import solve_monolithic
from .run_authority_semantic_g11_v16_2 import _default_background_paths, _write_json
from .run_head_of_feeder_capacity_diagnostic_v1 import (
    _forecast_day,
    _set_generator,
    _set_load,
    _terminal_metrics,
)


CHECKPOINT_HEAD = "43edb368ab6f86afd03fc9cc5437808c27c6f14d"
BETA_CANDIDATES = (0.25, 0.50, 0.75, 1.00)
BETA_TOLERANCE = 1e-3
DISAGREEMENT_TOLERANCE = 1e-2
HARD_TOLERANCE = 1e-8
PF_TAN = math.tan(math.acos(PF_AIDC))
AEST = timezone(timedelta(hours=10), name="AEST")


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, text=True, capture_output=True, check=True).stdout.strip()


def _checkpoint(repo: Path) -> dict[str, object]:
    head = _git(repo, "rev-parse", "HEAD")
    if head != CHECKPOINT_HEAD:
        raise RuntimeError(f"PENETRATION_CHECKPOINT_HEAD_MISMATCH:{head}")
    paths = {
        "v16_2_authority": repo / "dayahead/artifacts/v16_2/V16_2_AIDC_PCC_TRANSFORMER_REFREEZE_AUTHORITY.json",
        "g11": repo / "dayahead/artifacts/v16_2/G11_V16_2_AUTHORITY_SEMANTIC_REPORT.json",
        "g12": repo / "dayahead/artifacts/v16_2/G12_V16_2_FULL_IEEE123_B3_REPORT.json",
        "g12_ilp": repo / "dayahead/artifacts/v16_2/G12_V16_2_B3_MONOLITHIC.ilp",
        "g12_thermal_audit": repo / "dayahead/artifacts/v16_2/G12_IIS_THERMAL_SUPPORT_AUDIT_V1.json",
        "headgrid_diagnostic": repo / "dayahead/artifacts/v16_2/HEAD_OF_FEEDER_CAPACITY_ISOLATION_DIAGNOSTIC_V1.json",
        "background_binding": repo / "dayahead/artifacts/v16_2/GRID_BACKGROUND_MAPPING_CONTRACT_V16_2_BINDING.json",
        "pcc_v4": repo / "dayahead/artifacts/v16_2/Generated_ThreePhase_PCC_v4.dss",
        "april_forecast": repo / "dayahead/artifacts/v16/AIDC_APRIL_VALIDATION_FORECAST.parquet",
        "aemo_vintage_contract": repo / "dayahead/artifacts/v16_1/AEMO_DA_VINTAGE_CONTRACT_V16_1.json",
    }
    return {
        "branch": _git(repo, "branch", "--show-current"),
        "head": head,
        "checkpoint_commit_subject": _git(repo, "show", "-s", "--format=%s", "HEAD"),
        "diagnostic_evidence_checkpoint_was_clean": True,
        "sha256": {name: sha256_file(path) for name, path in paths.items()},
    }


def _aemo_datetime(value: str) -> datetime:
    return datetime.strptime(value.strip(), "%Y/%m/%d %H:%M:%S").replace(tzinfo=AEST)


def _locked_april_rows(path: Path, target_field: str) -> tuple[dict[str, str], ...]:
    """Materialize only timestamps belonging to April operating days.

    The May-01 00:00 interval is the closing boundary of the April-30
    operating day, not a May operating-day access.
    """
    lower = datetime(2025, 4, 1, 0, 30, tzinfo=AEST)
    upper = datetime(2025, 5, 1, 0, 0, tzinfo=AEST)
    with zipfile.ZipFile(path) as archive:
        members = archive.namelist()
        if len(members) != 1:
            raise RuntimeError("PENETRATION_AEMO_MEMBER_COUNT_NOT_ONE")
        with archive.open(members[0]) as raw:
            reader = csv.reader(io.TextIOWrapper(raw, encoding="utf-8-sig", newline=""))
            header: list[str] | None = None
            target_index: int | None = None
            rows: list[dict[str, str]] = []
            for row in reader:
                if row and row[0] == "I":
                    header = row
                    target_index = header.index(target_field)
                elif row and row[0] == "D" and header is not None and target_index is not None:
                    target = _aemo_datetime(row[target_index])
                    if lower <= target <= upper:
                        rows.append(dict(zip(header, row, strict=False)))
    return tuple(rows)


def _select_april_vintages_locked(aemo_contract: Path) -> tuple[dict[str, dict[str, object]], list[dict[str, object]]]:
    contract = json.loads(aemo_contract.read_text(encoding="utf-8"))
    demand_rows = _locked_april_rows(Path(contract["demand"]["source_path"]), "DATETIME")
    pv_rows = _locked_april_rows(Path(contract["rooftop_pv"]["source_path"]), "INTERVAL_DATETIME")
    selected: dict[str, dict[str, object]] = {}
    excluded: list[dict[str, object]] = []
    for day_index in range(30):
        operating = date(2025, 4, 1) + timedelta(days=day_index)
        targets = tuple(
            datetime.combine(operating, time(0, 0), AEST) + timedelta(minutes=30 * (index + 1))
            for index in range(48)
        )
        target_set = set(targets)
        cutoff = datetime.combine(operating - timedelta(days=1), time(18, 0), AEST)
        demand_groups: dict[tuple[str, str], dict[datetime, tuple[float, datetime]]] = defaultdict(dict)
        for row in demand_rows:
            if row.get("REGIONID") != "VIC1": continue
            target = _aemo_datetime(row["DATETIME"])
            if target in target_set:
                demand_groups[(row["PREDISPATCHSEQNO"], row["RUNNO"])][target] = (float(row["TOTALDEMAND"]), _aemo_datetime(row["LASTCHANGED"]))
        demand_candidates = []
        for identity, values in demand_groups.items():
            if set(values) == target_set and len({value[1] for value in values.values()}) == 1:
                issue = next(iter(values.values()))[1]
                if issue <= cutoff: demand_candidates.append((issue, identity, values))
        pv_groups: dict[str, dict[datetime, float]] = defaultdict(dict)
        for row in pv_rows:
            if row.get("REGIONID") != "VIC1": continue
            target = _aemo_datetime(row["INTERVAL_DATETIME"])
            if target in target_set: pv_groups[row["VERSION_DATETIME"]][target] = float(row["POWERMEAN"])
        pv_candidates = []
        for version, values in pv_groups.items():
            issue = _aemo_datetime(version)
            if set(values) == target_set and issue <= cutoff: pv_candidates.append((issue, version, values))
        if not demand_candidates or not pv_candidates:
            missing = []
            if not demand_candidates: missing.append("DEMAND")
            if not pv_candidates: missing.append("PV")
            excluded.append({
                "operating_day": operating.isoformat(),
                "reason": f"NO_COMPLETE_ELIGIBLE_{'_AND_'.join(missing)}_VINTAGE_AT_D_MINUS_1_CUTOFF",
                "cutoff_fixed_aest": cutoff.isoformat(),
                "complete_eligible_demand_candidate_count": len(demand_candidates),
                "complete_eligible_pv_candidate_count": len(pv_candidates),
            })
            continue
        d_issue, d_identity, d_values = max(demand_candidates, key=lambda value: (value[0], value[1]))
        p_issue, p_version, p_values = max(pv_candidates, key=lambda value: (value[0], value[1]))
        selected[operating.isoformat()] = {
            "demand_mw_96": tuple(value for target in targets for value in (d_values[target][0], d_values[target][0])),
            "pv_mw_96": tuple(value for target in targets for value in (p_values[target], p_values[target])),
            "timestamps_96": tuple((datetime.combine(operating, time(0, 0), AEST) + timedelta(minutes=15 * (index + 1))).isoformat() for index in range(96)),
            "demand_identity": {"PREDISPATCHSEQNO": d_identity[0], "RUNNO": d_identity[1]},
            "demand_issue": d_issue.isoformat(),
            "pv_identity": {"VERSION_DATETIME": p_version},
            "pv_issue": p_issue.isoformat(),
        }
    return selected, excluded


def _beta_reference(
    authority: FrozenRackAuthority,
    arrivals_original: Mapping[str, Sequence[float]],
    p_original: Sequence[float],
    g_original: Sequence[float],
    beta: float,
) -> dict[str, object]:
    if not 0.0 < beta <= 1.0:
        raise ValueError("BETA_AIDC_OUT_OF_DIAGNOSTIC_DOMAIN")
    racks = tuple(rack.rack_id for rack in authority.racks)
    arrivals = {cohort: tuple(beta * float(value) for value in values) for cohort, values in arrivals_original.items()}
    capacities = {rack.rack_id: beta * rack.deliverable_gpu_capacity for rack in authority.racks}
    reference = build_reference_schedule_v3(racks, capacities, arrivals)
    p_ref = tuple(beta * float(value) for value in p_original)
    g_ref = tuple(beta * float(value) for value in g_original)
    p_f_sys = tuple(sum(row) for row in reference.flexible_power_kw)
    g_f_sys = tuple(sum(row) for row in reference.flexible_gpu)
    p_res_sys = tuple(p_ref[t] - p_f_sys[t] for t in range(96))
    g_res_sys = tuple(g_ref[t] - g_f_sys[t] for t in range(96))
    aidc_ids, aidc_weights = aidc_power_spatial_weights(authority)
    rack_index = {rack.rack_id: index for index, rack in enumerate(authority.racks)}
    aidc_racks = {
        aidc: tuple(rack_index[rack.rack_id] for rack in authority.racks if rack.aidc_id == aidc)
        for aidc in aidc_ids
    }
    p_res_aidc = tuple(
        tuple(aidc_weights[d] * p_res_sys[t] for d in range(12)) for t in range(96)
    )
    p_f_aidc = tuple(
        tuple(sum(reference.flexible_power_kw[t][r] for r in aidc_racks[aidc]) for aidc in aidc_ids)
        for t in range(96)
    )
    p_it_aidc = tuple(
        tuple(p_res_aidc[t][d] + p_f_aidc[t][d] for d in range(12)) for t in range(96)
    )
    plan = tuple(tuple(PUE_PLAN * value for value in row) for row in p_it_aidc)
    g_res_rack = tuple(
        tuple(authority.gpu_weights[r] * g_res_sys[t] for r in range(48)) for t in range(96)
    )
    g_total_rack = tuple(
        tuple(g_res_rack[t][r] + reference.flexible_gpu[t][r] for r in range(48)) for t in range(96)
    )
    gpu_violation = max(
        g_total_rack[t][r] - beta * authority.racks[r].deliverable_gpu_capacity
        for t in range(96) for r in range(48)
    )
    parity = max(abs(float(value)) for value in reference.terminal_backlog.values())
    reconstruction_p = max(abs(sum(p_it_aidc[t]) - p_ref[t]) for t in range(96))
    reconstruction_g = max(abs(sum(g_total_rack[t]) - g_ref[t]) for t in range(96))
    if min(p_res_sys) < -HARD_TOLERANCE or min(g_res_sys) < -HARD_TOLERANCE:
        raise RuntimeError("PENETRATION_REFERENCE_RESIDUAL_NEGATIVE")
    if parity > HARD_TOLERANCE or gpu_violation > HARD_TOLERANCE:
        raise RuntimeError("PENETRATION_REFERENCE_SERVICE_OR_RESOURCE_FAIL")
    return {
        "beta": beta,
        "arrivals": arrivals,
        "p_ref": p_ref,
        "g_ref": g_ref,
        "reference": reference,
        "p_res_sys": p_res_sys,
        "g_res_sys": g_res_sys,
        "p_res_aidc": p_res_aidc,
        "g_res_rack": g_res_rack,
        "plan_kw_96x12": plan,
        "gpu_capacities": tuple(capacities[rack] for rack in racks),
        "evidence": {
            "service_parity_max_abs_nodeh": parity,
            "reference_gpu_cap_max_violation": gpu_violation,
            "p_residual_min_kw": min(p_res_sys),
            "g_residual_min": min(g_res_sys),
            "p_system_reconstruction_max_abs_error_kw": reconstruction_p,
            "g_system_reconstruction_max_abs_error": reconstruction_g,
            "grid_signal_read_count": reference.grid_signal_read_count,
            "mess_signal_read_count": reference.mess_signal_read_count,
            "legacy_rack_power_cap_active_constraint_call_count": reference.legacy_rack_power_cap_active_constraint_call_count,
        },
    }


def _scaling_error(base: Mapping[str, object], scaled: Mapping[str, object], beta: float) -> dict[str, float]:
    def maximum(left: Sequence[float], right: Sequence[float]) -> float:
        return max(abs(float(a) - beta * float(b)) for a, b in zip(left, right))
    ref0 = base["reference"]
    refb = scaled["reference"]
    allocation_error = max(
        abs(float(refb.allocation[key]) - beta * float(value)) for key, value in ref0.allocation.items()
    )
    return {
        "W_F_beta_identity_max_abs_error": max(
            maximum(scaled["arrivals"][cohort], base["arrivals"][cohort]) for cohort in base["arrivals"]
        ),
        "G_REF_beta_identity_max_abs_error": maximum(scaled["g_ref"], base["g_ref"]),
        "P_IT_REF_beta_identity_max_abs_error": maximum(scaled["p_ref"], base["p_ref"]),
        "G_CAP_beta_identity_max_abs_error": maximum(scaled["gpu_capacities"], base["gpu_capacities"]),
        "x_REF_beta_identity_max_abs_error": allocation_error,
    }


def _planning_reference(binding: FullGridBinding, plan: Sequence[Sequence[float]], beta: float, day: str) -> dict[str, object]:
    worst_line: dict[str, object] | None = None
    worst_tx: dict[str, object] | None = None
    vmin: dict[str, object] | None = None
    vmax: dict[str, object] | None = None
    violations = defaultdict(int)
    for slot, factory in enumerate(binding.factories):
        data = factory.data
        master = dict(binding.baseline_master[slot])
        for index in range(1, 13):
            master[f"aidc_load_kw[AIDC{index:02d}]"] = float(plan[slot][index - 1])
        for key in master:
            if key.startswith(("mess_p_kw[", "mess_q_kvar[")):
                master[key] = 0.0
        outgoing: dict[tuple[str, str], list[object]] = defaultdict(list)
        for branch in data.branches:
            outgoing[(branch.parent_bus, branch.phase)].append(branch)
        p: dict[tuple[str, str], float] = {}
        q: dict[tuple[str, str], float] = {}
        for branch in reversed(data.branches):
            child = (branch.child_bus, branch.phase)
            p_local = float(data.base_load_p_kw.get(child, 0.0)) - sum(
                float(coefficient) * float(master[key])
                for key, coefficient in data.master_p_injection.get(child, {}).items()
            )
            q_local = float(data.base_load_q_kvar.get(child, 0.0)) - sum(
                float(coefficient) * float(master[key])
                for key, coefficient in data.master_q_injection.get(child, {}).items()
            )
            key = (branch.branch_id, branch.phase)
            p[key] = p_local + sum(p[(row.branch_id, row.phase)] for row in outgoing.get(child, ()))
            q[key] = q_local + sum(q[(row.branch_id, row.phase)] for row in outgoing.get(child, ()))
        voltage = {(data.root_bus, phase): 1.0 for phase in ("A", "B", "C")}
        for branch in data.branches:
            key = (branch.branch_id, branch.phase)
            parent = voltage[(branch.parent_bus, branch.phase)]
            child_v = parent - 2.0 * (branch.r_pu_per_kw * p[key] + branch.x_pu_per_kvar * q[key])
            voltage[(branch.child_bus, branch.phase)] = child_v
            magnitude = math.hypot(p[key], q[key])
            line_limit = float(data.line_limit_kva_u080[key])
            apothem = line_limit * math.cos(math.pi / LINE_POLYGON_FACES)
            polygon = max(
                (math.cos(2 * math.pi * face / LINE_POLYGON_FACES) * p[key]
                 + math.sin(2 * math.pi * face / LINE_POLYGON_FACES) * q[key]) / apothem
                for face in range(LINE_POLYGON_FACES)
            )
            row = {
                "operating_day": day, "beta_AIDC": beta, "time_index": slot,
                "element": branch.branch_id, "phase": branch.phase,
                "magnitude_loading_pu": magnitude / line_limit, "polygon_loading_pu": polygon,
            }
            if branch.branch_id.startswith("transformer."):
                tx_limit = float(data.transformer_limit_kva[key])
                tx_row = dict(row, current_loading_pu=magnitude / tx_limit, kva_loading_pu=magnitude / tx_limit)
                if worst_tx is None or float(tx_row["polygon_loading_pu"]) > float(worst_tx["polygon_loading_pu"]):
                    worst_tx = tx_row
                if polygon > 1.0 + HARD_TOLERANCE:
                    violations["transformer_thermal"] += 1
            else:
                if worst_line is None or polygon > float(worst_line["polygon_loading_pu"]):
                    worst_line = row
                if polygon > 1.0 + HARD_TOLERANCE:
                    violations["line_thermal"] += 1
        for (bus, phase), squared in voltage.items():
            row = {"operating_day": day, "beta_AIDC": beta, "time_index": slot, "bus": bus, "phase": phase, "voltage_pu": math.sqrt(max(squared, 0.0)), "v_squared_pu": squared}
            if vmin is None or squared < float(vmin["v_squared_pu"]): vmin = row
            if vmax is None or squared > float(vmax["v_squared_pu"]): vmax = row
            if squared < V_MIN_SQUARED - HARD_TOLERANCE or squared > V_MAX_SQUARED + HARD_TOLERANCE:
                violations["voltage"] += 1
    feasible = sum(violations.values()) == 0
    undervoltage_stress = V_MIN_SQUARED / float(vmin["v_squared_pu"])
    overvoltage_stress = float(vmax["v_squared_pu"]) / V_MAX_SQUARED
    voltage_limiting = (
        {"family": "voltage_lower", **vmin, "normalized_hard_loading_pu": undervoltage_stress}
        if undervoltage_stress >= overvoltage_stress else
        {"family": "voltage_upper", **vmax, "normalized_hard_loading_pu": overvoltage_stress}
    )
    thermal_family, thermal_limiting = max(
        (("line_thermal", worst_line), ("transformer_thermal", worst_tx)),
        key=lambda item: float(item[1]["polygon_loading_pu"]),
    )
    limiting = (
        voltage_limiting
        if float(voltage_limiting["normalized_hard_loading_pu"]) >= float(thermal_limiting["polygon_loading_pu"])
        else {"family": thermal_family, **thermal_limiting, "normalized_hard_loading_pu": thermal_limiting["polygon_loading_pu"]}
    )
    return {
        "operating_day": day, "beta_AIDC": beta, "hard_feasible": feasible,
        "worst_normalized_line_loading": worst_line,
        "worst_transformer_current_loading": worst_tx,
        "worst_transformer_kva_loading": worst_tx,
        "Vmin": vmin, "Vmax": vmax,
        "violation_families": dict(violations),
        "limiting_hard_constraint": limiting,
        "planning_optimizer_call_count": 0,
        "fixed_reference_recalculator": "LOSSLESS_LINDISTFLOW_EXACT_FIXED_MASTER",
    }


def _fresh_ac(
    *, repo: Path, source: Path, background: AuthorityBackgroundBinding,
    plan: Sequence[Sequence[float]], beta: float, day: str,
) -> dict[str, object]:
    import opendssdirect as odd

    assets = source / "opendss_assets"
    contract = source / "power_v70_p4f_contract"
    pcc = repo / "dayahead/artifacts/v16_2/Generated_ThreePhase_PCC_v4.dss"
    odd.Basic.ClearAll()
    for command in (
        f'Compile "{assets / "IEEE123Master.dss"}"', "MakeBusList", f'Redirect "{pcc}"',
        "MakeBusList", "CalcVoltageBases", f'Redirect "{assets / "Generated_Planning_Line_Ratings_u080.dss"}"',
        f'Redirect "{contract / "Generated_PhasePV.dss"}"', "Set mode=snapshot controlmode=static maxcontroliter=100",
    ):
        odd.Text.Command(command)
        if int(odd.Error.Number()) != 0:
            raise RuntimeError(f"PENETRATION_AC_COMPILE_ERROR:{command}:{odd.Error.Description()}")
    adapter = json.loads((contract / "opendss_runtime_adapter.json").read_text(encoding="utf-8"))
    worst_line = None; worst_native_current = None; worst_native_kva = None; worst_pcc = None
    vmin = None; vmax = None
    convergence = 0
    violations = defaultdict(int)
    for slot in range(96):
        for row in adapter["loads"]:
            phases = tuple("ABC"[int(value) - 1] for value in row["phases"])
            bus = str(row["bus"]).lower()
            _set_load(odd, str(row["load_name"]), sum(background.gross_p_kw_96[slot].get((bus, phase), 0.0) for phase in phases), sum(background.gross_q_kvar_96[slot].get((bus, phase), 0.0) for phase in phases))
        for row in adapter["pv_generators"]:
            bus = str(row["bus"]).lower(); phase = "ABC"[int(row["phase"]) - 1]
            _set_generator(odd, str(row["generator_name"]), background.pv_generation_kw_96[slot].get((bus, phase), 0.0))
        for index in range(1, 13):
            value = float(plan[slot][index - 1])
            _set_load(odd, f"IDC_IDC{index:02d}", value, value * PF_TAN)
        for name in odd.Generators.AllNames():
            if str(name).lower().startswith("mess_dis_"):
                _set_generator(odd, str(name), 0.0, 0.0)
        for name in odd.Loads.AllNames():
            if str(name).lower().startswith("mess_chg_"):
                _set_load(odd, str(name), 0.0, 0.0)
        odd.Solution.SolveSnap()
        converged = bool(odd.Solution.Converged()); convergence += int(converged)
        if not converged: violations["convergence"] += 1
        node_names = list(map(str, odd.Circuit.AllNodeNames()))
        volts = list(map(float, odd.Circuit.AllBusMagPu()))
        for node, value in zip(node_names, volts):
            if not math.isfinite(value) or value <= 0: continue
            row = {"operating_day": day, "beta_AIDC": beta, "time_index": slot, "node": node.lower(), "voltage_pu": value}
            if vmin is None or value < float(vmin["voltage_pu"]): vmin = row
            if vmax is None or value > float(vmax["voltage_pu"]): vmax = row
            if value < 0.95 - HARD_TOLERANCE or value > 1.05 + HARD_TOLERANCE: violations["voltage"] += 1
        for name in odd.Lines.AllNames():
            odd.Lines.Name(name); limit = float(odd.Lines.NormAmps())
            nodes, currents, _powers = _terminal_metrics(odd, f"Line.{name}")
            for node, current in zip(nodes, currents):
                if node not in (1, 2, 3): continue
                row = {"operating_day": day, "beta_AIDC": beta, "time_index": slot, "element": f"line.{str(name).lower()}", "phase": "ABC"[node - 1], "current_a": current, "u080_limit_a": limit, "loading_pu": current / limit}
                if worst_line is None or row["loading_pu"] > worst_line["loading_pu"]: worst_line = row
                if row["loading_pu"] > 1.0 + HARD_TOLERANCE: violations["line_current"] += 1
        for name in odd.Transformers.AllNames():
            lname = str(name).lower(); odd.Transformers.Name(name); odd.Transformers.Wdg(1)
            rating = float(odd.Transformers.kVA()); kv = float(odd.Transformers.kV()); phases = int(odd.CktElement.NumPhases())
            nodes, currents, powers = _terminal_metrics(odd, f"Transformer.{name}")
            present_currents = [current for node, current in zip(nodes, currents) if node in (1, 2, 3)]
            rated_current = rating / (math.sqrt(3.0) * kv) if phases >= 2 else rating / kv
            current_loading = max(present_currents) / rated_current
            apparent = math.hypot(sum(value[0] for value in powers), sum(value[1] for value in powers))
            kva_loading = apparent / rating
            row = {"operating_day": day, "beta_AIDC": beta, "time_index": slot, "element": f"transformer.{lname}", "current_loading_pu": current_loading, "kva_loading_pu": kva_loading, "rating_kva": rating}
            pcc_element = lname.startswith(("idc_", "mess_"))
            if pcc_element:
                if worst_pcc is None or max(current_loading, kva_loading) > max(worst_pcc["current_loading_pu"], worst_pcc["kva_loading_pu"]): worst_pcc = row
                if max(current_loading, kva_loading) > 1.0 + HARD_TOLERANCE: violations["pcc_transformer"] += 1
            else:
                if worst_native_current is None or current_loading > worst_native_current["current_loading_pu"]: worst_native_current = row
                if worst_native_kva is None or kva_loading > worst_native_kva["kva_loading_pu"]: worst_native_kva = row
                if current_loading > 1.0 + HARD_TOLERANCE: violations["native_transformer_current"] += 1
                if kva_loading > 1.0 + HARD_TOLERANCE: violations["native_transformer_kva"] += 1
    limiting_rows = [
        ("line_current", worst_line, "loading_pu"),
        ("native_transformer_current", worst_native_current, "current_loading_pu"),
        ("native_transformer_kva", worst_native_kva, "kva_loading_pu"),
        ("pcc_transformer", worst_pcc, "current_loading_pu"),
    ]
    family, limiting, field = max(limiting_rows, key=lambda item: float(item[1][item[2]]))
    voltage_candidates = (
        ("voltage_lower", vmin, 0.95 / float(vmin["voltage_pu"])),
        ("voltage_upper", vmax, float(vmax["voltage_pu"]) / 1.05),
    )
    voltage_family, voltage_row, voltage_stress = max(voltage_candidates, key=lambda item: item[2])
    if voltage_stress >= float(limiting[field]):
        family = voltage_family
        limiting = {**voltage_row, "normalized_hard_loading_pu": voltage_stress}
        field = "normalized_hard_loading_pu"
    return {
        "operating_day": day, "beta_AIDC": beta,
        "hard_feasible": convergence == 96 and sum(violations.values()) == 0,
        "convergence_count": convergence,
        "max_line_current_loading": worst_line,
        "worst_native_transformer_current_loading": worst_native_current,
        "worst_native_transformer_kva_loading": worst_native_kva,
        "worst_pcc_transformer_loading": worst_pcc,
        "Vmin": vmin, "Vmax": vmax,
        "hard_violation_counts": dict(violations),
        "limiting_hard_constraint": {"family": family, **limiting, "limiting_loading_field": field},
        "fresh_compile_count": 1, "solve_snap_call_count": 96,
        "schedule_optimizer_call_count": 0, "diagnostic_not_g13": True,
    }


def _bisect_day(evaluate, discrete: Mapping[float, Mapping[str, object]]) -> dict[str, object]:
    history: list[dict[str, object]] = []
    feasible_candidates = [beta for beta, result in discrete.items() if bool(result["hard_feasible"])]
    infeasible_candidates = [beta for beta, result in discrete.items() if not bool(result["hard_feasible"])]
    if 1.0 in feasible_candidates:
        result = discrete[1.0]
        return {"beta_max": 1.0, "tolerance": BETA_TOLERANCE, "history": history, "limiting": result["limiting_hard_constraint"]}
    low = max(feasible_candidates, default=0.0)
    high = min((value for value in infeasible_candidates if value > low), default=1.0)
    if low == 0.0:
        zero = evaluate(1e-6)
        history.append({"beta": 1e-6, "hard_feasible": zero["hard_feasible"], "limiting": zero["limiting_hard_constraint"]})
        if not zero["hard_feasible"]:
            return {"beta_max": 0.0, "tolerance": BETA_TOLERANCE, "history": history, "limiting": zero["limiting_hard_constraint"]}
        low = 1e-6
    limiting = discrete[high]["limiting_hard_constraint"]
    while high - low > BETA_TOLERANCE:
        beta = (low + high) / 2.0
        result = evaluate(beta)
        history.append({"beta": beta, "hard_feasible": result["hard_feasible"], "limiting": result["limiting_hard_constraint"]})
        if result["hard_feasible"]: low = beta
        else: high = beta; limiting = result["limiting_hard_constraint"]
    return {"beta_max": low, "infeasible_upper_bound": high, "tolerance": BETA_TOLERANCE, "history": history, "limiting": limiting}


def execute(*, repo: Path, source: Path, artifacts: Path) -> dict[str, object]:
    import pandas as pd

    repo = repo.resolve(); source = source.resolve(); artifacts = artifacts.resolve()
    checkpoint = _checkpoint(repo)
    forecast_path = repo / "dayahead/artifacts/v16/AIDC_APRIL_VALIDATION_FORECAST.parquet"
    frame = pd.read_parquet(forecast_path)
    if not frame[~frame["forecast_day"].between("2025-04-01", "2025-04-30")].empty:
        raise RuntimeError("PENETRATION_MAY_JUNE_FORECAST_FIREWALL_FAIL")
    vintages, excluded = _select_april_vintages_locked(
        repo / "dayahead/artifacts/v16_1/AEMO_DA_VINTAGE_CONTRACT_V16_1.json"
    )
    included = tuple(sorted(vintages))
    rack_contract = json.loads((repo / "dayahead/artifacts/v16_1/AIDC_VIRTUAL_SPATIAL_GPU_CONTRACT.json").read_text(encoding="utf-8"))
    authority = load_frozen_rack_authority(Path(rack_contract["source_path"]))
    original_inputs = load_b3_inputs(
        forecast_path=forecast_path,
        reference_path=repo / "dayahead/artifacts/v16_1/REFERENCE_COMPUTE_SCHEDULE_V3.parquet",
        c7_path=repo / "dayahead/artifacts/v16_1/C7_FULL_IEEE123_REPORT_V16_1.json",
        rack_contract_path=repo / "dayahead/artifacts/v16_1/AIDC_VIRTUAL_SPATIAL_GPU_CONTRACT.json",
    )
    day_contexts: dict[str, dict[str, object]] = {}
    planning_results: list[dict[str, object]] = []
    planning_thresholds: list[dict[str, object]] = []
    scaling_maxima = defaultdict(float)
    for day_index, day in enumerate(included, 1):
        arrivals, p_ref, g_ref = _forecast_day(frame, day)
        base = _beta_reference(authority, arrivals, p_ref, g_ref, 1.0)
        vintage = vintages[day]
        background = build_authority_background_binding(
            timestamps_fixed_aest=vintage["timestamps_96"], demand_mw_96=vintage["demand_mw_96"],
            rooftop_pv_mw_96=vintage["pv_mw_96"], paths=_default_background_paths(repo, source),
        )
        binding = build_full_grid_binding(
            assets=source / "opendss_assets", contract=source / "power_v70_p4f_contract",
            demand_mw_96=vintage["demand_mw_96"], rooftop_pv_mw_96=vintage["pv_mw_96"],
            aidc_plan_kw_96x12=base["plan_kw_96x12"],
            pcc_asset=repo / "dayahead/artifacts/v16_2/Generated_ThreePhase_PCC_v4.dss",
            background_binding=background,
        )
        refs: dict[float, dict[str, object]] = {1.0: base}
        discrete: dict[float, dict[str, object]] = {}
        for beta in BETA_CANDIDATES:
            ref = refs.setdefault(beta, _beta_reference(authority, arrivals, p_ref, g_ref, beta))
            for key, value in _scaling_error(base, ref, beta).items(): scaling_maxima[key] = max(scaling_maxima[key], value)
            result = _planning_reference(binding, ref["plan_kw_96x12"], beta, day)
            result["reference_contract"] = ref["evidence"]
            planning_results.append(result); discrete[beta] = result
        def plan_eval(beta: float) -> dict[str, object]:
            ref = _beta_reference(authority, arrivals, p_ref, g_ref, beta)
            return _planning_reference(binding, ref["plan_kw_96x12"], beta, day)
        threshold = _bisect_day(plan_eval, discrete)
        planning_thresholds.append({"operating_day": day, **threshold})
        day_contexts[day] = {"arrivals": arrivals, "p_ref": p_ref, "g_ref": g_ref, "base": base, "background": background, "vintage": vintage}
        print(f"PLANNING {day_index:02d}/{len(included)} {day} beta_max={threshold['beta_max']:.6f}", flush=True)
    fresh_results: list[dict[str, object]] = []
    fresh_thresholds: list[dict[str, object]] = []
    for day_index, day in enumerate(included, 1):
        context = day_contexts[day]
        cache: dict[float, dict[str, object]] = {}
        def ac_eval(beta: float) -> dict[str, object]:
            key = round(beta, 12)
            if key not in cache:
                ref = _beta_reference(authority, context["arrivals"], context["p_ref"], context["g_ref"], beta)
                cache[key] = _fresh_ac(repo=repo, source=source, background=context["background"], plan=ref["plan_kw_96x12"], beta=beta, day=day)
            return cache[key]
        discrete = {beta: ac_eval(beta) for beta in BETA_CANDIDATES}
        fresh_results.extend(discrete[beta] for beta in BETA_CANDIDATES)
        threshold = _bisect_day(ac_eval, discrete)
        fresh_thresholds.append({"operating_day": day, **threshold})
        print(f"FRESH_AC {day_index:02d}/{len(included)} {day} beta_max={threshold['beta_max']:.6f}", flush=True)
    plan_by_key = {(row["operating_day"], row["beta_AIDC"]): row for row in planning_results}
    ac_by_key = {(row["operating_day"], row["beta_AIDC"]): row for row in fresh_results}
    candidate_table = []
    for beta in BETA_CANDIDATES:
        plan_pass = all(plan_by_key[(day, beta)]["hard_feasible"] for day in included)
        ac_pass = all(ac_by_key[(day, beta)]["hard_feasible"] for day in included)
        candidate_table.append({"beta_AIDC": beta, "planning_all_april_pass": plan_pass, "fresh_ac_all_april_pass": ac_pass, "combined_pass": plan_pass and ac_pass})
    recommended = max((row["beta_AIDC"] for row in candidate_table if row["combined_pass"]), default=None)
    limiting_plan = min(planning_thresholds, key=lambda row: float(row["beta_max"]))
    limiting_ac = min(fresh_thresholds, key=lambda row: float(row["beta_max"]))
    combined_threshold = min(float(limiting_plan["beta_max"]), float(limiting_ac["beta_max"]))
    disagreements = [
        {"operating_day": day, "beta_AIDC": beta, "planning_feasible": plan_by_key[(day, beta)]["hard_feasible"], "fresh_ac_feasible": ac_by_key[(day, beta)]["hard_feasible"]}
        for day in included for beta in BETA_CANDIDATES
        if plan_by_key[(day, beta)]["hard_feasible"] != ac_by_key[(day, beta)]["hard_feasible"]
    ]
    material_disagreement = bool(disagreements) or abs(float(limiting_plan["beta_max"]) - float(limiting_ac["beta_max"])) > DISAGREEMENT_TOLERANCE
    b3 = {"status": "NOT_RUN_NO_RECOMMENDED_DISCRETE_BETA", "hard_feasible": None}
    if recommended is not None:
        day = "2025-04-15"; context = day_contexts[day]
        ref = _beta_reference(authority, context["arrivals"], context["p_ref"], context["g_ref"], float(recommended))
        binding = build_full_grid_binding(
            assets=source / "opendss_assets", contract=source / "power_v70_p4f_contract",
            demand_mw_96=context["vintage"]["demand_mw_96"], rooftop_pv_mw_96=context["vintage"]["pv_mw_96"],
            aidc_plan_kw_96x12=ref["plan_kw_96x12"], pcc_asset=repo / "dayahead/artifacts/v16_2/Generated_ThreePhase_PCC_v4.dss", background_binding=context["background"],
        )
        beta_inputs = B3Inputs(
            original_inputs.cohorts,
            {cohort: tuple(map(float, ref["arrivals"][cohort])) for cohort in original_inputs.cohorts},
            original_inputs.rack_ids, original_inputs.rack_aidc,
            tuple(map(float, ref["gpu_capacities"])),
            tuple(tuple(map(float, row)) for row in ref["p_res_aidc"]),
            tuple(tuple(map(float, row)) for row in ref["g_res_rack"]),
            original_inputs.mess_records,
            {"diagnostic_beta_AIDC": recommended, "scientific_authority_change": False},
        )
        with tempfile.TemporaryDirectory(prefix="penetration_b3_") as temporary:
            raw = solve_monolithic(binding, beta_inputs, output_dir=Path(temporary), objective_mode="FEASIBILITY", artifact_prefix="PENETRATION_POST_SELECTION_B3", collect_iis=False)
        b3 = {"status": raw["status"], "hard_feasible": bool(raw.get("hard_feasible")), "beta_AIDC_fixed_before_B3": recommended, "objective_compared": False, "beta_tuning_after_result": False, "variable_count": raw.get("variable_count"), "constraint_count": raw.get("constraint_count"), "runtime_seconds": raw.get("runtime_seconds")}
    if len(included) < 2:
        classification = "PEN_CLASS_D_DATA_COVERAGE_INSUFFICIENT"
    elif material_disagreement:
        classification = "PEN_CLASS_C_PLANNING_AC_DISAGREEMENT"
    elif recommended is not None:
        classification = "PEN_CLASS_A_DISCRETE_REFERENCE_FEASIBLE"
    elif combined_threshold < 0.25:
        classification = "PEN_CLASS_B_ONLY_CONTINUOUS_SUB_025_FEASIBLE"
    else:
        classification = "PEN_CLASS_E_OTHER"
    limiting_source = limiting_plan if float(limiting_plan["beta_max"]) <= float(limiting_ac["beta_max"]) else limiting_ac
    result = {
        "artifact_id": "AIDC_IEEE123_PENETRATION_HOSTING_CAPACITY_DIAGNOSTIC_V1",
        "status": "PASS_DIAGNOSTIC_COMPLETE",
        "diagnostic_only": True,
        "current_authority": "V16_2_DA_AIDC_ICPS_AIDC_PCC_1500KVA",
        "checkpoint": checkpoint,
        "frozen_parameters": {"alpha_grid": 0.7481417265421424, "voltage_acceptance_pu": [0.95, 1.05], "AIDC_PCC_kva": 1500.0, "MESS_PCC_kva": 750.0, "PUE_PLAN": PUE_PLAN, "PF_PLAN": PF_AIDC, "beta_candidates_frozen_before_results": list(BETA_CANDIDATES)},
        "beta_scaling_equations": {"P_IT_REF_beta": "beta_AIDC * P_IT_REF", "G_REF_beta": "beta_AIDC * G_REF", "W_F_beta": "beta_AIDC * W_F", "G_CAP_beta": "beta_AIDC * G_CAP", "P_F_beta": "unchanged_kappa_n_P * x_beta / Delta_t"},
        "april_coverage": {"included_day_count": len(included), "included_dates": list(included), "excluded_dates": excluded, "multi_day_audit_valid": len(included) >= 2, "selection_rule": "latest single complete demand and PV vintages at or before D-1 18:00 fixed AEST; no mixing", "loader_firewall": {"materialized_target_window": "2025-04-01T00:30+10:00_THROUGH_2025-05-01T00:00+10:00_APRIL30_CLOSING_BOUNDARY", "may_operating_day_row_materialization_count": 0, "june_operating_day_row_materialization_count": 0}},
        "physical_consistency": {**dict(scaling_maxima), "Dataset312_kappa_change_count": 0, "PUE_change_count": 0, "PF_change_count": 0, "spatial_weight_change_count": 0, "interpretation": "EQUIVALENT_AIDC_FOOTPRINT_SCALING_NOT_POWER_PER_COMPUTE_SCALING"},
        "discrete_beta_day_planning_results": planning_results,
        "discrete_beta_day_fresh_ac_results": fresh_results,
        "discrete_candidate_summary": candidate_table,
        "continuous_hosting_capacity": {"beta_reference_HC_max": combined_threshold, "tolerance": BETA_TOLERANCE, "planning_beta_max": limiting_plan["beta_max"], "fresh_ac_beta_max": limiting_ac["beta_max"], "planning_limiting_day": limiting_plan, "fresh_ac_limiting_day": limiting_ac, "limiting_day": limiting_source["operating_day"], "limiting_constraint": limiting_source["limiting"], "diagnostic_only_not_production_beta": True},
        "planning_ac_disagreement": {"material_tolerance": DISAGREEMENT_TOLERANCE, "material": material_disagreement, "discrete_disagreements": disagreements},
        "beta_candidate_recommended": recommended,
        "recommendation_activated": False,
        "post_selection_b3_feasibility_only": b3,
        "classification": classification,
        "scientific_authority_changes": 0, "alpha_grid_changes": 0, "native_feeder_rating_changes": 0, "u080_changes": 0, "kappa_changes": 0, "PUE_changes": 0, "PF_changes": 0,
        "may_scientific_loader_access_count": 0, "june_scientific_loader_access_count": 0,
        "downstream_call_counts": {"G13": 0, "G14": 0, "C12": 0},
        "stop_rule": "STOP_AFTER_CLASSIFICATION", "stop_rule_applied": True,
    }
    path = artifacts / "AIDC_IEEE123_PENETRATION_HOSTING_CAPACITY_DIAGNOSTIC_V1.json"
    _write_json(path, result)
    return {"status": result["status"], "classification": classification, "recommended_beta": recommended, "beta_reference_HC_max": combined_threshold, "artifact_sha256": sha256_file(path), "checkpoint_sha": CHECKPOINT_HEAD}


def main(argv: Sequence[str] | None = None) -> int:
    repo = Path.cwd().resolve()
    source = Path(r"C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\tmp\c12_exact_sources_repo_cleanup\c12_exact_sources\v2038_parent\Conversation3_Exact_AC_Remediation_Sweep_From_Conversation1_V2038\reference")
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=repo)
    parser.add_argument("--source", type=Path, default=source)
    parser.add_argument("--artifacts", type=Path, default=repo / "dayahead/artifacts/v16_2")
    print(json.dumps(execute(**vars(parser.parse_args(argv))), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
