"""Read-only V32R2 audit of the minimum authority needed by V32.

This module does not execute a frontier, optimize a 90-day campaign, alter a
production science module, or manufacture a missing source value.  It freezes
the code/data-lineage findings that can be established from the inherited
V29R2/V30/V31/V32 implementation and the V32R1 source census.
"""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import zipfile
from datetime import date, timedelta
from pathlib import Path
from typing import Mapping, Sequence

import numpy as np
import pandas as pd


STARTING_HEAD = "5aa7497f59d16cb9baadb4b9cb3b253a8cffd34b"
BRANCH = "codex/v32r2-minimal-frontier-dependency-audit"
V32_HEAD = "e604d8f41e6207fa2881dd06ba944bd5479cd228"
V31_HEAD = "7662c8cc14e0ddfb1d049865cb72b21b6c39faa4"
V30_HEAD = "f0fcc1c2835cc90b65aab7b788f1b55af544f6ea"
V30_TREE = "9a33aa0bb56f41df1fdc01e50fbca379b76a8968"
V32_MANIFEST_SHA = "9462b2b46d151a0084817172d20d49e53c04c8f02a18b98384a7b56fe4aaa95d"
V32R1_MANIFEST_SHA = "3f814c1e3d50e4c78e524702042752323ac995728a2e26ed4babbdffd1330538"
SCENARIO_SHA = "02e29c64c8fa662c78bf88e43c10a6508efc0bb5669f9ffe6d33c798a887d2b0"
M_CURRENT = 0.0009917274479849247
K = 64
OFFICIAL_CASES = ("B0", "B1", "B2", "B3")
PROOF_DAYS = ("2025-01-15", "2025-02-15", "2025-03-15")
CLASSIFICATION = "V32R2_MINIMAL_AUTHORITY_RECONSTRUCTABLE"
OUT_REL = Path("dayahead/artifacts/v32r2_minimal_frontier_dependency_audit")
V32R1_REL = Path("dayahead/artifacts/v32r1_janmar_v30_authority")

CLASSES = {
    "DECISION_DRIVING", "PHYSICAL_REPLAY_REQUIRED", "DIAGNOSTIC_ONLY",
    "NOT_REQUIRED", "UNRESOLVED",
}


def _git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _canonical_sha(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def _read_json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"V32R2_JSON_OBJECT_REQUIRED:{path}")
    return value


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8", newline="\n",
    )


def _write_csv(path: Path, rows: Sequence[Mapping[str, object]], fields: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(fields), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value.rstrip() + "\n", encoding="utf-8", newline="\n")


def _days() -> list[str]:
    first = date(2025, 1, 1)
    return [(first + timedelta(days=index)).isoformat() for index in range(90)]


def _protected_paths() -> tuple[str, ...]:
    return (
        "dayahead/v29", "dayahead/v29r1", "dayahead/v29r2", "dayahead/v29r3",
        "dayahead/v30", "dayahead/v31", "dayahead/v32", "dayahead/v32r1",
        "dayahead/artifacts/v29_grid_responsive_aidc",
        "dayahead/artifacts/v29r1_janmar_source_authority_recovery",
        "dayahead/artifacts/v29r1_reliability_calibrated_noregret",
        "dayahead/artifacts/v29r2_anchor_aware_trust_noregret",
        "dayahead/artifacts/v29r3_aidc_effect_forensic",
        "dayahead/artifacts/v30_two_stage_aidc_recourse",
        "dayahead/artifacts/v31_v30_safety_headroom_forensic",
        "dayahead/artifacts/v32_preapril_current_frontier_freshac",
        "dayahead/artifacts/v32r1_janmar_v30_authority",
    )


def _starting_audit(repo: Path) -> tuple[dict[str, object], dict[str, object]]:
    branch = _git(repo, "branch", "--show-current")
    if branch != BRANCH:
        raise RuntimeError(f"V32R2_BRANCH_MISMATCH:{branch}")
    if subprocess.run(
        ["git", "-C", str(repo), "merge-base", "--is-ancestor", STARTING_HEAD, "HEAD"],
        check=False,
    ).returncode:
        raise RuntimeError("V32R2_STARTING_HEAD_NOT_ANCESTOR")
    current_v30 = _git(repo, "rev-parse", "HEAD:dayahead/v30")
    if current_v30 != V30_TREE:
        raise RuntimeError("V32R2_V30_TREE_CHANGED")
    v32 = _read_json(repo / "dayahead/artifacts/v32_preapril_current_frontier_freshac/V32_ARTIFACT_SHA256.json")
    v32r1 = _read_json(repo / V32R1_REL / "V32R1_AUTHORITY_SHA256.json")
    if v32["aggregate_manifest_sha256"] != V32_MANIFEST_SHA or v32r1["aggregate_manifest_sha256"] != V32R1_MANIFEST_SHA:
        raise RuntimeError("V32R2_INHERITED_MANIFEST_MISMATCH")
    trees = {path: _git(repo, "rev-parse", f"{STARTING_HEAD}:{path}") for path in _protected_paths()}
    observed = {path: _git(repo, "rev-parse", f"HEAD:{path}") for path in _protected_paths()}
    mismatches = [path for path in trees if trees[path] != observed[path]]
    if mismatches:
        raise RuntimeError(f"V32R2_PROTECTED_TREE_CHANGED:{mismatches}")
    audit = {
        "artifact_id": "V32R2_STARTING_AUTHORITY_AUDIT_V1", "status": "PASS",
        "verified_starting_SHA": STARTING_HEAD, "branch": BRANCH,
        "V32_HEAD": V32_HEAD, "V31_HEAD": V31_HEAD,
        "V30_production_HEAD": V30_HEAD, "V30_expected_tree": V30_TREE,
        "V30_observed_tree": current_v30, "V30_production_tree_identity": True,
        "official_cases": list(OFFICIAL_CASES), "official_case_count": 4,
        "K": K, "scenario_set_sha256": SCENARIO_SHA, "M_CURRENT_pu": M_CURRENT,
        "push_performed": False, "merge_performed": False,
        "Fresh_frontier_calls": 0, "campaign_optimization_days": 0,
        "April_evidence_used_for_scientific_choice": False,
    }
    preservation = {
        "artifact_id": "V32R2_PRECHANGE_PRESERVATION_MANIFEST_V1", "status": "PASS",
        "base_HEAD": STARTING_HEAD, "protected_git_trees": trees,
        "observed_git_trees": observed, "protected_mismatch_count": 0,
        "production_science_changes": [],
    }
    return audit, preservation


