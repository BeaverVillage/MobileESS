#!/usr/bin/env python3
"""Run the prospective V29R1 authority and fail-closed trust gate."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from dayahead.v29r1.runner import run  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--authority", type=Path, required=True)
    parser.add_argument("--campaign", type=Path, required=True)
    parser.add_argument("--post-forensic", type=Path, required=True)
    parser.add_argument("--preapril-census", type=Path, required=True)
    parser.add_argument("--v28-forensic", type=Path, required=True)
    args = parser.parse_args()
    run(
        REPO, args.authority.resolve(), args.campaign.resolve(),
        args.post_forensic.resolve(), args.preapril_census.resolve(),
        args.v28_forensic.resolve(),
    )


if __name__ == "__main__":
    main()
