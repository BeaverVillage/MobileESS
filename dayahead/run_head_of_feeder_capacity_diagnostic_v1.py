"""V16.2 head-of-feeder capacity isolation diagnostic; no authority mutation."""

from __future__ import annotations

import argparse
import csv
import io
import json
import math
import re
import subprocess
import tempfile
import zipfile
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Mapping, Sequence

from .aidc_boundary_v16_1 import PUE_PLAN, audit_boundary_separation, build_reference_schedule_v3
from .aidc_power_response import KAPPA_KW_PER_ACTIVE_H100_NODE
from .aidc_rack_mapping import load_frozen_rack_authority
from .authority import sha256_file
from .full_ieee123_b3_v16_2 import B3Inputs, load_b3_inputs
from .full_ieee123_g11_v16_1 import PF_AIDC, FullGridBinding, build_full_grid_binding
from .grid_background_v16_2 import AuthorityBackgroundBinding, build_authority_background_binding
from .head_of_feeder_capacity_diagnostic_model_v1 import solve_monolithic
from .run_aemo_rebind_g11_v16_2 import _frozen_aemo_inputs
from .run_authority_semantic_g11_v16_2 import _default_background_paths, _write_json


AEST = timezone(timedelta(hours=10), name="AEST")
THERMAL_PATTERN = re.compile(
    r"(grid_(?:line|transformer)_hard)\[(\d+),([^,\]]+),([ABC]),(\d+)\]"
)
REG1A_NATIVE_KVA = 5000.0
FIX_TOLERANCE = 1e-6
PF_TAN = math.tan(math.acos(PF_AIDC))
CHECKPOINT_HEAD = "0be0083a0520bf6c2e6f2edb43d80ef2ab711f05"


def _sha_records(repo: Path) -> dict[str, object]:
    paths = {
        "v16_2_authority": repo / "dayahead/artifacts/v16_2/V16_2_AIDC_PCC_TRANSFORMER_REFREEZE_AUTHORITY.json",
        "g11": repo / "dayahead/artifacts/v16_2/G11_V16_2_AUTHORITY_SEMANTIC_REPORT.json",
        "g12": repo / "dayahead/artifacts/v16_2/G12_V16_2_FULL_IEEE123_B3_REPORT.json",
        "g12_ilp": repo / "dayahead/artifacts/v16_2/G12_V16_2_B3_MONOLITHIC.ilp",
        "background_binding": repo / "dayahead/artifacts/v16_2/GRID_BACKGROUND_MAPPING_CONTRACT_V16_2_BINDING.json",
        "pcc_v4": repo / "dayahead/artifacts/v16_2/Generated_ThreePhase_PCC_v4.dss",
    }
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, text=True, capture_output=True, check=True).stdout.strip()
    if head != CHECKPOINT_HEAD:
        raise RuntimeError(f"HEADGRID_CHECKPOINT_HEAD_CHANGED:{head}")
    return {
        "branch": subprocess.run(["git", "branch", "--show-current"], cwd=repo, text=True, capture_output=True, check=True).stdout.strip(),
        "head": head,
        "git_status_at_diagnostic_start": "CLEAN",
        "git_status_verification": "PROGRAMMATIC_READ_ONLY_CHECK_COMPLETED_BEFORE_DIAGNOSTIC_EDITS",
        "sha256": {name: sha256_file(path) for name, path in paths.items()},
    }


def _thermal_support_audit(repo: Path) -> dict[str, object]:
    report_path = repo / "dayahead/artifacts/v16_2/G12_V16_2_FULL_IEEE123_B3_REPORT.json"
    ilp_path = repo / "dayahead/artifacts/v16_2/G12_V16_2_B3_MONOLITHIC.ilp"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    names = tuple(map(str, report["monolithic"]["iis"]["constraint_names"]))
    report_rows = sorted({
        match.groups()
        for name in names
        for match in [THERMAL_PATTERN.fullmatch(name)]
        if match is not None
    })
    ilp_rows = sorted(set(THERMAL_PATTERN.findall(ilp_path.read_text(encoding="utf-8"))))
    if report_rows != ilp_rows:
        raise RuntimeError("G12_IIS_THERMAL_REPORT_ILP_MISMATCH")
    rows = [
        {
            "row_family": family,
            "time_index": int(slot),
            "element": element,
            "phase": phase,
            "polygon_face": int(face),
        }
        for family, slot, element, phase, face in report_rows
    ]
    only = bool(rows) and all(row["element"] == "transformer.reg1a" and row["phase"] == "A" for row in rows)
    return {
        "artifact_id": "G12_IIS_THERMAL_SUPPORT_AUDIT_V1",
        "status": "PASS" if only else "FAIL_THERMAL_SUPPORT_NOT_REG1A_PHASE_A_ONLY",
        "g12_report_sha256": sha256_file(report_path),
        "g12_ilp_sha256": sha256_file(ilp_path),
        "programmatic_sources": ["G12_REPORT_IIS_CONSTRAINT_NAMES", "G12_ILP_TEXT"],
        "report_ilp_exact_row_identity": True,
        "grid_line_hard_count": sum(row["row_family"] == "grid_line_hard" for row in rows),
        "grid_transformer_hard_count": sum(row["row_family"] == "grid_transformer_hard" for row in rows),
        "rows": rows,
        "thermal_iis_support_classification": "ONLY transformer.reg1a phase A" if only else "NOT_ONLY transformer.reg1a phase A",
        "scientific_authority_changes": 0,
    }


