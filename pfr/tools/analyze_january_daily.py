"""Outcome-blind paired-day statistics frozen before the PFR9 outcome."""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from typing import Iterable, Mapping, Sequence


SEED = 20250131
REPLICATES = 10_000
SERIAL_THRESHOLD = 0.30
BLOCK_LENGTH = 4
METHODS = tuple(f"B{index}" for index in range(8))
METRICS = (
    "realized_grid_cost_aud",
    "deadline_misses",
    "compute_debt_gpu_hours",
    "energy_debt_kwh",
    "full_replan_count",
    "communication_bytes",
    "safety_filter_interventions",
    "mobility_energy_kwh",
)
CONTRASTS = {"B7_MINUS_B5": ("B7", "B5"), "B7_MINUS_B6": ("B7", "B6")}


def percentile(values: Sequence[float], probability: float) -> float:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        raise ValueError("percentile requires observations")
    position = probability * (len(ordered) - 1)
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def lag1_autocorrelation(values: Sequence[float]) -> float:
    if len(values) < 3:
        return 0.0
    mean = sum(values) / len(values)
    denominator = sum((value - mean) ** 2 for value in values)
    if denominator <= 1e-18:
        return 0.0
    numerator = sum(
        (values[index] - mean) * (values[index - 1] - mean)
        for index in range(1, len(values))
    )
    return numerator / denominator


def bootstrap_mean_ci(values: Sequence[float]) -> Mapping[str, float | int | str]:
    if not values:
        raise ValueError("bootstrap requires paired daily differences")
    rng = random.Random(SEED)
    count = len(values)
    rho1 = lag1_autocorrelation(values)
    dependent = abs(rho1) >= SERIAL_THRESHOLD
    estimates = []
    for _ in range(REPLICATES):
        if dependent:
            sample = []
            while len(sample) < count:
                start = rng.randrange(count)
                sample.extend(values[(start + offset) % count] for offset in range(BLOCK_LENGTH))
            sample = sample[:count]
        else:
            sample = [values[rng.randrange(count)] for _ in range(count)]
        estimates.append(sum(sample) / count)
    return {
        "paired_day_count": count,
        "mean_difference": sum(values) / count,
        "lag1_autocorrelation": rho1,
        "bootstrap_mode": "CIRCULAR_MOVING_BLOCK" if dependent else "PAIRED_DAY_IID",
        "bootstrap_seed": SEED,
        "bootstrap_replicates": REPLICATES,
        "ci95_lower": percentile(estimates, 0.025),
        "ci95_upper": percentile(estimates, 0.975),
    }


def load_episode(root: Path) -> Mapping[str, Mapping[str, float]]:
    result = {}
    for method in METHODS:
        marker_paths = sorted((root / method).glob("issue_*/COMMIT_MARKER.json"))
        if len(marker_paths) != 288:
            raise RuntimeError(f"{root.name}/{method} does not have 288 commit markers")
        rows = [json.loads(path.read_text(encoding="utf-8")) for path in marker_paths]
        if any(row.get("status") != "PASS" or not row.get("commit_marker") for row in rows):
            raise RuntimeError(f"{root.name}/{method} contains an invalid commit marker")
        if any(not row.get("actual_gurobi_used") or not row.get("actual_fresh_opendss_used") for row in rows):
            raise RuntimeError(f"{root.name}/{method} lacks required solver authority")
        if any(row.get("future_actual_used") for row in rows):
            raise RuntimeError(f"{root.name}/{method} used future actual")
        for previous, current in zip(rows, rows[1:]):
            if previous["post_state_sha256"] != current["pre_state_sha256"]:
                raise RuntimeError(f"{root.name}/{method} state chain is incomplete")
        result[method] = {
            "realized_grid_cost_aud": sum(float(row["realized_grid_cost_aud"]) for row in rows),
            "deadline_misses": float(rows[-1]["deadline_misses"]),
            "compute_debt_gpu_hours": float(rows[-1]["compute_debt_gpu_hours"]),
            "energy_debt_kwh": float(rows[-1]["energy_debt_kwh"]),
            "full_replan_count": float(rows[-1]["full_replan_count_cumulative"]),
            "communication_bytes": float(rows[-1]["communication_bytes_cumulative"]),
            "safety_filter_interventions": float(sum(bool(row["safety_filter_intervention"]) for row in rows)),
            "mobility_energy_kwh": sum(float(row["mobility_energy_kwh"]) for row in rows),
        }
    return result


def analyze(episodes: Iterable[tuple[str, Path]]) -> Mapping[str, object]:
    daily = {date: load_episode(path) for date, path in episodes}
    if len(daily) != 31:
        raise RuntimeError("January inference requires exactly 31 calendar days")
    contrasts = {}
    for contrast_id, (minuend, subtrahend) in CONTRASTS.items():
        contrasts[contrast_id] = {}
        for metric in METRICS:
            differences = [
                daily[date][minuend][metric] - daily[date][subtrahend][metric]
                for date in sorted(daily)
            ]
            contrasts[contrast_id][metric] = bootstrap_mean_ci(differences)
    return {
        "schema_version": "JANUARY_2025_PAIRED_DAY_STATISTICS_V13_2",
        "status": "PASS",
        "calendar_day_count": 31,
        "daily_metrics": daily,
        "primary_contrasts": contrasts,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--episode", action="append", required=True, help="YYYY-MM-DD=artifact_root")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    episodes = []
    for value in args.episode:
        date, separator, raw_path = value.partition("=")
        if not separator:
            raise ValueError("episode must be YYYY-MM-DD=artifact_root")
        episodes.append((date, Path(raw_path)))
    result = analyze(episodes)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": "PASS", "days": 31, "output": str(args.output)}))


if __name__ == "__main__":
    main()
