"""Run the V39D independent-day scientific preflight (never the May campaign)."""

from __future__ import annotations

from multiprocessing import freeze_support
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dayahead.v39d.evaluate import main


if __name__ == "__main__":
    freeze_support()
    raise SystemExit(main())

