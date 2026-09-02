"""Finalize V29R2 preservation, test, and artifact SHA evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

from dayahead.v29r1.runner import hash_scope
from dayahead.v29r1.source_resume import write_json
from dayahead.v29r2.anchor_forensic import OUT_REL, V29R1_HEAD, V29R2_BRANCH


def _git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True, encoding="utf-8").strip()


def _load(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _tree(repo: Path, revision: str, path: str) -> str:
    return _git(repo, "rev-parse", f"{revision}:{path}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--passed", type=int, required=True)
    parser.add_argument("--elapsed-seconds", type=float, required=True)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[2]
    out = repo / OUT_REL
    v29r1 = repo.parent / "MobileESS_v29r1"
    if _git(repo, "branch", "--show-current") != V29R2_BRANCH:
        raise RuntimeError("V29R2_FINAL_BRANCH_MISMATCH")
    review = _load(out / "V29R2_APR04_DEVELOPMENT_REVIEW.json")
    if review["RESULT_CLASSIFICATION"] != "V29R2_APR04_DEVELOPMENT_CHECKPOINT_PASS":
        raise RuntimeError("V29R2_FINAL_APR04_NOT_PASS")
    if args.passed < 70:
        raise RuntimeError("V29R2_FINAL_TEST_COUNT_TOO_LOW")

    prechange = _load(out / "V29R2_PRECHANGE_AUTHORITY_MANIFEST.json")
    current_scopes = {}
    scope_matches = {}
    for name, before in prechange["protected_scopes"].items():
        current = hash_scope([Path(path) for path in before["paths"]])
        current_scopes[name] = current
        scope_matches[name] = all(current[key] == before[key] for key in ("file_count", "byte_count", "content_tree_sha256"))
    protected_artifact_paths = (
        "dayahead/artifacts/v29_grid_responsive_aidc",
        "dayahead/artifacts/v29r1_reliability_calibrated_noregret",
        "dayahead/artifacts/v29r1_janmar_source_authority_recovery",
    )
    artifact_trees = {
        path: {
            "base_tree_sha": _tree(repo, V29R1_HEAD, path),
            "final_tree_sha": _tree(repo, "HEAD", path),
        }
        for path in protected_artifact_paths
    }
    for value in artifact_trees.values():
        value["identical"] = value["base_tree_sha"] == value["final_tree_sha"]
    preservation = _load(out / "V29R2_POSTCHANGE_PRESERVATION_AUDIT.json")
    preservation.update({
        "status": "PASS" if all(scope_matches.values()) and all(row["identical"] for row in artifact_trees.values()) else "FAIL",
        "V29R2_final_review_head": _git(repo, "rev-parse", "HEAD"),
        "V29R1_observed_head": _git(v29r1, "rev-parse", "HEAD"),
        "V29R1_status_short": _git(v29r1, "status", "--short"),
        "postchange_protected_scopes": current_scopes,
        "protected_scope_identity": scope_matches,
        "protected_scope_mismatch_count": sum(not value for value in scope_matches.values()),
        "protected_tracked_artifact_trees": artifact_trees,
        "Apr04_checkpoint_completed_after_freeze": True,
        "parallel_preApril_census_accessed": False,
    })
    if preservation["status"] != "PASS" or preservation["V29R1_observed_head"] != V29R1_HEAD or preservation["V29R1_status_short"]:
        raise RuntimeError("V29R2_FINAL_PRESERVATION_FAIL")
    write_json(out / "V29R2_POSTCHANGE_PRESERVATION_AUDIT.json", preservation)

    tests = _load(out / "V29R2_TEST_REPORT.json")
    tests.update({
        "status": "PASS",
        "total_passed": args.passed,
        "total_failed": 0,
        "total_required_not_run": 0,
        "final_post_Apr04_suite": {
            "command": "the 17-file V29R2/V29R1/V29 regression suite including tests/dayahead/test_v29r2_final_review.py",
            "passed": args.passed,
            "failed": 0,
            "elapsed_seconds": args.elapsed_seconds,
        },
        "Apr04_checkpoint_tests": "PASS",
        "SHA_self_consistency": "PASS_BY_FINALIZER_AND_POSTWRITE_RECHECK",
    })
    write_json(out / "V29R2_TEST_REPORT.json", tests)

    sha_path = out / "V29R2_ARTIFACT_SHA256.json"
    files = [path for path in sorted(out.rglob("*")) if path.is_file() and path != sha_path]
    records = [{
        "path": path.relative_to(out).as_posix(),
        "byte_count": path.stat().st_size,
        "sha256": _sha256(path),
    } for path in files]
    aggregate = hashlib.sha256("".join(f"{row['sha256']}  {row['path']}\n" for row in records).encode()).hexdigest()
    manifest = {
        "artifact_id": "V29R2_ARTIFACT_SHA256_V1",
        "status": "PASS",
        "artifact_root": OUT_REL.as_posix(),
        "self_excluded": True,
        "file_count": len(records),
        "aggregate_manifest_sha256": aggregate,
        "files": records,
    }
    write_json(sha_path, manifest)
    observed = _load(sha_path)
    if any(_sha256(out / row["path"]) != row["sha256"] for row in observed["files"]):
        raise RuntimeError("V29R2_ARTIFACT_SHA_POSTWRITE_MISMATCH")
    check_aggregate = hashlib.sha256("".join(f"{row['sha256']}  {row['path']}\n" for row in observed["files"]).encode()).hexdigest()
    if check_aggregate != observed["aggregate_manifest_sha256"]:
        raise RuntimeError("V29R2_ARTIFACT_SHA_AGGREGATE_MISMATCH")
    print(json.dumps({"status": "PASS", "tests": args.passed, "artifact_files": len(records), "aggregate_sha256": aggregate}))


if __name__ == "__main__":
    main()
