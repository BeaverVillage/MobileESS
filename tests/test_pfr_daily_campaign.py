from pathlib import Path
import json
import os
import signal
import subprocess
import sys
import tempfile

import pytest

from pfr.tools.run_pfr_daily_campaign import (
    _STOP_REQUESTED,
    CampaignAlreadyRunningError,
    DaySpec,
    acquire_campaign_lock,
    campaign_payload,
    day_specs,
    discover_campaign_process_groups,
    preserve_existing_day,
    release_campaign_lock,
    reusable_pass,
    stop_active_children,
    write_day_failure_evidence,
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


def test_failed_day_evidence_contains_command_log_tail_and_artifact_inventory(
    tmp_path: Path,
) -> None:
    day = tmp_path / "2025-01-04"
    day.mkdir()
    (day / "DAY_RUN.log").write_text("line one\nroot exception\n", encoding="utf-8")
    (day / "partial.json").write_text("{}\n", encoding="utf-8")

    path = write_day_failure_evidence(
        day_root=day,
        spec=DaySpec(4, "2025-01-04", 864, "JAN2025_DAY04"),
        returncode=1,
        command=("python", "-m", "pfr.tools.run_pfr_matrix"),
        implementation_fingerprint="frozen-fingerprint",
        preserved_attempt=None,
    )

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["status"] == "FAIL_CLOSED"
    assert payload["returncode"] == 1
    assert payload["day_log_tail"][-1] == "root exception"
    assert "partial.json" in payload["artifact_files"]


def test_fail_fast_campaign_payload_declares_abort_policy() -> None:
    payload = campaign_payload(
        start_day=1,
        end_day=31,
        day_workers=4,
        summaries=(),
        final=False,
        supplementary_b8_periodic_5min=False,
        diagnostic_method="B07",
        fail_fast=True,
    )

    assert payload["continue_to_next_day_after_failure"] is False
    assert payload["fail_fast_on_first_day_failure"] is True
    assert payload["failure_evidence_preserved_before_abort"] is True


@pytest.mark.skipif(os.name != "posix", reason="flock requires POSIX")
def test_campaign_output_lock_rejects_second_owner(tmp_path: Path) -> None:
    first = acquire_campaign_lock(tmp_path)
    try:
        with pytest.raises(CampaignAlreadyRunningError):
            acquire_campaign_lock(tmp_path)
    finally:
        release_campaign_lock(first)


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
    assert reusable_pass(
        day,
        "changed",
        authorized_implementation_fingerprints=("current",),
    )
    assert not reusable_pass(
        day,
        "changed",
        shared_authority_sha256="source-b",
        authorized_implementation_fingerprints=("current",),
    )


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


@pytest.mark.skipif(os.name != "posix", reason="POSIX signal semantics required")
def test_signal_handlers_restore_sigint_ignored_by_parent() -> None:
    script = """
import os
import signal
signal.signal(signal.SIGINT, signal.SIG_IGN)
from pfr.tools.run_pfr_daily_campaign import install_stop_signal_handlers
install_stop_signal_handlers()
os.kill(os.getpid(), signal.SIGINT)
raise SystemExit(99)
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).resolve().parents[1],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == -signal.SIGINT
    assert "KeyboardInterrupt" in completed.stderr
