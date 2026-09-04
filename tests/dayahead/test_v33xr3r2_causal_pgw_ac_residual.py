from __future__ import annotations

import csv
import json
import subprocess
from pathlib import Path

import pandas as pd
import pytest

from dayahead.v28r2.lightgbm_channels import COMMON, DAILY_FEATURES, SLOT_FEATURES
from dayahead.v33xr3r2.contracts import BRANCH, CASE, SMOKE_DAYS, STARTING_HEAD, TARGET_DAYS
from dayahead.v33xr3r2.rolling_pgw import frozen_specs, issue_time


REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "dayahead/artifacts/v33xr3r2_causal_pgw_ac_residual"


def _json(name: str) -> dict[str, object]:
    return json.loads((OUT / name).read_text(encoding="utf-8"))


def _csv(name: str) -> list[dict[str, str]]:
    with (OUT / name).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _git(*args: str) -> str:
    return subprocess.check_output(["git", "-C", str(REPO), *args], text=True).strip()


def _checks() -> list[tuple[str, bool]]:
    contract = _json("V33XR3R2_CONTRACT.json")
    freeze = _json("V33XR3R2_MODEL_SPEC_FREEZE.json")
    causal = _json("V33XR3R2_PGW_CAUSALITY_AUDIT.json")
    source = _json("V33XR3R2_PGW_SOURCE_AUDIT.json")
    firewall = _json("V33XR3R2_FIREWALL_AUDIT.json")
    residual = _json("V33XR3R2_BASE_RESIDUAL_SUMMARY.json")
    axis = _json("V33XR3R2_AXIS_MAPPING_AUDIT.json")
    candidate = _json("V33XR3R2_CANDIDATE_CORRECTION_CONTRACT.json")
    review = _json("V33XR3R2_FINAL_REVIEW.json")
    pgw = _csv("V33XR3R2_PGW_DAY_STATUS.csv")
    forecasts = _csv("V33XR3R2_PGW_FORECAST_SHA256.csv")
    b1 = _csv("V33XR3R2_B1_DAY_STATUS.csv")
    schedules = _csv("V33XR3R2_SCHEDULE_SHA256.csv")
    families = _csv("V33XR3R2_CORRECTION_FAMILY_COMPARISON.csv")
    specs = frozen_specs(REPO)
    smoke = causal["smoke"]
    mess_paths = ("dayahead/mess_physics.py", "dayahead/v28r2/mess_replay.py", "dayahead/v28r2/variable_registry.py")
    mess_diff = _git("diff", "--name-only", STARTING_HEAD, "--", *mess_paths)
    mess_status = _git("status", "--porcelain", "--", *mess_paths)
    definitions = residual["definition"]
    return [
        ("exact starting HEAD", STARTING_HEAD == "2a88c99bf02aed2e170caaf0e389ab1faeb48a6d" and _git("merge-base", "HEAD", STARTING_HEAD) == STARTING_HEAD and _git("branch", "--show-current") == BRANCH),
        ("fixed AEST cutoff", issue_time("2025-01-01") == pd.Timestamp("2024-12-31 18:00:00+10:00") and contract["issue_cutoff"] == "D-1 18:00 fixed AEST UTC+10"),
        ("identical spec", freeze["identical_for_all_90_target_days"] is True and len({json.dumps(specs[c], sort_keys=True) for c in specs}) == 3),
        ("only cutoff changes", freeze["only_allowed_daily_change"] == "causal expanding-window training cutoff/statistics"),
        ("future features zero", causal["future_feature_read_count"] == 0),
        ("future labels zero", causal["future_label_read_count"] == 0),
        ("label availability gate", tuple(row["day"] for row in smoke) == SMOKE_DAYS and all(not row["gate_pass"] and "lag_2d" in row["missing_target_features"] for row in smoke)),
        ("P semantics", freeze["channels"]["P"]["target"] == "P^IT,REF total IT active power" and freeze["channels"]["P"]["features_in_order"] == list(SLOT_FEATURES)),
        ("G semantics", freeze["channels"]["G"]["target"] == "G^REF H100 occupancy" and freeze["channels"]["G"]["features_in_order"] == list(SLOT_FEATURES)),
        ("W semantics", freeze["channels"]["W"]["target"].startswith("W^F strict FULL-node") and freeze["channels"]["W"]["features_in_order"] == list(DAILY_FEATURES)),
        ("P Q90", freeze["channels"]["P"]["optimizer_statistic"] == "Q90"),
        ("G Q90", freeze["channels"]["G"]["optimizer_statistic"] == "Q90"),
        ("W Q50", freeze["channels"]["W"]["optimizer_statistic"] == "Q50"),
        ("no partial/shared W", source["partial_shared_controllable_W"] is False),
        ("W mass identity contract", freeze["channels"]["W"]["optimizer_shape"] == [96, 15] and review["PGW"]["W_max_mass_error"] is None),
        ("causal rolling statistics", all(not row["lag_2d_available_by_issue"] for row in smoke)),
        ("no HPO", freeze["model_selection_or_HPO"] is False and COMMON["random_state"] == 20260901),
        ("90-day forecast shape", len(TARGET_DAYS) == len(pgw) == len(forecasts) == 90 and all(row["forecast_bundle_complete"] == "False" for row in pgw)),
        ("deterministic SHA fail closed", all(not row["forecast_sha256"] and row["status"] == "NOT_MATERIALIZED" for row in forecasts)),
        ("B1 only", CASE == "B1" and {row["case"] for row in b1} == {"B1"}),
        ("planning 0.95-1.05", contract["planning_limits_pu"] == [0.95, 1.05]),
        ("no 1.0495", 1.0495 not in contract["planning_limits_pu"]),
        ("no Actual Stage2", firewall["Actual_Stage2_calls"] == 0),
        ("no E2", firewall["E2_calls"] == 0),
        ("no PI", firewall["PI_calls"] == 0),
        ("no Fresh before freeze", firewall["Fresh_reads_before_schedule_freeze"] == 0),
        ("exact schedule SHA fail closed", len(schedules) == 90 and all(row["identity_status"] == "NOT_EVALUATED" and not row["Stage1_schedule_sha256"] for row in schedules)),
        ("future Actual zero", firewall["Actual_Stage2_calls"] == firewall["E1_Actual_recourse_calls"] == 0),
        ("96-slot Planning contract", contract["slots_per_day"] == 96 and review["B1"]["Planning_complete_days"] == 0),
        ("96-slot Fresh contract", contract["slots_per_day"] == 96 and review["B1"]["Fresh_96_of_96_days"] == 0),
        ("node mapping", axis["mapping_completeness_claimed"] is False and axis["matched_count"] == 0),
        ("phase mapping", axis["phase_mismatch_count"] == 0 and axis["status"] == "NOT_RUN_PHASE_A_GATE"),
        ("schedule identity", review["B1"]["schedule_identity_failures"] == 0 and review["B1"]["exact_matched_days"] == 0),
        ("no Fresh cut", firewall["Fresh_cuts"] == 0),
        ("no Fresh reoptimization", firewall["Fresh_reoptimization_calls"] == 0),
        ("no Fresh oracle", firewall["FRESH_OPTIMIZER_ORACLE_CALLS"] == 0),
        ("E_SIGNED", definitions["E_SIGNED"] == "V_FRESH - V_PLAN"),
        ("E_UP", definitions["E_UP"] == "max(0, V_FRESH - V_PLAN)"),
        ("E_LOW", definitions["E_LOW"] == "max(0, V_PLAN - V_FRESH)"),
        ("Jan-Feb only", residual["calibration"] == ["2025-01-01", "2025-02-28", 59]),
        ("March only", residual["prospective_validation"] == ["2025-03-01", "2025-03-31", 31]),
        ("M1 Jan-Feb", next(row for row in families if row["family"] == "M1")["calibration_source"] == "JAN_FEB_ONLY"),
        ("M2 Jan-Feb", next(row for row in families if row["family"] == "M2")["calibration_source"] == "JAN_FEB_ONLY"),
        ("M3 Jan-Feb", next(row for row in families if row["family"] == "M3")["calibration_source"] == "JAN_FEB_ONLY"),
        ("selection rule", "25%" in contract["family_selection_rule"] and candidate["selected_NEXT_CORRECTION_FAMILY"] is None),
        ("no April", firewall["APRIL_ROWS_USED"] == firewall["APR04_NUMERIC_RESULT_READS"] == 0),
        ("AIDC scale unchanged", firewall["AIDC_physical_scale_changes"] == 0),
        ("PF unchanged", firewall["PF_changes"] == 0),
        ("C1 unchanged", firewall["C1_changes"] == 0),
        ("objective unchanged", firewall["objective_changes"] == 0),
        ("rack capacity unchanged", firewall["rack_capacity_changes"] == 0),
        ("MESS unchanged", firewall["MESS_files_changed"] == 0 and firewall["V33M3_modifications"] == 0 and not mess_diff and not mess_status),
        ("MESS optimization zero", firewall["MESS_optimization_calls"] == 0),
    ]


CHECKS = _checks()


@pytest.mark.parametrize(("name", "passed"), CHECKS, ids=[f"{index:02d}-{name}" for index, (name, _) in enumerate(CHECKS, 1)])
def test_v33xr3r2_targeted_gate(name: str, passed: bool) -> None:
    assert passed, name
