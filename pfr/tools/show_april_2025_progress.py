"""Show execution-only progress for the standalone April 2025 campaign."""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path
import time

from pfr.tools.show_january_to_march_progress import (
    B8_METHODS,
    MAIN_METHODS,
    Period,
    snapshot,
)


def main() -> None:
    base = Path("/home/jaewon/mobile_ess_work/frozen_artifacts")
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--april-root",
        type=Path,
        default=base / "CODEX_PR6_V13_13_APR2025_FULL_DAILY_20260824",
    )
    parser.add_argument(
        "--april-b8-root",
        type=Path,
        default=base / "CODEX_PR6_V13_13_APR2025_FULL_B8_PERIODIC5_20260824",
    )
    parser.add_argument("--watch-seconds", type=float, default=10.0)
    args = parser.parse_args()
    periods = [
        Period(
            "APRIL B0-B7",
            args.april_root,
            date(2025, 4, 1),
            30,
            MAIN_METHODS,
        ),
        Period(
            "APRIL B08",
            args.april_b8_root,
            date(2025, 4, 1),
            30,
            B8_METHODS,
        ),
    ]
    while True:
        print(snapshot(periods), flush=True)
        if args.watch_seconds <= 0:
            break
        time.sleep(args.watch_seconds)
        print("", flush=True)


if __name__ == "__main__":
    main()
