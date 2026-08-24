"""V13.2 workload uncertainty reconstruction after spatial-operator change."""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from typing import Iterable, Mapping


class WorkloadUncertaintyError(ValueError):
    pass


@dataclass(frozen=True)
class WorkloadResidual:
    issue_date: str
    actual_global_gpu: float
    predicted_global_gpu_q50: float
    total_gpu_capacity: float

    @property
    def normalized_one_sided_score(self) -> float:
        if self.total_gpu_capacity <= 0:
            raise WorkloadUncertaintyError("total GPU capacity must be positive")
        return (self.actual_global_gpu - self.predicted_global_gpu_q50) / self.total_gpu_capacity


@dataclass(frozen=True)
class WorkloadCalibration:
    target_coverage: float
    day_block_count: int
    finite_sample_rank: int
    normalized_daily_joint_quantile: float
    total_gpu_capacity: float
    global_gpu_reserve: float
    idc_gpu_reserve: Mapping[str, float]
    idc_incremental_it_reserve_kw: Mapping[str, float]


def calibrate_daily_joint_workload(
    residuals: Iterable[WorkloadResidual],
    *,
    target_coverage: float,
    spatial_weights: Mapping[str, float],
    incremental_it_kw_per_gpu: Mapping[str, float],
) -> WorkloadCalibration:
    rows = tuple(residuals)
    if not rows or not 0 < target_coverage < 1:
        raise WorkloadUncertaintyError("rows and a valid target coverage are required")
    capacities = {row.total_gpu_capacity for row in rows}
    if len(capacities) != 1:
        raise WorkloadUncertaintyError("GPU capacity normalization must be frozen")
    if set(spatial_weights) != set(incremental_it_kw_per_gpu):
        raise WorkloadUncertaintyError("weight and power-adapter IDC axes differ")
    if abs(sum(spatial_weights.values()) - 1.0) > 1e-12:
        raise WorkloadUncertaintyError("spatial weights must sum to one")
    daily_scores: dict[str, float] = {}
    for row in rows:
        daily_scores[row.issue_date] = max(
            daily_scores.get(row.issue_date, float("-inf")), row.normalized_one_sided_score
        )
    ordered = sorted(daily_scores.values())
    rank = min(ceil((len(ordered) + 1) * target_coverage), len(ordered))
    quantile = ordered[rank - 1]
    total_capacity = capacities.pop()
    global_reserve = max(0.0, quantile * total_capacity)
    idc_gpu = {idc: global_reserve * weight for idc, weight in spatial_weights.items()}
    idc_power = {
        idc: idc_gpu[idc] * incremental_it_kw_per_gpu[idc] for idc in spatial_weights
    }
    return WorkloadCalibration(
        target_coverage=target_coverage,
        day_block_count=len(ordered),
        finite_sample_rank=rank,
        normalized_daily_joint_quantile=quantile,
        total_gpu_capacity=total_capacity,
        global_gpu_reserve=global_reserve,
        idc_gpu_reserve=idc_gpu,
        idc_incremental_it_reserve_kw=idc_power,
    )
