#!/usr/bin/env python3
"""Freeze the V29R2 B2-anchored MESS no-regret ladder."""

from __future__ import annotations

import json
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from dayahead.v29r2.mess_noregret import freeze_noregret_contract  # noqa: E402


if __name__ == "__main__":
    value = freeze_noregret_contract(REPO)
    print(json.dumps({"status": value["status"], "rung_order": value["rung_order"]}, sort_keys=True))