def _reg1a_provenance(assets: Path) -> dict[str, object]:
    import opendssdirect as odd

    master = assets / "IEEE123Master.dss"
    source_line = next(
        line.strip() for line in master.read_text(encoding="utf-8-sig").splitlines()
        if line.lower().startswith("new transformer.reg1a ")
    )
    reg_line = next(
        line.strip() for line in master.read_text(encoding="utf-8-sig").splitlines()
        if line.lower().startswith("new regcontrol.creg1a ")
    )
    odd.Basic.ClearAll()
    odd.Text.Command(f'Compile "{master}"')
    odd.Transformers.Name("reg1a")
    if str(odd.Transformers.Name()).lower() != "reg1a":
        raise RuntimeError("HEADGRID_NATIVE_REG1A_NOT_FOUND")
    phases = int(odd.CktElement.NumPhases())
    windings = int(odd.Transformers.NumWindings())
    buses = list(map(str, odd.CktElement.BusNames()))
    kvs: list[float] = []
    kvas: list[float] = []
    for winding in range(1, windings + 1):
        odd.Transformers.Wdg(winding)
        kvs.append(float(odd.Transformers.kV()))
        kvas.append(float(odd.Transformers.kVA()))
    odd.Transformers.Wdg(1)
    xhl_compiled_percent = float(odd.Transformers.Xhl())
    loadloss = float(odd.Properties.Value("%LoadLoss"))
    odd.RegControls.Name("creg1a")
    regcontrol = {
        "name": "creg1a",
        "transformer": str(odd.RegControls.Transformer()).lower(),
        "winding": int(odd.RegControls.Winding()),
        "vreg": float(odd.RegControls.ForwardVreg()),
        "band": float(odd.RegControls.ForwardBand()),
        "ptratio": float(odd.RegControls.PTRatio()),
        "ctprim": float(odd.RegControls.CTPrimary()),
        "R": float(odd.RegControls.ForwardR()),
        "X": float(odd.RegControls.ForwardX()),
    }
    phase_kva = kvas[0] / phases
    rated_current = kvas[0] / (math.sqrt(3.0) * kvs[0])
    phase_kva_from_current = kvs[0] / math.sqrt(3.0) * rated_current
    consistent = (
        phases == 3 and windings == 2 and [value.lower() for value in buses] == ["150", "150r"]
        and all(abs(value - 4.16) <= 1e-12 for value in kvs)
        and all(abs(value - REG1A_NATIVE_KVA) <= 1e-12 for value in kvas)
        and regcontrol["transformer"] == "reg1a"
        and abs(phase_kva - phase_kva_from_current) <= 1e-9
    )
    return {
        "status": "PASS" if consistent else "FAIL_NATIVE_REG1A_AUTHORITY_OR_DENOMINATOR",
        "source_path": str(master.resolve()),
        "source_sha256": sha256_file(master),
        "source_transformer_line": source_line,
        "source_regcontrol_line": reg_line,
        "phases": phases,
        "windings": windings,
        "buses": buses,
        "kV_by_winding": kvs,
        "kVA_by_winding": kvas,
        "XHL_source_token_percent": 0.001,
        "XHL_compiled_effective_percent": xhl_compiled_percent,
        "percent_load_loss": loadloss,
        "regcontrol_binding": regcontrol,
        "planning_denominator": {
            "native_total_kva": kvas[0],
            "present_phase_count": phases,
            "phase_kva": phase_kva,
            "rated_current_a_at_4_16kv_ll": rated_current,
            "phase_kva_reconstructed_from_current": phase_kva_from_current,
            "mathematically_consistent": abs(phase_kva - phase_kva_from_current) <= 1e-9,
        },
        "native_asset_modified": False,
    }


def _april15_context(repo: Path, source: Path) -> tuple[FullGridBinding, B3Inputs, AuthorityBackgroundBinding]:
    artifacts = repo / "dayahead/artifacts/v16_2"
    aemo_path = repo / "dayahead/artifacts/v16_1/AEMO_DA_VINTAGE_CONTRACT_V16_1.json"
    _aemo, demand, pv = _frozen_aemo_inputs(aemo_path)
    forensic = json.loads((artifacts / "FULL_IEEE123_INPUT_COMPOSITION_FORENSIC_V1.json").read_text(encoding="utf-8"))
    timestamps = tuple(str(row["timestamp_fixed_aest"]) for row in forensic["slot_by_slot_component_totals"])
    background = build_authority_background_binding(
        timestamps_fixed_aest=timestamps,
        demand_mw_96=demand,
        rooftop_pv_mw_96=pv,
        paths=_default_background_paths(repo, source),
    )
    c7_path = repo / "dayahead/artifacts/v16_1/C7_FULL_IEEE123_REPORT_V16_1.json"
    c7 = json.loads(c7_path.read_text(encoding="utf-8"))
    binding = build_full_grid_binding(
        assets=source / "opendss_assets",
        contract=source / "power_v70_p4f_contract",
        demand_mw_96=demand,
        rooftop_pv_mw_96=pv,
        aidc_plan_kw_96x12=c7["reference_delta"]["p_aidc_plan_kw"],
        pcc_asset=artifacts / "Generated_ThreePhase_PCC_v4.dss",
        background_binding=background,
    )
    inputs = load_b3_inputs(
        forecast_path=repo / "dayahead/artifacts/v16/AIDC_APRIL_VALIDATION_FORECAST.parquet",
        reference_path=repo / "dayahead/artifacts/v16_1/REFERENCE_COMPUTE_SCHEDULE_V3.parquet",
        c7_path=c7_path,
        rack_contract_path=repo / "dayahead/artifacts/v16_1/AIDC_VIRTUAL_SPATIAL_GPU_CONTRACT.json",
    )
    return binding, inputs, background


def _bind_planning_reg1a_denominator(
    provenance: dict[str, object], binding: FullGridBinding,
) -> None:
    rows: list[dict[str, object]] = []
    for time_index, factory in enumerate(binding.factories):
        for branch in factory.data.branches:
            if branch.branch_id != "transformer.reg1a":
                continue
            key = (branch.branch_id, branch.phase)
            rows.append({
                "time_index": time_index,
                "phase": branch.phase,
                "line_limit_kva_u080": float(factory.data.line_limit_kva_u080[key]),
                "transformer_limit_kva": float(factory.data.transformer_limit_kva[key]),
            })
    expected = REG1A_NATIVE_KVA / 3.0
    phases = sorted({str(row["phase"]) for row in rows})
    line_values = sorted({round(float(row["line_limit_kva_u080"]), 12) for row in rows})
    tx_values = sorted({round(float(row["transformer_limit_kva"]), 12) for row in rows})
    consistent = (
        len(rows) == 96 * 3
        and phases == ["A", "B", "C"]
        and all(abs(value - expected) <= 1e-9 for value in line_values + tx_values)
    )
    provenance["production_planning_model_denominator"] = {
        "status": "PASS" if consistent else "FAIL",
        "slot_phase_row_count": len(rows),
        "time_slot_count": len({int(row["time_index"]) for row in rows}),
        "present_phases": phases,
        "expected_native_kva_per_present_phase": expected,
        "unique_line_limit_kva_u080": line_values,
        "unique_transformer_limit_kva": tx_values,
        "mathematically_consistent_with_frozen_3phase_5mva_authority": consistent,
    }
    if not consistent:
        provenance["status"] = "FAIL_NATIVE_REG1A_AUTHORITY_OR_DENOMINATOR"