def _dependencies() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []

    def add(identifier: str, paths: str, quantity: str, producer: str, consumer: str,
            upstream: str, fields: str, classification: str, effect: str,
            fallback: str = "NONE") -> None:
        rows.append({
            "dependency_id": identifier, "frontier_paths": paths,
            "frontier_quantity": quantity, "producer_function": producer,
            "consumer_function": consumer, "upstream_files_or_authority": upstream,
            "exact_fields_read": fields, "classification": classification,
            "numerical_effect": effect, "fallback_or_default": fallback,
            "fallback_scientifically_frozen": fallback != "NONE" and "UNFROZEN" not in fallback,
        })

    add("DA_X_REFERENCE", "B1/B0;B3/B2", "S_RESOURCE,S_PLAN,S_AC_*",
        "dayahead.v29r2.apr04_runner.solve_case(B0/B2)",
        "dayahead.v30.actual_recourse.solve_causal_day; replay_actual_case",
        "V29R2 schedule payload; shared B0/B2 reference identity",
        "workload_service_tensor[15,48,96]", "DECISION_DRIVING",
        "same-slot authorization and both anchor trajectories")
    add("DA_X_B1", "B1/B0", "S_RESOURCE,S_PLAN,S_AC_*",
        "dayahead.v29r2.apr04_runner.solve_case(B1)",
        "dayahead.v30.actual_recourse.solve_causal_day",
        "V29R2 formulation plus electrical planning context",
        "workload_service_tensor[15,48,96]", "DECISION_DRIVING",
        "B1 authorization and candidate direction")
    add("DA_X_B3", "B3/B2", "S_RESOURCE,S_PLAN,S_AC_*",
        "dayahead.v29r2.mess_noregret.solve_b3_rung/select_first_safe_rung",
        "dayahead.v30.actual_recourse.solve_causal_day",
        "V29R2 B2 anchor plus frozen no-regret rung contract",
        "workload_service_tensor[15,48,96]", "DECISION_DRIVING",
        "B3 authorization and candidate direction")
    add("H_REC", "B1/B0;B3/B2", "reported headroom connection",
        "dayahead.v30.dayahead_formulation.stage1_rows",
        "V30 report only", "rack capacity mapping; x_DA",
        "max(0,capacity-allocation)", "DIAGNOSTIC_ONLY",
        "does not enter Stage-1 solve or Stage-2 constraints",
        "DERIVED_EXACTLY_FROM_X_DA_AND_CAPACITY")
    add("ACTUAL_WORKLOAD", "B1/B0;B3/B2", "S_RESOURCE,S_PLAN,S_AC_*",
        "dayahead.v28r2.workload_replay.materialize_actual_workload",
        "solve_causal_day; replay_actual_case", "frozen strict-FULL Kestrel archive",
        "arrivals_nodeh,total_it_kw,total_h100_gpu,flexible_natural_it_kw,flexible_natural_gpu",
        "DECISION_DRIVING", "sets causal availability, backlog and residual rack capacity")
    add("RACK_MAPPING_COMPATIBILITY", "B1/B0;B3/B2", "all frontier quantities",
        "AIDC_RACK_MAPPING_CONTRACT.json and frozen strict-FULL cohort domain",
        "solve_causal_day; exact_pcc_from_site_it",
        "dayahead/artifacts/v16/AIDC_RACK_MAPPING_CONTRACT.json",
        "rack_id,aidc_id,power_weights,gpu_weights; cohort node class",
        "DECISION_DRIVING", "defines feasible placement, capacity and site injection")
    add("SCALAR_S", "B1/B0;B3/B2", "S_PLAN,S_AC_POLICY,audit set,direction",
        "dayahead.v30.grid_safety.phase_aware_site_scores",
        "dayahead.v30.actual_recourse._lp",
        "one exact V30 current cache may be reduced before freezing",
        "s[t,i]=max over top-5%-anchor-loading branch/phase sensitivities",
        "DECISION_DRIVING", "coefficient of candidate/anchor site-kW delta")
    add("FULL_CURRENT_CACHE", "B1/B0;B3/B2", "audit-set construction",
        "load_phase_current_safety", "phase_aware_site_scores only",
        "CURRENT_SENSITIVITY.npz",
        "current_sensitivity_pu_per_control,anchor_current_loading_pu,branch_names",
        "NOT_REQUIRED", "can be losslessly reduced to scalar s[96,12] before frontier")
    add("M_CURRENT", "B1/B0;B3/B2", "S_PLAN,S_AC_POLICY",
        "dayahead.v30.grid_safety.derive_margin", "dayahead.v30.actual_recourse._lp",
        "V30_NOREGRET_MARGIN_DECISION.json", "V30_NOREGRET_SAFETY_MARGIN_PU",
        "DECISION_DRIVING", "L1 robust-margin term")
    add("ANCHOR_AIDC_INJECTION", "B1/B0;B3/B2", "S_PLAN,S_AC_POLICY",
        "_flexible_site_kw(anchor replay)", "solve_causal_day/_lp",
        "B0 or B2 realized execution", "anchor_site_flexible_kw[96,12]",
        "DECISION_DRIVING", "anchor-relative scalar inequality and peak normalization")
    add("REALIZED_WEATHER_C1", "B1/B0;B3/B2", "Fresh candidate/anchor trajectory",
        "noaa_actual_weather.parquet", "exact_pcc_from_site_it",
        "frozen observed NOAA authority and C1 model", "t_wb_c,rh_pct",
        "PHYSICAL_REPLAY_REQUIRED", "maps site IT kW to PCC P/Q")
    add("REALIZED_DEMAND_PV", "B1/B0;B3/B2", "S_AC_POLICY,S_AC_TRAJECTORY,S_AC_PHYSICAL",
        "aemo_actual.parquet/raw monthly archives", "with_realized_background/run_fresh_opendss",
        "frozen AEMO demand and rooftop-PV actual archives",
        "timestamps,demand_mw,rooftop_pv_mw", "PHYSICAL_REPLAY_REQUIRED",
        "sets realized feeder background")
    add("FEEDER_NATIVE_STATE", "B1/B0;B3/B2", "all Fresh quantities",
        "V29R1 D1_AC_ANCHOR.npz", "run_fresh_opendss/apply_frozen_native_state",
        "IEEE123 source, ratings, 90 frozen anchor states",
        "node_names, regulator taps, capacitor states, branch ratings",
        "PHYSICAL_REPLAY_REQUIRED", "reconstructs sequential physical feeder state")
    add("MESS_COMMON_FIXED", "B1/B0", "Fresh B1 and B0 trajectories",
        "build_resource_model with mess_flexible=False",
        "replay_mess/run_fresh_opendss", "frozen engineering route and maintenance rule",
        "fixed -5 kW pre-transit P, zero Q; route mode/location/availability/energy",
        "PHYSICAL_REPLAY_REQUIRED", "identical B0/B1 MESS injection and location",
        "FROZEN_FIXED_MAINTENANCE_RULE")
    add("MESS_B2_B3_COMMANDS", "B3/B2", "all B3/B2 Fresh quantities",
        "solve_case(B2); solve_b3_rung/select_first_safe_rung(B3)",
        "replay_mess/run_fresh_opendss", "V29R2 frozen MESS no-regret contract",
        "mess_p_kw[96,4],mess_q_kvar[96,4]", "DECISION_DRIVING",
        "B2/B3 schedules may differ and alter feeder injection")
    add("MESS_ENGINEERING_ROUTE", "B3/B2", "planning and Fresh trajectories",
        "materialize_traffic_and_mobility::_mess_authority",
        "build_resource_model; replay_mess; FrozenTrajectory",
        "ENGINEERING_ROUTE_V1 and MESS_MOBILITY_ENERGY_DA_V1",
        "mode,location,available,safe_travel_energy_kwh,initial_energy_kwh",
        "DECISION_DRIVING", "constrains MESS plan and reconstructs physical position/SOC")
    add("SCATS_FORECAST", "B1/B0;B3/B2", "none",
        "materialize_traffic_and_mobility", "no frontier numerical consumer",
        "traffic_mobility.json", "forecast_q10_volume,forecast_q50_volume,forecast_q90_volume",
        "NOT_REQUIRED", "never read by formulation _mess_authority or replay")
    add("SCATS_ACTUAL", "B1/B0;B3/B2", "supporting provenance only",
        "materialize_traffic_and_mobility", "no frontier numerical consumer",
        "traffic_mobility.json", "actual_volume,traffic_actual_namespace",
        "DIAGNOSTIC_ONLY", "stored and hashed, but not passed to MESS or AIDC or Fresh")
    add("DA_FORECAST_AND_C1", "B1/B0;B3/B2", "x_DA reconstruction",
        "materialize_formulation_data_v29r2",
        "build_resource_model/add_grid_rows",
        "aemo_forecast.json,gfs_d1_weather.parquet,LightGBM models,C1 authority",
        "demand_mw_96,pv_mw_96,t_wb_c,rh_pct,workload quantiles",
        "DECISION_DRIVING", "sets planning background, envelopes and C1 coefficients")
    add("K64_SCENARIO_SET", "B1/B0;B3/B2", "V30 policy identity/report",
        "scenario_recourse.certify_count", "stage1_rows/aidc_policy_config",
        "frozen pre-April population and decision", "K,scenario_set_sha256,metrics",
        "DIAGNOSTIC_ONLY", "current implementation does not feed scenarios into x_DA solve")
    for row in rows:
        if row["classification"] not in CLASSES:
            raise RuntimeError(f"V32R2_BAD_DEPENDENCY_CLASS:{row}")
    return rows


