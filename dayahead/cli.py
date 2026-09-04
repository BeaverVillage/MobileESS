"""Command-line entry points for pre-code gates."""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from .aidc_preflight import main as preflight_main
from .authority import AUTHORITY_IDS, FROZEN_DIGESTS, authority_fingerprint
from .authority import AIDC_SCIENTIFIC_STATUS, CURRENT_FROZEN_DIMENSIONS
from .science_firewall import CURRENT_AIDC_GATE


def _git(repo: Path, *arguments: str) -> str:
    return subprocess.check_output(("git", "-C", str(repo), *arguments), text=True).strip()


def _atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def authority_snapshot(repo: Path, output: Path) -> None:
    payload = {
        "scientific_status": f"AIDC_SCIENTIFIC_AUTHORITY_{AIDC_SCIENTIFIC_STATUS}",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "repository": "BeaverVillage/MobileESS",
        "branch": _git(repo, "branch", "--show-current"),
        "parent_sha": _git(repo, "rev-parse", "HEAD"),
        "head_sha_at_snapshot": _git(repo, "rev-parse", "HEAD"),
        "working_tree_porcelain": _git(repo, "status", "--porcelain=v1"),
        "authority_ids": dict(AUTHORITY_IDS),
        "authority_fingerprint": authority_fingerprint(),
        "frozen_digest_authorities": [item.__dict__ for item in FROZEN_DIGESTS],
        "historical_results_relabelled": False,
        "aidc_dimension_authority": CURRENT_FROZEN_DIMENSIONS.to_dict(),
        "aidc_gate": CURRENT_AIDC_GATE.status(),
    }
    _atomic_json(output, payload)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    snapshot = subparsers.add_parser("authority-snapshot")
    snapshot.add_argument("--repo", type=Path, default=Path.cwd())
    snapshot.add_argument("--output", type=Path, required=True)
    preflight = subparsers.add_parser("preflight")
    preflight.add_argument("args", nargs=argparse.REMAINDER)
    subparsers.add_parser("aidc-status")
    args = parser.parse_args(argv)
    if args.command == "authority-snapshot":
        authority_snapshot(args.repo.resolve(), args.output)
        return 0
    if args.command == "aidc-status":
        status = CURRENT_AIDC_GATE.status()
        print(json.dumps(status, indent=2, sort_keys=True))
        return 0 if status["status"] == "PASS" else 2
    return preflight_main(args.args)


if __name__ == "__main__":
    raise SystemExit(main())
