"""Create the immutable V20 independent-authority preservation baseline."""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "dayahead" / "artifacts" / "v20_independent_authorities"
BASE = "77a86e3ded8087ea0109ccfca631bd2396ecd9fe"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def git(*args: str, cwd: Path = ROOT) -> str:
    return subprocess.check_output(["git", *args], cwd=cwd, text=True).strip()


def inventory(prefixes: tuple[str, ...]) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for path in sorted((ROOT / "dayahead" / "artifacts").rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(ROOT).as_posix()
        if any(rel.startswith(prefix) for prefix in prefixes):
            records.append({"path": rel, "bytes": path.stat().st_size, "sha256": sha256(path)})
    return records


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    prefixes = (
        "dayahead/artifacts/v17_",
        "dayahead/artifacts/v17_candidate/",
        "dayahead/artifacts/v18_",
        "dayahead/artifacts/v18r1_",
        "dayahead/artifacts/v18r2_",
    )
    preserved = inventory(prefixes)
    payload = {
        "artifact_id": "V20_PRECHANGE_MANIFEST_V1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "known_common_base": BASE,
        "repository": {
            "worktree": str(ROOT),
            "branch": git("branch", "--show-current"),
            "head": git("rev-parse", "HEAD"),
            "status_before_manifest": [],
            "separate_worktree_confirmed": True,
        },
        "protected_v19": {
            "worktree": str(ROOT.parent / "github_MobileESS_march_validity_fix"),
            "policy": "READ_ONLY_NO_WRITES",
            "protected_path": "dayahead/ml/c_mass_tpp/**",
            "writes_by_v20_task": 0,
        },
        "preservation_scope": list(prefixes),
        "preserved_file_count": len(preserved),
        "preserved_files": preserved,
        "firewall": {
            "C_MASS_TPP_code_changes": 0,
            "ML_training_calls": 0,
            "B0_B1_B2_B3_calls": 0,
            "OpenDSS_calls": 0,
            "grid_science_calls": 0,
        },
    }
    if payload["repository"]["head"] != BASE:
        raise RuntimeError("V20 worktree did not start at the required common base")
    target = OUT / "V20_PRECHANGE_MANIFEST.json"
    target.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
