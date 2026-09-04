"""Materialize the post-preflight V39D Rack semantics guardrail audit."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from dayahead.v39d.semantic_audit import materialize_semantic_guardrail


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    args = parser.parse_args()
    result = materialize_semantic_guardrail(args.repo)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
