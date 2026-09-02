"""Run or finalize the V31 diagnostic-only forensic."""

from __future__ import annotations

import argparse
from pathlib import Path

from dayahead.v31.forensic import finalize, run


DEFAULT_SOURCE = Path(r"C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\MobileESS_v28r2_heavy_backend")
DEFAULT_CACHE = DEFAULT_SOURCE / "frozen_artifacts/v28r2_april_full_month_preflight/2025-04-04/dayahead/electrical_cache"
DEFAULT_TRUST = Path(r"C:\codex_mobileess_workspace\MobileESS_v29r1\cache\v29r1_trust_cert_sources\jan_mar_2025")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--source-repo", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--electrical-cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--trust-cache", type=Path, default=DEFAULT_TRUST)
    parser.add_argument("--finalize", action="store_true")
    parser.add_argument("--passed", type=int, default=0)
    parser.add_argument("--failed", type=int, default=0)
    parser.add_argument("--not-run", type=int, default=0)
    parser.add_argument("--test-command", default="")
    args = parser.parse_args()
    if args.finalize:
        result = finalize(args.repo, passed=args.passed, failed=args.failed, not_run=args.not_run, command=args.test_command)
        print(result["manifest"]["aggregate_manifest_sha256"])
    else:
        result = run(args.repo, args.source_repo, args.electrical_cache, args.trust_cache)
        print(result["review"]["RESULT_CLASSIFICATION"])


if __name__ == "__main__":
    main()