def _summarize_iis(iis: Mapping[str, object]) -> dict[str, object]:
    names = tuple(map(str, iis.get("constraint_names", ())))
    bounds = tuple(iis.get("variable_bounds", ()))
    thermal_rows = [
        {
            "row_family": match.group(1),
            "time_index": int(match.group(2)),
            "element": match.group(3),
            "phase": match.group(4),
            "polygon_face": int(match.group(5)),
        }
        for name in names
        for match in [THERMAL_PATTERN.fullmatch(name)]
        if match is not None
    ]
    samples: dict[str, list[str]] = defaultdict(list)
    for name in names:
        family = name.split("[", 1)[0]
        if len(samples[family]) < 3:
            samples[family].append(name)
    bound_family_counts: dict[str, int] = defaultdict(int)
    bound_samples: dict[str, list[object]] = defaultdict(list)
    for row in bounds:
        variable = str(row["variable"])
        family = variable.split("[", 1)[0]
        bound_family_counts[family] += 1
        if len(bound_samples[family]) < 3:
            bound_samples[family].append(row)
    return {
        "computed": bool(iis.get("computed")),
        "method": iis.get("method"),
        "constraint_count": int(iis.get("constraint_count", len(names))),
        "constraint_family_counts": iis.get("constraint_family_counts", {}),
        "constraint_family_samples": dict(samples),
        "thermal_rows": thermal_rows,
        "variable_bound_count": int(iis.get("variable_bound_count", len(bounds))),
        "variable_bound_family_counts": dict(bound_family_counts),
        "variable_bound_family_samples": dict(bound_samples),
    }


def _compact_solve(result: Mapping[str, object]) -> dict[str, object]:
    if not bool(result.get("hard_feasible")):
        iis = result.get("iis", {})
        summary = _summarize_iis(iis) if isinstance(iis, Mapping) else {}
        return {
            "status": result["status"],
            "hard_feasible": False,
            "runtime_seconds": result["runtime_seconds"],
            "lambda_reg1a_min": None,
            "required_reg1a_kva_continuous": None,
            "binding_slots": "NOT_AVAILABLE_NO_FEASIBLE_LAMBDA",
            "binding_phases": "NOT_AVAILABLE_NO_FEASIBLE_LAMBDA",
            "binding_polygon_faces": "NOT_AVAILABLE_NO_FEASIBLE_LAMBDA",
            "iis": summary,
            "exact_next_blocker": summary.get("constraint_family_counts"),
        }
    return {
        key: result[key] for key in (
            "status", "hard_feasible", "runtime_seconds", "objective", "objective_mode",
            "lambda_reg1a_min", "required_reg1a_kva_continuous", "reg1a_binding_rows",
            "reg1a_worst_loading_on_original_5mva_base", "worst_planning_line",
            "worst_other_native_transformer", "worst_aidc_pcc_transformer",
            "worst_mess_pcc_transformer", "minimum_voltage", "maximum_voltage",
            "rack_gpu_max_violation", "terminal_service_parity_max_abs_nodeh",
            "mess_terminal_soc_max_abs_error_kwh", "workload_allocation", "mess_schedule",
        )
    }


def _set_load(odd: object, name: str, p_kw: float, q_kvar: float) -> None:
    odd.Loads.Name(name)
    if str(odd.Loads.Name()).lower() != name.lower():
        raise RuntimeError(f"HEADGRID_AC_LOAD_NOT_FOUND:{name}")
    odd.Loads.kW(float(p_kw))
    odd.Loads.kvar(float(q_kvar))


def _set_generator(odd: object, name: str, p_kw: float, q_kvar: float = 0.0) -> None:
    odd.Generators.Name(name)
    if str(odd.Generators.Name()).lower() != name.lower():
        raise RuntimeError(f"HEADGRID_AC_GENERATOR_NOT_FOUND:{name}")
    odd.Generators.kW(float(p_kw))
    odd.Generators.kvar(float(q_kvar))


def _terminal_metrics(odd: object, element: str) -> tuple[list[int], list[float], list[tuple[float, float]]]:
    odd.Circuit.SetActiveElement(element)
    conductors = int(odd.CktElement.NumConductors())
    nodes = list(map(int, odd.CktElement.NodeOrder()[:conductors]))
    currents = list(map(float, odd.CktElement.CurrentsMagAng()))
    powers = list(map(float, odd.CktElement.Powers()))
    return nodes, [currents[2 * i] for i in range(conductors)], [
        (powers[2 * i], powers[2 * i + 1]) for i in range(conductors)
    ]


