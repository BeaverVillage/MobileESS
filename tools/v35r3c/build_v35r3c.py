from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from dayahead.v35r3c.pipeline import build


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the local-only V35R3C forensic")
    parser.add_argument("--repo", type=Path, default=REPO)
    args = parser.parse_args()
    print(json.dumps(build(args.repo), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
