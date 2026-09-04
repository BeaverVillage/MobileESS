"""Write the V29R2 pre-Apr-04 scientific freeze marker from a clean HEAD."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from dayahead.v29r1.source_resume import write_json
from dayahead.v29r2.anchor_forensic import OUT_REL, V29R2_BRANCH


def _git(repo: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(repo), *args], text=True, encoding="utf-8"
    ).strip()


def _load(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--invalidation-reason",
        default="Apr-04 fail-closed runner exposed an unsupported trajectory namespace before any Apr-04 result artifact was written.",
    )
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[2]
    out = repo / OUT_REL
    prior_freeze_path = out / "V29R2_DEV_FREEZE.json"
    prior_freeze = _load(prior_freeze_path) if prior_freeze_path.is_file() else None
    if _git(repo, "branch", "--show-current") != V29R2_BRANCH:
        raise RuntimeError("V29R2_FREEZE_BRANCH_MISMATCH")
    if _git(repo, "status", "--short"):
        raise RuntimeError("V29R2_FREEZE_REQUIRES_CLEAN_HEAD")
    reports = {
        "tests": _load(out / "V29R2_TEST_REPORT.json"),
        "preservation": _load(out / "V29R2_POSTCHANGE_PRESERVATION_AUDIT.json"),
        "anchor": _load(out / "V29R2_ANCHOR_FORENSIC_FINAL_REVIEW.json"),
        "trust": _load(out / "V29R2_TRUST_CERT_DECISION.json"),
        "service": _load(out / "V29R2_EXEC_SERVICE_MODEL_AUTHORITY.json"),
        "bridge": _load(out / "V29R2_BRIDGE_V2_CALIBRATION.json"),
        "reference": _load(out / "V29R2_REFERENCE_V4_CONTRACT.json"),
        "no_regret": _load(out / "V29R2_MESS_NOREGRET_CONTRACT.json"),
    }
    if any(report["status"] != "PASS" for report in reports.values()):
        raise RuntimeError("V29R2_FREEZE_GATE_NOT_PASS")
    if any(out.joinpath(name).exists() for name in (
        "V29R2_APR04_DA_RESULTS.csv", "V29R2_APR04_ACTUAL_RESULTS.csv",
        "V29R2_APR04_PI_RESULTS.csv", "V29R2_APR04_DEVELOPMENT_REVIEW.json",
    )):
        raise RuntimeError("V29R2_APR04_RESULT_EXISTS_BEFORE_FREEZE")
    head = _git(repo, "rev-parse", "HEAD")
    payload = {
        "artifact_id": "V29R2_DEV_FREEZE_V1",
        "status": "PASS",
        "classification": "V29R2_PRE_APR04_SCIENTIFIC_FREEZE",
        "V29R2_DEV_FREEZE_HEAD": head,
        "V29R2_DEV_FREEZE_TREE": _git(repo, "rev-parse", "HEAD^{tree}"),
        "branch": V29R2_BRANCH,
        "all_pre_Apr04_gates_pass": True,
        "required_test_not_run_count": 0,
        "Apr04_results_opened": False,
        "scientific_paths_frozen": ["dayahead/v29r2", "dayahead/v28r2/variable_registry.py"],
        "postfreeze_rule": "No scientific changes; an implementation bug invalidates this freeze and requires affected evidence rerun plus a new freeze.",
    }
    if prior_freeze is not None:
        payload["supersedes_invalidated_freeze_head"] = prior_freeze["V29R2_DEV_FREEZE_HEAD"]
        payload["invalidation_reason"] = args.invalidation_reason
    write_json(out / "V29R2_DEV_FREEZE.json", payload)
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
