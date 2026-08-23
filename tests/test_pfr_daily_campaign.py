from pathlib import Path
import os
import subprocess
import sys
import tempfile

import pytest

from pfr.tools.run_pfr_daily_campaign import (
    _STOP_REQUESTED,
    day_specs,
    discover_campaign_process_groups,
    preserve_existing_day,
    reusable_pass,
    stop_active_children,
)


def test_january_day_specs_use_global_fixed_aest_issue_axis() -> None:
    specs = day_specs(1, 7)

    assert len(specs) == 7
    assert specs[0].calendar_date == "2025-01-01"
    assert specs[0].start_issue == 0
    assert specs[-1].calendar_date == "2025-01-07"
    assert specs[-1].start_issue == 6 * 288
    assert specs[-1].candidate_id == "JAN2025_DAY07"


def test_january_day_specs_reject_non_january_range() -> None:
    with pytest.raises(ValueError):
        day_specs(0, 7)
    with pytest.raises(ValueError):
        day_specs(8, 32)


def test_failed_day_attempt_is_moved_to_preserved_namespace() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        day = root / "2025-01-04"
        day.mkdir()
        evidence = day / "FAILURE.json"
        evidence.write_text("failure evidence", encoding="utf-8")

        preserved = preserve_existing_day(day, root)

        assert not day.exists()
        assert preserved.parent == root / "_preserved_attempts"
        assert (preserved / "FAILURE.json").read_text(encoding="utf-8") == (
            "failure evidence"
        )


def test_preserve_refuses_target_outside_campaign_root() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        outside = root / "outside"
        campaign = root / "campaign"
        outside.mkdir()
        campaign.mkdir()
        with pytest.raises(RuntimeError):
            preserve_existing_day(outside, campaign)


def test_pass_reuse_requires_matching_implementation_fingerprint(
    tmp_path: Path,
) -> None:
    day = tmp_path / "2025-01-01"
    day.mkdir()
    (day / "MATRIX_SUMMARY.json").write_text(
        """{
          "status": "PASS",
          "expected_commit_markers": 2304,
          "all_actual_gurobi": true,
          "all_fresh_exact_opendss": true,
          "all_state_chains_complete": true,
          "future_actual_used": false
        }""",
        encoding="utf-8",
    )
    (day / "RUN_MANIFEST.json").write_text(
        '{"scientific_implementation_fingerprint":"current",'
        '"shared_exogenous_authority_sha256":"source-a"}', encoding="utf-8"
    )

    assert reusable_pass(day, "current")
    assert reusable_pass(day, "current", "source-a")
    assert not reusable_pass(day, "current", "source-b")
    assert not reusable_pass(day, "changed")


def test_b8_pass_reuse_requires_288_markers(tmp_path: Path) -> None:
    day = tmp_path / "2025-01-01"
    day.mkdir()
    (day / "MATRIX_SUMMARY.json").write_text(
        """{
          "status": "PASS",
          "expected_commit_markers": 288,
          "all_actual_gurobi": true,
          "all_fresh_exact_opendss": true,
          "all_state_chains_complete": true,
          "future_actual_used": false
        }""",
        encoding="utf-8",
    )
    (day / "RUN_MANIFEST.json").write_text(
        '{"scientific_implementation_fingerprint":"current"}',
        encoding="utf-8",
    )

    assert reusable_pass(day, "current", method_count=1)
    assert not reusable_pass(day, "current", method_count=8)


@pytest.mark.skipif(os.name != "posix", reason="process groups use POSIX semantics")
def test_ctrl_c_cleanup_discovers_and_stops_orphan_matrix_group(
    tmp_path: Path,
) -> None:
    day = tmp_path / "2025-01-01"
    day.mkdir()
    process = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "import time; time.sleep(60)",
            "pfr.tools.run_pfr_matrix",
            "--output",
            str(day),
        ],
        start_new_session=True,
    )
    try:
        assert process.pid in discover_campaign_process_groups(tmp_path)
        stop_active_children(tmp_path)
        process.wait(timeout=5)
        assert process.returncode is not None
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        _STOP_REQUESTED.clear()
