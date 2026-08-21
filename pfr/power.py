"""Measured H100 utilization-power envelope for normalized effective work."""

from __future__ import annotations

from dataclasses import dataclass
import bisect
import math
from typing import Tuple


class PowerCurveContractError(ValueError):
    pass


@dataclass(frozen=True)
class H100UtilizationPowerCurve:
    utilization_fraction: Tuple[float, ...]
    per_gpu_power_kw_p95_envelope: Tuple[float, ...]
    source_sha256: str
    source_member_sha256: Tuple[str, ...]
    work_fraction_semantics: str = "NORMALIZED_FULL_UTILIZATION_H100_EQUIVALENT_NOT_MEASURED_THROUGHPUT"

    def validate(self) -> None:
        x, y = self.utilization_fraction, self.per_gpu_power_kw_p95_envelope
        if len(x) < 2 or len(x) != len(y):
            raise PowerCurveContractError("power curve axes must have equal length >=2")
        if x[0] != 0.0 or x[-1] != 1.0 or any(b <= a for a, b in zip(x, x[1:])):
            raise PowerCurveContractError("utilization axis must be strict on [0,1]")
        if any(not math.isfinite(value) or value < 0.0 for value in y):
            raise PowerCurveContractError("power envelope must be finite and non-negative")
        if any(b < a for a, b in zip(y, y[1:])):
            raise PowerCurveContractError("p95 power envelope must be monotone")
        if len(self.source_sha256) != 64 or not self.source_member_sha256:
            raise PowerCurveContractError("measured source hashes are required")
        if "NOT_MEASURED_THROUGHPUT" not in self.work_fraction_semantics:
            raise PowerCurveContractError("curve must not claim a measured throughput target")

    def per_gpu_power_kw(self, compute_rate_fraction: float) -> float:
        self.validate()
        if not math.isfinite(float(compute_rate_fraction)) or not 0.0 <= compute_rate_fraction <= 1.0:
            raise PowerCurveContractError("compute rate fraction must lie in [0,1]")
        index = bisect.bisect_right(self.utilization_fraction, compute_rate_fraction) - 1
        index = min(max(index, 0), len(self.utilization_fraction) - 2)
        left_x, right_x = self.utilization_fraction[index : index + 2]
        left_y, right_y = self.per_gpu_power_kw_p95_envelope[index : index + 2]
        weight = (compute_rate_fraction - left_x) / (right_x - left_x)
        return left_y + weight * (right_y - left_y)

    def gang_power_kw(self, gpu_count: int, compute_rate_fraction: float) -> float:
        if gpu_count <= 0:
            raise PowerCurveContractError("GPU gang size must be positive")
        return gpu_count * self.per_gpu_power_kw(compute_rate_fraction)
