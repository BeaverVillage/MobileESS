#!/usr/bin/env python3
"""Build the pre-April REFERENCE_COMPUTE_SCHEDULE_V4 authority."""

from __future__ import annotations

import json
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from dayahead.v29r2.reference_v4 import build_reference_v4_authority  # noqa: E402


if __name__ == "__main__":
    result = build_reference_v4_authority(REPO)
    print(json.dumps({"status": result["status"], "prefreeze_structural_day_count": result["prefreeze_structural_day_count"]}, sort_keys=True))
