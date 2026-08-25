import json
from pathlib import Path

from pfr.tools.show_january_progress import inspect_day, snapshot


def test_progress_distinguishes_active_failure_from_finished_failure(tmp_path: Path) -> None:
    day = tmp_path / "2025-01-01"
    (day / "B0" / "issue_000000").mkdir(parents=True)
    (day / "B0" / "issue_000000" / "COMMIT_MARKER.json").write_text(
        "{}", encoding="utf-8"
    )
    (day / "B0" / "FAILURE.json").write_text("{}", encoding="utf-8")

    active = inspect_day(day, active=True)
    assert active["status"] == "RUNNING_WITH_FAILURE"
    assert active["counts"]["B0"] == 1

    (day / "MATRIX_SUMMARY.json").write_text(
        json.dumps({"status": "FAIL_CLOSED"}), encoding="utf-8"
    )
    finished = inspect_day(day)
    assert finished["status"] == "FAIL"


def test_progress_does_not_call_abandoned_partial_directory_running(
    tmp_path: Path,
) -> None:
    day = tmp_path / "2025-01-01"
    (day / "B0" / "issue_000000").mkdir(parents=True)
    (day / "B0" / "issue_000000" / "COMMIT_MARKER.json").write_text(
        "{}", encoding="utf-8"
    )

    assert inspect_day(day)["status"] == "INCOMPLETE"
    assert inspect_day(day, active=True)["status"] == "RUNNING"


def test_snapshot_prints_per_method_counts(tmp_path: Path) -> None:
    day = tmp_path / "2025-01-01"
    (day / "B3" / "issue_000000").mkdir(parents=True)
    (day / "B3" / "issue_000000" / "COMMIT_MARKER.json").write_text(
        "{}", encoding="utf-8"
    )

    rendered = snapshot(tmp_path, 1, 1)

    assert "B3=001" in rendered
    assert "total | 1/2304" in rendered


def test_snapshot_counts_new_b07_calibration_axis(tmp_path: Path) -> None:
    day = tmp_path / "2025-01-01"
    marker = day / "B07" / "issue_000000" / "COMMIT_MARKER.json"
    marker.parent.mkdir(parents=True)
    marker.write_text("{}", encoding="utf-8")

    rendered = snapshot(tmp_path, 1, 1, methods=("B07",))

    assert "B07=001" in rendered
    assert "total | 1/288" in rendered
