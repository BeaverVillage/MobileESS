from copy import deepcopy
from pathlib import Path

import numpy as np
import pytest

from v42_integration import release_date_case as api
from v42_integration import release_initial_states as initial


def test_case_compiler_refuses_other_month():
    with pytest.raises(ValueError, match="INDEPENDENT_MAY_DATE"):
        api.require_day("2025-06-01")


def test_other_date_initial_snapshot_is_not_a_valid_substitute(monkeypatch):
    monkeypatch.setattr(initial, "load_initial_state", lambda receipt: dict(day="2025-05-01", begin_epoch_seconds=1746021600.))
    with pytest.raises(ValueError, match="SAME_DAY_BINDING"):
        api.load_state("2025-05-02", dict(path="never_read", sha256="0" * 64, bytes=1))


def test_missing_or_wrong_day_physical_certificate_fails_before_read():
    with pytest.raises(ValueError, match="APPROVED_11SVR_FORECAST_CERTIFICATE"):
        api.coefficient_axes(dict(day="2025-05-01"), "2025-05-02")


def test_original_source_check_cache_detects_changed_files(tmp_path):
    path = tmp_path / "source.txt"
    path.write_text("first", encoding="utf8")
    receipt = initial.record(path)
    api.verify_sources([receipt, receipt])
    path.write_text("second and different length", encoding="utf8")
    with pytest.raises(ValueError, match="EXACT_SOURCE_UNAVAILABLE"):
        api.verify_sources([receipt])


def coefficient_fixture(tmp_path, slots=96):
    from v42_integration.production_case import FIELDS
    path = tmp_path / "coeff.npz"
    arrays = {field: np.zeros((slots, 1), dtype=float) for field in FIELDS + ("anchor_control",)}
    arrays.update(control_names=np.array(["control" + str(i) for i in range(60)]),
        branch_names=np.array(["transformer.t" + str(i) for i in range(153)]), rating_a=np.ones(153))
    np.savez_compressed(path, **arrays)
    return dict(day="2025-05-02", schema="V42_SVR11_LDC_INTERVAL_ELECTRICAL_CERTIFICATE_V2",
        input_identity=dict(identity=dict(inputs=dict(day="2025-05-02"))), Actual_inputs_read=0,
        tap_optimization_variables=0, outputs=dict(planning_coefficients=initial.record(path)),
        global_nonlinear_envelope_certified=False, validity_scope="local; independent AC required")


def test_native_input_header_validation_does_not_solve_physics(tmp_path):
    certificate = coefficient_fixture(tmp_path)
    result = api.coefficient_axes(certificate, "2025-05-02")
    assert result["PASS"] and result["AC_solves"] == 0
    assert result["transformer_current_rows"] == 153
    assert result["global_nonlinear_envelope_certified"] is False


def test_short_physical_projection_is_not_silently_padded(tmp_path):
    with pytest.raises(ValueError, match="ORIGINAL_96_AXIS"):
        api.coefficient_axes(coefficient_fixture(tmp_path, slots=16), "2025-05-02")


def test_day_specific_projection_uses_same_day_source_and_retains_routes(tmp_path, monkeypatch):
    certificate = coefficient_fixture(tmp_path)
    folder = tmp_path / "models/2025-05-02"
    folder.mkdir(parents=True)
    initial.write_json(folder / "ELECTRICAL_CERTIFICATE.json", certificate)
    monkeypatch.setattr(api, "ARCHIVE", tmp_path)
    route = dict(path="source route", sha256="a" * 64, bytes=12)
    native = dict(electrical_certificate=dict(path="old"), grid_outputs={}, route_table=route, known_population=[dict(job_uid="kept")])
    merged, _, _, _ = api.merge_same_day_physical(native, "2025-05-02")
    assert merged["route_table"] == route
    assert merged["known_population"] == native["known_population"]
    assert native["grid_outputs"] == {}


def forbid_native(monkeypatch):
    import gurobipy as gp
    def forbidden(*args, **kwargs):
        raise AssertionError("Date input compilation must never build a model or solve")
    for method in ("__init__", "optimize", "presolve", "computeIIS"):
        monkeypatch.setattr(gp.Model, method, forbidden)


def require_local_sources():
    if not api.SAVED.is_dir() or not api.INITIALS.is_dir():
        pytest.skip("Authoritative local saved A1/31 D0 sources are unavailable")


def test_real_may02_compile_resume_and_tamper_gate_are_native_zero(tmp_path, monkeypatch):
    require_local_sources()
    forbid_native(monkeypatch)
    folder = tmp_path / "DAY_20250502"
    context = api.compile_date_case("2025-05-02", output=folder)
    assert context["manifest"]["day"] == "2025-05-02"
    assert context["input_audit"]["initial_running_GPU"] == 435
    assert context["production_case_verifier"] is api.require_date_case
    assert context["date_case_compile_acceptance"]["native_model_builds"] == 0
    before = {str(p.relative_to(folder)): p.read_bytes() for p in folder.iterdir() if p.is_file()}
    loaded = api.load_date_case("2025-05-02", folder)
    assert loaded["manifest"] == context["manifest"]
    assert loaded["input_audit"]["a_input_sha"] == context["input_audit"]["a_input_sha"]
    assert before == {str(p.relative_to(folder)): p.read_bytes() for p in folder.iterdir() if p.is_file()}
    with pytest.raises(FileExistsError):
        api.compile_date_case("2025-05-02", output=folder)
    (folder / "D0_NATIVE_PUBLIC_INPUT.json.gz").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="RESUME_FROZEN_DATE_INPUT_ARTIFACT_DRIFT"):
        api.load_date_case("2025-05-02", folder)


def test_real_may01_saved_p1_case_exact_identity_is_preserved(tmp_path, monkeypatch):
    require_local_sources()
    forbid_native(monkeypatch)
    context = api.compile_date_case("2025-05-01", output=tmp_path / "DAY_20250501")
    assert context["manifest"] == initial.read(api.SAVED / "D0_CASE_MANIFEST.json")
    assert context["manifest"]["identity"]["case_sha"] == "c39c3fd7f35b017a69b96da91f52ba4a4208428ae5abae745f0d61f7911c2d51"
    assert context["date_case_compile_acceptance"]["saved_P1_case_exact_preserved"]


def test_dummy_or_incomplete_manifest_never_passes_production_verifier():
    with pytest.raises(ValueError, match="EXPLICIT_D0_CASE_MANIFEST"):
        api.require_date_case(dict(PASS=True, day="2025-05-02", schema="DUMMY"), stage="A1")