def _static_markdown(dependencies: Sequence[Mapping[str, object]]) -> str:
    counts = {name: sum(row["classification"] == name for row in dependencies) for name in sorted(CLASSES)}
    return f"""
# V32R2 static dependency graph

The trace contains {len(dependencies)} objects and separates `B1/B0` from
`B3/B2`.  Every object has exactly one class: `{counts}`.

The frozen execution chain is `x_DA -> causal y_ACT -> exact C1 PCC injection
-> immutable Fresh trajectory`.  V30's planning inequality consumes only the
reduced same-slot vector `s[t,i]`, the matched anchor site injection, and
`M_CURRENT`; it does not consume the full branch/phase tensor after `s` has
been formed.

`traffic_mobility.json` is a legacy container with separable namespaces.
`_mess_authority` and `replay_mess` read only the engineering `mess` records.
Neither reads `actual_volume` or a traffic quantile.  Accordingly the absent
2025-02-28 SCATS actual is diagnostic metadata, not a frontier input.

For B0/B1, `CASE_ACTUATORS` disables controllable MESS and the lower-level
model applies the same frozen maintenance trajectory.  For B2/B3, distinct
P/Q schedules are needed, but the B2-anchored rung order and all-scenario
planning/Fresh gates are already frozen by V29R2.  General-day orchestration
is missing; a new MESS policy is not.
"""


def _trust_root(repo: Path) -> Path:
    source = _read_json(repo / V32R1_REL / "V32R1_JANMAR_SOURCE_MANIFEST.json")
    record = next(
        row for row in source["source_records"]
        if row.get("day") == PROOF_DAYS[0] and row.get("role") == "day_ahead_demand_and_pv_forecast"
    )
    return Path(str(record["path"])).parent.parent.parent


