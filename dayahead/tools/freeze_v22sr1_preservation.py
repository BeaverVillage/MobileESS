"""Freeze immutable V17--V22S inputs before V22S-R1 arithmetic work."""

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
OUT = ROOT / "dayahead" / "artifacts" / "v22s_r1_final_operating_scale"


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
    tracked = git("ls-files").splitlines()
    protected = re.compile(
        r"^dayahead/(?:artifacts/(?:v(?:17|18|19|20|21)(?:[^/]*)|v22s_melbourne_12site_scale)/|"
        r"ml/|v(?:17|18|19|20|21|22)|tools/[^/]*v(?:17|18|19|20|21|22s)(?!r1)|"
        r"tests/test_v(?:17|18|19|20|21|22s)(?!r1))",
        re.IGNORECASE,
    )
    paths = sorted(rel for rel in tracked if protected.search(rel))
    records = []
    for rel in paths:
        path = ROOT / rel
        if not path.is_file():
            raise RuntimeError(f"Protected file missing: {rel}")
        records.append(
            {"path": rel, "size_bytes": path.stat().st_size, "sha256": sha256(path)}
        )
    groups: dict[str, int] = {}
    for record in records:
        match = re.match(r"dayahead/artifacts/([^/]+)/", record["path"])
        group = match.group(1) if match else "protected_code"
        groups[group] = groups.get(group, 0) + 1
    now = datetime.now(timezone.utc)
    payload = {
        "artifact_id": "V22SR1_PRECHANGE_MANIFEST_V1",
        "retrieval_datetime_utc": now.isoformat(),
        "branch": git("branch", "--show-current"),
        "HEAD": git("rev-parse", "HEAD"),
        "starting_authority_HEAD": "a842d301febc523dfca5d4803aebdf70b048586e",
        "worktree": str(ROOT),
        "git_status_before_V22SR1_files": "CLEAN",
        "git_status_at_manifest_generation": git("status", "--short") or "CLEAN",
        "protected_file_count": len(records),
        "protected_artifact_counts": groups,
        "protected_files": records,
        "tool_environment": {
            "python_executable": sys.executable,
            "python_version": sys.version,
            "platform": platform.platform(),
            "os_name": os.name,
            "git_version": git("--version"),
        },
        "internet_access_status": "ENABLED_AND_TO_BE_REVERIFIED",
        "firewall_at_freeze": {
            "ML_retraining": 0,
            "forecast_edits": 0,
            "GPU_h_scale_calls": 0,
            "B0_B1_B2_B3_calls": 0,
            "OpenDSS_calls": 0,
            "grid_science_calls": 0,
        },
    }
    target = OUT / "V22SR1_PRECHANGE_MANIFEST.json"
    target.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"path": str(target), "protected_file_count": len(records), "sha256": sha256(target)}, indent=2))


if __name__ == "__main__":
    main()
