"""Final executor rebind cannot waive failed inputs or changed science source."""
import pytest

from tools.audit_v42_table_v_month import DAYS, record, write_new
from tools.rebind_v42_table_v_month import checked_public_serialization, completed_input_proof, rebind
from tools.audit_v42_table_v_month import native0_guard


def test_rebind_rejects_incomplete_or_blocked_original_inputs(tmp_path):
    original = tmp_path / "old"
    original.mkdir()
    write_new(original / "MONTH_NATIVE0_AUDIT.json", dict(dates=list(DAYS), case_count=124,
        successful_dates=30, blocked_dates=[dict(day="2025-05-12", reason="source unavailable")], operations={}))
    with pytest.raises(ValueError, match="ALL_PASS_BEFORE_REBIND"):
        rebind(original, tmp_path / "new")
    with pytest.raises(ValueError, match="COMPLETED_124_INDEPENDENT_TYPED_INPUTS"):
        completed_input_proof(original, tmp_path / "proof.json")
    assert not (tmp_path / "new").exists()
    assert not (tmp_path / "proof.json").exists()


def test_rebind_only_allows_reviewed_supervisor_file_changes(tmp_path):
    original = tmp_path / "old"
    original.mkdir()
    science = tmp_path / "experimental_qos.py"
    science.write_text("original science")
    pin = record(science)
    science.write_text("changed E1 science")
    write_new(original / "MONTH_NATIVE0_AUDIT.json", dict(dates=list(DAYS), case_count=124,
        successful_dates=31, blocked_dates=[], operations={},
        cases=[dict(status="PASS_NATIVE0_BINDING") for _ in range(124)], pinned_source=[pin]))
    with pytest.raises(ValueError, match="SCIENTIFIC_INPUT_SOURCE_CHANGED"):
        rebind(original, tmp_path / "new")
    assert not (tmp_path / "new").exists()


def test_fast_public_serialization_keeps_native_constructor_guard(monkeypatch):
    import gurobipy as gp
    from v42_integration import m_engine
    monkeypatch.setattr(m_engine, "_write", lambda *a, **k: gp.Model())
    with native0_guard() as (calls, _):
        with checked_public_serialization():
            with pytest.raises(RuntimeError, match="FORBIDDEN:model_builds"):
                m_engine._write(None, None)
    assert calls["model_builds"] == 1
