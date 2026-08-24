"""Assemble all 16 January source blocks with the frozen power/price generator."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys


BLOCK = 576
GROUP_BLOCKS = 4
GROUP_STEPS = BLOCK * GROUP_BLOCKS
GROUP_COUNT = 4
SCORED_ISSUES = 31 * 288
SOURCE_ISSUES = GROUP_COUNT * GROUP_STEPS


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _authority_files(root: Path) -> list[dict[str, str]]:
    rows = []
    for path in sorted(root.rglob("*.json")):
        upper = path.name.upper()
        if "AUTHORITY" in upper or "MANIFEST" in upper or "CERTIFICATE" in upper:
            rows.append({"path": str(path), "sha256": sha256(path)})
    if not rows:
        raise RuntimeError(f"no authority JSON found under {root}")
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--mobility-root", type=Path, action="append", required=True)
    parser.add_argument("--q2-root", type=Path, required=True)
    args = parser.parse_args()
    if len(args.mobility_root) != 4:
        raise RuntimeError("January authority requires exactly four mobility chunks")
    root = args.output_root.resolve()
    power_root = root / "power_price"
    power_root.mkdir(parents=True, exist_ok=True)
    generator = (
        args.repo.resolve()
        / "performance/post_stage15_runtime_acceleration/package/scripts/PREPARE_W02_POWER_PRICE_SOURCE.py"
    )
    blocks = []
    for group in range(GROUP_COUNT):
        start = group * GROUP_STEPS
        targets = [
            power_root / f"block_{group * GROUP_BLOCKS + local:02d}_{start + local * BLOCK}_{start + (local + 1) * BLOCK - 1}"
            for local in range(GROUP_BLOCKS)
        ]
        if not all((target / "BLOCK_AUTHORITY.json").is_file() for target in targets):
            subprocess.run(
                [
                    sys.executable, str(generator), "--repo", str(args.repo.resolve()),
                    "--output-root", str(power_root), "--candidate-id", "JAN2025_INDEPENDENT_DAILY",
                    "--start-index", str(start),
                ],
                check=True,
            )
            for local, target in enumerate(targets):
                generated = power_root / f"block_{local:02d}_{start + local * BLOCK}_{start + (local + 1) * BLOCK - 1}"
                if generated != target:
                    if target.exists():
                        shutil.rmtree(target)
                    generated.rename(target)
        for target in targets:
            authority = json.loads((target / "BLOCK_AUTHORITY.json").read_text(encoding="utf-8"))
            if authority.get("status") != "PASS" or authority.get("future_actual_used") is not False:
                raise RuntimeError(f"power/price block authority failed: {target}")
            blocks.append({"path": str(target), "authority_sha256": sha256(target / "BLOCK_AUTHORITY.json")})
    power_authority = {
        "schema_version": "PFR_JAN2025_POWER_PRICE_SOURCE_V13_2",
        "status": "PASS",
        "candidate_id": "JAN2025_INDEPENDENT_DAILY",
        "scored_issue_first": 0,
        "scored_issue_last": SCORED_ISSUES - 1,
        "scored_issue_count": SCORED_ISSUES,
        "source_issue_last": SOURCE_ISSUES - 1,
        "source_issue_count": SOURCE_ISSUES,
        "source_padding_steps": SOURCE_ISSUES - SCORED_ISSUES,
        "future_actual_used": False,
        "blocks": blocks,
    }
    power_path = power_root / "JANUARY_POWER_PRICE_SOURCE_AUTHORITY.json"
    _write(power_path, power_authority)
    mobility = [entry for source in args.mobility_root for entry in _authority_files(source.resolve())]
    q2 = _authority_files(args.q2_root.resolve())
    shared = {
        "schema_version": "PFR_JAN2025_SHARED_EXOGENOUS_AUTHORITY_V13_2",
        "status": "PASS",
        "candidate_id": "JAN2025_INDEPENDENT_DAILY",
        "scored_issue_first": 0,
        "scored_issue_last": SCORED_ISSUES - 1,
        "scored_issue_count": SCORED_ISSUES,
        "source_issue_count": SOURCE_ISSUES,
        "same_source_for_all_methods": True,
        "future_actual_used_by_optimizer": False,
        "power_price_authority_sha256": sha256(power_path),
        "mobility_authorities": mobility,
        "q2_overlay_authorities": q2,
    }
    _write(root / "SHARED_EXOGENOUS_AUTHORITY.json", shared)
    print(json.dumps({"status": "PASS", "blocks": len(blocks), "output": str(root)}))


if __name__ == "__main__":
    main()
