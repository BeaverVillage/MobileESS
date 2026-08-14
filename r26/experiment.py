"""Fixed experiment matrix and runtime metric aggregation for R26."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from statistics import mean, median
from typing import Any, Iterable, Mapping, Sequence, Tuple


@dataclass(frozen=True)
class ExperimentCase:
    name: str
    policy: str
    max_refresh_steps: int
    cadence_seconds: int = 300


def required_matrix() -> Tuple[ExperimentCase, ...]:
    return (
        ExperimentCase("r25r_exact_5min_reference", "OFFLINE_EXACT_REFERENCE", 1),
        ExperimentCase("fixed_route_refresh_15m", "FIXED_PERIODIC", 3),
        ExperimentCase("event_route_refresh_max15m", "EVENT_TRIGGERED", 3),
        ExperimentCase("fixed_route_refresh_30m", "FIXED_PERIODIC", 6),
        ExperimentCase("event_route_refresh_max30m", "EVENT_TRIGGERED", 6),
        ExperimentCase("fixed_route_refresh_60m", "FIXED_PERIODIC", 12),
        ExperimentCase("event_route_refresh_max60m", "EVENT_TRIGGERED", 12),
    )


def _percentile(values: Sequence[float], fraction: float) -> float:
    if not values:
        return math.nan
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def aggregate_metrics(records: Iterable[Mapping[str, Any]]) -> Mapping[str, Any]:
    rows = list(records)
    runtimes = [float(row["runtime_seconds"]) for row in rows]
    commits = sum(bool(row.get("committed")) for row in rows)
    failures = [str(row.get("status")) for row in rows if not row.get("committed")]
    result = {
        "issues": len(rows),
        "committed_issues": commits,
        "fast_runtime_mean_seconds": mean(runtimes) if runtimes else None,
        "fast_runtime_median_seconds": median(runtimes) if runtimes else None,
        "fast_runtime_p95_seconds": _percentile(runtimes, 0.95) if runtimes else None,
        "fast_runtime_p99_seconds": _percentile(runtimes, 0.99) if runtimes else None,
        "fast_runtime_max_seconds": max(runtimes) if runtimes else None,
        "all_fast_runtime_below_300_seconds": bool(runtimes) and max(runtimes) < 300.0,
        "deadline_miss_count": sum(runtime >= 300.0 for runtime in runtimes),
        "failure_statuses": failures,
        "route_replans_started": sum(row.get("planner_disposition") == "STARTED" for row in rows),
        "route_replans_coalesced": sum(row.get("planner_disposition") == "COALESCED" for row in rows),
        "route_replans_observed": sum(
            row.get("planner_disposition") == "STARTED" for row in rows
        ),
        "route_replans_equivalent_per_288_step_day": (
            288.0
            * sum(row.get("planner_disposition") == "STARTED" for row in rows)
            / len(rows)
            if rows
            else None
        ),
        "route_replan_fraction_of_5min_opportunities": (
            sum(row.get("planner_disposition") == "STARTED" for row in rows) / len(rows)
            if rows
            else None
        ),
        "fresh_opendss_failures": sum(
            row.get("status") == "FAIL_CLOSED_FRESH_OPENDSS_GATE" for row in rows
        ),
        "max_remaining_integer_vars": max(
            (int(row.get("num_integer_vars") or 0) for row in rows), default=0
        ),
        "total_travel_energy_kwh": sum(
            float(row.get("travel_energy_kwh") or 0.0) for row in rows
        ),
        "minimum_soc_reserve_margin_kwh": min(
            (float(row["soc_reserve_margin_kwh"]) for row in rows if row.get("soc_reserve_margin_kwh") is not None),
            default=None,
        ),
        "minimum_rack_support_margin": min(
            (float(row["rack_support_margin"]) for row in rows if row.get("rack_support_margin") is not None),
            default=None,
        ),
        "ac_violation_count": sum(int(row.get("ac_violation_count") or 0) for row in rows),
        "winner_declared": False,
        "winner_rule": "NO_WINNER_UNTIL_ALL_MATRIX_CASES_HAVE_COMPLETE_VALIDATED_RESULTS",
    }
    return result


def matrix_as_records() -> Sequence[Mapping[str, Any]]:
    return [asdict(case) for case in required_matrix()]


def threshold_sensitivity_matrix() -> Sequence[Mapping[str, Any]]:
    """Reviewer-facing sensitivity grid; values are not silently optimized."""

    return [
        {
            "eta_error_trigger_minutes": eta,
            "max_refresh_minutes": refresh,
            "soc_margin_multiplier": soc_multiplier,
        }
        for eta in (5, 10, 15)
        for refresh in (15, 30, 60)
        for soc_multiplier in (0.5, 1.0, 1.5)
    ]


def exact_online_comparison(
    *,
    exact_objective: float,
    online_objective: float,
    online_route_solves: int,
    issue_count: int = 288,
) -> Mapping[str, Any]:
    if not (math.isfinite(exact_objective) and math.isfinite(online_objective)):
        raise ValueError("comparison objectives must be finite")
    if abs(exact_objective) <= 1e-12:
        raise ValueError("exact objective must be nonzero for relative degradation")
    if not (0 <= online_route_solves <= issue_count) or issue_count <= 0:
        raise ValueError("invalid route-solve count")
    return {
        "exact_objective": exact_objective,
        "online_objective": online_objective,
        "economic_degradation_relative": (
            online_objective - exact_objective
        ) / abs(exact_objective),
        "online_route_solves": online_route_solves,
        "full_5min_route_solves": issue_count,
        "route_solve_fraction": online_route_solves / issue_count,
        "same_input_required": True,
    }
