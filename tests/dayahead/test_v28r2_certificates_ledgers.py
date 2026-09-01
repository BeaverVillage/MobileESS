import json
from pathlib import Path

import pytest

from dayahead.v28r2.backend_contract import EXECUTION_STEPS
from dayahead.v28r2.certificate import file_references, verify_certificate, write_certificate
from dayahead.v28r2.gatekeeper import verify_authority_launch, verify_smoke_launch
from dayahead.v28r2.heavy_backend import HeavyBackend
from dayahead.v28r2.day_state import DayState
import dayahead.v28r2.production_handlers as production_handlers_module
from dayahead.v28r2.production_handlers import ProductionHandlers, build_day_run_spec
from dayahead.v28r2.runtime_ledger import OPENDSS_TRAJECTORIES, PUE_TRAJECTORIES, RuntimeLedger


REPO = Path(__file__).resolve().parents[2]


def solver_record(case: str, solver: str) -> dict[str, object]:
    return {
        "case": case,
        "solver": solver,
        "status": "OPTIMAL",
        "runtime_seconds": 1.0,
        "objective": 0.9,
        "incumbent": 0.9,
        "lower_bound": 0.9,
        "upper_bound": 0.9,
        "gap": 0.0,
        "iterations": 1,
        "optimality_cuts": 0,
        "feasibility_cuts": 0,
    }


def complete_measured_ledger() -> RuntimeLedger:
    ledger = RuntimeLedger("2025-04-01")
    for case, solver in (
        ("B0", "MONOLITHIC"), ("B1", "MONOLITHIC"), ("B2", "MONOLITHIC"),
        ("B3", "CL_MC_BD"), ("B3", "MONOLITHIC"), ("B3", "STANDARD_BD"),
    ):
        ledger.begin_solver("DAYAHEAD", case, solver)
        ledger.record_solver(solver_record(case, solver))
    ledger.begin_solver("PI", "B3", "CL_MC_BD")
    ledger.record_solver(solver_record("B3", "CL_MC_BD"))
    for trajectory in PUE_TRAJECTORIES:
        ledger.record_pue(trajectory, 1152)
    for trajectory in OPENDSS_TRAJECTORIES:
        ledger.begin_opendss(trajectory)
        for slot in range(96):
            ledger.record_opendss_slot(trajectory, slot, True)
        ledger.complete_opendss(trajectory, "test-version")
    return ledger


def test_complete_ledger_is_entirely_measured_and_tamper_evident(tmp_path: Path):
    ledger = complete_measured_ledger()
    ledger.validate_complete()
    assert ledger.optimizer_calls_by_namespace == {"DAYAHEAD": 6, "ACTUAL": 0, "PI": 1}
    assert ledger.peak_active_heavy_solves == 1
    assert set(ledger.opendss_solved_slots.values()) == {96}
    path = tmp_path / "ledger.json"
    ledger.save(path)
    loaded = RuntimeLedger.load(path)
    loaded.validate_complete()
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["opendss_solved_slots"]["DA/B0"] = 95
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(RuntimeError, match="LEDGER_SHA_MISMATCH"):
        RuntimeLedger.load(path)


def test_heavy_operations_cannot_overlap_and_actual_cannot_optimize():
    ledger = RuntimeLedger("2025-04-01")
    ledger.begin_solver("DAYAHEAD", "B0", "MONOLITHIC")
    with pytest.raises(RuntimeError, match="OVERLAPPING"):
        ledger.begin_opendss("DA/B0")
    fresh = RuntimeLedger("2025-04-01")
    with pytest.raises(RuntimeError, match="ACTUAL_OPTIMIZER"):
        fresh.begin_solver("ACTUAL", "B0", "MONOLITHIC")


def test_certificate_recomputes_digest_and_every_referenced_file(tmp_path: Path):
    evidence = tmp_path / "evidence.json"
    evidence.write_text('{"status":"PASS"}\n', encoding="utf-8")
    certificate = tmp_path / "certificate.json"
    write_certificate(certificate, {
        "artifact_id": "TEST_CERTIFICATE",
        "status": "PASS",
        "references": file_references({"evidence": evidence}),
    })
    assert verify_certificate(certificate)["status"] == "PASS"
    evidence.write_text('{"status":"FAIL"}\n', encoding="utf-8")
    with pytest.raises(RuntimeError, match="REFERENCE_TAMPER"):
        verify_certificate(certificate)


