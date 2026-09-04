"""CLI for the V29R3 read-only Apr-04 forensic."""

from __future__ import annotations

import argparse
from pathlib import Path

from dayahead.v29r3.forensic import run


DEFAULT_SOURCE_REPO = Path(r"C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\MobileESS_v28r2_heavy_backend")
DEFAULT_ELECTRICAL_CACHE = DEFAULT_SOURCE_REPO / "frozen_artifacts/v28r2_april_full_month_preflight/2025-04-04/dayahead/electrical_cache"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--source-repo", type=Path, default=DEFAULT_SOURCE_REPO)
    parser.add_argument("--electrical-cache", type=Path, default=DEFAULT_ELECTRICAL_CACHE)
    args = parser.parse_args()
    result = run(args.repo, args.source_repo, args.electrical_cache)
    print(result["root"]["RESULT_CLASSIFICATION"])
    print(result["manifest"]["aggregate_manifest_sha256"])


if __name__ == "__main__":
    main()
