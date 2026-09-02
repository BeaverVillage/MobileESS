#!/usr/bin/env python3
"""Freeze V29R2 trust contract before any candidate execution."""

from __future__ import annotations

import json
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from dayahead.v29r2.trust_contract import freeze  # noqa: E402


if __name__ == "__main__":
    print(json.dumps(freeze(REPO), indent=2, sort_keys=True))
