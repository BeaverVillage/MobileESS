#!/usr/bin/env python3
"""Build PRE_DAY_QUEUE_BRIDGE_V2."""

from __future__ import annotations

import json
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from dayahead.v29r2.bridge_v2 import build_bridge_v2  # noqa: E402


if __name__ == "__main__":
    result = build_bridge_v2(REPO)
    print(json.dumps({"status": result["status"], "calibration": result["calibration"]}, sort_keys=True))
