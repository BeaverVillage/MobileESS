"""Read-only input/preflight checks; never launches Actual or day-ahead optimization."""
import argparse
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from dayahead.v40d_actual.preflight import run


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--job-check-only", action="store_true")
    p.add_argument("--output", type=Path)
    a = p.parse_args()
    repo = Path(__file__).resolve().parents[2]
    output = a.output or repo / "dayahead/artifacts/v40d_actual_realized_replay/implementation_preflight"
    result = run(repo, output, raw=not a.job_check_only)
    print(result)
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
