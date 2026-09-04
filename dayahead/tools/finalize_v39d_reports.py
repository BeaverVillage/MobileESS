"""Finalize reporting for a completed V39D preflight without solver calls."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from dayahead.v39d.finalize import finalize


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    args = parser.parse_args()
    result = finalize(args.repo)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
