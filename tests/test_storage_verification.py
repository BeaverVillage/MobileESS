import csv
import json
from pathlib import Path

from pfr.tools.verify_daily_campaign_storage import (
    inspect_campaign_registry,
    inspect_method,
)


def write_complete_method(root: Path, first_issue: int = 8928) -> None:
    method_root = root / "B8"
    rows = []
    for offset in range(288):
        issue = first_issue + offset
        row = {
            "status": "PASS_COMMITTED",
            "commit_marker": True,
            "comparison_method_id": "B8",
            "issue": issue,
            "actual_gurobi_used": True,
            "actual_fresh_opendss_used": True,
            "future_actual_used": False,
            "pre_state_sha256": f"state-{offset}",
            "post_state_sha256": f"state-{offset + 1}",
        }
        issue_root = method_root / f"issue_{issue:06d}"
        issue_root.mkdir(parents=True)
        (issue_root / "COMMIT_MARKER.json").write_text(
            json.dumps(row), encoding="utf-8"
        )
        rows.append(row)
    (method_root / "METHOD_SUMMARY.json").write_text(
        json.dumps(
            {
                "status": "PASS",
                "comparison_method_id": "B8",
                "commit_marker_count": 288,
            }
        ),
        encoding="utf-8",
    )
    with (method_root / "MATERIALIZED_COMMIT_ROWS.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0])
        writer.writeheader()
        writer.writerows(rows)


def test_exact_daily_issue_and_csv_axes_pass(tmp_path: Path) -> None:
    write_complete_method(tmp_path)
    result = inspect_method(tmp_path / "B8", "B8", 8928)
    assert result["errors"] == []
    assert result["commit_markers"] == 288
    assert result["materialized_csv_rows"] == 288


def test_equal_count_with_one_missing_and_one_foreign_issue_fails(tmp_path: Path) -> None:
    write_complete_method(tmp_path)
    missing = tmp_path / "B8/issue_008938"
    foreign = tmp_path / "B8/issue_009999"
    missing.rename(foreign)
    marker_path = foreign / "COMMIT_MARKER.json"
    marker = json.loads(marker_path.read_text(encoding="utf-8"))
    marker["issue"] = 9999
    marker_path.write_text(json.dumps(marker), encoding="utf-8")

    result = inspect_method(tmp_path / "B8", "B8", 8928)
    assert result["commit_markers"] == 288
    assert "committed issue axis is not the exact daily 288-step range" in result[
        "errors"
    ]
    assert "PASS method issue-directory axis is incomplete or contains extras" in result[
        "errors"
    ]


def test_missing_materialized_csv_fails(tmp_path: Path) -> None:
    write_complete_method(tmp_path)
    (tmp_path / "B8/MATERIALIZED_COMMIT_ROWS.csv").unlink()
    result = inspect_method(tmp_path / "B8", "B8", 8928)
    assert "PASS method lacks MATERIALIZED_COMMIT_ROWS.csv" in result["errors"]


def test_campaign_registry_requires_exact_date_and_b8_axes(tmp_path: Path) -> None:
    dates = ["2025-02-01", "2025-02-02"]
    (tmp_path / "CAMPAIGN_SUMMARY.json").write_text(
        json.dumps(
            {
                "status": "PASS",
                "daily_runs": [
                    {"calendar_date": value, "status": "PASS"} for value in dates
                ],
                "method_ids": ["B8"],
                "methods_per_day": 1,
                "issues_per_method_per_day": 288,
                "continue_to_next_method_after_failure": True,
                "continue_to_next_day_after_failure": True,
                "supplementary_b8_periodic_5min": True,
            }
        ),
        encoding="utf-8",
    )
    assert inspect_campaign_registry(tmp_path, dates, ("B8",))["errors"] == []


def test_campaign_registry_detects_missing_day(tmp_path: Path) -> None:
    dates = ["2025-03-01", "2025-03-02"]
    (tmp_path / "CAMPAIGN_SUMMARY.json").write_text(
        json.dumps(
            {
                "status": "PASS",
                "daily_runs": [{"calendar_date": dates[0], "status": "PASS"}],
                "method_ids": ["B8"],
                "methods_per_day": 1,
                "issues_per_method_per_day": 288,
                "continue_to_next_method_after_failure": True,
                "continue_to_next_day_after_failure": True,
                "supplementary_b8_periodic_5min": True,
            }
        ),
        encoding="utf-8",
    )
    result = inspect_campaign_registry(tmp_path, dates, ("B8",))
    assert "campaign daily date axis is incomplete, duplicated, or reordered" in result[
        "errors"
    ]
