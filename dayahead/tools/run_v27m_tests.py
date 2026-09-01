"""Run pytest-compatible V27M test functions without an optional pytest install."""

from __future__ import annotations

import inspect

from dayahead.ml.safe_flex_r1.tests import test_v27m_safe_flex_r1 as suite


def main() -> None:
    tests = [(name, function) for name, function in inspect.getmembers(suite, inspect.isfunction) if name.startswith("test_")]
    failures = []
    for name, function in tests:
        try:
            function()
            print(f"PASS {name}")
        except Exception as error:  # pragma: no cover - runner reporting path
            failures.append((name, repr(error)))
            print(f"FAIL {name}: {error!r}")
    print(f"SUMMARY passed={len(tests) - len(failures)} failed={len(failures)} total={len(tests)}")
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
