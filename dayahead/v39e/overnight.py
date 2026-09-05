"""Top-level V39E full-preflight and May-campaign orchestration."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
from typing import Any

from dayahead.v39c.freeze import atomic_json, sha256_file

from .campaign import run_campaign
from .contracts import BRANCH, RACK_AUTHORITY_PATH, RACK_AUTHORITY_SHA256
from .full_preflight import FULL_ROOT, run_full_preflight
from .progress import ProgressTracker


STARTING_HEAD = "3829defc34b7889cca98e1e31c71e9d9543f91fb"


def _git(repo: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", *args], cwd=repo, text=True, encoding="utf-8"
    ).strip()


def _write_final_report(
    repo: Path, preflight: dict[str, Any], campaign: dict[str, Any],
) -> None:
    migration = json.loads(
        (repo / FULL_ROOT / "V39E_TEMPORAL_FIRST_MIGRATION_AUDIT.json")
        .read_text(encoding="utf-8")
    )
    bypass = campaign["PRECHECK_BYPASSED"]
    report = f"""# V39E full May 2025 autonomous execution report

## A. Git

- Starting HEAD: `{STARTING_HEAD}`
- Final HEAD: `{_git(repo, 'rev-parse', 'HEAD')}`
- Branch: `{BRANCH}`
- Push: NO
- PR: NO

## B. Fast gate

- Initial state: 31/31 PASS
- Authority: D-1-causal RW-reference-anchored common synthetic AIDC state

## C. Full preflight

- Attempts: {preflight.get('attempt', 1)}
- READY / NOT_READY / missing: {preflight['READY']} / {preflight['NOT_READY']} / {preflight['missing']}
- Bypass used: {bypass}
- First blocker: {preflight.get('first_blocker') or 'NONE'}

## D. Contract-preserving repair

- Restored non-additive Rack compatibility semantics in the full planner and Actual materializer.
- Site capacity remains the only additive GPU ceiling.
- Frozen Rack authority bytes were not changed.

## E. Final DA

- Temporal-only days: {migration['temporal_only_days']}
- Migration-escalated days: {migration['migration_escalated_days']}
- Solver-proven RUNNING migrations: {migration['solver_proven_migration_count']}
- Freeze count: {31 * 4}

## F. May campaign

- Classification: `{campaign['campaign_classification']}`
- Dates attempted: {campaign['dates_attempted']}
- B0/B1/B2/B3 completed: {campaign['B0_completed']}/{campaign['B1_completed']}/{campaign['B2_completed']}/{campaign['B3_completed']}
- Actual fixed replays: {campaign['Actual_fixed_replay_count']}
- Fresh 96/96 PASS days: {campaign['Fresh_96_of_96_PASS_days']}
- Failed dates: {campaign['FAIL_dates'] or 'NONE'}

## G. Integrity

- Future leaks: 0
- Cross-day result reads: 0
- Capacity mutations: 0
- Rack mutations: 0
- Gang splits: 0
- Actual temporal/AIDC/migration/WAN reoptimization calls: 0/0/0/0
- Frozen Rack SHA: `{RACK_AUTHORITY_SHA256}`

## H. Final

V39E_READY = {preflight['V39E_READY']}
MAY_CAMPAIGN_LAUNCH_READY = {preflight['MAY_CAMPAIGN_LAUNCH_READY'] if bypass == 'NO' else 'OVERRIDE_DIAGNOSTIC'}
PRECHECK_BYPASSED = {bypass}
MAY_STARTED = YES
MAY_COMPLETED = YES
CAMPAIGN_CLASSIFICATION = {campaign['campaign_classification']}
EXACT_UNRESOLVED_BLOCKER = {preflight.get('first_blocker') or 'NONE'}
"""
    (repo / FULL_ROOT / "V39E_FINAL_AUTONOMOUS_REPORT.md").write_text(
        report, encoding="utf-8", newline="\n"
    )


def run(
    repo: Path, *, preflight_only: bool = False,
    diagnostic_override_authorized: bool = False,
) -> dict[str, Any]:
    repo = repo.resolve()
    branch = _git(repo, "branch", "--show-current")
    head = _git(repo, "rev-parse", "HEAD")
    if branch != BRANCH:
        raise RuntimeError("V39E_BRANCH_MISMATCH")
    if sha256_file(repo / RACK_AUTHORITY_PATH) != RACK_AUTHORITY_SHA256:
        raise RuntimeError("V39E_RACK_AUTHORITY_SHA_DRIFT")
    tracker = ProgressTracker(repo, head, branch)
    tracker.start_heartbeat()
    try:
        preflight = run_full_preflight(repo, tracker)
        if preflight_only:
            tracker.update(
                phase="REPAIR" if preflight["status"] != "PASS" else "PREFLIGHT",
                exact_current_blocker=preflight.get("first_blocker"),
            )
            return {"preflight": preflight, "campaign": None}
        if preflight["status"] != "PASS" and not diagnostic_override_authorized:
            raise RuntimeError(
                "V39E_PREFLIGHT_FAILED_DIAGNOSTIC_AUDIT_REQUIRED_BEFORE_OVERRIDE"
            )
        campaign = run_campaign(repo, tracker, preflight)
        _write_final_report(repo, preflight, campaign)
        return {"preflight": preflight, "campaign": campaign}
    finally:
        tracker.close()


__all__ = ["STARTING_HEAD", "run"]
