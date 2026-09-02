"""Build or finalize the V32 evidence package."""

from __future__ import annotations

import argparse
from pathlib import Path

from dayahead.v32.forensic import finalize, run


DEFAULT_TRUST = Path(r"C:\codex_mobileess_workspace\MobileESS_v29r1\cache\v29r1_trust_cert_sources\jan_mar_2025")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path.cwd())
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
        print(run(args.repo, args.trust_cache)["RESULT_CLASSIFICATION"])


if __name__ == "__main__":
    main()
