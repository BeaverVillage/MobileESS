"""Audit aligned H0 surrogate/Fresh-AC candidate scores."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from pfr.h0_fidelity import H0CandidateScore, audit_h0_candidate_fidelity


def _load(path: Path) -> list[dict[str, Any]]:
    if path.suffix.lower() == ".jsonl":
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        payload = payload.get("rows")
    if not isinstance(payload, list):
        raise ValueError("input must be a JSON list, {rows: [...]}, or JSONL")
    return payload


def _load_campaign(root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for marker_path in sorted(root.glob("**/issue_*/COMMIT_MARKER.json")):
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
        audit = marker.get("h0_surrogate_fidelity_audit")
        if not isinstance(audit, dict):
            continue
        for row in audit.get("candidate_rows", ()): 
            rows.append(
                {
                    "state_id": str(row["state_id"]),
                    "candidate_id": str(row["candidate_id"]),
                    "surrogate_h0_stress": float(
                        row["surrogate_h0_stress"]
                    ),
                    "fresh_ac_h0_stress": float(row["fresh_ac_h0_stress"]),
                    "is_reference": bool(row.get("is_reference", False)),
                }
            )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--input", type=Path)
    source.add_argument("--campaign-root", type=Path)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--phase", choices=("january", "february"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    contract = json.loads(args.contract.read_text(encoding="utf-8"))
    thresholds = contract["phases"][args.phase]
    raw_rows = (
        _load_campaign(args.campaign_root)
        if args.campaign_root is not None
        else _load(args.input)
    )
    rows = [H0CandidateScore(**row) for row in raw_rows]
    result = dict(
        audit_h0_candidate_fidelity(
            rows,
            tie_tolerance=float(contract["tie_tolerance"]),
            minimum_states=int(thresholds["minimum_states"]),
            minimum_sign_agreement=float(thresholds["minimum_sign_agreement"]),
            minimum_pairwise_concordance=float(
                thresholds["minimum_pairwise_concordance"]
            ),
        )
    )
    result["phase"] = args.phase.upper()
    result["contract"] = contract["schema_version"]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
