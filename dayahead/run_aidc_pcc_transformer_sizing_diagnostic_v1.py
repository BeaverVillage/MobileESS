"""V16.2 April-only AIDC PCC transformer sizing diagnostic.

This module is deliberately outside the active scientific authority.  It
reads the frozen April forecast and V16.1 resource authorities, computes a
resource-only apparent-power envelope, and stops without invoking any grid,
MESS, OpenDSS, Benders, or production-freeze workflow.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import zipfile
from hashlib import sha256
from pathlib import Path
from typing import Mapping, Sequence
from xml.etree import ElementTree

from .aidc_boundary_v16_1 import (
    DT_HOURS,
    PUE_PLAN,
    aidc_power_spatial_weights,
    build_reference_schedule_v3,
)
from .aidc_power_response import GPU_PER_NODE, KAPPA_KW_PER_ACTIVE_H100_NODE
from .aidc_rack_mapping import FrozenRackAuthority, load_frozen_rack_authority


AUTHORITY_ID = "V16_2_AIDC_PCC_TRANSFORMER_SIZING_DIAGNOSTIC_V1"
CURRENT_SCIENTIFIC_AUTHORITY = "V16_1_DA_AIDC_ICPS_BOUNDARYSEP"
PF_PLAN = 0.95
EXPECTED_DSS_SHA256 = "3c3e27020e266dc8f1c4e28e90d49f298d6ca741ef6b54599e44265882cd747c"
EXPECTED_GRID_RESULT_SHA256 = "19d21c1311f1d05fbe826639a0ec3d3a6a8f87bd25f8829e6d826e91cd117f98"
EXPECTED_RATINGS = (
    ("P525_S650", 525.0, 650.0),
    ("P525_S675", 525.0, 675.0),
    ("P525_S700", 525.0, 700.0),
)
TOLERANCE = 1e-9


def sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(
        (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
    )
    temporary.replace(path)


def _git(repo: Path, *arguments: str) -> str:
    return subprocess.run(
        ("git", *arguments), cwd=repo, check=True, text=True, capture_output=True
    ).stdout.strip()


def linear_quantile(values: Sequence[float], probability: float) -> float:
    """NumPy-compatible linear quantile without a numerical dependency."""

    if not values or not 0.0 <= probability <= 1.0:
        raise ValueError("INVALID_QUANTILE_INPUT")
    ordered = sorted(map(float, values))
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def maximize_flexible_power_kw(
    cumulative_arrivals: Mapping[str, float], node_hour_capacity: float
) -> tuple[float, float, dict[str, float]]:
    """Solve the one-slot resource LP exactly by descending Dataset312 kappa.

    Every cohort consumes one H100-node-hour of the same GPU resource per
    allocated node-hour, so the continuous knapsack ordering by kappa is the
    exact optimum.  No power, transformer, network, or outcome constraint is
    present.
    """

    if node_hour_capacity < -TOLERANCE or any(float(value) < -TOLERANCE for value in cumulative_arrivals.values()):
        raise ValueError("INVALID_RESOURCE_ENVELOPE_INPUT")
    remaining = max(0.0, float(node_hour_capacity))
    allocation: dict[str, float] = {cohort: 0.0 for cohort in cumulative_arrivals}
    power_kw = 0.0
    ordered = sorted(
        cumulative_arrivals,
        key=lambda cohort: (-KAPPA_KW_PER_ACTIVE_H100_NODE[int(cohort[1:3])], cohort),
    )
    for cohort in ordered:
        served = min(remaining, max(0.0, float(cumulative_arrivals[cohort])))
        allocation[cohort] = served
        power_kw += KAPPA_KW_PER_ACTIVE_H100_NODE[int(cohort[1:3])] * served / DT_HOURS
        remaining -= served
        if remaining <= TOLERANCE:
            break
    served_total = sum(allocation.values())
    return power_kw, served_total, allocation


def _docx_text(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        root = ElementTree.fromstring(archive.read("word/document.xml"))
    paragraphs: list[str] = []
    for paragraph in root.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p"):
        paragraphs.append("".join(paragraph.itertext()))
    return "\n".join(paragraphs)


def _dss_audit(path: Path) -> dict[str, object]:
    actual_sha = sha256_file(path)
    if actual_sha != EXPECTED_DSS_SHA256:
        raise RuntimeError("PCC_DSS_SHA_MISMATCH")
    text = path.read_text(encoding="utf-8-sig")
    aidc_transformers = re.findall(r"(?im)^New\s+Transformer\.IDC_IDC\d{2}_TX\b", text)
    mess_transformers = re.findall(r"(?im)^New\s+Transformer\.MESS_(?:IDC|STA)\d{2}_TX\b", text)
    ratios = re.findall(r"(?im)^~\s*kVs=\[4\.16\s+0\.48\]\s+kVAs=\[750\s+750\]\s*$", text)
    if (len(aidc_transformers), len(mess_transformers), len(ratios)) != (12, 24, 36):
        raise RuntimeError("PCC_DSS_TRANSFORMER_TEMPLATE_MISMATCH")
    return {
        "path": str(path.resolve()),
        "bytes": path.stat().st_size,
        "sha256": actual_sha,
        "aidc_transformer_count": len(aidc_transformers),
        "mess_transformer_count": len(mess_transformers),
        "common_rating_kva": 750.0,
        "primary_secondary_kv": [4.16, 0.48],
        "matching_750_kva_4_16_0_48_templates": len(ratios),
        "asset_role": "SYNTHETIC_DEDICATED_PCC_INTERFACE_ASSET",
    }


def _historical_grid_audit(root: Path) -> dict[str, object]:
    result_path = root / "EXPANDED_KVA_MARGIN_SEARCH_RESULT.json"
    manifest_path = root / "stage_manifest.json"
    prepared_path = root / "PREPARED_EXPANDED_MARGIN_INPUTS.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    prepared = json.loads(prepared_path.read_text(encoding="utf-8"))
    recovered = tuple(
        (str(row["rating_id"]), float(row["pmax_kw"]), float(row["smax_kva"]))
        for row in result["ratings_tested"]
    )
    if recovered != EXPECTED_RATINGS or sha256_file(result_path) != EXPECTED_GRID_RESULT_SHA256:
        raise RuntimeError("V2_0_22_EXACT_GRID_MISMATCH")
    fixed_aidc = prepared["transformer_contract"]["final_nameplate_kva_by_idc"]
    if set(map(float, fixed_aidc.values())) != {750.0}:
        raise RuntimeError("V2_0_22_AIDC_TRANSFORMER_CONTEXT_MISMATCH")
    return {
        "status": "PRIOR_KVA_GRID_RECOVERED",
        "stage_id": "stage_expanded_kva_margin_search_prefreeze_v2_0_22",
        "version": manifest["version"],
        "purpose_verbatim": manifest["purpose"],
        "scope_classification": "MESS_MOBILE_ESS_PCS_P_S_CAPABILITY_SEARCH_NOT_AIDC_PCC_TRANSFORMER_NAMEPLATE_GRID",
        "scope_evidence": {
            "candidate_design": "525-kW PCS at 650/675/700 kVA",
            "aidc_pcc_transformer_context_kva": fixed_aidc,
            "mess_count_changed": bool(result["MESS_count_changed"]),
            "idc_phase_allocations_used": True,
        },
        "source_files": [
            {"path": str(result_path.resolve()), "sha256": sha256_file(result_path), "bytes": result_path.stat().st_size},
            {"path": str(manifest_path.resolve()), "sha256": sha256_file(manifest_path), "bytes": manifest_path.stat().st_size},
            {"path": str(prepared_path.resolve()), "sha256": sha256_file(prepared_path), "bytes": prepared_path.stat().st_size},
        ],
        "ratings": [
            {"scenario_id": scenario, "pmax_kw": pmax, "smax_kva": smax}
            for scenario, pmax, smax in recovered
        ],
        "selected_prefreeze_candidate_in_source": result["selected_prefreeze_candidate"],
        "electrical_rating_phase_prefreeze_authorized": bool(result["electrical_rating_phase_prefreeze_authorized"]),
        "candidate_selected_before_2025_outcomes": False,
        "pre_2025_outcome_evidence": {
            "reason": "Source was created after 2025 and its prepared state bundle explicitly includes 2025 operating states.",
            "source_created_at_utc": json.loads((root / "_RESULT.json").read_text(encoding="utf-8"))["created_at_utc"],
            "prepared_state_ids": [row["state_id"] for row in prepared["states"]],
        },
        "candidate_use_in_this_diagnostic": "NUMERIC_COVERAGE_COMPARATOR_ONLY_NOT_AIDC_TRANSFORMER_AUTHORITY",
    }


def _provenance_audit(
    *, repo: Path, transformer_authority: Path, pcc_dss: Path, v14_spec: Path,
    g11_failure: Path, v16_1_authority: Path, git_status_before: str,
) -> dict[str, object]:
    authority = json.loads(transformer_authority.read_text(encoding="utf-8"))
    if authority.get("rating_kVA") != 750.0 or authority.get("measured_DNSP_nameplate_claimed") is not False:
        raise RuntimeError("TRANSFORMER_SCENARIO_AUTHORITY_MISMATCH")
    text = " ".join(_docx_text(v14_spec).split())
    required_fragments = (
        "Common synthetic transformer scenario authority",
        "rating=750 kVA",
        "actual_DNSP_nameplate_claim=false",
        "IDC_specific_deployment_sizing=DEFERRED_TO_DEPLOYMENT_SENSITIVITY",
        "4.16 kV IEEE123 three-phase host bus",
        "750 kVA, 4.16/0.48 kV IDC transformer",
    )
    missing = [fragment for fragment in required_fragments if fragment not in text]
    if missing:
        raise RuntimeError(f"V14_2_TRANSFORMER_PROVENANCE_TEXT_MISSING:{missing}")
    dss = _dss_audit(pcc_dss)
    head = _git(repo, "rev-parse", "HEAD")
    preserved = {
        "g11_failure_artifact": {"path": str(g11_failure.resolve()), "sha256": sha256_file(g11_failure)},
        "v16_1_active_authority": {"path": str(v16_1_authority.resolve()), "sha256": sha256_file(v16_1_authority)},
        "generated_three_phase_pcc_v3": {"path": str(pcc_dss.resolve()), "sha256": sha256_file(pcc_dss)},
        "transformer_scenario_authority": {
            "path": str(transformer_authority.resolve()), "sha256": sha256_file(transformer_authority)
        },
    }
    return {
        "artifact_id": "AIDC_PCC_TRANSFORMER_PROVENANCE_AUDIT_V1",
        "status": "PASS_PROVENANCE_DIAGNOSTIC_ONLY",
        "current_scientific_authority": CURRENT_SCIENTIFIC_AUTHORITY,
        "repository": {
            "head": head,
            "branch": _git(repo, "branch", "--show-current"),
            "working_tree_clean": not bool(git_status_before),
            "git_status_porcelain": git_status_before.splitlines(),
        },
        "scenario_authority": {
            "rating_kva": 750.0,
            "interpretation": authority["interpretation"],
            "synthetic_engineering_scenario": True,
            "actual_dnsp_nameplate_claim": False,
            "common_to_prior_aidc_and_mess_pccs": True,
            "deployment_specific_sizing_scope": authority["deployment_specific_sizing_scope"],
            "deployment_sizing_was_deferred": True,
            "physical_installed_rating_inferred": False,
        },
        "v14_2_evidence": {
            "path": str(v14_spec.resolve()),
            "sha256": sha256_file(v14_spec),
            "bytes": v14_spec.stat().st_size,
            "required_provenance_fragments_present": list(required_fragments),
        },
        "generated_interface_asset": dss,
        "mess_transformer": {
            "rating_kva": 750.0,
            "status": "UNCHANGED",
            "reason": "MESS PCS remains 700 kVA; MESS authority is outside this diagnostic.",
        },
        "preserved_evidence": preserved,
        "preserved_evidence_sha_unchanged": all(Path(row["path"]).is_file() and sha256_file(Path(row["path"])) == row["sha256"] for row in preserved.values()),
        "scientific_authority_change_count": 0,
        "may_scientific_loader_access_count": 0,
        "june_scientific_loader_access_count": 0,
    }


def _locus(rows: Sequence[dict[str, object]], field: str) -> dict[str, object]:
    selected = max(rows, key=lambda row: float(row[field]))
    return {
        "aidc_id": selected["aidc_id"],
        "operating_day": selected["operating_day"],
        "slot": selected["slot"],
        "timestamp_fixed_aest": selected["timestamp_fixed_aest"],
        field: selected[field],
    }


def _stats(rows: Sequence[dict[str, object]], field: str) -> dict[str, float]:
    values = [float(row[field]) for row in rows]
    return {
        "max_kva": max(values),
        "p95_kva": linear_quantile(values, 0.95),
        "p99_kva": linear_quantile(values, 0.99),
    }


def execute(
    *, repo: Path, forecast: Path, rack_source: Path, transformer_authority: Path,
    pcc_dss: Path, v14_spec: Path, historical_grid_root: Path, artifacts: Path,
) -> dict[str, object]:
    import pandas as pd

    repo = repo.resolve()
    artifacts = artifacts.resolve()
    git_status_before = _git(repo, "status", "--porcelain=v1")
    g11_failure = repo / "dayahead/artifacts/v16_1/G11_V16_1_FULL_IEEE123_AEMO_REBIND_REPORT.json"
    v16_1_authority = repo / "dayahead/artifacts/v16_1/V16_1_AIDC_POWER_BOUNDARY_REFREEZE_AUTHORITY.json"
    provenance = _provenance_audit(
        repo=repo, transformer_authority=transformer_authority, pcc_dss=pcc_dss,
        v14_spec=v14_spec, g11_failure=g11_failure, v16_1_authority=v16_1_authority,
        git_status_before=git_status_before,
    )
    historical = _historical_grid_audit(historical_grid_root)
    frame = pd.read_parquet(forecast)
    forbidden = frame[~frame["forecast_day"].between("2025-04-01", "2025-04-30")]
    if not forbidden.empty:
        raise RuntimeError("MAY_JUNE_OR_NON_APRIL_FORECAST_ROW_PROHIBITED")
    frame = frame[(frame["namespace"] == "APRIL_VALIDATION_ONLY") & (frame["model"] == "Proposed AIDC RC-MQT")]
    days = tuple(sorted(map(str, frame["forecast_day"].unique())))
    expected_days = tuple(f"2025-04-{day:02d}" for day in range(1, 31))
    if days != expected_days:
        raise RuntimeError("APRIL_VALIDATION_DAY_COVERAGE_MISMATCH")
    cohorts = tuple(sorted(str(target).split("::", 1)[1] for target in frame["target"].unique() if str(target).startswith("W_F::")))
    authority: FrozenRackAuthority = load_frozen_rack_authority(rack_source)
    rack_ids = tuple(rack.rack_id for rack in authority.racks)
    gpu_caps = {rack.rack_id: rack.deliverable_gpu_capacity for rack in authority.racks}
    aidc_ids, aidc_power_weights = aidc_power_spatial_weights(authority)
    rack_indices = {
        aidc: tuple(index for index, rack in enumerate(authority.racks) if rack.aidc_id == aidc)
        for aidc in aidc_ids
    }

    rows: list[dict[str, object]] = []
    daily: list[dict[str, object]] = []
    p_res_min = math.inf
    g_res_min = math.inf
    terminal_backlog_max = 0.0
    one_slot_service_slack_min = math.inf
    for day in days:
        selected = frame[frame["forecast_day"] == day]

        def values(target: str, quantile: float) -> tuple[float, ...]:
            subset = selected[(selected["target"] == target) & (selected["quantile"] == quantile)].sort_values("slot")
            if tuple(map(int, subset["slot"])) != tuple(range(96)):
                raise RuntimeError(f"APRIL_DIRECT96_AXIS_MISMATCH:{day}:{target}:{quantile}")
            return tuple(map(float, subset["prediction"]))

        arrivals = {cohort: values(f"W_F::{cohort}", 0.5) for cohort in cohorts}
        p_it_ref = values("P_IT_REF", 0.9)
        g_ref = values("G_REF", 0.9)
        reference = build_reference_schedule_v3(rack_ids, gpu_caps, arrivals)
        terminal_backlog = sum(map(float, reference.terminal_backlog.values()))
        terminal_backlog_max = max(terminal_backlog_max, terminal_backlog)
        cumulative = {
            cohort: [sum(arrivals[cohort][: slot + 1]) for slot in range(96)] for cohort in cohorts
        }
        total_workload = sum(sum(values_) for values_ in arrivals.values())
        timestamps = selected[(selected["target"] == "P_IT_REF") & (selected["quantile"] == 0.9)].sort_values("slot")["timestamp_aest"].astype(str).tolist()
        day_rows: list[dict[str, object]] = []
        system_slot_capacities: list[float] = []
        for slot in range(96):
            p_f_ref = reference.flexible_power_kw[slot]
            g_f_ref = reference.flexible_gpu[slot]
            p_res_sys = p_it_ref[slot] - sum(p_f_ref)
            g_res_sys = g_ref[slot] - sum(g_f_ref)
            p_res_min = min(p_res_min, p_res_sys)
            g_res_min = min(g_res_min, g_res_sys)
            if p_res_sys < -TOLERANCE or g_res_sys < -TOLERANCE:
                raise RuntimeError("TX_CLASS_D_DEEPER_MODEL_INCONSISTENCY")
            system_slot_capacities.append(
                (sum(rack.deliverable_gpu_capacity for rack in authority.racks) - g_res_sys) * DT_HOURS / GPU_PER_NODE
            )
            for aidc_index, aidc in enumerate(aidc_ids):
                indices = rack_indices[aidc]
                p_res_aidc = aidc_power_weights[aidc_index] * p_res_sys
                p_f_ref_aidc = sum(p_f_ref[index] for index in indices)
                p_it_ref_aidc = p_res_aidc + p_f_ref_aidc
                s_ref = PUE_PLAN * p_it_ref_aidc / PF_PLAN
                node_hour_capacity = sum(
                    authority.racks[index].deliverable_gpu_capacity - authority.gpu_weights[index] * g_res_sys
                    for index in indices
                ) * DT_HOURS / GPU_PER_NODE
                available = {cohort: cumulative[cohort][slot] for cohort in cohorts}
                flex_power, served, _ = maximize_flexible_power_kw(available, node_hour_capacity)
                p_it_max = p_res_aidc + flex_power
                s_max = PUE_PLAN * p_it_max / PF_PLAN
                row = {
                    "aidc_id": aidc,
                    "operating_day": day,
                    "slot": slot,
                    "timestamp_fixed_aest": timestamps[slot],
                    "p_res_aidc_kw": p_res_aidc,
                    "p_f_ref_v3_aidc_kw": p_f_ref_aidc,
                    "p_it_ref_aidc_kw": p_it_ref_aidc,
                    "s_ref_aidc_kva": s_ref,
                    "resource_node_hour_capacity": node_hour_capacity,
                    "resource_node_hours_served_at_target": served,
                    "p_flex_resource_max_kw": flex_power,
                    "p_it_max_aidc_kw": p_it_max,
                    "s_max_aidc_kva": s_max,
                    "increment_above_reference_kva": s_max - s_ref,
                }
                rows.append(row)
                day_rows.append(row)
        day_slack = min(system_slot_capacities) - total_workload
        one_slot_service_slack_min = min(one_slot_service_slack_min, day_slack)
        if terminal_backlog > TOLERANCE or day_slack < -TOLERANCE:
            raise RuntimeError("TX_CLASS_D_DEEPER_MODEL_INCONSISTENCY")
        daily.append({
            "operating_day": day,
            "total_w_f_q50_h100_node_hours": total_workload,
            "minimum_single_slot_system_service_capacity_h100_node_hours": min(system_slot_capacities),
            "single_slot_service_capacity_slack_h100_node_hours": day_slack,
            "reference_terminal_backlog_h100_node_hours": terminal_backlog,
            "reference_global_max": _locus(day_rows, "s_ref_aidc_kva"),
            "resource_global_max": _locus(day_rows, "s_max_aidc_kva"),
        })

    by_aidc: dict[str, object] = {}
    for aidc in aidc_ids:
        selected_rows = [row for row in rows if row["aidc_id"] == aidc]
        max_resource = max(selected_rows, key=lambda row: float(row["s_max_aidc_kva"]))
        max_delta = max(selected_rows, key=lambda row: float(row["increment_above_reference_kva"]))
        by_aidc[aidc] = {
            "power_spatial_weight": aidc_power_weights[aidc_ids.index(aidc)],
            "reference": {**_stats(selected_rows, "s_ref_aidc_kva"), "locus": _locus(selected_rows, "s_ref_aidc_kva")},
            "resource_maximum": {
                **_stats(selected_rows, "s_max_aidc_kva"),
                "locus": _locus(selected_rows, "s_max_aidc_kva"),
                "reference_at_resource_max_kva": max_resource["s_ref_aidc_kva"],
                "increment_at_resource_max_kva": max_resource["increment_above_reference_kva"],
                "maximum_increment_above_reference_kva": max_delta["increment_above_reference_kva"],
                "maximum_increment_locus": {
                    key: max_delta[key] for key in ("operating_day", "slot", "timestamp_fixed_aest")
                },
            },
        }

    candidate_coverage: list[dict[str, object]] = []
    total_cases = len(rows)
    for scenario_id, pmax_kw, candidate in EXPECTED_RATINGS:
        violations = [row for row in rows if float(row["s_max_aidc_kva"]) > candidate + TOLERANCE]
        candidate_coverage.append({
            "scenario_id": scenario_id,
            "source_scope": historical["scope_classification"],
            "pmax_kw": pmax_kw,
            "s_candidate_kva": candidate,
            "violation_count": len(violations),
            "worst_excess_kva": max((float(row["s_max_aidc_kva"]) - candidate for row in violations), default=0.0),
            "coverage_fraction": (total_cases - len(violations)) / total_cases,
            "covers_all_12_aidcs_all_april_slots": not violations,
        })
    covering = [row for row in candidate_coverage if row["covers_all_12_aidcs_all_april_slots"]]
    classification = (
        "TX_CLASS_A_EXISTING_COMMON_CANDIDATE_AVAILABLE"
        if covering else "TX_CLASS_B_EXISTING_GRID_INSUFFICIENT"
    )
    global_resource = max(rows, key=lambda row: float(row["s_max_aidc_kva"]))
    sizing = {
        "artifact_id": "AIDC_PCC_TRANSFORMER_SIZING_DIAGNOSTIC_V1",
        "authority_id": AUTHORITY_ID,
        "status": "PASS_DIAGNOSTIC_COMPLETE_STOP",
        "classification": classification,
        "diagnostic_only": True,
        "active_scientific_authority_modified": False,
        "current_scientific_authority": CURRENT_SCIENTIFIC_AUTHORITY,
        "provenance_summary": {
            "inherited_rating_kva": 750.0,
            "synthetic_engineering_scenario": True,
            "actual_dnsp_nameplate_claim": False,
            "deployment_sizing_was_deferred": True,
            "mess_transformer_rating_kva": 750.0,
            "mess_transformer_status": "UNCHANGED",
        },
        "historical_v2_0_22_grid": historical,
        "april_coverage": {
            "first_operating_day": days[0],
            "last_operating_day": days[-1],
            "operating_day_count": len(days),
            "slots_per_day": 96,
            "aidc_count": len(aidc_ids),
            "evaluated_aidc_day_slot_case_count": total_cases,
            "forecast_artifact": {"path": str(forecast.resolve()), "sha256": sha256_file(forecast)},
            "forecast_model": "Proposed AIDC RC-MQT",
            "forecast_namespace": "APRIL_VALIDATION_ONLY",
            "forecast_inputs": {"P_IT_REF": "Q90", "G_REF": "Q90", "W_F": "Q50"},
        },
        "frozen_semantics": {
            "pue_plan": PUE_PLAN,
            "pf_plan": PF_PLAN,
            "gpu_per_node": GPU_PER_NODE,
            "kappa_kw_per_active_h100_node": dict(KAPPA_KW_PER_ACTIVE_H100_NODE),
            "rack_capacity_source_path": str(rack_source.resolve()),
            "rack_capacity_source_sha256": authority.source_sha256,
            "aidc_power_weight_sum": sum(aidc_power_weights),
            "reference_policy": "REFERENCE_COMPUTE_SCHEDULE_V3",
            "legacy_rack_kw_cap_used": False,
        },
        "resource_maximum_method": {
            "optimization_form": "CONTINUOUS_RESOURCE_LP_SOLVED_EXACTLY_BY_DESCENDING_KAPPA",
            "arrival_causality": "CUMULATIVE_W_F_Q50_AVAILABLE_THROUGH_TARGET_SLOT",
            "terminal_service_feasibility_proof": "For every April day, total daily workload is below the minimum one-slot system GPU service capacity; target-site allocation plus remaining system capacity can therefore clear all work by slot 95.",
            "minimum_one_slot_service_capacity_slack_h100_node_hours": one_slot_service_slack_min,
            "transformer_constraint_call_count": 0,
            "line_current_constraint_call_count": 0,
            "voltage_constraint_call_count": 0,
            "mess_constraint_call_count": 0,
            "opendss_call_count": 0,
            "grid_performance_selection_call_count": 0,
            "objective_outcome_selection_call_count": 0,
        },
        "boundary_validity": {
            "status": "PASS",
            "minimum_p_res_sys_kw": p_res_min,
            "minimum_g_res_sys": g_res_min,
            "maximum_reference_terminal_backlog_h100_node_hours": terminal_backlog_max,
        },
        "reference_s_envelope": {
            "global": {**_stats(rows, "s_ref_aidc_kva"), "locus": _locus(rows, "s_ref_aidc_kva")},
            "by_aidc": {aidc: by_aidc[aidc]["reference"] for aidc in aidc_ids},
        },
        "resource_feasible_maximum_s_envelope": {
            "s_required_continuous_kva": global_resource["s_max_aidc_kva"],
            "global": {**_stats(rows, "s_max_aidc_kva"), "locus": _locus(rows, "s_max_aidc_kva")},
            "reference_at_global_resource_max_kva": global_resource["s_ref_aidc_kva"],
            "increment_above_reference_at_global_max_kva": global_resource["increment_above_reference_kva"],
            "by_aidc": {aidc: by_aidc[aidc]["resource_maximum"] for aidc in aidc_ids},
        },
        "aidc_weight_and_envelope_summary": by_aidc,
        "daily_global_summary": daily,
        "candidate_coverage": candidate_coverage,
        "common_rating_policy": {
            "policy": "ONE_COMMON_AIDC_PCC_TRANSFORMER_RATING_FOR_ALL_12_AIDCS",
            "minimum_existing_candidate_covering_full_april_envelope": (
                min(covering, key=lambda row: float(row["s_candidate_kva"]))["scenario_id"] if covering else None
            ),
            "common_existing_candidate_available": bool(covering),
            "result": "EXISTING_KVA_GRID_INSUFFICIENT" if not covering else "EXISTING_COMMON_CANDIDATE_COVERS",
            "mess_rating_separate_and_unchanged": True,
        },
        "execution_firewall": {
            "may_scientific_loader_access_count": 0,
            "june_scientific_loader_access_count": 0,
            "g11_call_count": 0,
            "g12_call_count": 0,
            "g13_call_count": 0,
            "g14_call_count": 0,
            "c12_call_count": 0,
            "rc_mqt_retrain_call_count": 0,
            "scientific_authority_change_count": 0,
        },
        "stop_point": "STOP_AFTER_V16_2_PRE_REFREEZE_DIAGNOSTIC",
    }
    artifacts.mkdir(parents=True, exist_ok=True)
    provenance_path = artifacts / "AIDC_PCC_TRANSFORMER_PROVENANCE_AUDIT_V1.json"
    sizing_path = artifacts / "AIDC_PCC_TRANSFORMER_SIZING_DIAGNOSTIC_V1.json"
    _write_json(provenance_path, provenance)
    _write_json(sizing_path, sizing)
    return {
        "classification": classification,
        "provenance_path": str(provenance_path),
        "provenance_sha256": sha256_file(provenance_path),
        "sizing_path": str(sizing_path),
        "sizing_sha256": sha256_file(sizing_path),
        "s_required_continuous_kva": global_resource["s_max_aidc_kva"],
    }


def main(argv: Sequence[str] | None = None) -> int:
    repo_default = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=repo_default)
    parser.add_argument("--forecast", type=Path, default=repo_default / "dayahead/artifacts/v16/AIDC_APRIL_VALIDATION_FORECAST.parquet")
    parser.add_argument("--rack-source", type=Path, default=Path(r"C:\Users\kjw39\OneDrive\Desktop\4-2\Mobile ESS\processed데이터\데이터센터\NLR Kestrel Jobs Data\stage_k5c3_20260723_062008\outputs\optimization_main_rack_parameters.csv"))
    parser.add_argument("--transformer-authority", type=Path, default=repo_default / "performance/post_stage15_runtime_acceleration/package/authority/TRANSFORMER_SCENARIO_AUTHORITY.json")
    parser.add_argument("--pcc-dss", type=Path, default=Path(r"C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\tmp\c12_exact_sources_repo_cleanup\c12_exact_sources\v2038_parent\Conversation3_Exact_AC_Remediation_Sweep_From_Conversation1_V2038\reference\opendss_assets\Generated_ThreePhase_PCC_v3.dss"))
    parser.add_argument("--v14-spec", type=Path, default=Path(r"C:\Users\kjw39\OneDrive\Desktop\4-2\Mobile ESS\정리 자료\Mobile_ESS_AI_ICPS_정식화_구현명세_v14_2_Current_Authority_20260827.docx"))
    parser.add_argument("--historical-grid-root", type=Path, default=Path(r"\\wsl.localhost\Ubuntu-MobileESS-D\home\jaewon\mobile_ess_work\stage_expanded_kva_margin_search_prefreeze_v2_0_22\stage_expanded_kva_margin_search_prefreeze_v2_0_22"))
    parser.add_argument("--artifacts", type=Path, default=repo_default / "dayahead/artifacts/v16_2")
    args = parser.parse_args(argv)
    result = execute(**vars(args))
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
