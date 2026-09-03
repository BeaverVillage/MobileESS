"""CLI for the isolated V35R3A artifact build and test finalization."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from dayahead.v35r3a.contracts import ACTIVE_V35R3_WORKTREE, AUTHORITY_ROOT, KESTREL_ZIP  # noqa: E402
from dayahead.v35r3a.pipeline import build, finalize_tests  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=REPO)
    parser.add_argument("--authority-root", type=Path, default=AUTHORITY_ROOT)
    parser.add_argument("--kestrel-zip", type=Path, default=KESTREL_ZIP)
    parser.add_argument("--active-worktree", type=Path, default=ACTIVE_V35R3_WORKTREE)
    parser.add_argument("--finalize-tests", action="store_true")
    parser.add_argument("--passed", type=int, default=0)
    parser.add_argument("--failed", type=int, default=0)
    parser.add_argument("--test-command", default="")
    parser.add_argument("--test-output", default="")
    args = parser.parse_args()
    if args.finalize_tests:
        result = finalize_tests(
            args.repo.resolve(),
            passed=args.passed,
            failed=args.failed,
            command=args.test_command,
            output=args.test_output,
        )
    else:
        result = build(
            args.repo.resolve(),
            authority_root=args.authority_root,
            kestrel_zip=args.kestrel_zip,
            active_worktree=args.active_worktree,
        )
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