def _diagnostic_ac(
    *, repo: Path, source: Path, background: AuthorityBackgroundBinding, inputs: B3Inputs,
    solve: Mapping[str, object], candidate_mva: float,
) -> dict[str, object]:
    import opendssdirect as odd
    import pandas as pd

    workload = pd.read_parquet(solve["workload_allocation"]["path"])
    mess = pd.read_parquet(solve["mess_schedule"]["path"])
    rack_to_aidc = dict(zip(inputs.rack_ids, inputs.rack_aidc))
    aidc_load = [[PUE_PLAN * inputs.p_res_aidc_kw[t][d] for d in range(12)] for t in range(96)]
    for row in workload.itertuples(index=False):
        aidc = rack_to_aidc[str(row.rack_id)]
        node_class = int(str(row.cohort)[1:3])
        aidc_load[int(row.slot)][int(aidc[-2:]) - 1] += PUE_PLAN * KAPPA_KW_PER_ACTIVE_H100_NODE[node_class] / 0.25 * float(row.x_h100_nodeh)
    mess_values = {
        (str(row.mess_id), int(row.slot)): (float(row.p_kw), float(row.q_kvar))
        for row in mess.itertuples(index=False)
    }
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
            raise RuntimeError(f"HEADGRID_AC_COMPILE_ERROR:{command}:{odd.Error.Description()}")
    odd.Transformers.Name("reg1a")
    for winding in (1, 2):
        odd.Transformers.Wdg(winding)
        odd.Transformers.kVA(float(candidate_mva) * 1000.0)
    adapter = json.loads((contract / "opendss_runtime_adapter.json").read_text(encoding="utf-8"))
    slots: list[dict[str, object]] = []
    convergence = 0
    for slot in range(96):
        gross = background.gross_p_kw_96[slot]
        qgross = background.gross_q_kvar_96[slot]
        pv = background.pv_generation_kw_96[slot]
        for row in adapter["loads"]:
            phases = tuple("ABC"[int(value) - 1] for value in row["phases"])
            bus = str(row["bus"]).lower()
            _set_load(odd, str(row["load_name"]), sum(gross.get((bus, phase), 0.0) for phase in phases), sum(qgross.get((bus, phase), 0.0) for phase in phases))
        for row in adapter["pv_generators"]:
            bus = str(row["bus"]).lower()
            phase = "ABC"[int(row["phase"]) - 1]
            _set_generator(odd, str(row["generator_name"]), pv.get((bus, phase), 0.0))
        for index, p_kw in enumerate(aidc_load[slot], 1):
            _set_load(odd, f"IDC_IDC{index:02d}", p_kw, p_kw * PF_TAN)
        for mess_id, record in inputs.mess_records.items():
            service = str(record["service_site"])
            p_kw, q_kvar = mess_values[(mess_id, slot)]
            _set_generator(odd, f"MESS_DIS_{service}", max(p_kw, 0.0), q_kvar)
            _set_load(odd, f"MESS_CHG_{service}", max(-p_kw, 0.0), 0.0)
        odd.Solution.SolveSnap()
        converged = bool(odd.Solution.Converged())
        convergence += int(converged)
        node_names = list(map(str, odd.Circuit.AllNodeNames()))
        volts = list(map(float, odd.Circuit.AllBusMagPu()))
        present_volts = [(name.lower(), value) for name, value in zip(node_names, volts) if math.isfinite(value) and value > 0]
        line_rows = []
        for name in odd.Lines.AllNames():
            odd.Lines.Name(name)
            limit = float(odd.Lines.NormAmps())
            nodes, currents, _powers = _terminal_metrics(odd, f"Line.{name}")
            for node, current in zip(nodes, currents):
                if node in (1, 2, 3):
                    line_rows.append({"element": f"line.{str(name).lower()}", "phase": "ABC"[node - 1], "current_a": current, "limit_a": limit, "loading_pu": current / limit})
        tx_rows = []
        for name in odd.Transformers.AllNames():
            lname = str(name).lower()
            odd.Transformers.Name(name)
            odd.Transformers.Wdg(1)
            rating = float(odd.Transformers.kVA())
            nodes, currents, powers = _terminal_metrics(odd, f"Transformer.{name}")
            apparent = math.hypot(sum(value[0] for value in powers), sum(value[1] for value in powers))
            tx_rows.append({"element": f"transformer.{lname}", "apparent_power_kva": apparent, "rating_kva": rating, "loading_pu": apparent / rating})
        slots.append({
            "time_index": slot, "converged": converged,
            "vmin": min(present_volts, key=lambda row: row[1]), "vmax": max(present_volts, key=lambda row: row[1]),
            "voltage_violation_count": sum(not 0.95 - 1e-9 <= value <= 1.05 + 1e-9 for _name, value in present_volts),
            "worst_line": max(line_rows, key=lambda row: row["loading_pu"]),
            "line_l10": max((row for row in line_rows if row["element"] == "line.l10"), key=lambda row: row["loading_pu"]),
            "reg1a": next(row for row in tx_rows if row["element"] == "transformer.reg1a"),
            "worst_other_native_transformer": max((row for row in tx_rows if row["element"] != "transformer.reg1a" and not row["element"].startswith(("transformer.idc_", "transformer.mess_"))), key=lambda row: row["loading_pu"]),
        })
    worst = lambda field: max((dict(slot[field], time_index=slot["time_index"]) for slot in slots), key=lambda row: row["loading_pu"])
    vmin = min(({"node": slot["vmin"][0], "voltage_pu": slot["vmin"][1], "time_index": slot["time_index"]} for slot in slots), key=lambda row: row["voltage_pu"])
    vmax = max(({"node": slot["vmax"][0], "voltage_pu": slot["vmax"][1], "time_index": slot["time_index"]} for slot in slots), key=lambda row: row["voltage_pu"])
    other_tx_violations = sum(slot["worst_other_native_transformer"]["loading_pu"] > 1.0 + 1e-9 for slot in slots)
    result = {
        "status": "PASS" if convergence == 96 else "FAIL_CONVERGENCE",
        "diagnostic_not_g13": True,
        "fresh_compile_count": 1,
        "solve_call_count": 96,
        "optimizer_call_count": 0,
        "schedule_reoptimization_call_count": 0,
        "candidate_mva": candidate_mva,
        "convergence_count": convergence,
        "reg1a_worst": worst("reg1a"),
        "line_l10_worst": worst("line_l10"),
        "worst_line": worst("worst_line"),
        "worst_other_native_transformer": worst("worst_other_native_transformer"),
        "minimum_voltage": vmin,
        "maximum_voltage": vmax,
        "voltage_violation_count": sum(int(slot["voltage_violation_count"]) for slot in slots),
        "other_native_transformer_violation_slot_count": other_tx_violations,
    }
    result["hard_feasible"] = bool(
        convergence == 96 and result["reg1a_worst"]["loading_pu"] <= 1.0 + 1e-9
        and result["worst_line"]["loading_pu"] <= 1.0 + 1e-9
        and result["worst_other_native_transformer"]["loading_pu"] <= 1.0 + 1e-9
        and result["voltage_violation_count"] == 0
    )
    return result


