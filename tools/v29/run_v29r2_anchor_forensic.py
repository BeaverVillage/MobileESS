#!/usr/bin/env python3
"""Run V29R2 Stage A anchor-physics forensic."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from dayahead.v29r2.anchor_forensic import run  # noqa: E402


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    print(json.dumps(run(REPO, workers=args.workers), indent=2, sort_keys=True))
