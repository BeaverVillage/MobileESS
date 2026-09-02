#!/usr/bin/env python3
"""Run the V29R1 Jan--Mar causal source-authority recovery audit."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from dayahead.v29r1.source_authority_recovery import run  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--authority", type=Path, required=True)
    parser.add_argument("--campaign", type=Path, required=True)
    parser.add_argument("--post-forensic", type=Path, required=True)
    parser.add_argument("--preapril-census", type=Path, required=True)
    args = parser.parse_args()
    run(
        REPO, args.authority.resolve(), args.campaign.resolve(),
        args.post_forensic.resolve(), args.preapril_census.resolve(),
    )


if __name__ == "__main__":
    main()
