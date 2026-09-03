"""WSL entry point for V37 May source materialization."""

from __future__ import annotations

import argparse
from pathlib import Path

from dayahead.v37.sources import materialize_sources
from dayahead.v37.status import atomic_json


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-repo", type=Path, required=True)
    parser.add_argument("--dates", nargs="+", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = materialize_sources(args.source_repo.resolve(), args.dates)
    atomic_json(args.output, report)
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
