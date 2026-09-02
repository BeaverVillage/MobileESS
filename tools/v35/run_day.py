#!/usr/bin/env python3
"""Execute one V35 phase/day in a fresh process."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from dayahead.v35.contracts import PHASES  # noqa: E402
from dayahead.v35.execution import DEFAULT_SOURCE_REPO, execute_day, load_static_correction  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=PHASES, required=True)
    parser.add_argument("--day", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--science-sha", required=True)
    parser.add_argument("--correction")
    parser.add_argument("--admission")
    parser.add_argument("--source-repo", default=str(DEFAULT_SOURCE_REPO))
    args = parser.parse_args()
    admission = None if args.admission is None else json.loads(Path(args.admission).read_text(encoding="utf-8"))
    artifact_root = REPO / "dayahead/artifacts/v35_april_may_final"
    cache_root = REPO / "dayahead/cache/v35"
    result = execute_day(
        repo=REPO, source_repo=Path(args.source_repo), artifact_root=artifact_root,
        cache_root=cache_root, phase=args.phase, day=args.day, run_id=args.run_id,
        science_sha=args.science_sha,
        correction=load_static_correction(None if args.correction is None else Path(args.correction)),
        admission=admission,
    )
    print(json.dumps({"day": args.day, "phase": args.phase, "status": result["status"]}, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
