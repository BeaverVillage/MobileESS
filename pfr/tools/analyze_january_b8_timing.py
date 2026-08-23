"""Paired January analysis of B7 event timing against B8 periodic five-minute timing."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Mapping, Sequence

from pfr.tools.analyze_january_daily import (
    METRICS,
    bootstrap_mean_ci,
    load_method_rows,
)


B8_TIMING_METRICS = METRICS + ("runtime_seconds",)


def _parse_episode(values: Sequence[str]) -> Mapping[str, Path]:
    result: dict[str, Path] = {}
    for value in values:
        calendar_date, separator, raw_path = value.partition("=")
        if not separator or not calendar_date or not raw_path:
            raise ValueError("episode must be YYYY-MM-DD=artifact_root")
        if calendar_date in result:
            raise ValueError(f"duplicate episode date: {calendar_date}")
        result[calendar_date] = Path(raw_path)
    return result


def analyze(main: Mapping[str, Path], b8: Mapping[str, Path]) -> Mapping[str, object]:
    expected_dates = {f"2025-01-{day:02d}" for day in range(1, 32)}
    if set(main) != expected_dates or set(b8) != expected_dates:
        raise RuntimeError("B7-B8 timing analysis requires all 31 January 2025 dates")
    daily = {}
    paired_exogenous_sha256 = {}
    for calendar_date in sorted(main):
        b7_rows = load_method_rows(main[calendar_date], "B7")
        b8_rows = load_method_rows(b8[calendar_date], "B8")
        b7_hashes = [str(row.get("causal_exogenous_sha256", "")) for row in b7_rows]
        b8_hashes = [str(row.get("causal_exogenous_sha256", "")) for row in b8_rows]
        if any(not value for value in b7_hashes + b8_hashes):
            raise RuntimeError(f"{calendar_date} lacks causal exogenous authority")
        if b7_hashes != b8_hashes:
            raise RuntimeError(f"{calendar_date} B7-B8 exogenous inputs are not paired")
        paired_exogenous_sha256[calendar_date] = hashlib.sha256(
            json.dumps(b7_hashes, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        daily[calendar_date] = {
            "B7": _summarize_rows(b7_rows),
            "B8": _summarize_rows(b8_rows),
        }
    contrast = {}
    for metric in B8_TIMING_METRICS:
        differences = [
            daily[calendar_date]["B7"][metric]
            - daily[calendar_date]["B8"][metric]
            for calendar_date in sorted(daily)
        ]
        contrast[metric] = bootstrap_mean_ci(differences)
    return {
        "schema_version": "JANUARY_2025_B7_EVENT_VS_B8_PERIODIC_5MIN_V1",
        "status": "PASS",
        "evaluation_classification": "POST_HOC_SUPPLEMENTARY_TIMING_BASELINE",
        "independent_holdout_claim": False,
        "calendar_day_count": 31,
        "contrast_direction": "B7_EVENT_CALIBRATED_MINUS_B8_PERIODIC_5MIN",
        "paired_exogenous_identity": "PASS",
        "paired_exogenous_sha256": paired_exogenous_sha256,
        "daily_metrics": daily,
        "paired_contrast": contrast,
    }


def _summarize_rows(rows: Sequence[Mapping[str, object]]) -> Mapping[str, float]:
    return {
        "realized_grid_cost_aud": sum(float(row["realized_grid_cost_aud"]) for row in rows),
        "deadline_misses": float(rows[-1]["deadline_misses"]),
        "compute_debt_gpu_hours": float(rows[-1]["compute_debt_gpu_hours"]),
        "energy_debt_kwh": float(rows[-1]["energy_debt_kwh"]),
        "full_replan_count": float(rows[-1]["full_replan_count_cumulative"]),
        "communication_bytes": float(rows[-1]["communication_bytes_cumulative"]),
        "safety_filter_interventions": float(
            sum(bool(row["safety_filter_intervention"]) for row in rows)
        ),
        "mobility_energy_kwh": sum(float(row["mobility_energy_kwh"]) for row in rows),
        "runtime_seconds": sum(float(row["runtime_seconds"]) for row in rows),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--main-episode",
        action="append",
        required=True,
        help="YYYY-MM-DD=existing_B0_B7_day_root",
    )
    parser.add_argument(
        "--b8-episode",
        action="append",
        required=True,
        help="YYYY-MM-DD=B8_supplementary_day_root",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = analyze(
        _parse_episode(args.main_episode),
        _parse_episode(args.b8_episode),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"status": "PASS", "days": 31, "output": str(args.output)}))


if __name__ == "__main__":
    main()
