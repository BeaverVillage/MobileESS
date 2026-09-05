"""Execute one V39E May day from byte-frozen DA decisions."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dayahead.v39e.campaign_adapter import run_day_with_unavailable_da


def _install_windows_safe_k_archive() -> None:
    """Keep K-fallback evidence below Win32's legacy 260-character limit."""

    import dayahead.v37.runner as runner

    if getattr(runner, "_v39e_windows_safe_k_archive", False):
        return
    original_archived = runner._archived_k_attempt
    short_names = {
        "RESTRICTED_VALUES.csv": "RV",
        "SEEDS.json": "S",
        "LOCAL_SEARCH.json": "LS",
    }

    def archive(search_root: Path, level: str) -> None:
        for name, short in short_names.items():
            source = search_root / name
            if not source.is_file():
                continue
            suffix = Path(name).suffix
            index = 1
            while True:
                target = search_root / f"{short}.K{level}.A{index}{suffix}"
                if not target.exists():
                    source.replace(target)
                    break
                index += 1

    def archived(search_root: Path, label: str) -> dict[str, Any] | None:
        candidates = list(search_root.glob(f"RV.K{label}.A*.csv"))
        if not candidates:
            return original_archived(search_root, label)
        path = max(candidates, key=lambda item: (item.stat().st_mtime_ns, item.name))
        values = pd.read_csv(path)
        failure_rows = runner._uncertified_rows(values)
        if not failure_rows:
            return None
        return {
            "K": label,
            "status": "CERTIFICATION_FAILURE_RESTORED",
            "restricted_candidates": int(len(values)),
            "uncertified_candidate_count": len(failure_rows),
            "uncertified_candidate_ids": [
                str(row["candidate_id"]) for row in failure_rows
            ],
            "signatures": [
                str(row["exact_optimality_certificate"]) for row in failure_rows
            ],
            "restored_from": str(path),
            "restricted_solver_calls": 0,
            "restricted_cache_hits": int(len(values)),
            "restricted_cache_misses": 0,
            "restricted_duplicate_solves": 0,
        }

    runner._archive_local_attempt = archive
    runner._archived_k_attempt = archived
    runner._v39e_windows_safe_k_archive = True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--day", required=True)
    parser.add_argument("--repo", type=Path, default=ROOT)
    parser.add_argument("--check-launch-gate", action="store_true")
    args = parser.parse_args()
    from dayahead.tools.v39h_terminal_launch_gate import admission, wait_for_admission
    if args.check_launch_gate:
        print(admission(args.repo.resolve(), args.day), flush=True)
        return 0
    wait_for_admission(args.repo.resolve(), args.day)
    _install_windows_safe_k_archive()
    if (args.repo / "dayahead/artifacts/v39h_production_refreeze_may_close/PRODUCTION_REFREEZE_AUTHORITY.json").is_file():
        from dayahead.v39e.runtime import install_runtime
        print(f"V39H_RUNTIME_AUTHORITY {install_runtime()}", flush=True)
    result = run_day_with_unavailable_da(args.repo.resolve(), args.day)
    print(f"V39E MAY DATE {args.day} {result['status']}", flush=True)
    return 0 if result.get("status") != "FAIL" else 1


if __name__ == "__main__":
    raise SystemExit(main())
