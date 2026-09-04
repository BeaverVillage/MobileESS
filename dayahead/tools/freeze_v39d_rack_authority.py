"""Freeze or seal the V39D logical-Rack compatibility authority."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from dayahead.v39d.rack_freeze import freeze, seal


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("freeze", "seal"))
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    args = parser.parse_args()
    result = freeze(args.repo) if args.mode == "freeze" else seal(args.repo)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
