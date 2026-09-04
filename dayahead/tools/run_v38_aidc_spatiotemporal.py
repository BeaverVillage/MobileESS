"""V38 recovery/preflight entry point.

Production campaign execution is intentionally unavailable until the exact
31/31 gate is satisfied.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from dayahead.v38.home import materialize_home_mapping
from dayahead.v38.preflight import write_fail_closed_preflight


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--solve-home", action="store_true")
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--campaign", action="store_true")
    args = parser.parse_args()
    repo = Path.cwd()
    if args.solve_home:
        materialize_home_mapping(repo, force=True)
        return 0
    if args.preflight:
        payload = write_fail_closed_preflight(repo)
        print(f"V38_READY={payload['V38_READY']}")
        print(f"MAY_STARTED={payload['MAY_STARTED']}")
        print(f"BLOCKER={payload['blocker']}")
        return 2
    if args.campaign:
        raise RuntimeError("V38_CAMPAIGN_REFUSED_WITHOUT_31_OF_31_FROZEN_READINESS")
    parser.error("choose --solve-home, --preflight, or --campaign")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
