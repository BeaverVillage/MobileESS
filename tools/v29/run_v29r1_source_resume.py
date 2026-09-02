#!/usr/bin/env python3
"""Validate downloaded Jan--Mar sources and materialize the V29R1 cache."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from dayahead.v29r1.source_resume import run_source_resume  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--campaign", type=Path, required=True)
    parser.add_argument("--validation-workers", type=int, default=12)
    parser.add_argument("--materialization-workers", type=int, default=1)
    args = parser.parse_args()
    result = run_source_resume(
        REPO,
        args.campaign.resolve(),
        validation_workers=args.validation_workers,
        materialization_workers=args.materialization_workers,
    )
    print(json.dumps({
        "RAW_SOURCE_READY": result["raw"]["RAW_SOURCE_READY"],
        "materialized_days": result["materialization"]["materialized_day_count"],
        "deterministic": result["materialization"]["deterministic_rematerialization"],
        "contract_equivalence": result["equivalence"]["JANMAR_APRIL_CONTRACT_EQUIVALENCE"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
