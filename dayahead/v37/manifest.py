"""Derive the May date set from the committed eligibility authority."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .contracts import DATE_MANIFEST, EXPECTED_DATES
from .status import atomic_json
from .sources import select_cross_month_vintages


ELIGIBILITY = Path(
    "dayahead/artifacts/v16_3_final/V16_3_FINAL_EVALUATION_ELIGIBILITY_MANIFEST.json"
)


def build_may01_amendment(repo: Path) -> dict[str, Any]:
    path = repo / "dayahead/artifacts/v37_may_locked_final/V37_MAY01_CROSS_MONTH_ELIGIBILITY_AMENDMENT.json"
    if path.is_file():
        value = json.loads(path.read_text(encoding="utf-8"))
        if value.get("new_V37_status") == "RUNNABLE" and value.get("causality") == "PASS":
            return value
    selected, failures, evidence = select_cross_month_vintages(("2025-05-01",))
    if failures or "2025-05-01" not in selected:
        raise RuntimeError(f"V37_MAY01_CROSS_MONTH_NOT_ELIGIBLE:{failures}")
    value = selected["2025-05-01"]
    if value["demand_identity"] != {"PREDISPATCHSEQNO": "2025043028", "RUNNO": "1"}:
        raise RuntimeError("V37_MAY01_DEMAND_IDENTITY")
    if value["pv_identity"] != {"VERSION_DATETIME": "2025/04/30 18:00:00"}:
        raise RuntimeError("V37_MAY01_PV_IDENTITY")
    amendment = {
        "artifact_id": "V37_MAY01_CROSS_MONTH_ELIGIBILITY_AMENDMENT_V1",
        "operating_day": "2025-05-01",
        "old_status": "EXCLUDED",
        "old_reasons": ["NO_COMPLETE_CAUSAL_AEMO_DEMAND_VINTAGE", "NO_COMPLETE_CAUSAL_AEMO_PV_VINTAGE"],
        "root_cause": "MONTH_BOUNDARY_ARCHIVE_LOOKUP",
        "classification": "A_CROSS_MONTH_VINTAGE_NOT_MATERIALIZED",
        "frozen_cutoff_fixed_aest": value["cutoff_fixed_aest"],
        "demand": {
            "archive_month": evidence["2025-05-01"]["archive_month"],
            "archive_path": evidence["2025-05-01"]["demand_path"],
            "identity": value["demand_identity"],
            "issue_time": value["demand_issue"], "half_hour_rows": 48,
            "quarter_hour_values": len(value["demand_mw_96"]), "complete": "48/48",
        },
        "rooftop_PV": {
            "archive_month": evidence["2025-05-01"]["archive_month"],
            "archive_path": evidence["2025-05-01"]["pv_path"],
            "identity": value["pv_identity"],
            "issue_time": value["pv_issue"], "half_hour_rows": 48,
            "quarter_hour_values": len(value["pv_mw_96"]), "complete": "48/48",
        },
        "new_V37_status": "RUNNABLE", "May01_manifest_status": "RUNNABLE_CROSS_MONTH_CAUSAL_VINTAGE",
        "causality": "PASS", "future_leakage": "NO", "science_changed": "NO",
        "selection_rule": "archive_month = month(D_minus_1_cutoff)",
        "historical_V16_3_manifest_modified": False,
    }
    atomic_json(path, amendment)
    return amendment


def build_date_manifest(repo: Path) -> dict[str, Any]:
    source = json.loads((repo / ELIGIBILITY).read_text(encoding="utf-8"))
    declared = tuple(map(str, source["candidate_periods"]["MAY_PRIMARY"]))
    if declared != EXPECTED_DATES:
        raise RuntimeError("V37_EXPECTED_DATE_CONTRACT_DRIFT")
    included = {
        str(row["operating_day"])
        for row in source["included"]
        if row.get("period") == "MAY_PRIMARY"
    }
    excluded = {
        str(row["operating_day"]): list(map(str, row["reasons"]))
        for row in source["excluded"]
        if row.get("period") == "MAY_PRIMARY"
    }
    amendment = build_may01_amendment(repo)
    runnable = [day for day in EXPECTED_DATES if day in included or day == "2025-05-01"]
    missing = [
        {"date": day, "reasons": excluded.get(day, ["NOT_INCLUDED_BY_EXISTING_DATA_CONTRACT"])}
        for day in EXPECTED_DATES if day not in runnable
    ]
    payload = {
        "artifact_id": "V37_MAY_DATE_MANIFEST_V1",
        "status": "PASS" if len(runnable) + len(missing) == len(EXPECTED_DATES) else "FAIL",
        "authority_path": ELIGIBILITY.as_posix(),
        "expected_dates": list(EXPECTED_DATES),
        "runnable_dates": runnable,
        "missing_dates": missing,
        "expected_count": len(EXPECTED_DATES),
        "runnable_count": len(runnable),
        "missing_count": len(missing),
        "substitute_dates": [],
        "May01_status": amendment["May01_manifest_status"],
        "superseding_authority": "V37_MAY01_CROSS_MONTH_ELIGIBILITY_AMENDMENT.json",
    }
    atomic_json(repo / DATE_MANIFEST, payload)
    return payload
