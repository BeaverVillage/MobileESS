"""CLI for the V39E unattended full-preflight and May campaign."""

from __future__ import annotations

import argparse
import json
from multiprocessing import freeze_support
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dayahead.v39e.overnight import run


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=ROOT)
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--diagnostic-override-authorized", action="store_true")
    args = parser.parse_args()
    result = run(
        args.repo,
        preflight_only=args.preflight_only,
        diagnostic_override_authorized=args.diagnostic_override_authorized,
    )
    print(json.dumps(result, indent=2, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    freeze_support()
    raise SystemExit(main())
