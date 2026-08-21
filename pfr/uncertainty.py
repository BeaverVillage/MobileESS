"""PFR3 joint mobility uncertainty contracts.

The joint score couples ETA and mobility-energy residuals at an independent
OD-date block.  It replaces paper-facing claims based on two independent
marginal quantiles while retaining the inherited point predictions.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from typing import Iterable, Mapping


class UncertaintyContractError(ValueError):
    pass


@dataclass(frozen=True)
class MobilityResidualObservation:
    block_id: str
    eta_actual_seconds: float
    eta_predicted_seconds: float
    eta_scale_seconds: float
    energy_actual_kwh: float
    energy_predicted_kwh: float
    energy_scale_kwh: float
    source_year: int

    def validate(self) -> None:
        if not self.block_id:
            raise UncertaintyContractError("mobility residual block identity is required")
        if self.eta_scale_seconds <= 0 or self.energy_scale_kwh <= 0:
            raise UncertaintyContractError("mobility residual scales must be positive")
        if self.source_year != 2024:
            raise UncertaintyContractError(
                "PFR3 calibration observations must come from 2024 only"
            )

    @property
    def normalized_eta_residual(self) -> float:
        self.validate()
        return (self.eta_actual_seconds - self.eta_predicted_seconds) / self.eta_scale_seconds

    @property
    def normalized_energy_residual(self) -> float:
        self.validate()
        return (self.energy_actual_kwh - self.energy_predicted_kwh) / self.energy_scale_kwh

    @property
    def joint_score(self) -> float:
        return max(self.normalized_eta_residual, self.normalized_energy_residual)


@dataclass(frozen=True)
class MobilitySafeBound:
    eta_safe_seconds: float
    energy_safe_kwh: float
    joint_quantile: float


@dataclass(frozen=True)
class JointMobilityCalibration:
    alpha: float
    target_joint_coverage: float
    calibration_block_count: int
    finite_sample_rank: int
    joint_quantile: float
    calibration_year: int
    block_aggregation: str
    fallback: str
    source_identities: tuple[str, ...]

    def validate(self) -> None:
        if not 0 < self.alpha < 1:
            raise UncertaintyContractError("alpha must lie in (0, 1)")
        if self.target_joint_coverage != 1.0 - self.alpha:
            raise UncertaintyContractError("coverage target and alpha disagree")
        expected_rank = ceil((self.calibration_block_count + 1) * (1.0 - self.alpha))
        if self.finite_sample_rank != min(expected_rank, self.calibration_block_count):
            raise UncertaintyContractError("invalid finite-sample conformal rank")
        if self.calibration_year != 2024:
            raise UncertaintyContractError("2025 labels cannot calibrate PFR3")
        if self.calibration_block_count <= 0 or not self.source_identities:
            raise UncertaintyContractError("calibration blocks and sources are required")

    def safe_bound(
        self,
        *,
        eta_prediction_seconds: float,
        eta_scale_seconds: float,
        energy_prediction_kwh: float,
        energy_scale_kwh: float,
    ) -> MobilitySafeBound:
        self.validate()
        if eta_scale_seconds <= 0 or energy_scale_kwh <= 0:
            raise UncertaintyContractError("safe-bound scales must be positive")
        return MobilitySafeBound(
            eta_safe_seconds=eta_prediction_seconds + self.joint_quantile * eta_scale_seconds,
            energy_safe_kwh=energy_prediction_kwh + self.joint_quantile * energy_scale_kwh,
            joint_quantile=self.joint_quantile,
        )


def finite_sample_upper_quantile(
    scores: Iterable[float], *, alpha: float
) -> tuple[float, int]:
    values = sorted(float(score) for score in scores)
    if not values:
        raise UncertaintyContractError("at least one conformal score is required")
    if not 0 < alpha < 1:
        raise UncertaintyContractError("alpha must lie in (0, 1)")
    rank = min(ceil((len(values) + 1) * (1.0 - alpha)), len(values))
    return values[rank - 1], rank


def fit_joint_mobility_calibration(
    observations: Iterable[MobilityResidualObservation],
    *,
    alpha: float,
    source_identities: tuple[str, ...],
) -> JointMobilityCalibration:
    observations = tuple(observations)
    block_scores: dict[str, float] = {}
    for observation in observations:
        observation.validate()
        block_scores[observation.block_id] = max(
            block_scores.get(observation.block_id, float("-inf")),
            observation.joint_score,
        )
    quantile, rank = finite_sample_upper_quantile(block_scores.values(), alpha=alpha)
    calibration = JointMobilityCalibration(
        alpha=alpha,
        target_joint_coverage=1.0 - alpha,
        calibration_block_count=len(block_scores),
        finite_sample_rank=rank,
        joint_quantile=quantile,
        calibration_year=2024,
        block_aggregation="maximum_within_OD_date_block",
        fallback="global_2024_OD_date_block_quantile",
        source_identities=source_identities,
    )
    calibration.validate()
    return calibration


def empirical_coverage(scores: Iterable[float], *, quantile: float) -> float:
    values = tuple(float(score) for score in scores)
    if not values:
        raise UncertaintyContractError("coverage requires at least one score")
    return sum(score <= quantile for score in values) / len(values)


@dataclass(frozen=True)
class UncertaintyUniverse:
    """Separated mobility, workload, and grid uncertainty components."""

    mobility: Mapping[str, float]
    workload: Mapping[str, float]
    grid: Mapping[str, float]

    def validate(self) -> None:
        if not self.mobility or not self.workload or not self.grid:
            raise UncertaintyContractError(
                "U_t requires separate nonempty mobility, workload, and grid components"
            )

    def as_product_contract(self) -> Mapping[str, Mapping[str, float]]:
        self.validate()
        return {
            "U_mob": dict(self.mobility),
            "U_work": dict(self.workload),
            "U_grid": dict(self.grid),
        }
