"""Fail-closed isolation authority for January-to-April campaign outputs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
from typing import Any, Mapping


SCHEMA_VERSION = "PFR_JAN_TO_APRIL_ELECTRICAL_STRESS_ISOLATED_RUN_ROOT_V3"
MANIFEST_NAME = "JFM_ISOLATION_MANIFEST.json"
LAYOUT = {
    "january_b00_b09": "january/B00_B09",
    "february_b00_b09": "february/B00_B09",
    "march_b00_b09": "march/B00_B09",
    "april_b00_b09": "april/B00_B09",
    "january_b07_calibration_raw": "january_b07_electrical_stress_raw",
    "risk_calibration": "calibration/ELECTRICAL_STRESS_EVENT_RISK_CALIBRATION_JAN2025.json",
}


def _expected_payload(
    run_root: Path,
    expected_full_commit_sha: str,
    expected_branch: str,
) -> dict[str, Any]:
    if not re.fullmatch(r"[0-9a-f]{40}", expected_full_commit_sha):
        raise ValueError("expected full commit SHA must contain 40 lowercase hex characters")
    if not expected_branch.strip():
        raise ValueError("expected branch must be non-empty")
    resolved = run_root.expanduser().resolve()
    if not run_root.expanduser().is_absolute():
        raise ValueError("run root must be an absolute path")
    return {
        "schema_version": SCHEMA_VERSION,
        "run_root": str(resolved),
        "expected_full_commit_sha": expected_full_commit_sha,
        "expected_branch": expected_branch,
        "layout": dict(LAYOUT),
        "isolated_from_legacy_fixed_output_roots": True,
    }


def _read_manifest(path: Path) -> Mapping[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"invalid JFM isolation manifest: {path}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("JFM isolation manifest must be a JSON object")
    return payload


def initialize_isolated_run_root(
    run_root: Path,
    expected_full_commit_sha: str,
    expected_branch: str,
) -> Mapping[str, Any]:
    expected = _expected_payload(
        run_root, expected_full_commit_sha, expected_branch
    )
    resolved = Path(expected["run_root"])
    manifest = resolved / MANIFEST_NAME
    if manifest.is_file():
        observed = _read_manifest(manifest)
        if observed != expected:
            raise RuntimeError(
                "run root belongs to a different commit, branch, layout, or path"
            )
        return observed
    if resolved.exists() and any(resolved.iterdir()):
        raise RuntimeError(
            "refusing non-empty run root without a valid isolation manifest"
        )
    resolved.mkdir(parents=True, exist_ok=True)
    temporary = manifest.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(expected, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(manifest)
    return expected


def load_isolated_run_root(run_root: Path) -> Mapping[str, Any]:
    resolved = run_root.expanduser().resolve()
    manifest = resolved / MANIFEST_NAME
    payload = _read_manifest(manifest)
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise RuntimeError("unsupported JFM isolation manifest schema")
    if payload.get("run_root") != str(resolved):
        raise RuntimeError("JFM isolation manifest is bound to another run root")
    if payload.get("layout") != LAYOUT:
        raise RuntimeError("JFM isolation layout does not match the frozen layout")
    if payload.get("isolated_from_legacy_fixed_output_roots") is not True:
        raise RuntimeError("JFM isolation authority is missing")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", type=Path, required=True)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--initialize", action="store_true")
    action.add_argument("--check", action="store_true")
    parser.add_argument("--expected-full-commit-sha")
    parser.add_argument("--expected-branch")
    args = parser.parse_args()
    try:
        if args.initialize:
            if args.expected_full_commit_sha is None or args.expected_branch is None:
                parser.error(
                    "--initialize requires --expected-full-commit-sha and --expected-branch"
                )
            payload = initialize_isolated_run_root(
                args.run_root,
                args.expected_full_commit_sha,
                args.expected_branch,
            )
        else:
            payload = load_isolated_run_root(args.run_root)
    except (OSError, RuntimeError, ValueError) as exc:
        parser.exit(2, f"ABORT_ISOLATION: {exc}\n")
    print(json.dumps({"status": "PASS", **payload}, sort_keys=True))


if __name__ == "__main__":
    main()
