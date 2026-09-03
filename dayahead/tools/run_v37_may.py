"""CLI for the V37 May campaign and one-date workers."""

from __future__ import annotations

import argparse
from pathlib import Path

from dayahead.v37.campaign import run_campaign
from dayahead.v37.runner import run_day


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--campaign", action="store_true")
    parser.add_argument("--day")
    args = parser.parse_args()
    repo = Path.cwd().resolve()
    if args.campaign == bool(args.day):
        parser.error("select exactly one of --campaign or --day")
    if args.campaign:
        result = run_campaign(repo)
        print(f"V37 CAMPAIGN {result.get('classification', result.get('status'))}", flush=True)
    else:
        result = run_day(repo, str(args.day))
        print(f"V37 DATE {args.day} {result['status']}", flush=True)
    return 0 if result.get("status") != "FAIL" else 1


if __name__ == "__main__":
    raise SystemExit(main())
