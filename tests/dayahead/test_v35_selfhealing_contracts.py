from __future__ import annotations

import ast
import json
from pathlib import Path

import numpy as np
import pytest

from dayahead.v35.contracts import (
    ACTUAL_AIDC_FIREWALL_FIELDS,
    AIDC_STAGE_CASE,
    APRIL_DAYS,
    CALIBRATION_DAYS,
    CASE_ACTUATORS,
    MAY_DAYS,
    OFFICIAL_CASES,
    VALIDATION_DAYS,
    assert_may_access,
    assert_official_cases,
    phase_for_day,
    zero_firewall,
)
from dayahead.v35.effects import aidc_effect_watchdog, mess_effect_watchdog, repeated_zero_effect_sentinel
from dayahead.v35.recovery import RetryExhausted, classify_failure, quarantine_may_run, run_self_healing
from dayahead.v35.scheduler import CaseLaunch, heavy_launch_capacity, ordered_launches
from dayahead.v35.storage import (
    CheckpointDependencies,
    atomic_json,
    atomic_npz,
    checkpoint_is_reusable,
    checkpoint_payload,
    invalidation_scope,
    rebind_serialization_only_checkpoint,
    storage_schema_sha256,
)
from dayahead.v35.calibration import calibrate_vectorized, prospective_coverage, select_family
from dayahead.v35.may_sources import materialize_may_sources
from dayahead.v35.campaign import windows_path_to_wsl
from dayahead.v35.execution import _actual_mess, normalize_v35_fresh_storage
from dayahead.v28r2.source_cache import day_root
from dayahead.v34.actual_resource_recourse import solve_resource_only_recourse


REPO = Path(__file__).resolve().parents[2]
SHA = "a" * 64


def dependencies() -> CheckpointDependencies:
    return CheckpointDependencies(
        code_HEAD=SHA,
        science_authority_SHA=SHA,
        forecast_SHA=SHA,
        route_table_SHA=SHA,
        AIDC_schedule_SHA=SHA,
        MESS_trajectory_SHA=SHA,
        combined_schedule_SHA=SHA,
        Planning_SHA=SHA,
        Fresh_SHA=SHA,
        Actual_SHA=SHA,
        solver_settings_SHA=SHA,
        storage_schema_SHA=storage_schema_sha256(),
    )


def test_01_exact_cases_and_b3_lineage():
    assert OFFICIAL_CASES == ("B0", "B1", "B2", "B3")
    assert CASE_ACTUATORS["B0"] == {"aidc": False, "mess": False}
    assert CASE_ACTUATORS["B1"] == {"aidc": True, "mess": False}
    assert CASE_ACTUATORS["B2"] == {"aidc": False, "mess": True}
    assert CASE_ACTUATORS["B3"] == {"aidc": True, "mess": True}
    assert tuple(AIDC_STAGE_CASE[case] for case in OFFICIAL_CASES) == ("B0", "B1", "B0", "B1")
    assert_official_cases(OFFICIAL_CASES)
    with pytest.raises(ValueError):
        assert_official_cases((*OFFICIAL_CASES, "B4"))


def test_02_chronology_and_may_firewall():
    assert len(CALIBRATION_DAYS) == 20 and len(VALIDATION_DAYS) == 10 and len(APRIL_DAYS) == 30
    assert len(MAY_DAYS) == 31
    assert phase_for_day("2025-04-20") == "APR01_20_AC_FIDELITY_CALIBRATION"
    assert phase_for_day("2025-04-21") == "APR21_30_PROSPECTIVE_UNCORRECTED_RESIDUAL_VALIDATION"
    assert phase_for_day("2025-04-21", corrected=True) == "APR21_30_CORRECTED_INTEGRATED_VALIDATION"
    with pytest.raises(PermissionError):
        assert_may_access("2025-05-01", None)
    assert_may_access("2025-05-01", {"status": "PASS", "May_numeric_reads_before_admission": 0})


def test_03_actual_aidc_firewall_is_explicitly_zero():
    assert zero_firewall(ACTUAL_AIDC_FIREWALL_FIELDS) == {field: 0 for field in ACTUAL_AIDC_FIREWALL_FIELDS}


