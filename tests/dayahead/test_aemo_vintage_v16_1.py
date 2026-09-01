from __future__ import annotations

import csv
import io
import json
import zipfile
from datetime import timedelta
from pathlib import Path

from dayahead.aemo_vintage_v16_1 import (
    CUTOFF,
    SOURCE_TIMESTAMPS,
    mapped_input_sha256,
    optimizer_timestamps,
    pwc_hold_30_to_15,
    select_demand_vintage,
    select_pv_vintage,
)


def _archive(path: Path, header: list[str], rows: list[list[str]]) -> Path:
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(header)
    writer.writerows(rows)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(path.stem + ".CSV", stream.getvalue())
    return path


def _stamp(value) -> str:
    return value.strftime("%Y/%m/%d %H:%M:%S")


def test_single_complete_latest_vintages_and_future_exclusion(tmp_path: Path) -> None:
    demand_header = [
        "I", "PREDISPATCH", "REGION_SOLUTION", "8", "PREDISPATCHSEQNO", "RUNNO",
        "REGIONID", "PERIODID", "TOTALDEMAND", "LASTCHANGED", "DATETIME",
    ]
    demand_rows: list[list[str]] = []
    for sequence, issue, offset, complete in (
        ("eligible", CUTOFF - timedelta(minutes=30), 1000.0, True),
        ("incomplete", CUTOFF, 2000.0, False),
        ("future", CUTOFF + timedelta(minutes=30), 3000.0, True),
    ):
        targets = SOURCE_TIMESTAMPS if complete else SOURCE_TIMESTAMPS[:-1]
        for index, target in enumerate(targets, start=1):
            demand_rows.append([
                "D", "PREDISPATCH", "REGION_SOLUTION", "8", sequence, "1", "VIC1",
                str(index), str(offset + index), _stamp(issue), _stamp(target),
            ])
    demand = select_demand_vintage(_archive(tmp_path / "demand.zip", demand_header, demand_rows))
    assert demand.identity == {"PREDISPATCHSEQNO": "eligible", "RUNNO": "1"}
    assert demand.issue_time < CUTOFF
    assert len(demand.values) == 48

    pv_header = [
        "I", "ROOFTOP", "FORECAST", "1", "VERSION_DATETIME", "REGIONID",
        "INTERVAL_DATETIME", "POWERMEAN",
    ]
    pv_rows: list[list[str]] = []
    for issue, offset in ((CUTOFF, 10.0), (CUTOFF + timedelta(minutes=30), 20.0)):
        for index, target in enumerate(SOURCE_TIMESTAMPS):
            pv_rows.append([
                "D", "ROOFTOP", "FORECAST", "1", _stamp(issue), "VIC1", _stamp(target),
                str(offset + index),
            ])
    pv = select_pv_vintage(_archive(tmp_path / "pv.zip", pv_header, pv_rows))
    assert pv.identity == {"VERSION_DATETIME": _stamp(CUTOFF)}
    assert pv.issue_time == CUTOFF
    assert len(pv.values) == 48


def test_pwc_hold_is_exact_energy_consistent_and_deterministic(tmp_path: Path) -> None:
    values = tuple(float(index) for index in range(48))
    mapped = pwc_hold_30_to_15(values)
    assert len(mapped) == 96
    assert all(mapped[2 * index:2 * index + 2] == (value, value) for index, value in enumerate(values))
    assert abs(sum(values) * 0.5 - sum(mapped) * 0.25) <= 1e-12
    stamps = optimizer_timestamps()
    assert len(stamps) == len(set(stamps)) == 96
    assert all(right - left == timedelta(minutes=15) for left, right in zip(stamps, stamps[1:]))


def test_official_april_selection_is_reproducible_when_archives_exist() -> None:
    root = Path(r"C:\Users\kjw39\OneDrive\Desktop\4-2\Mobile ESS\raw데이터\AEMO")
    demand_path = root / "Day-Ahead demand forecast" / "PUBLIC_ARCHIVE#PREDISPATCHREGIONSUM#ALL#FILE01#202504010000.zip"
    pv_path = root / "AEMO Rooftop PV — forecast + actual" / "Forecast" / "PUBLIC_ARCHIVE#ROOFTOP_PV_FORECAST#FILE01#202504010000.zip"
    if not (demand_path.is_file() and pv_path.is_file()):
        return
    demand_1, pv_1 = select_demand_vintage(demand_path), select_pv_vintage(pv_path)
    demand_2, pv_2 = select_demand_vintage(demand_path), select_pv_vintage(pv_path)
    assert demand_1.canonical_payload() == demand_2.canonical_payload()
    assert pv_1.canonical_payload() == pv_2.canonical_payload()
    assert mapped_input_sha256(demand_1, pv_1) == mapped_input_sha256(demand_2, pv_2)


def test_materialized_rebind_stops_fail_closed_at_full_ieee123_g11() -> None:
    artifacts = Path(__file__).resolve().parents[2] / "dayahead" / "artifacts" / "v16_1"
    contract = json.loads((artifacts / "AEMO_DA_VINTAGE_CONTRACT_V16_1.json").read_text(encoding="utf-8"))
    assert contract["status"] == "PASS"
    assert contract["demand"]["selected_identity"] == {"PREDISPATCHSEQNO": "2025041428", "RUNNO": "1"}
    assert contract["rooftop_pv"]["selected_identity"] == {"VERSION_DATETIME": "2025/04/14 18:00:00"}
    assert contract["mapping"]["source_slots"] == 48
    assert contract["mapping"]["optimizer_slots"] == 96
    assert contract["firewalls"]["may_scientific_loader_access_count"] == 0
    assert contract["firewalls"]["june_scientific_loader_access_count"] == 0
    assert contract["firewalls"]["actual_as_forecast_read_count"] == 0
    c7 = json.loads((artifacts / "C7_FULL_IEEE123_REPORT_V16_1_AEMO_REBIND.json").read_text(encoding="utf-8"))
    g10 = json.loads((artifacts / "G10_V16_1_AEMO_REBIND_REPORT.json").read_text(encoding="utf-8"))
    g11 = json.loads((artifacts / "G11_V16_1_FULL_IEEE123_AEMO_REBIND_REPORT.json").read_text(encoding="utf-8"))
    assert c7["status"] == "PASS_FULL_IEEE123_V16_1"
    assert g10["status"] == "PASS"
    assert g11["status"] == "FAIL_FULL_IEEE123_BASELINE_INFEASIBLE"
    assert g11["execution"]["grid_lp_count"] == 96
    assert g11["execution"]["master_dependent_row_registry_complete"]
    assert g11["execution"]["pi_sign_convention"] == "PASS"
    assert g11["execution"]["farkasdual_sign_convention"] == "PASS"
    assert g11["execution"]["sampled_perturbation_cut_validity"]["status"] == "PASS"
    assert g11["execution"]["infeasible_incumbent_exclusion"]["status"] == "PASS"
    assert not g11["execution"]["reduced_star_used_as_final_evidence"]
    assert g11["dedicated_aidc_pcc_transformer_audit"]["violation_count_aidc_slots"] > 0
    assert all(value == 0 for value in g11["downstream_call_counts"].values())
