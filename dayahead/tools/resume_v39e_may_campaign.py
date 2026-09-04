"""Resume the V39E May campaign from a fully sealed preflight artifact."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dayahead.v38.authority import canonical_sha256
from dayahead.v39c.freeze import sha256_file
from dayahead.v39e.campaign import run_campaign
from dayahead.v39e.contracts import (
    BRANCH,
    CAPACITY_FILE_SHA256,
    EXPECTED_DATES,
    RACK_AUTHORITY_PATH,
    RACK_AUTHORITY_SHA256,
)
from dayahead.v39e.full_preflight import CASES, FULL_ROOT, FAST_ROOT
from dayahead.v39e.overnight import _write_final_report
from dayahead.v39e.progress import ProgressTracker


def _git(repo: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", *args], cwd=repo, text=True, encoding="utf-8"
    ).strip()


def _load_valid_preflight(repo: Path) -> dict[str, Any]:
    path = repo / FULL_ROOT / "V39E_FULL_PREFLIGHT.json"
    preflight = json.loads(path.read_text(encoding="utf-8"))
    days = {str(row["operating_day"]) for row in preflight.get("days", [])}
    if (
        days != set(EXPECTED_DATES)
        or int(preflight.get("READY", -1)) + int(preflight.get("NOT_READY", -1)) != 31
        or int(preflight.get("missing", -1)) != 0
    ):
        raise RuntimeError("V39E_RESUME_PREFLIGHT_AXIS_OR_COUNTS")

    inputs = {
        "initial_authority_SHA256": sha256_file(
            repo / FAST_ROOT / "V39E_COMMON_INITIAL_STATE_AUDIT.json"
        ),
        "Rack_authority_SHA256": RACK_AUTHORITY_SHA256,
        "site_capacity_SHA256": CAPACITY_FILE_SHA256,
        "source_SHA256": {
            source.name: sha256_file(source)
            for source in sorted((repo / "dayahead/v39e").glob("*.py"))
        },
    }
    if inputs != preflight.get("implementation_fingerprint_inputs"):
        raise RuntimeError("V39E_RESUME_PREFLIGHT_INPUT_DRIFT")
    if canonical_sha256(inputs) != preflight.get(
        "final_implementation_fingerprint_sha256"
    ):
        raise RuntimeError("V39E_RESUME_PREFLIGHT_FINGERPRINT_MISMATCH")

    for day in EXPECTED_DATES:
        for case in CASES:
            freeze_path = (
                repo / FULL_ROOT
                / f"V39E_DAYAHEAD_DECISION_FREEZE_{day}_{case}.json"
            )
            freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
            if canonical_sha256(freeze["decision"]) != freeze.get(
                "DA_decision_SHA256"
            ):
                raise RuntimeError(f"V39E_RESUME_DA_FREEZE_SHA:{day}:{case}")
    return preflight


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=ROOT)
    args = parser.parse_args()
    repo = args.repo.resolve()
    branch = _git(repo, "branch", "--show-current")
    head = _git(repo, "rev-parse", "HEAD")
    if branch != BRANCH:
        raise RuntimeError("V39E_BRANCH_MISMATCH")
    if sha256_file(repo / RACK_AUTHORITY_PATH) != RACK_AUTHORITY_SHA256:
        raise RuntimeError("V39E_RACK_AUTHORITY_SHA_DRIFT")
    preflight = _load_valid_preflight(repo)
    tracker = ProgressTracker(repo, head, branch)
    tracker.start_heartbeat()
    try:
        tracker.update(
            phase="RERUN",
            campaign_classification="DIAGNOSTIC_OVERRIDE",
            preflight_READY=preflight["READY"],
            preflight_NOT_READY=preflight["NOT_READY"],
            preflight_missing=preflight["missing"],
            preflight_attempt=preflight.get("attempt", 1),
            repair_iteration=2,
            last_repair_classification="EXECUTION_INFRASTRUCTURE_DEFECT",
            last_repair_commit=head,
            repair_summary="WINDOWS_ATOMIC_REPLACE_RETRY_AND_VALIDATED_PREFLIGHT_RESUME",
            rerun_mode="AFFECTED_SCOPE",
            reusable_count=0,
            invalidated_count=0,
            rerun_count=4,
            exact_current_blocker="RESUMING_INTERRUPTED_MAY_WORKERS_FROM_EXACT_CHECKPOINTS",
            PRECHECK_BYPASSED="YES",
        )
        campaign = run_campaign(repo, tracker, preflight)
        _write_final_report(repo, preflight, campaign)
        print(
            json.dumps(
                {"preflight": preflight, "campaign": campaign},
                indent=2,
                sort_keys=True,
            ),
            flush=True,
        )
        return 0
    finally:
        tracker.close()


if __name__ == "__main__":
    raise SystemExit(main())