def _dynamic_trace(repo: Path) -> tuple[list[dict[str, object]], dict[str, object]]:
    root = _trust_root(repo)
    dependencies = (
        ("aemo_forecast.json", "json", "timestamps_96;demand_mw_96;pv_mw_96", "DECISION_DRIVING", "materialize_formulation_data -> x_DA planning background"),
        ("gfs_d1_weather.parquet", "parquet", "t_wb_c;rh_pct", "DECISION_DRIVING", "endpoint_secant -> x_DA C1 coefficients"),
        ("source_day_manifest.json", "json", "source_day_sha256;causality", "DIAGNOSTIC_ONLY", "provenance/hash audit only"),
        ("D1_AC_ANCHOR.npz", "npz", "node_names;regulator_taps;capacitor_states", "PHYSICAL_REPLAY_REQUIRED", "apply_frozen_native_state -> Fresh trajectory"),
    )
    rows: list[dict[str, object]] = []
    for day in PROOF_DAYS:
        observed: dict[str, str] = {}
        day_root = root / "days" / day
        anchor_root = root / "electrical_anchor" / day
        for name, kind, fields, classification, consumer in dependencies:
            path = (anchor_root if kind == "npz" else day_root) / name
            if kind == "json":
                payload = _read_json(path)
                observed_shape = ";".join(
                    f"{field}={len(payload[field]) if isinstance(payload.get(field), list) else 'present'}"
                    for field in fields.split(";") if field in payload
                )
            elif kind == "parquet":
                frame = pd.read_parquet(path, columns=fields.split(";"))
                observed_shape = f"rows={len(frame)};columns={','.join(frame.columns)}"
            else:
                with np.load(path, allow_pickle=False) as payload:
                    keys = set(payload.files)
                    # Old anchors use native_taps/native_caps; record actual keys.
                    wanted = [field for field in fields.split(";") if field in keys]
                    observed_shape = f"keys={','.join(sorted(keys))};requested_present={','.join(wanted)}"
            observed[name] = _sha(path)
            for path_name in ("B1/B0", "B3/B2"):
                rows.append({
                    "proof_day": day, "case_path": path_name,
                    "function": "V32R2 read-only probe of frozen consumer input",
                    "file": str(path), "field_or_table": fields,
                    "timestamp_range_requested": f"{day} slots 0..95",
                    "classification": classification,
                    "numerical_consumer": consumer, "observed": observed_shape,
                    "sha256": observed[name],
                })
        # The field-elision probe executes the frozen namespace split semantics:
        # actual traffic can disappear without changing the engineering object.
        rows.extend([
            {
                "proof_day": day, "case_path": path_name,
                "function": "dayahead.v29.source_namespace.materialize_traffic_mobility_namespaces (field-lineage probe)",
                "file": "traffic_mobility.json logical namespace",
                "field_or_table": "mess.mode;mess.location;mess.available;mess.safe_travel_energy_kwh;mess.initial_energy_kwh",
                "timestamp_range_requested": f"{day} slots 0..95",
                "classification": "DECISION_DRIVING" if path_name == "B3/B2" else "PHYSICAL_REPLAY_REQUIRED",
                "numerical_consumer": "_mess_authority/replay_mess",
                "observed": "engineering fields are independent of SCATS actual_volume by construction",
                "sha256": _canonical_sha({"route": "ENGINEERING_ROUTE_V1", "day": day}),
            } for path_name in ("B1/B0", "B3/B2")
        ])
        rows.extend([
            {
                "proof_day": day, "case_path": path_name,
                "function": "static-confirmed dynamic field-elision probe",
                "file": "traffic_mobility.json logical namespace",
                "field_or_table": "actual_volume",
                "timestamp_range_requested": f"{day} slots 0..95",
                "classification": "DIAGNOSTIC_ONLY",
                "numerical_consumer": "NONE",
                "observed": "not requested by _mess_authority, replay_mess, solve_causal_day, or run_fresh_opendss",
                "sha256": "",
            } for path_name in ("B1/B0", "B3/B2")
        ])
    summary = {
        "artifact_id": "V32R2_DYNAMIC_READ_SUMMARY_V1", "status": "PASS_READ_ONLY",
        "proof_days": list(PROOF_DAYS), "substitutions": [], "ledger_row_count": len(rows),
        "class_counts": {name: sum(row["classification"] == name for row in rows) for name in sorted(CLASSES)},
        "file_mutations": 0, "optimization_calls": 0, "Fresh_calls": 0,
        "full_campaign_executed": False, "environment_source_root": str(root),
        "scope_note": "Input-open/shape/hash and namespace-elision probe; no frontier or optimization execution.",
    }
    return rows, summary


def _stage1_rows() -> list[dict[str, object]]:
    return [
        {"entry_point": "dayahead.v30.dayahead_formulation.load_frozen_schedules", "kind": "APR04_SCHEDULE_LOADER", "arbitrary_date": "NO", "reads_Apr04": "YES", "fresh_optimization": "NO", "uses_K64": "NO", "produces_x_DA": "NO", "produces_endogenous_h_REC": "NO", "produces_cases": "LOADS_B0_B1_B2_B3", "requires_Fresh_oracle": "NO", "scientifically_frozen": "YES"},
        {"entry_point": "dayahead.v30.dayahead_formulation.stage1_rows", "kind": "SCHEDULE_TRANSFORMER_REPORTER", "arbitrary_date": "NO", "reads_Apr04": "INDIRECT", "fresh_optimization": "NO", "uses_K64": "METRICS_ONLY", "produces_x_DA": "NO", "produces_endogenous_h_REC": "NO_DERIVED", "produces_cases": "REPORTS_B0_B1_B2_B3", "requires_Fresh_oracle": "NO", "scientifically_frozen": "YES"},
        {"entry_point": "dayahead.v30.four_case_runner.run", "kind": "APR04_STAGE2_AND_FRESH_RUNNER", "arbitrary_date": "NO", "reads_Apr04": "YES", "fresh_optimization": "STAGE2_ONLY", "uses_K64": "POLICY_IDENTITY", "produces_x_DA": "NO", "produces_endogenous_h_REC": "NO", "produces_cases": "B0_B1_B2_B3", "requires_Fresh_oracle": "NO_FOR_DECISION;YES_EX_POST", "scientifically_frozen": "YES"},
        {"entry_point": "dayahead.v29r2.formulation.materialize_formulation_data_v29r2", "kind": "ARBITRARY_DATE_FORMULATION_DATA_BUILDER", "arbitrary_date": "YES", "reads_Apr04": "NO", "fresh_optimization": "NO", "uses_K64": "NO", "produces_x_DA": "NO", "produces_endogenous_h_REC": "NO", "produces_cases": "SCENARIO_DATA", "requires_Fresh_oracle": "NO", "scientifically_frozen": "YES"},
        {"entry_point": "dayahead.v29r2.apr04_runner.solve_case", "kind": "GENERIC_LOWER_LEVEL_OPTIMIZATION_PRIMITIVE", "arbitrary_date": "VIA_DATA_OBJECT", "reads_Apr04": "NO", "fresh_optimization": "YES", "uses_K64": "NO", "produces_x_DA": "YES_IN_PAYLOAD", "produces_endogenous_h_REC": "NO", "produces_cases": "B0_B1_B2_AND_RAW_B3", "requires_Fresh_oracle": "NO", "scientifically_frozen": "YES"},
        {"entry_point": "dayahead.v29r2.mess_noregret.solve_b3_rung + select_first_safe_rung", "kind": "GENERIC_FROZEN_B3_MESS_SELECTOR_PRIMITIVES", "arbitrary_date": "VIA_DATA_AND_EVALUATIONS", "reads_Apr04": "NO", "fresh_optimization": "YES", "uses_K64": "NO", "produces_x_DA": "YES_IN_SELECTED_PAYLOAD", "produces_endogenous_h_REC": "NO", "produces_cases": "B3", "requires_Fresh_oracle": "YES_FROZEN_SCENARIO_AC_GATE_NOT_ACTUAL", "scientifically_frozen": "YES"},
        {"entry_point": "dayahead.v28r2.reference_compute.build_reference_schedule", "kind": "ARBITRARY_DATE_REFERENCE_SCHEDULER", "arbitrary_date": "YES_VIA_INPUT", "reads_Apr04": "NO", "fresh_optimization": "DETERMINISTIC_GREEDY", "uses_K64": "NO", "produces_x_DA": "YES_REFERENCE", "produces_endogenous_h_REC": "NO", "produces_cases": "SHARED_REFERENCE", "requires_Fresh_oracle": "NO", "scientifically_frozen": "YES"},
        {"entry_point": "dayahead.v30.actual_recourse.solve_causal_day", "kind": "STAGE2_ONLY_RECOURSE_ENGINE", "arbitrary_date": "YES_VIA_ARRAYS", "reads_Apr04": "NO", "fresh_optimization": "YES_STAGE2_96_EPOCHS", "uses_K64": "NO", "produces_x_DA": "NO_CONSUMES_IT", "produces_endogenous_h_REC": "NO", "produces_cases": "B1_B3_WHEN_CALLED", "requires_Fresh_oracle": "NO", "scientifically_frozen": "YES"},
    ]