def test_04_atomic_npz_reload_shapes_finiteness_and_checkpoint(tmp_path: Path):
    artifact = tmp_path / "arrays.npz"
    record = atomic_npz(
        artifact,
        {"voltage": np.ones((96, 3)), "schedule_sha": np.asarray(SHA)},
        {"voltage": (96, 3), "schedule_sha": ()},
        require_finite=("voltage",),
    )
    checkpoint = tmp_path / "checkpoint.json"
    payload = checkpoint_payload(
        phase="APR01_20_AC_FIDELITY_CALIBRATION",
        day="2025-04-01",
        case="B1",
        run_id="r1",
        timestamp="2026-09-03T00:00:00Z",
        dependencies=dependencies(),
        storage_files=(record,),
    )
    atomic_json(checkpoint, payload)
    assert checkpoint_is_reusable(checkpoint, dependencies())
    artifact.write_bytes(b"corrupt")
    assert not checkpoint_is_reusable(checkpoint, dependencies())


def test_05_dependency_impact_invalidation():
    assert invalidation_scope("MESS_ONLY") == ("B2", "B3")
    assert invalidation_scope("AIDC_ONLY") == ("B1", "B3")
    assert invalidation_scope("COMMON_GRID_PHYSICAL_OBJECTIVE") == OFFICIAL_CASES
    assert invalidation_scope("SERIALIZATION_REPORT_ONLY") == ("ARTIFACT_REGENERATION",)


def test_06_aidc_watchdog_detects_live_mapping_and_resolved_effect():
    off = np.zeros((2, 2, 96)); on = off.copy(); on[0, 0, 0] = 1; on[0, 1, 1] = -1
    p0 = np.zeros((96, 2)); p1 = p0.copy(); p1[0, 0] = 1
    q0 = np.zeros((96, 2)); q1 = q0.copy(); q1[0, 0] = .3
    grid0 = np.zeros((96, 2)); grid1 = grid0.copy(); grid1[0, 0] = .1
    fresh1 = grid1 * .9
    result = aidc_effect_watchdog(
        comparison="B1-B0", off_workload=off, on_workload=on,
        off_p=p0, on_p=p1, off_q=q0, on_q=q1,
        off_planning=grid0, on_planning=grid1,
        off_fresh=grid0, on_fresh=fresh1,
        objective_off=1.0, objective_on=.9,
        unresolved_gap_off=0.0, unresolved_gap_on=0.0,
        free_workload_count=1, rack_site_ids=("D1", "D2"),
    )
    assert result["status"] == "PASS" and result["resolved_effect"]
    assert result["shifted_workload_node_hours"] == 1.0
    assert result["changed_site_count"] == 2


def test_07_aidc_watchdog_rejects_disconnected_injection():
    off = np.zeros((1, 1, 96)); on = off.copy(); on[0, 0, 0] = 1
    zeros = np.zeros((96, 1))
    result = aidc_effect_watchdog(
        comparison="B1-B0", off_workload=off, on_workload=on,
        off_p=zeros, on_p=zeros, off_q=zeros, on_q=zeros,
        off_planning=zeros, on_planning=zeros, off_fresh=zeros, on_fresh=zeros,
        objective_off=1.0, objective_on=1.0,
        unresolved_gap_off=0.0, unresolved_gap_on=0.0, free_workload_count=1,
    )
    assert "AIDC_DECISIONS_DIFFER_BUT_PQ_IDENTICAL" in result["red_flags"]


def test_08_mess_watchdog_requires_full_to_dominate_restricted():
    record = {
        "mess_id": "MESS01", "termination": "WORK_LIMIT", "objective_value": .6,
        "restricted_stationary_objective": .5, "restricted_incumbent_improves_zero": True,
        "MIPStart_accepted": False,
    }
    result = mess_effect_watchdog(
        comparison="B2-B0", p_kw=np.zeros((96, 4)), q_kvar=np.zeros((96, 4)),
        move_count=0, objective_off=.7, objective_on=.6,
        planning_rho_off=.7, planning_rho_on=.6, fresh_rho_off=.7, fresh_rho_on=.6,
        travel_energy_kwh=0, terminal_soc=(.76,) * 4, solver_records=(record,),
    )
    assert result["status"] == "DIAGNOSE"
    assert result["restricted_beats_full_vehicle_ids"] == ["MESS01"]


