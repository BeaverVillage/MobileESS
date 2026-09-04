"""Materialize and audit V37-R4A day-specific AIDC inputs."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess

from dayahead.v37.aidc_materializer import R4A_ROOT, materialize_all, refresh_causal_snapshots


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8", newline="\n",
    )
    temporary.replace(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--refresh-causal-snapshots-only", action="store_true")
    args = parser.parse_args(argv)
    repo = args.repo.resolve()
    root = repo / R4A_ROOT
    branch = subprocess.check_output(["git", "branch", "--show-current"], cwd=repo, text=True).strip()
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    status = subprocess.check_output(["git", "status", "--short"], cwd=repo, text=True).splitlines()
    _write_json(root / "V37_R4A_START_STATE.json", {
        "artifact_id": "V37_R4A_START_STATE_V1", "branch": branch, "HEAD": head,
        "git_status": status, "started_at_utc": datetime.now(timezone.utc).isoformat(),
    })
    manifests = (
        refresh_causal_snapshots(repo)
        if args.refresh_causal_snapshots_only
        else materialize_all(repo)
    )
    _write_json(root / "V37_R4A_TEST_REPORT.json", {
        "artifact_id": "V37_R4A_TEST_REPORT_V1", "status": "PENDING_FOCUSED_PYTEST",
        "materialized_dates": len(manifests),
    })
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
