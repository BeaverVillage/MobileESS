#!/usr/bin/env python3
"""Finalize the fail-closed V29R1 source-recovery resume artifacts."""

from __future__ import annotations

import json
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from dayahead.v29r1.resume_finalize import finalize  # noqa: E402


if __name__ == "__main__":
    print(json.dumps(finalize(REPO), sort_keys=True))
