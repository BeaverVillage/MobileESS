"""Execute one V39E May day from byte-frozen DA decisions."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dayahead.v39e.campaign_adapter import run_day_with_unavailable_da


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--day", required=True)
    parser.add_argument("--repo", type=Path, default=ROOT)
    args = parser.parse_args()
    result = run_day_with_unavailable_da(args.repo.resolve(), args.day)
    print(f"V39E MAY DATE {args.day} {result['status']}", flush=True)
    return 0 if result.get("status") != "FAIL" else 1


if __name__ == "__main__":
    raise SystemExit(main())
