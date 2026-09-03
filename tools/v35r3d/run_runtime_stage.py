from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from dayahead.v35r3d.contracts import (
    B2_SPLIT_TIMES,
    CACHE_DIRNAME,
    CALIBRATION_SPLIT_TIMES,
    FULL_PREISSUE_SPLIT_TIMES,
)
from dayahead.v35r3d.data import load_historical_rows, prepare_historical_table
from dayahead.v35r3d.runtime import metric_summary, run_windows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=("b1", "tail32", "full120"))
    args = parser.parse_args()
    cache_dir = REPO / "dayahead" / "cache" / CACHE_DIRNAME
    table_path, preparation = prepare_historical_table(cache_dir)
    started = time.perf_counter()
    rows = load_historical_rows(table_path)
    loaded_seconds = time.perf_counter() - started
    if args.stage == "b1":
        times = B2_SPLIT_TIMES[:1]
    elif args.stage == "tail32":
        times = B2_SPLIT_TIMES + CALIBRATION_SPLIT_TIMES
    else:
        times = FULL_PREISSUE_SPLIT_TIMES
    run_started = time.perf_counter()
    frame, entries, equivalence = run_windows(
        rows,
        times,
        cache_dir,
        label=args.stage,
    )
    payload = {
        "stage": args.stage,
        "preparation": preparation,
        "historical_rows": len(rows),
        "load_seconds": loaded_seconds,
        "run_seconds": time.perf_counter() - run_started,
        "total_seconds": time.perf_counter() - started,
        "split_times": [value.isoformat() for value in times],
        "window_entries": entries,
        "metrics": metric_summary(frame),
        "query_adapter_equivalence": equivalence,
    }
    result_path = cache_dir / f"stage_{args.stage}.json"
    result_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
