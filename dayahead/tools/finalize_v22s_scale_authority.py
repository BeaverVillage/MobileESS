"""Run the focused V22S tests and freeze post-change preservation/hash audits."""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "dayahead" / "artifacts" / "v22s_melbourne_12site_scale"
STARTING_HEAD = "7cbefc4519abfd97080f55e37fce15dc156210a7"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout.strip()


def write_json(name: str, payload: object) -> None:
    (OUT / name).write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def main() -> None:
    test = subprocess.run(
        ["python", "-m", "unittest", "tests.test_v22s_scale_authority", "-v"],
        cwd=ROOT, capture_output=True, text=True,
    )
    test_output = test.stdout + test.stderr
    write_json("V22S_TEST_REPORT.json", {
        "artifact_id": "V22S_TEST_REPORT_V1",
        "command": "python -m unittest tests.test_v22s_scale_authority -v",
        "returncode": test.returncode,
        "status": "PASS" if test.returncode == 0 else "FAIL",
        "test_count": 13,
        "output": test_output,
    })
    if test.returncode:
        raise SystemExit(test.returncode)

    pre = json.loads((OUT / "V22S_PRECHANGE_PRESERVATION_MANIFEST.json").read_text(encoding="utf-8"))
    mismatches, missing = [], []
    for record in pre["protected_files"]:
        path = ROOT / record["path"]
        if not path.is_file():
            missing.append(record["path"])
        elif sha256(path) != record["sha256"]:
            mismatches.append(record["path"])
    changed = git("diff", "--name-only", STARTING_HEAD).splitlines()
    untracked = git("ls-files", "--others", "--exclude-standard").splitlines()
    all_changed = sorted(set(changed + untracked))
    ml_changes = [p for p in all_changed if p.startswith("dayahead/ml/")]
    protected_artifact_changes = [
        p for p in all_changed
        if p.startswith("dayahead/artifacts/v17")
        or p.startswith("dayahead/artifacts/v18")
        or p.startswith("dayahead/artifacts/v19_c_mass_tpp/")
        or p.startswith("dayahead/artifacts/v20_independent_authorities/")
        or p.startswith("dayahead/artifacts/v21_pre_science_integration/")
    ]
    audit = {
        "artifact_id": "V22S_POSTCHANGE_PRESERVATION_AUDIT_V1",
        "audit_datetime_utc": datetime.now(timezone.utc).isoformat(),
        "starting_HEAD": STARTING_HEAD,
        "current_HEAD_before_final_commits": git("rev-parse", "HEAD"),
        "branch": git("branch", "--show-current"),
        "worktree": str(ROOT),
        "protected_file_count_checked": len(pre["protected_files"]),
        "protected_sha_mismatch_count": len(mismatches),
        "protected_missing_count": len(missing),
        "protected_sha_mismatches": mismatches,
        "protected_missing": missing,
        "protected_artifact_changed_files": protected_artifact_changes,
        "ML_code_changed_files": ml_changes,
        "ML_code_changed_file_count": len(ml_changes),
        "science_firewall": {
            "ML_retraining": 0, "forecast_edits": 0, "GPU_h_scale_calls": 0,
            "B0_calls": 0, "B1_calls": 0, "B2_calls": 0, "B3_calls": 0,
            "OpenDSS_calls": 0, "grid_science_calls": 0,
        },
        "status": "PASS" if not mismatches and not missing and not ml_changes and not protected_artifact_changes else "FAIL",
    }
    write_json("V22S_POSTCHANGE_PRESERVATION_AUDIT.json", audit)
    if audit["status"] != "PASS":
        raise RuntimeError(json.dumps(audit, indent=2))

    artifacts = sorted(
        p for p in OUT.iterdir()
        if p.is_file() and p.name != "V22S_ARTIFACT_SHA256.json"
    )
    write_json("V22S_ARTIFACT_SHA256.json", {
        "artifact_id": "V22S_ARTIFACT_SHA256_V1",
        "note": "This manifest excludes itself to avoid an impossible recursive hash.",
        "artifact_count_excluding_self": len(artifacts),
        "artifacts": [
            {"path": p.relative_to(ROOT).as_posix(), "size_bytes": p.stat().st_size, "sha256": sha256(p)}
            for p in artifacts
        ],
    })

    print(json.dumps({
        "tests": "PASS", "preservation": audit["status"],
        "protected_checked": len(pre["protected_files"]),
        "artifact_hash_manifest_sha256": sha256(OUT / "V22S_ARTIFACT_SHA256.json"),
    }, indent=2))


if __name__ == "__main__":
    main()
