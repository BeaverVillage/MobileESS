#!/usr/bin/env python3
"""Build the V29R2 causal executable-service authority."""

from __future__ import annotations

import json
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from dayahead.v29r2.service_model import build_service_authority  # noqa: E402


if __name__ == "__main__":
    authority = build_service_authority(REPO)
    print(json.dumps({"status": authority["status"], "metrics": authority["metrics"]}, sort_keys=True))