def test_certificate_rejects_literal_placeholders(tmp_path: Path):
    with pytest.raises(ValueError, match="CERTIFICATE_PLACEHOLDER"):
        write_certificate(tmp_path / "bad.json", {"config_sha": "BOUND_IN_LATER"})


def test_production_factory_binds_all_steps_without_running_them(tmp_path: Path):
    spec = build_day_run_spec(REPO, "2025-04-01", "non-authority-smoke")
    state = tmp_path / "state.json"
    handlers = ProductionHandlers(REPO, spec, tmp_path / "day", state, "non-authority-smoke")
    assert tuple(handlers.handlers) == EXECUTION_STEPS
    assert spec.settings.day_workers == 2
    assert spec.settings.gurobi_threads == 4
    assert spec.source_day_sha256 == "ba0b73096bc32174e60c81af02e4aa9ef7ceae06370c249c05dd6ddc827c65cf"


def test_first_four_handlers_materialize_real_authorities_without_native_solves(tmp_path: Path):
    spec = build_day_run_spec(REPO, "2025-04-01", "non-authority-smoke")
    handlers = ProductionHandlers(REPO, spec, tmp_path / "day", tmp_path / "state.json", "non-authority-smoke")
    ledger = RuntimeLedger("2025-04-01")
    step1, _ = handlers.step_01_INPUT_AUTHORITY_CHECK(ledger)
    step2, counters2 = handlers.step_02_OPTIMIZER_CHANNEL_MATERIALIZATION(ledger)
    step3, _ = handlers.step_03_REFERENCE_COMPUTE_SCHEDULE(ledger)
    step4, _ = handlers.step_04_REFERENCE_DELTA_CLOSURE(ledger)
    assert all(path.is_file() for group in (step1, step2, step3, step4) for path in group.values())
    assert counters2 == {"P_cells": 96, "G_cells": 96, "W_cells": 1440}
    assert ledger.solver_calls == []
    assert ledger.opendss_solved_slots == {}


def test_smoke_is_authorized_but_authoritative_april_remains_fail_closed():
    assert verify_smoke_launch(REPO)["HEAVY_SMOKE_LAUNCH_AUTHORIZED"] is True
    with pytest.raises(RuntimeError, match="AUTHORITY_PRODUCTION_LAUNCH"):
        verify_authority_launch(REPO)


def test_missing_electrical_cache_invokes_real_preparation_adapter(tmp_path: Path, monkeypatch):
    spec = build_day_run_spec(REPO, "2025-04-01", "non-authority-smoke")
    handlers = ProductionHandlers(REPO, spec, tmp_path / "day", tmp_path / "state.json", "non-authority-smoke")
    handlers._data = object()
    prepared = object()
    monkeypatch.setattr(
        production_handlers_module, "build_electrical_context",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("V28R2_D1_ELECTRICAL_CACHE_MISSING:2025-04-01")),
    )
    monkeypatch.setattr(production_handlers_module, "prepare_electrical_context", lambda *_args, **_kwargs: prepared)
    assert handlers._electrical() is prepared


def test_failed_old_run_spec_is_archived_before_new_revision_retry(tmp_path: Path):
    spec = build_day_run_spec(REPO, "2025-04-01", "non-authority-smoke")
    day_root = tmp_path / "day"
    state_path = tmp_path / "progress" / "DAY_STATE.json"
    day_root.mkdir(parents=True)
    (day_root / "old-evidence.json").write_text("{}\n", encoding="utf-8")
    old = DayState(spec.day, spec.campaign, "a" * 64, status="FAIL", defect_ids=["DEFECT-1"])
    old.save(state_path)
    backend = HeavyBackend(spec, day_root, state_path, {})
    current = backend.load_or_create_state()
    assert current.status == "PENDING"
    assert current.defect_ids == ["DEFECT-1"]
    assert list((day_root / "_failed_attempts").rglob("old-evidence.json"))
    assert list((state_path.parent / "failed_attempts").rglob("DAY_STATE.json"))
