#!/usr/bin/env python3
"""Run the complete self-healing V35 chronology."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from dayahead.v35.campaign import run_all  # noqa: E402
from dayahead.v35.execution import DEFAULT_SOURCE_REPO  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-repo", default=str(DEFAULT_SOURCE_REPO))
    args = parser.parse_args()
    result = run_all(REPO, Path(args.source_repo))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
