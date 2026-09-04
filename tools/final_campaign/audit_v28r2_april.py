#!/usr/bin/env python3
"""Verify all 30 V28R2 April day certificates and freeze the aggregate result."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from dayahead.v28r2.backend_contract import sha256_file  # noqa: E402
from dayahead.v28r2.certificate import verify_certificate, write_certificate  # noqa: E402


ROOT_SUFFIX = "v28r2_april_full_month_preflight"
APRIL_DAYS = tuple(f"2025-04-{day:02d}" for day in range(1, 31))
REQUIRED_REFERENCES = {
    "code_tree_manifest", "config", "source_day_manifest", "selected_model_manifest",
    "thermal_model", "scale_authority", "formulation", "dayahead_schedule_manifest",
    "b3_equivalence", "pi_output", "pi_opendss", "runtime_ledger", "final_audit",
    "log_snapshot", "schedule_B0", "schedule_B1", "schedule_B2", "schedule_B3",
    "da_opendss_B0", "da_opendss_B1", "da_opendss_B2", "da_opendss_B3",
    "actual_replay_R0", "actual_replay_B0", "actual_replay_B1", "actual_replay_B2",
    "actual_replay_B3", "actual_opendss_R0", "actual_opendss_B0", "actual_opendss_B1",
    "actual_opendss_B2", "actual_opendss_B3",
}


def campaign_root(repo: Path = REPO) -> Path:
    return repo / "frozen_artifacts" / ROOT_SUFFIX


def certificate_path(root: Path, day: str) -> Path:
    return root / day / f"APRIL_DAY_CERTIFICATE_{day.replace('-', '_')}.json"


def audit(repo: Path = REPO) -> dict[str, object]:
    root = campaign_root(repo)
    valid: list[dict[str, object]] = []
    invalid: list[dict[str, str]] = []
    git_revisions: set[str] = set()
    for day in APRIL_DAYS:
        path = certificate_path(root, day)
        try:
            payload = verify_certificate(path)
            references = payload.get("references")
            if (
                payload.get("artifact_id") != "V28R2_APRIL_DAY_CERTIFICATE_V1"
                or payload.get("status") != "PASS"
                or payload.get("day") != day
                or payload.get("non_authority_smoke") is not False
                or payload.get("actual_optimizer_calls") != 0
                or float(payload.get("hidden_shedding_nodeh", 1.0)) != 0.0
                or float(payload.get("workload_mass_error_nodeh", 1.0)) > 1e-9
                or not isinstance(references, dict)
                or not REQUIRED_REFERENCES.issubset(references)
                or set(payload.get("OpenDSS_real_solved_slots", {}).values()) != {96}
            ):
                raise RuntimeError("V28R2_APRIL_DAY_CERTIFICATE_CONTENT")
            git_revisions.add(str(payload["git_head"]))
            valid.append({
                "day": day,
                "path": str(path.resolve()),
                "sha256": sha256_file(path),
                "certificate_sha256": payload["certificate_sha256"],
                "git_head": payload["git_head"],
            })
        except Exception as error:
            invalid.append({"day": day, "error": f"{type(error).__name__}:{error}"})
    passed = len(valid) == 30 and not invalid
    return {
        "artifact_id": "V28R2_APRIL_FULL_MONTH_AUDIT_V1",
        "status": "PASS" if passed else "INCOMPLETE",
        "APRIL_FULL_MONTH_PREFLIGHT_PASS": passed,
        "expected_day_count": 30,
        "valid_day_count": len(valid),
        "invalid_or_missing": invalid,
        "valid_day_certificates": valid,
        "distinct_git_revisions": sorted(git_revisions),
        "immutable_mixed_revision_preflight_allowed": True,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    result = audit()
    if result["APRIL_FULL_MONTH_PREFLIGHT_PASS"]:
        output = campaign_root() / "APRIL_FULL_MONTH_PREFLIGHT_PASS.json"
        write_certificate(output, result)
        verify_certificate(output)
        result = {**result, "aggregate_certificate": str(output.resolve()), "aggregate_sha256": sha256_file(output)}
    print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
    return 0 if result["APRIL_FULL_MONTH_PREFLIGHT_PASS"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