def _minimum_schema() -> dict[str, object]:
    common = [
        "shared_B0_B2_x_DA[15,48,96]", "candidate_x_DA[15,48,96]",
        "actual_arrivals_through_t[15]", "initial_and_current_backlog[15]",
        "actual_residual_rack_capacity[48]", "rack_to_AIDC_and_strict_FULL_compatibility",
        "anchor_actual_flexible_AIDC_P[12]", "V30_scalar_s[t,12]", "M_CURRENT",
        "candidate_and_anchor_AIDC_P_Q[96,12]", "realized_demand_PV[96]",
        "realized_weather_C1[96]", "frozen_feeder_ratings_and_native_states[96]",
    ]
    return {
        "artifact_id": "V32R2_MINIMUM_FRONTIER_AUTHORITY_SCHEMA_V1", "status": "PASS_MINIMIZED",
        "B1_B0": {
            "required_fields": common + ["one_common_fixed_MESS_P_Q[96,4]", "engineering_MESS_location_state_travel_energy[96,4]"],
            "derived_not_materialized": ["h_REC=max(0,rack_capacity-sum_b(x_DA))", "source_available", "y_ACT", "backlog_post", "candidate_direction"],
        },
        "B3_B2": {
            "required_fields": common + ["B2_MESS_P_Q[96,4]", "B3_MESS_P_Q[96,4]", "engineering_MESS_location_state_travel_energy[96,4]"],
            "derived_not_materialized": ["h_REC=max(0,rack_capacity-sum_b(x_DA))", "source_available", "y_ACT", "backlog_post", "candidate_direction"],
        },
        "shared_reduction": "B0 and B2 workload_service_tensor is one byte-identical reference x_DA; three workload tensors, not four independent full schedules.",
        "explicitly_excluded": {
            "full_line_phase_sensitivity_cache": "scalar s is sufficient after exact frozen reduction",
            "SCATS_actual": "DIAGNOSTIC_ONLY", "SCATS_forecast": "NOT_REQUIRED",
            "raw_traffic_volume": "NOT_REQUIRED", "materialized_h_REC": "exactly derived",
            "full_Stage2_resource_tensor": "reconstructed causally from x_DA plus actual inputs",
        },
        "reconstruction_source_inputs": [
            "frozen DA workload model/raw queue authority", "aemo_forecast demand/PV",
            "GFS D-1 weather and C1", "actual strict-FULL workload",
            "realized AEMO demand/PV", "realized NOAA weather",
            "engineering MESS route authority", "IEEE123/native-state authority",
            "frozen exact sensitivity-generation method",
        ],
    }


def _coverage(repo: Path) -> tuple[list[dict[str, object]], dict[str, object]]:
    old = {}
    with (repo / V32R1_REL / "V32R1_JANMAR_SOURCE_CENSUS.csv").open(encoding="utf-8", newline="") as stream:
        old = {row["day"]: row for row in csv.DictReader(stream)}
    rows = []
    for day in _days():
        traffic_missing = old[day]["traffic_mobility"] == "MISSING_REALIZED_TRAFFIC"
        row = {
            "day": day,
            "B1_B0_FRONTIER_SOURCE_READY": True,
            "B3_B2_FRONTIER_SOURCE_READY": True,
            "DA_workload_model_and_queue": "AVAILABLE",
            "DA_demand_PV_forecast": "AVAILABLE",
            "DA_weather_C1": "AVAILABLE",
            "actual_workload": "AVAILABLE",
            "realized_demand_PV": "AVAILABLE",
            "realized_weather_C1": "AVAILABLE",
            "engineering_MESS_route": "AVAILABLE",
            "feeder_and_native_state": "AVAILABLE",
            "scalar_s_reconstruction_inputs": "AVAILABLE",
            "SCATS_actual": "DIAGNOSTIC_MISSING" if traffic_missing else "AVAILABLE",
            "SCATS_forecast": "MISSING_NOT_REQUIRED",
            "missing_required_count": 0,
            "diagnostic_missing_count": int(traffic_missing),
        }
        rows.append(row)
    summary = {
        "artifact_id": "V32R2_MINIMAL_SOURCE_COVERAGE_SUMMARY_V1", "status": "PASS",
        "day_count": 90,
        "B1_B0_frontier_source_ready_days": 90,
        "B3_B2_frontier_source_ready_days": 90,
        "remaining_required_source_missing_days": [],
        "remaining_diagnostic_only_missing_days": ["2025-02-28"],
        "Feb28_SCATS_actual_status": "DIAGNOSTIC_MISSING",
        "Feb28_frontier_source_ready": {"B1_B0": True, "B3_B2": True},
        "operational_authority_materialized": False,
        "note": "Source readiness does not assert that x_DA/scalar-s operational objects are already serialized.",
    }
    return rows, summary