def test_09_three_day_zero_sentinel():
    result = repeated_zero_effect_sentinel([{"zero_actuation": True}] * 3)
    assert result["triggered"]


def test_10_memory_scheduler_reserves_four_gb_and_prefers_cheap():
    gib = 1024**3
    assert heavy_launch_capacity(available_bytes=3 * gib) == 0
    assert heavy_launch_capacity(available_bytes=17 * gib, estimated_heavy_process_bytes=6 * gib) == 2
    values = (
        CaseLaunch("2025-04-01", "B3", True),
        CaseLaunch("2025-04-01", "B1", False),
        CaseLaunch("2025-04-01", "B0", False),
    )
    assert tuple(row.case for row in ordered_launches(values)) == ("B0", "B1", "B3")


def test_11_failure_classification_and_bounded_retry():
    assert classify_failure(RuntimeError("OPENDSS engine failed")) == "FRESH_INTERFACE_DEFECT"
    calls = []

    def execute(attempt):
        calls.append(attempt)
        if attempt < 3:
            raise RuntimeError("cache resume")
        return "PASS"

    value, attempts = run_self_healing(execute, lambda *_: True, campaign="APRIL")
    assert value == "PASS" and len(attempts) == 2 and calls == [1, 2, 3]


def test_12_may_quarantine_is_whole_run(tmp_path: Path):
    run = tmp_path / "active"; run.mkdir(); (run / "2025-05-01.txt").write_text("x")
    target = quarantine_may_run(run, tmp_path / "quarantine", "run-1")
    assert not run.exists() and (target / "2025-05-01.txt").is_file()


