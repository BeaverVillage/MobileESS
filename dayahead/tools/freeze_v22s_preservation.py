"""Freeze the immutable V17--V21 and ML baseline before V22S work."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "dayahead" / "artifacts" / "v22s_melbourne_12site_scale"
BASELINE = (
    ROOT
    / "dayahead"
    / "artifacts"
    / "v21_pre_science_integration"
    / "V21_PRECHANGE_PRESERVATION_MANIFEST.json"
)


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout.strip()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    paths: set[str] = set()
    for records in baseline["preservation_groups"].values():
        paths.update(record["path"] for record in records)

    tracked = git("ls-files").splitlines()
    protected_code = re.compile(
        r"^dayahead/(?:ml/|v(?:17|18|19|20|21)|tools/[^/]*v(?:17|18|19|20|21)|tests/test_v(?:17|18|19|20|21))"
    )
    for rel in tracked:
        if rel.startswith("dayahead/artifacts/v21_pre_science_integration/"):
            paths.add(rel)
        elif protected_code.search(rel):
            paths.add(rel)

    records = []
    missing = []
    for rel in sorted(paths):
        path = ROOT / rel
        if not path.is_file():
            missing.append(rel)
            continue
        records.append(
            {
                "path": rel,
                "size_bytes": path.stat().st_size,
                "sha256": sha256(path),
                "tracked": rel in tracked,
            }
        )
    if missing:
        raise RuntimeError(f"Protected files missing: {missing}")

    groups: dict[str, int] = {}
    for record in records:
        rel = record["path"]
        match = re.match(r"dayahead/artifacts/(v[^/]+)/", rel)
        group = match.group(1) if match else "protected_code"
        groups[group] = groups.get(group, 0) + 1

    now = datetime.now(timezone.utc)
    payload = {
        "artifact_id": "V22S_PRECHANGE_PRESERVATION_MANIFEST_V1",
        "retrieval_datetime_utc": now.isoformat(),
        "branch": git("branch", "--show-current"),
        "HEAD": git("rev-parse", "HEAD"),
        "worktree": str(ROOT),
        "git_status_before_any_V22S_change": "CLEAN",
        "git_status_at_manifest_generation": git("status", "--short") or "CLEAN",
        "protected_file_count": len(records),
        "protected_artifact_counts": groups,
        "protected_files": records,
        "source_baseline_manifest": BASELINE.relative_to(ROOT).as_posix(),
        "source_baseline_manifest_sha256": sha256(BASELINE),
        "tool_environment": {
            "python_executable": sys.executable,
            "python_version": sys.version,
            "platform": platform.platform(),
            "os_name": os.name,
            "git_version": git("--version"),
        },
        "internet_access_status": "ENABLED_BY_SESSION_POLICY_NOT_YET_PROBED",
        "firewall_at_freeze": {
            "ML_retraining_calls": 0,
            "forecast_edits": 0,
            "GPU_h_scale_calls": 0,
            "B0_calls": 0,
            "B1_calls": 0,
            "B2_calls": 0,
            "B3_calls": 0,
            "OpenDSS_calls": 0,
            "grid_science_calls": 0,
        },
    }
    target = OUT / "V22S_PRECHANGE_PRESERVATION_MANIFEST.json"
    target.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "path": str(target),
                "protected_file_count": len(records),
                "groups": groups,
                "sha256": sha256(target),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
