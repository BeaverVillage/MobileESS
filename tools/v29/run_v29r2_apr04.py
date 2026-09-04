#!/usr/bin/env python3
"""Run the frozen V29R2 Apr-04 development checkpoint."""

from __future__ import annotations

import json
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from dayahead.v29r2.apr04_runner import run_apr04  # noqa: E402


if __name__ == "__main__":
    print(json.dumps(run_apr04(REPO), indent=2, sort_keys=True))