def test_13_solver_source_binds_restricted_incumbent_before_full_model():
    source = (REPO / "dayahead/v34/integrated_mess.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    assert "_stationary_restricted_incumbent" in source
    assert "WORK_LIMIT_TIERS = (60.0, 180.0, 300.0)" in source
    assert "V35_MESS_FULL_MODEL_WORSE_THAN_RESTRICTED_INCUMBENT" in source
    assert source.index("restricted = _stationary_restricted_incumbent") < source.index("for work_limit in WORK_LIMIT_TIERS")
    assert tree is not None


def test_14_no_actual_grid_feedback_imports_in_resource_recourse():
    source = (REPO / "dayahead/v34/actual_resource_recourse.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports = [node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
    imports += [name.name for node in ast.walk(tree) if isinstance(node, ast.Import) for name in node.names]
    assert not any(token in name.lower() for name in imports for token in ("fresh", "opendss", "grid"))


def test_15_preapril_audit_proves_feasible_stationary_effect():
    audit = json.loads((REPO / "dayahead/artifacts/v34_aidc_mess_april_calibration_validation/V34_FAST_OBJECTIVE_AIDC_MESS_COUPLING_AUDIT.json").read_text(encoding="utf-8"))
    stationary = audit["MESS_PQ_coupling_probe"]["stationary_PQ_only"]
    assert audit["status"] == "PASS"
    assert stationary["deterministic_feasible_Q_perturbation"]["all_production_planning_constraints_feasible"]
    assert stationary["P_Q_nonzero"] and stationary["rho_improvement"] > 1e-6
    assert stationary["resolved_absolute_gap"] <= 1e-6
    assert not audit["MESS_PQ_coupling_probe"]["MESS_solver_starvation_confirmed"]


def test_16_aidc_only_solver_has_zero_mess_and_correction_hooks():
    import inspect

    from dayahead.v28r2.solver_runner import solve_monolithic
    from dayahead.v28r2.variable_registry import build_resource_model

    assert "mess_disabled" in inspect.signature(build_resource_model).parameters
    assert "mess_disabled" in inspect.signature(solve_monolithic).parameters
    assert "voltage_correction" in inspect.signature(solve_monolithic).parameters


def test_17_may_source_cache_is_separate_from_april(tmp_path: Path):
    assert "april_2025" in str(day_root(tmp_path, "2025-04-30"))
    assert "may_2025" in str(day_root(tmp_path, "2025-05-01"))


def test_18_may_materialization_fails_before_any_numeric_read(tmp_path: Path):
    with pytest.raises(PermissionError, match="ADMISSION"):
        materialize_may_sources(tmp_path, {})
    assert not (tmp_path / "cache").exists()


def _tiny_residuals(value_by_node: tuple[float, float]):
    signed = np.zeros((2, 96, 2), dtype=float)
    signed[:, :, 0] = value_by_node[0]
    signed[:, :, 1] = value_by_node[1]
    return {
        "signed": signed,
        "node_names": ("n1.1", "n2.2"),
        "node_phases": ("A", "B"),
        "labels": (("2025-04-21", "B1"), ("2025-04-21", "B3")),
    }


def test_19_vectorized_correction_selection_preserves_25_percent_rule():
    residuals = _tiny_residuals((0.01, 0.001))
    candidates = calibrate_vectorized(residuals)
    assert candidates.m1.up["GLOBAL"] == pytest.approx(0.01)
    assert candidates.m2.up["n2.2|B"] == pytest.approx(0.001)
    assert prospective_coverage(candidates.m2, residuals)["covering"] is True
    selected, reports, reason = select_family(candidates, residuals)
    assert selected is not None and selected.family == "M2"
    assert reports["M1"]["covering"] is True
    assert reason == "MORE_COMPLEX_COVERING_FAMILY_AT_LEAST_25_PERCENT_LESS_MEAN_CORRECTION"


def test_20_checkpoint_accepts_native_40_hex_git_head_but_other_shas_remain_64():
    source = dependencies()
    native = CheckpointDependencies(**{**source.__dict__, "code_HEAD": "a" * 40})
    native.validate()
    with pytest.raises(ValueError, match="science_authority_SHA"):
        CheckpointDependencies(**{**native.__dict__, "science_authority_SHA": "b" * 40}).validate()


def test_21_serialization_only_rebind_preserves_old_checkpoint_and_scientific_files(tmp_path: Path):
    artifact = tmp_path / "data.json"
    artifact.write_text("{}", encoding="utf-8")
    checkpoint = checkpoint_payload(
        phase="P", day="2025-04-01", case="B0", run_id="r", timestamp="t",
        dependencies=CheckpointDependencies(**{**dependencies().__dict__, "code_HEAD": "a" * 40}),
        storage_files=({"path": str(artifact), "sha256": __import__("hashlib").sha256(b"{}").hexdigest()},),
    )
    path = tmp_path / "CHECKPOINT.json"; atomic_json(path, checkpoint)
    old_sha = __import__("hashlib").sha256(path.read_bytes()).hexdigest()
    history = tmp_path / "history/CHECKPOINT.json"
    record = rebind_serialization_only_checkpoint(
        path, old_code_head="a" * 40, new_code_head="b" * 40, history_path=history,
    )
    assert __import__("hashlib").sha256(history.read_bytes()).hexdigest() == old_sha
    assert json.loads(path.read_text())["code_HEAD"] == "b" * 40
    assert record["scientific_files_changed"] == 0


def test_22_windows_path_translation_does_not_read_may_data(monkeypatch):
    monkeypatch.setattr(Path, "resolve", lambda self: Path(r"C:\work space\MobileESS"))
    assert windows_path_to_wsl(Path("unused")) == "/mnt/c/work space/MobileESS"


def test_23_v35_fresh_storage_is_finite_with_explicit_transformer_mask(tmp_path: Path):
    output = tmp_path / "fresh"; output.mkdir()
    arrays_path = output / "OPENDSS_PHASE_ARRAYS.npz"
    np.savez_compressed(
        arrays_path,
        branch_kinds=np.asarray(["line", "transformer"]),
        transformer_total_kva_loading_pu=np.column_stack((
            np.full(96, np.nan), np.full(96, .7),
        )),
        voltage_pu=np.ones((96, 2)),
    )
    atomic_json(output / "OPENDSS_OUTPUT_MANIFEST.json", {
        "files": {arrays_path.name: {"sha256": "old", "bytes": arrays_path.stat().st_size}},
        "manifest_payload_sha256": "old",
    })
    arrays_record, manifest_record = normalize_v35_fresh_storage(output)
    assert arrays_record["sha256"] == __import__("hashlib").sha256(arrays_path.read_bytes()).hexdigest()
    assert manifest_record["sha256"] == __import__("hashlib").sha256((output / "OPENDSS_OUTPUT_MANIFEST.json").read_bytes()).hexdigest()
    with np.load(arrays_path, allow_pickle=False) as payload:
        assert np.isfinite(payload["transformer_total_kva_loading_pu"]).all()
        assert payload["transformer_total_kva_loading_pu"][0].tolist() == [0.0, .7]
        assert payload["transformer_total_kva_applicable"].tolist() == [False, True]


def test_24_small_exact_aidc_effect_is_not_mislabeled_as_solver_gap():
    off = np.zeros((1, 2, 96)); on = off.copy(); on[0, 0, 0] = 1; on[0, 1, 0] = -1
    p0 = np.zeros((96, 1)); p1 = p0.copy(); p1[0, 0] = 1
    grid0 = np.zeros((96, 1)); grid1 = grid0.copy(); grid1[0, 0] = 1e-5
    result = aidc_effect_watchdog(
        comparison="B1-B0", off_workload=off, on_workload=on,
        off_p=p0, on_p=p1, off_q=p0, on_q=p1,
        off_planning=grid0, on_planning=grid1, off_fresh=grid0, on_fresh=grid1,
        objective_off=1.0, objective_on=1.0 - 1e-8,
        unresolved_gap_off=0.0, unresolved_gap_on=0.0, free_workload_count=1,
        rack_site_ids=("AIDC01", "AIDC02"),
    )
    assert result["objective_effect_classification"] == "BELOW_REPORTING_RESOLUTION_ZERO_SOLVER_GAP"
    assert result["red_flags"] == [] and result["status"] == "PASS"
    assert result["changed_site_count"] == 2


def test_25_small_aidc_effect_inside_nonzero_solver_gap_remains_diagnostic():
    off = np.zeros((1, 1, 96)); on = off.copy(); on[0, 0, 0] = 1
    p0 = np.zeros((96, 1)); p1 = p0.copy(); p1[0, 0] = 1
    grid0 = np.zeros((96, 1)); grid1 = grid0.copy(); grid1[0, 0] = 1e-5
    result = aidc_effect_watchdog(
        comparison="B3-B2", off_workload=off, on_workload=on,
        off_p=p0, on_p=p1, off_q=p0, on_q=p1,
        off_planning=grid0, on_planning=grid1, off_fresh=grid0, on_fresh=grid1,
        objective_off=1.0, objective_on=.9999,
        unresolved_gap_off=.01, unresolved_gap_on=.02, free_workload_count=1,
    )
    assert result["objective_effect_classification"] == "UNRESOLVED_WITHIN_SOLVER_GAP"
    assert "AIDC_OBJECTIVE_EFFECT_UNRESOLVED_RELATIVE_TO_SOLVER_GAP" in result["red_flags"]


def test_26_actual_recourse_clamps_only_da_solver_tolerance_residue():
    da = np.zeros((1, 1, 96), dtype=float)
    da[0, 0, 0] = -4.7e-8
    result = solve_resource_only_recourse(
        da,
        np.zeros((96, 1), dtype=float),
        np.ones((96, 1), dtype=float),
        np.ones((1, 1), dtype=bool),
    )
    assert np.all(result.executed_nodeh >= 0.0)
    assert result.executed_total_nodeh == 0.0

    da[0, 0, 0] = -2e-6
    with pytest.raises(ValueError, match="V34_RESOURCE_INPUT_NEGATIVE"):
        solve_resource_only_recourse(
            da,
            np.zeros((96, 1), dtype=float),
            np.ones((96, 1), dtype=float),
            np.ones((1, 1), dtype=bool),
        )


def test_27_actual_mess_soc_uses_frozen_1200_kwh_capacity():
    summary, availability = _actual_mess(
        "2025-04-01", None, None, None, None,
    )
    assert summary["terminal_SoC"] == pytest.approx([760.0 / 1200.0] * 4)
    assert availability.shape == (96, 4) and availability.all()