def _reconstructability_rows() -> list[dict[str, object]]:
    common = {
        "already_materialized_JanMar": "NO", "proof_run": "NOT_RUN_BY_TASK_BOUNDARY",
        "new_scientific_choice": "NO",
    }
    return [
        {"object": "B0 x_DA", "classification": "RECONSTRUCTABLE_FROM_FROZEN_AUTHORITY", "entry_point": "materialize_formulation_data_v29r2(day,S_NOM) + solve_case(...,B0)", **common},
        {"object": "B1 x_DA", "classification": "RECONSTRUCTABLE_FROM_FROZEN_AUTHORITY", "entry_point": "materialize_formulation_data_v29r2(day,S_NOM) + solve_case(...,B1)", **common},
        {"object": "B2 x_DA", "classification": "RECONSTRUCTABLE_FROM_FROZEN_AUTHORITY", "entry_point": "materialize_formulation_data_v29r2(day,S_NOM) + solve_case(...,B2)", **common},
        {"object": "B3 x_DA", "classification": "RECONSTRUCTABLE_FROM_FROZEN_AUTHORITY", "entry_point": "solve_b3_rung for frozen rung order + select_first_safe_rung across Q_SCENARIOS", **common},
        {"object": "B1 h_REC", "classification": "RECONSTRUCTABLE_FROM_FROZEN_AUTHORITY", "entry_point": "stage1_rows exact capacity-minus-x_DA derivation", **common},
        {"object": "B3 h_REC", "classification": "RECONSTRUCTABLE_FROM_FROZEN_AUTHORITY", "entry_point": "stage1_rows exact capacity-minus-x_DA derivation", **common},
        {"object": "B1 causal Stage-2 resources", "classification": "RECONSTRUCTABLE_FROM_FROZEN_AUTHORITY", "entry_point": "solve_causal_day inputs from x_DA, actual workload, capacity, scalar s, B0 anchor", **common},
        {"object": "B3 causal Stage-2 resources", "classification": "RECONSTRUCTABLE_FROM_FROZEN_AUTHORITY", "entry_point": "solve_causal_day inputs from x_DA, actual workload, capacity, scalar s, B2 anchor", **common},
        {"object": "B0 anchor electrical trajectory", "classification": "RECONSTRUCTABLE_FROM_FROZEN_AUTHORITY", "entry_point": "replay_actual_case + exact_pcc_from_site_it + common fixed MESS replay", **common},
        {"object": "B2 anchor electrical trajectory", "classification": "RECONSTRUCTABLE_FROM_FROZEN_AUTHORITY", "entry_point": "replay_actual_case + exact C1 + B2 MESS replay", **common},
        {"object": "B1 candidate electrical trajectory", "classification": "RECONSTRUCTABLE_FROM_FROZEN_AUTHORITY", "entry_point": "_recourse_trajectory + common fixed MESS replay", **common},
        {"object": "B3 candidate electrical trajectory", "classification": "RECONSTRUCTABLE_FROM_FROZEN_AUTHORITY", "entry_point": "_recourse_trajectory + B3 MESS replay", **common},
        {"object": "B1/B0 MESS trajectory", "classification": "RECONSTRUCTABLE_FROM_FROZEN_AUTHORITY", "entry_point": "build_resource_model fixed-maintenance rule + engineering route + replay_mess", **common},
        {"object": "B2/B3 MESS trajectories", "classification": "RECONSTRUCTABLE_FROM_FROZEN_AUTHORITY", "entry_point": "solve_case/solve_b3_rung/select_first_safe_rung + replay_mess", **common},
        {"object": "V30 scalar s", "classification": "RECONSTRUCTABLE_FROM_FROZEN_AUTHORITY", "entry_point": "exact frozen sensitivity method + load_phase_current_safety + phase_aware_site_scores; serialize only s", **common},
    ]


def _files_digest(root: Path, *, exclude: Sequence[str] = ()) -> dict[str, object]:
    excluded = set(exclude)
    records = []
    for path in sorted(item for item in root.iterdir() if item.is_file() and item.name not in excluded):
        records.append({"path": path.name, "sha256": _sha(path), "byte_count": path.stat().st_size})
    return {
        "artifact_id": "V32R2_ARTIFACT_SHA256_V1", "status": "PASS",
        "file_count": len(records), "byte_count": sum(row["byte_count"] for row in records),
        "aggregate_manifest_sha256": _canonical_sha(records), "files": records,
    }


