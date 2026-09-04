"""Run the single authorized V30 Apr-04 development smoke."""

from __future__ import annotations

import argparse
from pathlib import Path

from dayahead.v30.four_case_runner import run


DEFAULT_SOURCE = Path(r"C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\MobileESS_v28r2_heavy_backend")
DEFAULT_CACHE = DEFAULT_SOURCE / "frozen_artifacts/v28r2_april_full_month_preflight/2025-04-04/dayahead/electrical_cache"
DEFAULT_TRUST = Path(r"C:\codex_mobileess_workspace\MobileESS_v29r1\cache\v29r1_trust_cert_sources\jan_mar_2025")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--source-repo", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--electrical-cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--trust-cache", type=Path, default=DEFAULT_TRUST)
    args = parser.parse_args()
    result = run(args.repo, args.source_repo, args.electrical_cache, args.trust_cache)
    print(result["review"]["RESULT_CLASSIFICATION"])


if __name__ == "__main__":
    main()
