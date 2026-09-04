#!/usr/bin/env python3
"""Run the V29R1 pre-April AIDC physics certificate."""

from __future__ import annotations

import json
import argparse
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from dayahead.v29r1.trust_certification import certify  # noqa: E402


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    decision = certify(REPO, workers=args.workers)
    print(json.dumps({"status": decision["status"], "selected_rho_AIDC": decision["selected_rho_AIDC"]}, sort_keys=True))
