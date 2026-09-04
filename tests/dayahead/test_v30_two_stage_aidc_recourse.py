from __future__ import annotations

import ast
import csv
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from dayahead.v29r3.forensic import preservation_snapshot
from dayahead.v30.actual_recourse import CausalReadLedger, _classify_execution, solve_causal_day
from dayahead.v30.contracts import (
    CASE_ACTUATORS, OFFICIAL_CASES, STARTING_SHA, aidc_policy_config,
    eligibility_contract, four_case_contract, information_firewall_contract,
    two_stage_contract,
)
from dayahead.v30.dayahead_formulation import load_frozen_schedules, reference_compute_payload
from dayahead.v30.grid_safety import derive_margin
from dayahead.v30.reporting import finalize_manifest
from dayahead.v30.scenario_recourse import build_day_population, certify_count, scenario_set


REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "dayahead/artifacts/v30_two_stage_aidc_recourse"
TRUST = Path(r"C:\codex_mobileess_workspace\MobileESS_v29r1\cache\v29r1_trust_cert_sources\jan_mar_2025")


def artifact(name: str) -> dict[str, object]:
    return json.loads((OUT / name).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def schedules():
    return load_frozen_schedules(REPO)


@pytest.fixture(scope="module")
def synthetic_result():
    owners = [f"AIDC{i // 4 + 1:02d}" for i in range(48)]
    da = np.zeros((15, 48, 96)); da[0, 0, :] = 0.1
    arrivals = np.zeros((96, 15)); arrivals[:, 0] = 0.1
    capacity = np.ones((96, 48))
    scores = np.zeros((96, 12))
    from dayahead.aidc_power_response import KAPPA_KW_PER_ACTIVE_H100_NODE
    anchor = np.zeros((96, 12)); anchor[:, 0] = 0.1 * KAPPA_KW_PER_ACTIVE_H100_NODE[1] / 0.25
    return solve_causal_day(da, arrivals, capacity, owners, scores, anchor, 0.0)


def test_01_starting_authority_artifact():
    assert artifact("V30_STARTING_AUTHORITY_AUDIT.json")["verified_starting_SHA"] == STARTING_SHA


def test_02_official_cases_exact():
    assert OFFICIAL_CASES == ("B0", "B1", "B2", "B3")


def test_03_no_fifth_case():
    assert four_case_contract()["official_case_count"] == 4


@pytest.mark.parametrize("case", OFFICIAL_CASES)
def test_04_case_contract_has_each(case):
    assert case in CASE_ACTUATORS


def test_05_b0_b2_reference_bytes(schedules):
    assert reference_compute_payload(schedules)["workload_service_tensor"] == schedules["B2"]["workload_service_tensor"]


def test_06_b0_b2_reference_sha_identity():
    row = artifact("V30_B0_B2_REFERENCE_IDENTITY.json")
    assert row["B0_sha256"] == row["B2_sha256"] and row["byte_identical"]


def test_07_b1_b3_policy_identity():
    row = artifact("V30_B1_B3_AIDC_POLICY_IDENTITY.json")
    assert row["B1_policy_sha256"] == row["B3_policy_sha256"] and row["byte_config_identical"]


def test_08_same_slot_only_contract():
    assert two_stage_contract()["stage_2"]["same_slot_constraint"] == "sum_r y_ACT[b,r,t] <= sum_r x_DA[b,r,t]"


def test_09_future_read_rejected():
    ledger = CausalReadLedger([])
    with pytest.raises(RuntimeError, match="FUTURE_READ"):
        ledger.read("x", np.zeros((2, 1)), 0, 1)
    assert ledger.future_actual_reads == 1


def test_10_strict_full_only():
    assert "strict FULL-node" in eligibility_contract()["included"]


def test_11_partial_shared_excluded():
    assert "PARTIAL/shared" in eligibility_contract()["excluded"]


@pytest.mark.parametrize("field", ["running_job_migration", "preemption", "checkpoint_restart", "synthetic_workload", "synthetic_deadline"])
def test_12_forbidden_workload_actions_zero(field):
    assert eligibility_contract()[field] == 0


def test_13_da_same_slot_upper_bound(synthetic_result):
    assert synthetic_result.summary["maximum_same_slot_authorization_excess_nodeh"] <= 1e-9


def test_14_backlog_conservation(synthetic_result):
    assert abs(synthetic_result.summary["authorization_mass_identity_error_nodeh"]) <= 1e-9


def test_15_rack_capacity(synthetic_result):
    assert np.max(synthetic_result.executed_nodeh.sum(axis=0).T) <= 1.0 + 1e-9


def test_16_same_site_classification():
    da = np.zeros((1, 4)); da[0, 0] = 1
    y = np.zeros_like(da); y[0, 1] = 1
    assert _classify_execution(y, da, np.array([0, 0, 1, 1])) == (0.0, 1.0, 0.0)


def test_17_cross_site_classification():
    da = np.zeros((1, 4)); da[0, 0] = 1
    y = np.zeros_like(da); y[0, 2] = 1
    assert _classify_execution(y, da, np.array([0, 0, 1, 1])) == (0.0, 0.0, 1.0)


def test_18_no_invented_compatibility():
    assert artifact("V30_CROSS_SITE_COMPATIBILITY_AUDIT.json")["new_compatibility_invented"] is False


def test_19_deterministic_tie_break(synthetic_result):
    assert synthetic_result.summary["EXECUTED_SAME_SITE_RECOURSE"] == 0


def test_20_mess_reoptimization_zero(synthetic_result):
    assert synthetic_result.mess_reoptimization_calls == 0


def test_21_full_system_reoptimization_zero(synthetic_result):
    assert synthetic_result.full_system_reoptimization_calls == 0


def test_22_epochs_96(synthetic_result):
    assert synthetic_result.recourse_epochs == 96


def test_23_solver_subcalls_disclosed(synthetic_result):
    assert synthetic_result.solver_subcalls == 384


def test_24_service_first(synthetic_result):
    assert synthetic_result.summary["EXECUTED_TOTAL"] == pytest.approx(synthetic_result.summary["DA_AUTHORIZED"], abs=1e-8)


def test_25_no_hidden_service_deletion(synthetic_result):
    assert abs(synthetic_result.summary["authorization_mass_identity_error_nodeh"]) <= 1e-9


def test_26_margin_preapril_only():
    rows, decision = derive_margin(REPO)
    assert decision["April_rows_used"] == 0 and all(row["day"] < "2025-04-01" for row in rows)


def test_27_margin_formula():
    rows, decision = derive_margin(REPO)
    assert decision["V30_NOREGRET_SAFETY_MARGIN_PU"] == max(row["one_sided_candidate_minus_anchor_error_bound_pu"] for row in rows)


def test_28_scenario_rows_no_april():
    population = build_day_population(REPO, TRUST)
    assert all(row.source_day < "2025-04-01" for row in population)


def test_29_scenario_count_no_april():
    _rows, decision, _set = certify_count(build_day_population(REPO, TRUST))
    assert decision["April_rows_used"] == 0


def test_30_scenario_sha_frozen():
    assert len(artifact("V30_SCENARIO_COUNT_DECISION.json")["V30_SCENARIO_SET_SHA256"]) == 64


def test_31_no_fixed_headroom_percentage():
    assert artifact("V30_DAYAHEAD_FORMULATION_CONTRACT.json")["manual_fixed_headroom"] is None


def test_32_common_stage1_contract():
    assert artifact("V30_DAYAHEAD_FORMULATION_CONTRACT.json")["common_cases"] == list(OFFICIAL_CASES)


def test_33_actual_module_has_no_opendss_import():
    path = REPO / "dayahead/v30/actual_recourse.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = [node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
    assert not any("opendss" in name.lower() for name in names)


def test_34_fresh_expost_runner_exact_cases():
    with (OUT / "V30_APR04_FRESH_OPENDSS_RESULTS.csv").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert tuple(row["case"] for row in rows) == OFFICIAL_CASES
    assert all(int(row["convergence_count"]) == 96 for row in rows)


def test_35_mass_ledger_identity(synthetic_result):
    assert synthetic_result.summary["maximum_slot_authorization_identity_error_nodeh"] <= 1e-9


@pytest.mark.parametrize("token", ["0.528808791958", "rho_AIDC\": 1.0", "AIDC_PF\": 0.95"])
def test_36_physical_authority_not_overridden(token):
    source = (REPO / "dayahead/v30/contracts.py").read_text(encoding="utf-8")
    if token.startswith("0.528"):
        assert token not in source  # scale is reused, never copied/overridden
    else:
        assert token in source


def test_37_mess_rating_not_defined_in_v30():
    assert "MESS_RATING" not in (REPO / "dayahead/v30/contracts.py").read_text(encoding="utf-8")


def test_38_feeder_not_changed():
    assert not any((REPO / "dayahead/v30").rglob("*.dss"))


def test_39_historical_preservation():
    assert preservation_snapshot(REPO)["status"] == "PASS"


def test_40_manifest_self_consistency(tmp_path):
    (tmp_path / "a.txt").write_text("a\n", encoding="utf-8")
    manifest = finalize_manifest(tmp_path)
    row = manifest["files"][0]
    assert row["sha256"] == hashlib.sha256((tmp_path / row["path"]).read_bytes()).hexdigest()


def test_41_required_not_run_zero_contract():
    assert artifact("V30_TEST_REPORT.json")["required_test_not_run_count"] == 0


def test_42_causal_read_count_zero(synthetic_result):
    assert synthetic_result.future_actual_reads == 0


def test_43_information_firewall():
    assert information_firewall_contract()["required_future_actual_reads"] == 0


def test_44_scenario_candidates_nested():
    population = build_day_population(REPO, TRUST)
    eight = [x.payload() for x in scenario_set(population, 8)]
    sixteen = [x.payload() for x in scenario_set(population, 16)]
    assert sixteen[:8] == eight


def test_45_policy_same_slot_and_causal():
    policy = aidc_policy_config(0.1, 8, "a" * 64)
    assert policy["same_slot_only"] and policy["causal"] and policy["future_actual_reads"] == 0


def _actual_rows():
    with (OUT / "V30_APR04_ACTUAL_RESULTS.csv").open(encoding="utf-8", newline="") as stream:
        return {row["case"]: row for row in csv.DictReader(stream)}


@pytest.mark.parametrize("case", ["B1", "B3"])
def test_46_apr04_recourse_complete_and_causal(case):
    row = _actual_rows()[case]
    assert int(row["AIDC_SECOND_STAGE_RECOURSE_EPOCHS"]) == 96
    assert int(row["AIDC_SECOND_STAGE_SOLVER_SUBCALLS"]) == 384
    assert int(row["future_Actual_reads"]) == 0


@pytest.mark.parametrize("case", ["B0", "B2"])
def test_47_reference_cases_have_no_recourse(case):
    row = _actual_rows()[case]
    assert int(row["AIDC_SECOND_STAGE_RECOURSE_EPOCHS"]) == 0


def test_48_apr04_fresh_no_regret():
    review = artifact("V30_APR04_DEVELOPMENT_REVIEW.json")
    assert review["B1_B0_Fresh_no_regret"] and review["B3_B2_Fresh_no_regret"]


def test_49_apr04_classification_pass():
    assert artifact("V30_APR04_DEVELOPMENT_REVIEW.json")["RESULT_CLASSIFICATION"] == "V30_APR04_TWO_STAGE_AIDC_DEVELOPMENT_CHECKPOINT_PASS"


def test_50_no_april_tuning_after_smoke():
    assert artifact("V30_APR04_DEVELOPMENT_REVIEW.json")["April_rows_used_for_tuning_or_certification"] == 0
