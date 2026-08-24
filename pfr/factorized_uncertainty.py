"""Factorized v13.2 workload and grid uncertainty calibration contracts."""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil, isfinite
from typing import Iterable, Mapping


class FactorizedUncertaintyError(ValueError):
    pass


@dataclass(frozen=True)
class NormalizedResidualObservation:
    family: str
    block_id: str
    actual: float
    predicted: float
    frozen_scale: float
    source_year: int

    def validate(self) -> None:
        if self.family not in {"workload", "grid"}:
            raise FactorizedUncertaintyError("family must be workload or grid")
        if not self.block_id:
            raise FactorizedUncertaintyError("independent block identity is required")
        if not all(isfinite(value) for value in (self.actual, self.predicted, self.frozen_scale)):
            raise FactorizedUncertaintyError("residual values must be finite")
        if self.frozen_scale <= 0:
            raise FactorizedUncertaintyError("normalization scale must be positive")
        if self.source_year != 2024:
            raise FactorizedUncertaintyError("PFR3 calibration is restricted to 2024")

    @property
    def one_sided_score(self) -> float:
        self.validate()
        return (self.actual - self.predicted) / self.frozen_scale


@dataclass(frozen=True)
class ComponentCalibration:
    family: str
    target_coverage: float
    calibration_year: int
    block_count: int
    finite_sample_rank: int
    normalized_quantile: float
    frozen_scale_authority: str


@dataclass(frozen=True)
class FactorizedUncertaintySet:
    mobility_joint_quantile: float
    workload: ComponentCalibration
    grid: ComponentCalibration
    factorization: str = "U_mob x U_work x U_grid"

    def as_mapping(self) -> Mapping[str, object]:
        return {
            "factorization": self.factorization,
            "U_mob": {"joint_eta_energy_quantile": self.mobility_joint_quantile},
            "U_work": self.workload.__dict__,
            "U_grid": self.grid.__dict__,
        }


def fit_component_calibration(
    observations: Iterable[NormalizedResidualObservation],
    *,
    family: str,
    target_coverage: float,
    frozen_scale_authority: str,
) -> ComponentCalibration:
    if not 0 < target_coverage < 1:
        raise FactorizedUncertaintyError("target coverage must lie in (0,1)")
    if not frozen_scale_authority:
        raise FactorizedUncertaintyError("frozen scale authority is required")
    block_scores: dict[str, float] = {}
    for row in observations:
        row.validate()
        if row.family != family:
            raise FactorizedUncertaintyError("mixed uncertainty families are prohibited")
        block_scores[row.block_id] = max(
            block_scores.get(row.block_id, float("-inf")), row.one_sided_score
        )
    if not block_scores:
        raise FactorizedUncertaintyError(f"{family} calibration rows are empty")
    ordered = sorted(block_scores.values())
    rank = min(ceil((len(ordered) + 1) * target_coverage), len(ordered))
    return ComponentCalibration(
        family=family,
        target_coverage=target_coverage,
        calibration_year=2024,
        block_count=len(ordered),
        finite_sample_rank=rank,
        normalized_quantile=ordered[rank - 1],
        frozen_scale_authority=frozen_scale_authority,
    )