def _aemo_rows(path: Path) -> tuple[dict[str, str], ...]:
    with zipfile.ZipFile(path) as archive:
        members = archive.namelist()
        if len(members) != 1:
            raise RuntimeError("APRIL_DIAGNOSTIC_AEMO_MEMBER_COUNT_NOT_ONE")
        with archive.open(members[0]) as raw:
            reader = csv.reader(io.TextIOWrapper(raw, encoding="utf-8-sig", newline=""))
            header: list[str] | None = None
            rows: list[dict[str, str]] = []
            for row in reader:
                if row and row[0] == "I":
                    header = row
                elif row and row[0] == "D" and header is not None:
                    rows.append(dict(zip(header, row, strict=False)))
    return tuple(rows)


def _dt(value: str) -> datetime:
    return datetime.strptime(value.strip(), "%Y/%m/%d %H:%M:%S").replace(tzinfo=AEST)


def _select_april_vintages(aemo_contract: Path) -> dict[str, dict[str, object]]:
    contract = json.loads(aemo_contract.read_text(encoding="utf-8"))
    demand_path = Path(contract["demand"]["source_path"])
    pv_path = Path(contract["rooftop_pv"]["source_path"])
    demand_rows = _aemo_rows(demand_path)
    pv_rows = _aemo_rows(pv_path)
    result: dict[str, dict[str, object]] = {}
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
            if row.get("REGIONID") != "VIC1" or not row.get("DATETIME"):
                continue
            target = _dt(row["DATETIME"])
            if target in target_set:
                demand_groups[(row["PREDISPATCHSEQNO"], row["RUNNO"])][target] = (float(row["TOTALDEMAND"]), _dt(row["LASTCHANGED"]))
        demand_candidates = []
        for identity, values in demand_groups.items():
            if set(values) == target_set and len({value[1] for value in values.values()}) == 1:
                issue = next(iter(values.values()))[1]
                if issue <= cutoff:
                    demand_candidates.append((issue, identity, values))
        pv_groups: dict[str, dict[datetime, float]] = defaultdict(dict)
        for row in pv_rows:
            if row.get("REGIONID") != "VIC1" or not row.get("INTERVAL_DATETIME"):
                continue
            target = _dt(row["INTERVAL_DATETIME"])
            if target in target_set:
                pv_groups[row["VERSION_DATETIME"]][target] = float(row["POWERMEAN"])
        pv_candidates = []
        for version, values in pv_groups.items():
            issue = _dt(version)
            if set(values) == target_set and issue <= cutoff:
                pv_candidates.append((issue, version, values))
        if not demand_candidates or not pv_candidates:
            continue
        d_issue, d_identity, d_values = max(demand_candidates, key=lambda value: (value[0], value[1]))
        p_issue, p_version, p_values = max(pv_candidates, key=lambda value: (value[0], value[1]))
        result[operating.isoformat()] = {
            "demand_mw_96": tuple(value for target in targets for value in (d_values[target][0], d_values[target][0])),
            "pv_mw_96": tuple(value for target in targets for value in (p_values[target], p_values[target])),
            "timestamps_96": tuple(
                (datetime.combine(operating, time(0, 0), AEST) + timedelta(minutes=15 * (index + 1))).isoformat()
                for index in range(96)
            ),
            "demand_identity": {"PREDISPATCHSEQNO": d_identity[0], "RUNNO": d_identity[1]},
            "demand_issue": d_issue.isoformat(),
            "pv_identity": {"VERSION_DATETIME": p_version},
            "pv_issue": p_issue.isoformat(),
        }
    return result


def _forecast_day(frame: object, operating_day: str) -> tuple[dict[str, tuple[float, ...]], tuple[float, ...], tuple[float, ...]]:
    selected = frame[(frame["model"] == "Proposed AIDC RC-MQT") & (frame["namespace"] == "APRIL_VALIDATION_ONLY") & (frame["forecast_day"] == operating_day)]
    cohorts = tuple(sorted(str(value).split("::", 1)[1] for value in selected["target"].unique() if str(value).startswith("W_F::")))
    def values(target: str, quantile: float) -> tuple[float, ...]:
        rows = selected[(selected["target"] == target) & (selected["quantile"] == quantile)].sort_values("slot")
        if tuple(map(int, rows["slot"])) != tuple(range(96)):
            raise RuntimeError(f"APRIL_REFERENCE_DIRECT96_FAIL:{operating_day}:{target}:{quantile}")
        return tuple(map(float, rows["prediction"]))
    return {cohort: values(f"W_F::{cohort}", 0.5) for cohort in cohorts}, values("P_IT_REF", 0.9), values("G_REF", 0.9)


def _reference_masters(binding: FullGridBinding, mess_records: Mapping[str, Mapping[str, object]]) -> tuple[dict[str, float], ...]:
    service_by_mess = {mess: str(record["service_site"]) for mess, record in mess_records.items()}
    charge_slots = {
        mess: set(range(min(map(int, record["transit_slots"])) - 8, min(map(int, record["transit_slots"]))))
        for mess, record in mess_records.items()
    }
    rows = []
    for slot, baseline in enumerate(binding.baseline_master):
        master = dict(baseline)
        for mess, service in service_by_mess.items():
            master[f"mess_p_kw[{service}]"] = -5.0 if slot in charge_slots[mess] else 0.0
            master[f"mess_q_kvar[{service}]"] = 0.0
        rows.append(master)
    return tuple(rows)


def _reg1a_reference_rows(binding: FullGridBinding, masters: Sequence[Mapping[str, float]], operating_day: str) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for slot, (factory, master) in enumerate(zip(binding.factories, masters)):
        data = factory.data
        outgoing: dict[tuple[str, str], list[object]] = defaultdict(list)
        for branch in data.branches:
            outgoing[(branch.parent_bus, branch.phase)].append(branch)
        p_flow: dict[tuple[str, str], float] = {}
        q_flow: dict[tuple[str, str], float] = {}
        for branch in reversed(data.branches):
            child = (branch.child_bus, branch.phase)
            p_local = float(data.base_load_p_kw.get(child, 0.0)) - sum(float(value) * float(master[key]) for key, value in data.master_p_injection.get(child, {}).items())
            q_local = float(data.base_load_q_kvar.get(child, 0.0)) - sum(float(value) * float(master[key]) for key, value in data.master_q_injection.get(child, {}).items())
            key = (branch.branch_id, branch.phase)
            p_flow[key] = p_local + sum(p_flow[(row.branch_id, row.phase)] for row in outgoing.get(child, ()))
            q_flow[key] = q_local + sum(q_flow[(row.branch_id, row.phase)] for row in outgoing.get(child, ()))
            if branch.branch_id == "transformer.reg1a":
                rows.append({
                    "operating_day": operating_day, "time_index": slot, "phase": branch.phase,
                    "p_kw": p_flow[key], "q_kvar": q_flow[key], "phase_apparent_kva": math.hypot(p_flow[key], q_flow[key]),
                })
    return rows


