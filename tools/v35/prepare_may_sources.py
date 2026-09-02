#!/usr/bin/env python3
"""Materialize May inputs after the signed V35 admission gate opens."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from dayahead.v35.may_sources import materialize_may_sources  # noqa: E402
from dayahead.v35.storage import atomic_json  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-repo", type=Path, required=True)
    parser.add_argument("--admission", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    admission = json.loads(args.admission.read_text(encoding="utf-8"))
    report = materialize_may_sources(args.source_repo, admission)
    atomic_json(args.output, report)
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
