"""Native0 release gates: immutable bytes, date authority and honest budgets."""
import importlib.util
import json
from pathlib import Path
import struct
import subprocess
import zipfile

import pytest

FILE = Path(__file__).resolve().parents[1] / "tools/audit_v42_release_preservation.py"
SPEC = importlib.util.spec_from_file_location("release_preservation", FILE)
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


def test_causal_cc4_uses_original_fixed_aest_midnight():
    assert audit.causal_day("2025-05-02", "2025-05-01 08:00:00+00:00", "2025-05-02")["PASS"]
    assert not audit.causal_day("2025-05-02", "2025-05-01 14:00:01+00:00", "2025-05-02")["PASS"]


@pytest.mark.parametrize("issue,target", [
    ("2025-05-01T08:00:00", "2025-05-02"),
    ("2025-05-01T08:00:00+00:00", "2025-05-01"),
    ("not-a-timestamp", "2025-05-02"),
])
def test_date_or_timezone_mismatch_cannot_certify(issue, target):
    assert not audit.causal_day("2025-05-02", issue, target)["PASS"]


def test_may01_approved_state_cannot_authorize_may02():
    result = audit.date_authority("2025-05-02", [dict(day="2025-05-01", authorized=True)])
    assert result["status"] == "NOT_FOUND_IN_AUDITED_SCOPE"
    assert not result["independent_day_ready"]
    assert not result["May01_state_copied"]


def test_same_date_unapproved_state_not_authority():
    assert not audit.date_authority("2025-05-10", [dict(day="2025-05-10", authorized=False)])["independent_day_ready"]


def test_historical_native_seed_and_main_sum_not_nested_wall():
    doc = dict(case_sha="old", Native_call=dict(Native_Runtime=45., cap_seconds=300., status=2),
        current_case_seed=dict(Native_call=dict(Native_Runtime=1.)), build_wall_seconds=27., FULL_feasible=True)
    result = audit.historical_stage(doc, "A2", {"sha256": "old"})
    assert result["Native_seconds"] == 46.
    assert result["stage_wall_seconds"] is None
    assert not result["new_D0_Wall_forecast_certified"]
    assert not result["observed_return_is_new_D0_feasibility_guarantee"]


def test_proposed_budget_cannot_spend_unused_a1_authorization():
    result = audit.proposed_budget("M1", {"Native_seconds": 86.}, 180.)
    assert result["proposed_ledger_envelope_seconds"] == 240.
    assert result["proposed_stage_total_solve_cap_seconds"] == 180.
    assert result["proposed_Optimize_cap_seconds"] == 140.
    assert result["existing_4Joint_140_second_call_clamp_preserved"]
    assert result["status"] == "PROPOSAL_ONLY_NOT_AUTHORIZED_NOT_RUN"
    assert result["certified_new_D0_runtime_estimate"] is None
    assert result["expected_Wall_seconds"] is None


@pytest.mark.parametrize("cap", [0., -1., float("nan"), float("inf")])
def test_invalid_budget_not_a_bounded_proposal(cap):
    with pytest.raises(ValueError, match="INVALID_CAP"):
        audit.proposed_budget("K48", {}, cap)


def test_byte_proof_detects_line_ending_and_coefficient_change(tmp_path):
    def run(*args):
        subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)
    run("init")
    run("config", "core.autocrlf", "false")
    original = tmp_path / "core.py"
    original.write_bytes(b"coefficient = 300\n")
    run("-c", "core.autocrlf=false", "add", "core.py")
    run("-c", "user.name=Audit", "-c", "user.email=audit@example.invalid", "commit", "-m", "fixture")
    reference = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=tmp_path).decode().strip()
    assert audit.byte_preservation(tmp_path, reference, ("core.py",))["PASS"]
    original.write_bytes(b"coefficient = 300\r\n")
    assert not audit.byte_preservation(tmp_path, reference, ("core.py",))["PASS"]
    original.write_bytes(b"coefficient = 600\n")
    assert not audit.byte_preservation(tmp_path, reference, ("core.py",))["PASS"]


def test_literal_cc4_row_reads_only_requested_daily_row(tmp_path):
    header = repr(dict(descr="<f8", fortran_order=False, shape=(2, 24, 2))).encode("ascii")
    path = tmp_path / "prediction.npz"
    payload = b"\x93NUMPY" + bytes([1, 0]) + struct.pack("<H", len(header)) + header
    payload += struct.pack("<96d", *range(96))
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("q.npy", payload)
    low, high, raw, shape = audit.original_prediction_row(path, 1)
    assert low == list(range(48, 96, 2)) and high == list(range(49, 96, 2))
    assert len(raw) == 384 and shape == [2, 24, 2]
    with pytest.raises(ValueError, match="ROW_INDEX"):
        audit.original_prediction_row(path, 2)


def test_import_does_not_import_solver_or_construct_models():
    # The auditor is intentionally stdlib-only; production modules may load
    # solver bindings elsewhere in the shared pytest process.
    import ast
    tree = ast.parse(FILE.read_text(encoding="utf-8"))
    imports = [n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
    imports += [a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names]
    assert all(not name.startswith(("gurobi", "scipy", "v42_")) for name in imports if name)