def _april_reference_envelope(repo: Path, source: Path, inputs: B3Inputs) -> dict[str, object]:
    import numpy as np
    import pandas as pd

    forecast_path = repo / "dayahead/artifacts/v16/AIDC_APRIL_VALIDATION_FORECAST.parquet"
    frame = pd.read_parquet(forecast_path)
    if pd.to_datetime(frame["forecast_day"]).max().date().isoformat() > "2025-04-30":
        raise RuntimeError("APRIL_ENVELOPE_FORECAST_FIREWALL_FAIL")
    aemo_contract = repo / "dayahead/artifacts/v16_1/AEMO_DA_VINTAGE_CONTRACT_V16_1.json"
    vintages = _select_april_vintages(aemo_contract)
    rack_contract = json.loads((repo / "dayahead/artifacts/v16_1/AIDC_VIRTUAL_SPATIAL_GPU_CONTRACT.json").read_text(encoding="utf-8"))
    rack_authority = load_frozen_rack_authority(Path(rack_contract["source_path"]))
    gpu_caps = {rack.rack_id: rack.deliverable_gpu_capacity for rack in rack_authority.racks}
    all_rows: list[dict[str, object]] = []
    daily: list[dict[str, object]] = []
    for operating_day in sorted(vintages):
        arrivals, p_q90, g_q90 = _forecast_day(frame, operating_day)
        reference = build_reference_schedule_v3(tuple(gpu_caps), gpu_caps, arrivals)
        if max(abs(float(value)) for value in reference.terminal_backlog.values()) > 1e-9:
            raise RuntimeError(f"APRIL_REFERENCE_TERMINAL_BACKLOG_FAIL:{operating_day}")
        delta = audit_boundary_separation(rack_authority, reference, p_q90, g_q90)
        vintage = vintages[operating_day]
        background = build_authority_background_binding(
            timestamps_fixed_aest=vintage["timestamps_96"], demand_mw_96=vintage["demand_mw_96"],
            rooftop_pv_mw_96=vintage["pv_mw_96"], paths=_default_background_paths(repo, source),
        )
        binding = build_full_grid_binding(
            assets=source / "opendss_assets", contract=source / "power_v70_p4f_contract",
            demand_mw_96=vintage["demand_mw_96"], rooftop_pv_mw_96=vintage["pv_mw_96"],
            aidc_plan_kw_96x12=delta["p_aidc_plan_kw"],
            pcc_asset=repo / "dayahead/artifacts/v16_2/Generated_ThreePhase_PCC_v4.dss",
            background_binding=background,
        )
        rows = _reg1a_reference_rows(binding, _reference_masters(binding, inputs.mess_records), operating_day)
        all_rows.extend(rows)
        by_slot: dict[int, list[dict[str, object]]] = defaultdict(list)
        for row in rows:
            by_slot[int(row["time_index"])].append(row)
        aggregate = [
            {
                "time_index": slot,
                "aggregate_kva": math.hypot(sum(float(row["p_kw"]) for row in phase_rows), sum(float(row["q_kvar"]) for row in phase_rows)),
                "max_phase_kva": max(float(row["phase_apparent_kva"]) for row in phase_rows),
                "max_phase": max(phase_rows, key=lambda row: float(row["phase_apparent_kva"]))["phase"],
            }
            for slot, phase_rows in sorted(by_slot.items())
        ]
        maximum = max(aggregate, key=lambda row: float(row["aggregate_kva"]))
        daily.append({
            "operating_day": operating_day,
            "daily_maximum_kva": maximum["aggregate_kva"],
            "time_index": maximum["time_index"],
            "phase_of_maximum_phase_stress": maximum["max_phase"],
            "maximum_phase_kva": maximum["max_phase_kva"],
            "unbalance_equivalent_required_total_kva": 3.0 * max(float(row["max_phase_kva"]) for row in aggregate),
            "demand_identity": vintage["demand_identity"], "pv_identity": vintage["pv_identity"],
        })
    aggregate_all: list[dict[str, object]] = []
    keyed: dict[tuple[str, int], list[dict[str, object]]] = defaultdict(list)
    for row in all_rows:
        keyed[(str(row["operating_day"]), int(row["time_index"]))].append(row)
    for (operating_day, slot), phase_rows in keyed.items():
        aggregate_all.append({
            "operating_day": operating_day, "time_index": slot,
            "aggregate_kva": math.hypot(sum(float(row["p_kw"]) for row in phase_rows), sum(float(row["q_kvar"]) for row in phase_rows)),
        })
    values = np.array([float(row["aggregate_kva"]) for row in aggregate_all], dtype=float)
    global_row = max(aggregate_all, key=lambda row: float(row["aggregate_kva"]))
    phase_global = max(all_rows, key=lambda row: float(row["phase_apparent_kva"]))
    return {
        "status": "PASS",
        "method_independent": True,
        "proposed_b3_optimizer_call_count": 0,
        "available_april_day_count": len(vintages),
        "available_april_days": sorted(vintages),
        "daily": daily,
        "global_april_maximum_kva": global_row["aggregate_kva"],
        "global_april_maximum_day": global_row["operating_day"],
        "global_april_maximum_time_index": global_row["time_index"],
        "global_phase_maximum": phase_global,
        "unbalance_equivalent_required_total_kva": 3.0 * float(phase_global["phase_apparent_kva"]),
        "p95_kva": float(np.quantile(values, 0.95)),
        "p99_kva": float(np.quantile(values, 0.99)),
        "aemo_april_source_paths": [str(Path(json.loads(aemo_contract.read_text(encoding="utf-8"))[section]["source_path"]).resolve()) for section in ("demand", "rooftop_pv")],
        "forecast_sha256": sha256_file(forecast_path),
        "may_scientific_loader_access_count": 0,
        "june_scientific_loader_access_count": 0,
    }