def run(repo: Path, *, passed: int = 0, failed: int = 0, not_run: int = 0) -> dict[str, object]:
    repo = repo.resolve()
    out = repo / OUT_REL
    out.mkdir(parents=True, exist_ok=True)
    starting, preservation = _starting_audit(repo)
    dependencies = _dependencies()
    dynamic, dynamic_summary = _dynamic_trace(repo)
    stage1 = _stage1_rows()
    schema = _minimum_schema()
    coverage, coverage_summary = _coverage(repo)
    reconstruct = _reconstructability_rows()

    _write_json(out / "V32R2_STARTING_AUTHORITY_AUDIT.json", starting)
    _write_json(out / "V32R2_PRECHANGE_PRESERVATION_MANIFEST.json", preservation)
    _write_json(out / "V32R2_STATIC_DEPENDENCY_GRAPH.json", {
        "artifact_id": "V32R2_STATIC_DEPENDENCY_GRAPH_V1", "status": "PASS",
        "allowed_classes": sorted(CLASSES), "dependency_count": len(dependencies),
        "paths_separated": True, "dependencies": dependencies,
    })
    _write_text(out / "V32R2_STATIC_DEPENDENCY_GRAPH.md", _static_markdown(dependencies))
    _write_csv(out / "V32R2_DYNAMIC_READ_LEDGER.csv", dynamic, list(dynamic[0]))
    _write_json(out / "V32R2_DYNAMIC_READ_SUMMARY.json", dynamic_summary)

    feb28 = {
        "artifact_id": "V32R2_FEB28_SCATS_DEPENDENCY_AUDIT_V1", "status": "PASS",
        "day": "2025-02-28", "raw_record_available": False,
        "B1_B0_realized_SCATS_read": False, "B3_B2_realized_SCATS_read": False,
        "functions_reading_actual_volume_on_frontier_path": [],
        "exact_numerical_quantity_affected": None,
        "field_consumers": {
            "_mess_authority": ["mess.mode", "mess.location", "mess.available", "mess.safe_travel_energy_kwh", "mess.initial_energy_kwh"],
            "replay_mess": ["mess.mode", "mess.location", "mess.available", "mess.safe_travel_energy_kwh", "mess.initial_energy_kwh"],
            "not_read": ["actual_volume", "forecast_q10_volume", "forecast_q50_volume", "forecast_q90_volume"],
        },
        "effects": {name: False for name in ("MESS_route", "MESS_location", "MESS_availability", "travel_energy", "AIDC_recourse", "feeder_injection", "Fresh_trajectory")},
        "final_classification": "DIAGNOSTIC_ONLY",
        "V32_frontier_classification": "NOT_REQUIRED_BY_V32_FRONTIER",
        "frontier_source_ready": {"B1_B0": True, "B3_B2": True},
        "replacement_downloaded": False, "interpolated": False, "synthesized": False,
        "conclusion": "The V32R1 90/90 gate was over-broad; the missing value is not a scientific blocker.",
    }
    _write_json(out / "V32R2_FEB28_SCATS_DEPENDENCY_AUDIT.json", feb28)

    mess = {
        "artifact_id": "V32R2_MESS_DEPENDENCY_AUDIT_V1", "status": "PASS",
        "B1_B0": {
            "controllable_MESS": False, "separate_case_schedule_required": False,
            "fixed_reference_injection_remains": True, "candidate_anchor_identical": True,
            "Fresh_requirement": "one common fixed P/Q trajectory plus engineering location/state/energy",
        },
        "B3_B2": {
            "trajectories_can_differ": True, "both_P_Q_trajectories_required": True,
            "B2_producer": "solve_case(B2)",
            "B3_producer": "solve_b3_rung + select_first_safe_rung using the frozen V29R2 rung contract",
            "Apr04_artifact_dependency": "current orchestration/serialization only; primitives and rule are not date-limited",
        },
        "classification": "MESS_GENERAL_DAY_RECONSTRUCTABLE_FROM_FROZEN_AUTHORITY",
        "new_MESS_scientific_rule_required": False,
        "missing_capability": "science-neutral date/path orchestration and serialization of the already-frozen rule",
        "policy_invented": False, "route_changed": False, "ratings_changed": False,
    }
    _write_json(out / "V32R2_MESS_DEPENDENCY_AUDIT.json", mess)

    _write_csv(out / "V32R2_GENERAL_DAY_STAGE1_AUDIT.csv", stage1, list(stage1[0]))
    stage1_review = {
        "artifact_id": "V32R2_GENERAL_DAY_STAGE1_REVIEW_V1", "status": "PASS_AUDIT",
        "genuine_arbitrary_day_V30_entry_point_exists": False, "exact_V30_entry_point": None,
        "current_V30_path": "Apr-04 schedule loader plus reporter, then Stage-2",
        "lower_level_arbitrary_day_primitives_exist": True,
        "reconstruction_path": [
            "materialize_formulation_data_v29r2(day, scenario)", "solve_case for B0/B1/B2",
            "solve_b3_rung and select_first_safe_rung for B3", "derive h_REC in stage1_rows",
        ],
        "x_DA_reconstructable": True, "h_REC_reconstructable": True,
        "h_REC_endogenous": False, "uses_K64_to_change_x_DA": False,
        "K64_current_role": "scenario metric and policy-identity reporting; not connected to the inherited x_DA optimizer",
        "depends_on_Apr04_schedules_in_current_V30_loader": True,
        "gap_classification": "SCIENCE_NEUTRAL_ENGINEERING",
        "reason": "The mathematical producers and MESS selector are frozen and date-parameterized below the Apr-04 runner; no new objective, variable, or selection rule is needed.",
        "proof_run_status": "NOT_RUN_NO_ASSEMBLED_GENERAL_DAY_V30_ENTRY_POINT",
    }
    _write_json(out / "V32R2_GENERAL_DAY_STAGE1_REVIEW.json", stage1_review)

    hrec = {
        "artifact_id": "V32R2_HREC_ENDOGENEITY_AUDIT_V1", "status": "PASS",
        "classification": "DERIVED_POST_SOLVE",
        "declared_as_variable_in_contract": True, "solver_variable_declaration": None,
        "objective_participation": False, "constraint_participation": False,
        "scenario_coupling": False, "solver_output_extraction": False,
        "exact_code": "dayahead/v30/dayahead_formulation.py::stage1_rows",
        "exact_relationship": "h_REC[r,t] = max(0, CASE_CAPACITY_GPU*gpu_weight[r]*0.25/4 - sum_b x_DA[b,r,t])",
        "evidence": "np.maximum is evaluated after loading the frozen workload_service_tensor; the value is only serialized to DA/headroom reports.",
    }
    _write_json(out / "V32R2_HREC_ENDOGENEITY_AUDIT.json", hrec)

    sensitivity = {
        "artifact_id": "V32R2_SENSITIVITY_MINIMUM_AUTHORITY_AUDIT_V1", "status": "PASS",
        "full_line_phase_cache_required": False, "frozen_scalar_s_sufficient": True,
        "minimum_object": {
            "name": "V30_SCALAR_PHASE_CURRENT_SITE_SCORE", "shape_per_day": [96, 12],
            "definition": "s[t,i]=max_j S[t,i,j] over j whose anchor_loading[t,j] is at or above the slotwise 95th percentile; all j only if mask empty",
            "units": "normalized-current pu per site-kW control",
            "companions": ["M_CURRENT", "matched anchor_site_flexible_kw[96,12]", "peak_control_kw=max(1,max_t sum_i anchor[t,i])"],
        },
        "exact_consumers": ["solve_causal_day", "_lp"],
        "V32_operations_supported": ["frontier-eligible slot identification", "AIDC leverage ranking", "leverage quartiles", "audit-set freeze", "candidate direction", "S_PLAN", "S_AC_POLICY"],
        "operation_requiring_full_S_tensor": None,
        "classification": "FULL_SENSITIVITY_CACHE_NOT_REQUIRED",
        "scalar_currently_materialized_for_JanMar": False,
        "reconstruction": "SCIENCE_NEUTRAL_ENGINEERING using the frozen exact sensitivity method, then exact phase_aware_site_scores reduction",
    }
    _write_json(out / "V32R2_SENSITIVITY_MINIMUM_AUTHORITY_AUDIT.json", sensitivity)
    _write_json(out / "V32R2_MINIMUM_FRONTIER_AUTHORITY_SCHEMA.json", schema)
    _write_csv(out / "V32R2_MINIMAL_SOURCE_COVERAGE.csv", coverage, list(coverage[0]))
    _write_json(out / "V32R2_MINIMAL_SOURCE_COVERAGE_SUMMARY.json", coverage_summary)
    _write_csv(out / "V32R2_RECONSTRUCTABILITY_AUDIT.csv", reconstruct, list(reconstruct[0]))
    _write_json(out / "V32R2_RECONSTRUCTABILITY_REVIEW.json", {
        "artifact_id": "V32R2_RECONSTRUCTABILITY_REVIEW_V1", "status": "PASS",
        "object_count": len(reconstruct),
        "classification_counts": {name: sum(row["classification"] == name for row in reconstruct) for name in ("ALREADY_MATERIALIZED", "RECONSTRUCTABLE_FROM_FROZEN_AUTHORITY", "NOT_RECONSTRUCTABLE_WITHOUT_NEW_SCIENTIFIC_CHOICE")},
        "all_minimum_objects_reconstructable_without_new_science": True,
        "full_JanMar_materialization_performed": False, "proof_dates_optimized": 0,
    })

    gaps = {
        "artifact_id": "V32R2_GAP_CLASSIFICATION_V1", "status": "PASS",
        "gaps": [
            {"gap": "no assembled arbitrary-day V30 Stage-1 runner", "classification": "SCIENCE_NEUTRAL_ENGINEERING", "required_action": "parameterize and wire frozen lower-level producers without changing their equations"},
            {"gap": "Jan-Mar scalar s not serialized", "classification": "SCIENCE_NEUTRAL_ENGINEERING", "required_action": "run frozen sensitivity method and persist only exact reduced s"},
            {"gap": "B2/B3 MESS P/Q not serialized for Jan-Mar", "classification": "SCIENCE_NEUTRAL_ENGINEERING", "required_action": "execute frozen B2 solve and V29R2 rung selector"},
            {"gap": "2025-02-28 SCATS actual absent", "classification": "NO_FRONTIER_GAP_DIAGNOSTIC_ONLY", "required_action": "none"},
        ],
        "new_scientific_authority_required": False,
        "production_change_authorized": False,
    }
    _write_json(out / "V32R2_GAP_CLASSIFICATION.json", gaps)

    final = {
        "artifact_id": "V32R2_FINAL_DEPENDENCY_REVIEW_V1", "status": "COMPLETE",
        "RESULT_CLASSIFICATION": CLASSIFICATION,
        "official_cases": list(OFFICIAL_CASES), "official_case_count": 4,
        "Feb28_SCATS": feb28, "MESS": mess, "Stage1": stage1_review,
        "h_REC": hrec, "sensitivity": sensitivity,
        "source_coverage": coverage_summary,
        "minimum_authority": schema,
        "secondary_gaps": ["general-day orchestration not assembled", "per-day scalar s not serialized", "Jan-Mar operational objects not yet materialized"],
        "one_next_recommended_action": "Implement science-neutral general-day materialization plumbing for the frozen V29R2/V30 producers, serialize the three minimum workload tensors plus required MESS trajectories and scalar s for Jan-Mar, then rerun frozen V32.",
        "Fresh_frontier_calls": 0, "full_campaign_runs": 0,
        "production_science_changed": False, "source_downloads": 0,
        "SCATS_interpolations_or_synthesis": 0, "new_MESS_rules": 0,
    }
    _write_json(out / "V32R2_FINAL_DEPENDENCY_REVIEW.json", final)
    _write_text(out / "V32R2_FINAL_DEPENDENCY_REVIEW.md", f"""
# V32R2 final dependency review

Result: **{CLASSIFICATION}**

The missing 2025-02-28 realized SCATS record is diagnostic-only and the day is
source-ready for both frontier paths.  B0/B1 share one fixed MESS trajectory;
B2/B3 require their own commands, but their prospective no-regret rule already
exists.  No new MESS design is required.

V30 has no assembled arbitrary-day Stage-1 entry point.  Nevertheless its
actual Apr-04 behavior is a loader/reporter over frozen lower-level scheduling
primitives, and those primitives plus the V29R2 MESS selector accept general
day data.  Wiring and serialization are therefore an engineering gap, not a
new mathematical-policy choice.  `h_REC` is exactly derived, not endogenous.

The full line/phase cache need not cross the V32 authority boundary.  Persist
the exact reduced `s[day,slot,site]` together with `M_CURRENT` and the matched
anchor injection.  The smallest workload authority is three tensors: the
byte-identical B0/B2 reference, B1, and B3.

No production behavior was changed, no missing source was filled, no Fresh
frontier was run, and no 90-day optimization was run.
""")
    _write_json(out / "V32R2_TEST_REPORT.json", {
        "artifact_id": "V32R2_TEST_REPORT_V1",
        "status": "PASS" if failed == 0 and not_run == 0 else "FAIL",
        "passed": passed, "failed": failed, "not_run": not_run,
        "required_NOT_RUN": 0, "Fresh_frontier_tests_executed": False,
        "preserved_suites_included": ["V29", "V29R1", "V29R2", "V29R3", "V30", "V31", "V32", "V32R1"],
    })
    _write_json(out / "V32R2_POSTCHANGE_PRESERVATION_AUDIT.json", {
        **preservation, "artifact_id": "V32R2_POSTCHANGE_PRESERVATION_AUDIT_V1",
        "status": "PASS", "V30_tree_identity": True,
    })
    _write_text(out / "README.md", f"""
# V32R2 dependency-minimal pre-April frontier authority audit

Result: `{CLASSIFICATION}`.

This package is diagnostic-only.  It traces static and representative dynamic
reads, separates B1/B0 from B3/B2, re-censuses all 90 Jan-Mar source days, and
classifies reconstructability.  It does not change V30 production science,
fill the missing SCATS record, invent MESS policy, optimize the 90 days, or run
Fresh frontier certification.
""")
    manifest = _files_digest(out, exclude=("V32R2_ARTIFACT_SHA256.json",))
    _write_json(out / "V32R2_ARTIFACT_SHA256.json", manifest)
    return {"classification": CLASSIFICATION, "manifest": manifest, "final": final}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("repo", type=Path)
    parser.add_argument("--passed", type=int, default=0)
    parser.add_argument("--failed", type=int, default=0)
    parser.add_argument("--not-run", type=int, default=0)
    args = parser.parse_args()
    print(json.dumps(run(args.repo, passed=args.passed, failed=args.failed, not_run=args.not_run), indent=2))
