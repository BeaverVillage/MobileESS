from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from dayahead.v35r3b.pipeline import finalize_tests


def main() -> int:
    parser = argparse.ArgumentParser(description="Finalize the V35R3B test evidence")
    parser.add_argument("--passed", type=int, required=True)
    parser.add_argument("--failed", type=int, required=True)
    parser.add_argument("--command", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    report = finalize_tests(
        REPO,
        passed=args.passed,
        failed=args.failed,
        command=args.command,
        output=args.output,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if args.failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