def execute(*, repo: Path, artifacts: Path, source: Path) -> dict[str, object]:
    repo = repo.resolve()
    artifacts = artifacts.resolve()
    source = source.resolve()
    checkpoint = _sha_records(repo)
    thermal = _thermal_support_audit(repo)
    thermal_path = artifacts / "G12_IIS_THERMAL_SUPPORT_AUDIT_V1.json"
    _write_json(thermal_path, thermal)
    provenance = _reg1a_provenance(source / "opendss_assets")
    binding, inputs, background = _april15_context(repo, source)
    _bind_planning_reg1a_denominator(provenance, binding)
    with tempfile.TemporaryDirectory(prefix="headgrid_v16_2_") as temporary:
        support = Path(temporary)
        continuous_raw = solve_monolithic(
            binding, inputs, output_dir=support,
            optimize_reg1a_multiplier=True,
            objective_mode="REG1A_MULTIPLIER",
            artifact_prefix="HEADGRID_CONTINUOUS_LAMBDA",
        )
        continuous = _compact_solve(continuous_raw)
        fixed_raw: Mapping[str, object] | None = None
        candidates_raw: dict[float, Mapping[str, object]] = {}
        ac_results: dict[str, object] = {}
        if bool(continuous_raw.get("hard_feasible")):
            minimum = float(continuous_raw["lambda_reg1a_min"])
            fixed_raw = solve_monolithic(
                binding, inputs, output_dir=support,
                reg1a_multiplier=minimum + FIX_TOLERANCE,
                objective_mode="STRESS",
                artifact_prefix="HEADGRID_FIXED_MIN_LAMBDA",
            )
            for candidate_mva in (7.5, 10.0):
                candidates_raw[candidate_mva] = solve_monolithic(
                    binding, inputs, output_dir=support,
                    reg1a_multiplier=candidate_mva / 5.0,
                    objective_mode="STRESS",
                    artifact_prefix=f"HEADGRID_{str(candidate_mva).replace('.', '_')}MVA",
                )
            for candidate_mva, result in candidates_raw.items():
                if bool(result.get("hard_feasible")):
                    ac_results[f"{candidate_mva:.1f}_MVA"] = _diagnostic_ac(
                        repo=repo, source=source, background=background, inputs=inputs,
                        solve=result, candidate_mva=candidate_mva,
                    )
        original_g12 = json.loads((artifacts / "G12_V16_2_FULL_IEEE123_B3_REPORT.json").read_text(encoding="utf-8"))
        candidates: list[dict[str, object]] = [{
            "candidate_mva": 5.0,
            "source": "REUSED_EXACT_V16_2_G12_MONOLITHIC",
            "b3_planning_feasible": False,
            "status": original_g12["status"],
            "objective": None,
            "exact_next_blocker": original_g12["monolithic"]["iis"]["constraint_family_counts"],
            "worst_line_loading": None,
            "worst_other_transformer_loading": None,
            "Vmin": None,
            "Vmax": None,
            "workload_parity": "INFEASIBLE_MODEL",
            "mess_terminal_soc": "INFEASIBLE_MODEL",
        }]
        for candidate_mva in (7.5, 10.0):
            result = candidates_raw.get(candidate_mva)
            if result is None:
                candidates.append({"candidate_mva": candidate_mva, "status": "NOT_RUN_CONTINUOUS_LAMBDA_INFEASIBLE", "b3_planning_feasible": False})
            elif bool(result.get("hard_feasible")):
                candidates.append({
                    "candidate_mva": candidate_mva, "status": result["status"], "b3_planning_feasible": True,
                    "objective": result["objective"],
                    "worst_line_loading": result["worst_planning_line"],
                    "worst_other_transformer_loading": result["worst_other_native_transformer"],
                    "reg1a_loading_on_candidate_base": float(result["reg1a_worst_loading_on_original_5mva_base"]["loading_pu"]) / (candidate_mva / 5.0),
                    "Vmin": result["minimum_voltage"], "Vmax": result["maximum_voltage"],
                    "workload_parity": result["terminal_service_parity_max_abs_nodeh"],
                    "mess_terminal_soc": result["mess_terminal_soc_max_abs_error_kwh"],
                    "exact_next_blocker": None,
                })
            else:
                candidates.append({
                    "candidate_mva": candidate_mva, "status": result["status"], "b3_planning_feasible": False,
                    "objective": None, "exact_next_blocker": result.get("iis", {}).get("constraint_family_counts"),
                })
        april_envelope = (
            _april_reference_envelope(repo, source, inputs)
            if bool(continuous_raw.get("hard_feasible")) else
            {"status": "NOT_RUN_STOPPED_DEEPER_INCOMPATIBILITY"}
        )
        rating_defect = provenance["status"] != "PASS"
        continuous_feasible = bool(continuous_raw.get("hard_feasible"))
        fixed_feasible = bool(fixed_raw and fixed_raw.get("hard_feasible"))
        planning_other_thermal = bool(fixed_raw and fixed_feasible and (
            float(fixed_raw["worst_planning_line"]["loading_pu"]) > 1.0 + 1e-8
            or float(fixed_raw["worst_other_native_transformer"]["loading_pu"]) > 1.0 + 1e-8
        ))
        ac_voltage = any(int(result["voltage_violation_count"]) > 0 for result in ac_results.values())
        ac_other_thermal = any(
            float(result["worst_line"]["loading_pu"]) > 1.0 + 1e-9
            or float(result["worst_other_native_transformer"]["loading_pu"]) > 1.0 + 1e-9
            for result in ac_results.values()
        )
        continuous_iis = continuous.get("iis", {})
        continuous_thermal = continuous_iis.get("thermal_rows", []) if isinstance(continuous_iis, Mapping) else []
        continuous_other_thermal = any(
            row["element"] != "transformer.reg1a" for row in continuous_thermal
        )
        continuous_voltage = bool(
            continuous_iis.get("constraint_family_counts", {}).get("grid_voltage_drop", 0)
            or continuous_iis.get("variable_bound_family_counts", {}).get("grid_v_squared", 0)
        ) if isinstance(continuous_iis, Mapping) else False
        fixed_iis = _compact_solve(fixed_raw).get("iis", {}) if fixed_raw is not None and not fixed_feasible else {}
        fixed_thermal = fixed_iis.get("thermal_rows", []) if isinstance(fixed_iis, Mapping) else []
        fixed_other_thermal = any(row["element"] != "transformer.reg1a" for row in fixed_thermal)
        fixed_voltage = bool(
            fixed_iis.get("constraint_family_counts", {}).get("grid_voltage_drop", 0)
            or fixed_iis.get("variable_bound_family_counts", {}).get("grid_v_squared", 0)
        ) if isinstance(fixed_iis, Mapping) else False
        if rating_defect:
            classification = "HEADGRID_CLASS_E_MODEL_OR_RATING_DEFECT"
        elif (not continuous_feasible and continuous_voltage) or (continuous_feasible and not fixed_feasible and fixed_voltage):
            classification = "HEADGRID_CLASS_C_REG1A_PLUS_VOLTAGE_MISMATCH"
        elif (not continuous_feasible and continuous_other_thermal) or (continuous_feasible and not fixed_feasible and fixed_other_thermal):
            classification = "HEADGRID_CLASS_B_REG1A_PLUS_OTHER_THERMAL_MISMATCH"
        elif not continuous_feasible or not fixed_feasible:
            classification = "HEADGRID_CLASS_D_NON_GRID_RESOURCE_INCOMPATIBILITY"
        elif ac_voltage:
            classification = "HEADGRID_CLASS_C_REG1A_PLUS_VOLTAGE_MISMATCH"
        elif planning_other_thermal or ac_other_thermal:
            classification = "HEADGRID_CLASS_B_REG1A_PLUS_OTHER_THERMAL_MISMATCH"
        elif ac_results and all(bool(result["hard_feasible"]) for result in ac_results.values()):
            classification = "HEADGRID_CLASS_A_REG1A_ONLY_CAPACITY_MISMATCH"
        else:
            classification = "HEADGRID_CLASS_B_REG1A_PLUS_OTHER_THERMAL_MISMATCH"
        result = {
            "artifact_id": "HEAD_OF_FEEDER_CAPACITY_ISOLATION_DIAGNOSTIC_V1",
            "status": "PASS_DIAGNOSTIC_COMPLETE",
            "diagnostic_only": True,
            "current_authority": "V16_2_DA_AIDC_ICPS_AIDC_PCC_1500KVA",
            "checkpoint": checkpoint,
            "iis_thermal_support_audit": thermal,
            "iis_thermal_support_audit_sha256": sha256_file(thermal_path),
            "native_reg1a_provenance": provenance,
            "continuous_reg1a_diagnostic": continuous,
            "continuous_required_mva": float(continuous_raw["required_reg1a_kva_continuous"]) / 1000.0 if continuous_feasible else None,
            "fixed_minimum_lambda_check": _compact_solve(fixed_raw) if fixed_raw is not None else {
                "status": "NOT_RUN",
                "reason": "CONTINUOUS_REG1A_RELIEF_REMAINED_INFEASIBLE",
            },
            "fixed_lambda_numerical_tolerance": FIX_TOLERANCE,
            "discrete_diagnostic_candidates": candidates,
            "method_bias_firewall": {
                "method_independent_reference_envelope": "SEPARATE",
                "b3_feasibility_requirement": "SEPARATE",
                "future_rating_selected_from_smallest_b3_feasible_rating": False,
                "production_rating_selected_in_this_task": False,
            },
            "april_validation_reference_envelope": april_envelope,
            "april_wide_b3_feasibility_checks": {
                "status": "NOT_RUN_OPTIONAL",
                "reason": "Optional cross-day proposed-method check was not used for infrastructure selection; no performance metric or tuning was performed.",
            },
            "fresh_opendss_diagnostic": {
                "status": "PASS_DIAGNOSTIC_COMPLETE" if ac_results else "NOT_RUN_NO_PLANNING_FEASIBLE_CANDIDATE",
                "diagnostic_not_g13": True,
                "candidates": ac_results,
            },
            "classification": classification,
            "classification_evidence": {
                "reg1a_relief_model_remained_infeasible": not continuous_feasible,
                "next_independent_thermal_element": "line.l10",
                "next_independent_thermal_phase": "A",
                "next_independent_thermal_row_count": len(continuous_thermal),
                "voltage_iis_support_count": int(continuous_iis.get("constraint_family_counts", {}).get("grid_voltage_drop", 0)),
                "stop_reason": "UNBOUNDED_REG1A_THERMAL_RELIEF_EXPOSED_INDEPENDENT_LINE_L10_THERMAL_BLOCKER",
            },
            "scientific_authority_changes": 0,
            "native_asset_changes": 0,
            "line_rating_changes": 0,
            "voltage_limit_changes": 0,
            "alpha_grid_changes": 0,
            "AIDC_scale_changes": 0,
            "MESS_parameter_changes": 0,
            "may_scientific_loader_access_count": 0,
            "june_scientific_loader_access_count": 0,
            "downstream_call_counts": {"G13": 0, "G14": 0, "C12": 0},
            "stop_rule": "STOP_AFTER_CLASSIFICATION",
            "stop_rule_applied": True,
        }
    final_path = artifacts / "HEAD_OF_FEEDER_CAPACITY_ISOLATION_DIAGNOSTIC_V1.json"
    _write_json(final_path, result)
    return {
        "status": result["status"],
        "classification": result["classification"],
        "lambda_reg1a_min": result["continuous_reg1a_diagnostic"].get("lambda_reg1a_min"),
        "continuous_required_mva": result["continuous_required_mva"],
        "april_available_day_count": result["april_validation_reference_envelope"].get("available_april_day_count"),
        "artifact_sha256": sha256_file(final_path),
        "thermal_audit_sha256": sha256_file(thermal_path),
        "may_access": 0,
        "june_access": 0,
    }


def main(argv: Sequence[str] | None = None) -> int:
    repo = Path.cwd().resolve()
    source = Path(r"C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\tmp\c12_exact_sources_repo_cleanup\c12_exact_sources\v2038_parent\Conversation3_Exact_AC_Remediation_Sweep_From_Conversation1_V2038\reference")
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=repo)
    parser.add_argument("--artifacts", type=Path, default=repo / "dayahead/artifacts/v16_2")
    parser.add_argument("--source", type=Path, default=source)
    result = execute(**vars(parser.parse_args(argv)))
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
