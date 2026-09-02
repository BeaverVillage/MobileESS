from __future__ import annotations

import ast
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from dayahead.v34 import (
    CALIBRATION_DAYS,
    CASE_ACTUATORS,
    OFFICIAL_CASES,
    VALIDATION_DAYS,
    ResidualRow,
    bind_squared_voltage_bounds,
    calibrate_candidates,
    evaluate_and_select,
    solve_resource_only_recourse,
)
from dayahead.v34.contracts import (
    ACTUAL_AIDC_FIREWALL_FIELDS,
    AIDC_STARTING_HEAD,
    BRANCH,
    CANDIDATE_FAMILIES,
    MAY_FIREWALL_FIELDS,
    MESS_PREINTEGRATION_HEAD,
    MESS_SOURCE_HEAD,
    PHASE_LABELS,
    assert_official_cases,
    reject_may,
)


REPO = Path(__file__).resolve().parents[2]
SHA = "a" * 64


def row(day="2025-04-01", case="B1", slot=0, node="n1", phase="A", plan=1.0, fresh=1.001):
    return ResidualRow(day, case, slot, node, phase, SHA, SHA, SHA, plan, fresh)


def calibration_rows():
    result = []
    for day_index, day in enumerate(CALIBRATION_DAYS):
        for case_index, case in enumerate(("B1", "B3")):
            for slot in (0, 24, 48, 72):
                error = (day_index + 1 + case_index) * 1e-5 + (slot // 24) * 1e-6
                result.append(row(day, case, slot, "n1", "A", 1.0, 1.0 + error))
                result.append(row(day, case, slot, "n2", "B", 1.0, 1.0 - error / 2))
    return result


def validation_rows(up=1e-5, low=1e-5):
    result = []
    for day in VALIDATION_DAYS:
        for case in ("B1", "B3"):
            result.append(row(day, case, 0, "n1", "A", 1.0, 1.0 + up))
            result.append(row(day, case, 25, "n2", "B", 1.0, 1.0 - low))
    return result


def test_01_exact_starting_heads_and_branch():
    assert AIDC_STARTING_HEAD == "8749f7785a61e0d3574dc3d847e63c8cd534ffbf"
    assert MESS_SOURCE_HEAD == "e02ea8d9be9298a482faf42d97a7cb9ec6a7c2fc"
    assert MESS_PREINTEGRATION_HEAD == "d42c3d2bdf1282f9e31563adfdbcf3100aa71f93"
    assert BRANCH == "codex/v34-aidc-mess-april-calibration-validation"


def test_02_exact_four_case_registry():
    assert OFFICIAL_CASES == ("B0", "B1", "B2", "B3")
    assert tuple(CASE_ACTUATORS) == OFFICIAL_CASES
    assert CASE_ACTUATORS["B0"] == {"aidc": False, "mess": False}
    assert CASE_ACTUATORS["B1"] == {"aidc": True, "mess": False}
    assert CASE_ACTUATORS["B2"] == {"aidc": False, "mess": True}
    assert CASE_ACTUATORS["B3"] == {"aidc": True, "mess": True}
    assert_official_cases(list(OFFICIAL_CASES))
    with pytest.raises(ValueError):
        assert_official_cases(["B0", "B1", "B2", "B3", "M1"])


def test_02b_v34_aidc_stage_does_not_import_legacy_mess_conditioning():
    from tools.v34.run_integration_smoke import _aidc_stage_case

    assert tuple(_aidc_stage_case(case) for case in OFFICIAL_CASES) == (
        "B0", "B1", "B0", "B1",
    )


def test_03_fixed_chronology_and_labels():
    assert len(CALIBRATION_DAYS) == 20 and CALIBRATION_DAYS[0] == "2025-04-01" and CALIBRATION_DAYS[-1] == "2025-04-20"
    assert len(VALIDATION_DAYS) == 10 and VALIDATION_DAYS[0] == "2025-04-21" and VALIDATION_DAYS[-1] == "2025-04-30"
    assert PHASE_LABELS == (
        "APR01_20_AC_FIDELITY_CALIBRATION",
        "APR21_30_PROSPECTIVE_UNCORRECTED_RESIDUAL_VALIDATION",
        "APR21_30_CORRECTED_INTEGRATED_VALIDATION",
    )
    assert CANDIDATE_FAMILIES == ("M1", "M2", "M3")


def test_04_residual_definitions_are_exact():
    positive = row(plan=1.0, fresh=1.01)
    negative = row(plan=1.0, fresh=.98)
    assert positive.e_signed == pytest.approx(.01)
    assert positive.e_up == pytest.approx(.01) and positive.e_low == 0
    assert negative.e_up == 0 and negative.e_low == pytest.approx(.02)
    assert negative.e_abs == pytest.approx(.02)


def test_05_schedule_sha_identity_is_mandatory():
    with pytest.raises(ValueError, match="MISMATCH"):
        replace(row(), fresh_schedule_sha="b" * 64).validate()


def test_06_actual_residual_is_rejected():
    with pytest.raises(ValueError, match="ACTUAL"):
        replace(row(), namespace="ACTUAL").validate()


def test_07_calibration_rejects_apr21_and_non_b1b3():
    with pytest.raises(ValueError):
        calibrate_candidates([row(day="2025-04-21")])
    with pytest.raises(ValueError):
        calibrate_candidates([row(case="B0")])


def test_08_m1_is_combined_b1_b3_maximum():
    values = calibration_rows()
    candidates = calibrate_candidates(values)
    assert candidates.m1.up["GLOBAL"] == max(item.e_up for item in values)
    assert candidates.m1.low["GLOBAL"] == max(item.e_low for item in values)


def test_09_m2_native_node_phase_and_m1_fallback():
    candidates = calibrate_candidates(calibration_rows(), [("n1", "A"), ("n2", "B"), ("n3", "C")])
    assert candidates.m2.up["n1|A"] < candidates.m1.up["GLOBAL"] + 1e-15
    assert candidates.m2.up["n3|C"] == candidates.m1.up["GLOBAL"]
    assert candidates.m2.low["n3|C"] == candidates.m1.low["GLOBAL"]
    assert candidates.m2.fallback_count == 1


def test_10_m3_fixed_blocks_and_m2_fallback():
    candidates = calibrate_candidates([row(slot=0)], [("n1", "A")])
    assert candidates.m3.up["n1|A|0"] == row().e_up
    assert candidates.m3.up["n1|A|1"] == candidates.m2.up["n1|A"]
    assert candidates.m3.fallback_count == 3


def test_11_candidate_freeze_sha_is_deterministic():
    first = calibrate_candidates(calibration_rows())
    second = calibrate_candidates(calibration_rows())
    assert first.freeze_sha256 == second.freeze_sha256
    assert first.m1.canonical_sha256 == second.m1.canonical_sha256


def test_12_validation_does_not_mutate_candidate_numbers():
    candidates = calibrate_candidates(calibration_rows())
    before = [item.canonical_sha256 for item in (candidates.m1, candidates.m2, candidates.m3)]
    evaluate_and_select(candidates, validation_rows())
    after = [item.canonical_sha256 for item in (candidates.m1, candidates.m2, candidates.m3)]
    assert before == after


def test_13_simplest_covering_family_selected_without_25pct_gain():
    candidates = calibrate_candidates(calibration_rows())
    selected, reports, reason = evaluate_and_select(candidates, validation_rows())
    assert selected is not None and reports[selected.family]["covering"]
    assert reason in {"SIMPLEST_COVERING_FAMILY", "MORE_COMPLEX_COVERING_FAMILY_AT_LEAST_25_PERCENT_LESS_MEAN_CORRECTION"}


def test_14_no_covering_family_fails_closed():
    candidates = calibrate_candidates(calibration_rows())
    selected, reports, reason = evaluate_and_select(candidates, validation_rows(up=.1, low=.1))
    assert selected is None
    assert not any(value["covering"] for value in reports.values())
    assert reason == "STATIC_AC_FIDELITY_CORRECTION_INSUFFICIENT"


def test_15_squared_voltage_conversion_exact():
    lower, upper = bind_squared_voltage_bounds(.002, .003)
    assert upper == pytest.approx((1.05 - .002) ** 2)
    assert lower == pytest.approx((.95 + .003) ** 2)
    assert upper != pytest.approx(1.05**2 - .002)


def test_16_empty_corrected_interval_fails_closed():
    with pytest.raises(ValueError):
        bind_squared_voltage_bounds(.1, .1)


def test_17_actual_resource_recourse_has_no_electrical_signature_or_import():
    path = REPO / "dayahead/v34/actual_resource_recourse.py"
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports = [node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
    imports += [name.name for node in ast.walk(tree) if isinstance(node, ast.Import) for name in node.names]
    assert not any(token in name.lower() for name in imports for token in ("fresh", "opendss", "grid"))
    signature = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "solve_resource_only_recourse")
    names = {arg.arg.lower() for arg in signature.args.args + signature.args.kwonlyargs}
    assert not any(token in name for name in names for token in ("voltage", "current", "transformer", "rho", "fresh", "sensitivity"))


def test_18_actual_resource_recourse_conserves_mass_and_reports_zero_firewall():
    da = np.zeros((2, 2, 96)); da[0, 0, 0] = 1; da[1, 1, 0] = 1
    arrivals = np.zeros((96, 2)); arrivals[0] = 1
    capacity = np.ones((96, 2))
    result = solve_resource_only_recourse(da, arrivals, capacity, np.ones((2, 2), dtype=bool))
    assert result.executed_total_nodeh == pytest.approx(2)
    assert result.backlog_nodeh[-1].sum() == pytest.approx(0)
    assert result.firewall == {field: 0 for field in ACTUAL_AIDC_FIREWALL_FIELDS}
    assert {item["field"] for item in result.read_ledger} == {
        "actual_workload_availability", "actual_rack_capacity", "rack_compatibility", "dayahead_authorization"
    }


def test_19_resource_recourse_respects_compatibility_and_capacity():
    da = np.zeros((1, 2, 96)); da[0, 0, 0] = 2
    arrivals = np.zeros((96, 1)); arrivals[0, 0] = 2
    capacity = np.ones((96, 2)); capacity[0, 0] = 0
    result = solve_resource_only_recourse(da, arrivals, capacity, np.asarray([[True, False]]))
    assert result.executed_total_nodeh == 0


def test_20_may_firewall_rejects_may_and_declares_all_counters():
    assert len(MAY_FIREWALL_FIELDS) == 5
    with pytest.raises(PermissionError, match="MAY"):
        reject_may("2025-05-01")
    reject_may("2025-04-30")
