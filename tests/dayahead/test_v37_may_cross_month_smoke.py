from __future__ import annotations

import json
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pandas as pd

from dayahead.v37.contracts import DAY_TOTAL_UNITS, EXPECTED_DATES, MAX_PARALLEL_DATES, MAX_WORKERS_PER_DATE
from dayahead.v37.campaign import MEETING_FIELDS
from dayahead.v37.manifest import build_date_manifest, build_may01_amendment
from dayahead.v37.runner import (
    _beam_fallback_allowed,
    _local_fallback_allowed,
    _run_local_with_frozen_k_fallback,
)
from dayahead.v37.sources import archive_month_for_operating_day, select_cross_month_vintages
from dayahead.v37.status import monitor_view, write_status


ROOT = Path(__file__).resolve().parents[2]


def test_may01_cross_month_demand_pv_and_causality() -> None:
    selected, failures, evidence = select_cross_month_vintages(("2025-05-01",))
    assert failures == {}
    value = selected["2025-05-01"]
    assert evidence["2025-05-01"]["archive_month"] == "202504"
    assert value["demand_identity"] == {"PREDISPATCHSEQNO": "2025043028", "RUNNO": "1"}
    assert value["pv_identity"] == {"VERSION_DATETIME": "2025/04/30 18:00:00"}
    assert len(value["demand_mw_96"]) == len(value["pv_mw_96"]) == 96
    assert value["demand_issue"] == "2025-04-30T17:32:39+10:00"
    assert value["pv_issue"] == value["cutoff_fixed_aest"] == "2025-04-30T18:00:00+10:00"
    assert "ACTUAL" not in evidence["2025-05-01"]["demand_path"].upper()
    assert "ROOFTOP_PV_FORECAST" in Path(evidence["2025-05-01"]["pv_path"]).name.upper()
    assert "ROOFTOP_PV_ACTUAL" not in Path(evidence["2025-05-01"]["pv_path"]).name.upper()


def test_may02_regression_stays_on_may_archive() -> None:
    selected, failures, evidence = select_cross_month_vintages(("2025-05-02",))
    assert failures == {}
    value = selected["2025-05-02"]
    assert archive_month_for_operating_day("2025-05-02") == "202505"
    assert evidence["2025-05-02"]["archive_month"] == "202505"
    assert value["demand_identity"] == {"PREDISPATCHSEQNO": "2025050128", "RUNNO": "1"}
    assert value["pv_identity"] == {"VERSION_DATETIME": "2025/05/01 18:00:00"}


def test_amendment_supersedes_without_editing_v16_manifest() -> None:
    historical = ROOT / "dayahead/artifacts/v16_3_final/V16_3_FINAL_EVALUATION_ELIGIBILITY_MANIFEST.json"
    before = historical.read_bytes()
    amendment = build_may01_amendment(ROOT)
    manifest = build_date_manifest(ROOT)
    assert historical.read_bytes() == before
    assert amendment["classification"] == "A_CROSS_MONTH_VINTAGE_NOT_MATERIALIZED"
    assert amendment["science_changed"] == "NO"
    assert manifest["expected_count"] == manifest["runnable_count"] == 31
    assert manifest["missing_count"] == 0
    assert manifest["May01_status"] == "RUNNABLE_CROSS_MONTH_CAUSAL_VINTAGE"


def test_monitor_atomic_terminal_hiding_and_counters(tmp_path: Path) -> None:
    write_status(tmp_path / "2025-05-01.json", "2025-05-01", "RUNNING", 5, "B2_MESS02")
    write_status(tmp_path / "2025-05-02.json", "2025-05-02", "PASS", 14, None)
    write_status(tmp_path / "2025-05-03.json", "2025-05-03", "FAIL", 4, None, error="synthetic")
    command = [
        "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
        str(ROOT / "tools/v37/monitor_may.ps1"), "-Once", "-Json",
        "-StatusRoot", str(tmp_path), "-ExpectedCount", "3",
    ]
    value = json.loads(subprocess.check_output(command, cwd=ROOT, text=True).strip())
    assert (value["PASS"], value["FAIL"], value["ACTIVE"], value["REMAIN"]) == (1, 1, 1, 1)
    assert [row["date"] for row in value["active_dates"]] == ["2025-05-01"]
    rows = [
        {"date": "2025-05-01", "status": "PASS"},
        {"date": "2025-05-02", "status": "PASS"},
        {"date": "2025-05-03", "status": "FAIL"},
    ]
    view = monitor_view(rows, expected_count=3)
    assert view["active_dates"] == [] and view["complete"] is True


def test_locked_execution_limits() -> None:
    assert len(EXPECTED_DATES) == 31
    assert MAX_PARALLEL_DATES == MAX_WORKERS_PER_DATE == 4
    assert DAY_TOTAL_UNITS == 14
    assert MEETING_FIELDS == (
        "date", "PASS_FAIL", "B0_Planning_rho", "B1_Planning_rho", "B2_Planning_rho", "B3_Planning_rho",
        "B0_Fresh_rho", "B1_Fresh_rho", "B2_Fresh_rho", "B3_Fresh_rho",
        "B1_minus_B0_Planning", "B2_minus_B0_Planning", "B3_minus_B0_Planning", "B3_minus_B2_Planning",
        "B1_minus_B0_Fresh", "B2_minus_B0_Fresh", "B3_minus_B0_Fresh", "B3_minus_B2_Fresh",
        "B2_relocations", "B3_relocations", "B2_fallback", "B3_fallback", "wallclock_min",
    )


def test_frozen_k_fallback_scope_and_sequence(tmp_path: Path) -> None:
    calls = []

    def write_json(path: Path, value: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding="utf-8")

    frozen = SimpleNamespace(
        APR01="2025-05-01",
        MESS_INITIAL={"MESS03": "STA08"},
        DEFAULT_K=200,
        enumerate_initial_relocations=lambda **_kwargs: SimpleNamespace(candidates=[object()] * 1001),
        _json=write_json,
    )
    parent = SimpleNamespace(beam_state_id="B2-PARENT")

    def local_search(**kwargs: object):
        calls.append(frozen.DEFAULT_K)
        root = Path(kwargs["cache"]) / "s1" / parent.beam_state_id
        root.mkdir(parents=True, exist_ok=True)
        certificate = "V37_FAIL_CLOSED:synthetic" if frozen.DEFAULT_K < 800 else "PASS"
        pd.DataFrame([{
            "candidate_id": "candidate",
            "exact_optimality_certificate": certificate,
        }]).to_csv(root / "RESTRICTED_VALUES.csv", index=False)
        return [], {"restricted_solver_calls": frozen.DEFAULT_K + 1}

    _seeds, summary = _run_local_with_frozen_k_fallback(
        frozen,
        local_search,
        cache=tmp_path,
        case="B2",
        mess_id="MESS03",
        sequence_index=0,
        parent=parent,
        aidc=None,
        coefficients=None,
        services=None,
        route_table=None,
        seed_line=None,
        workers=4,
    )
    assert calls == [200, 400, 800]
    assert summary["selected_K"] == "800"
    assert summary["K_fallback_used"] is True
    assert summary["full_scan_used"] is False
    assert frozen.DEFAULT_K == 200
    assert _local_fallback_allowed(RuntimeError("V35R3_FIXED_CERTIFICATE_STALLED:x"))
    assert not _local_fallback_allowed(FileNotFoundError("path"))
    assert not _beam_fallback_allowed(RuntimeError("V35R3_FIXED_CERTIFICATE_STALLED:x"))
