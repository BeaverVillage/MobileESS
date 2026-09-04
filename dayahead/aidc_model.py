"""V16 AIDC model configuration boundary.

Training is intentionally backend-injected.  This prevents silently replacing
the frozen Direct96 Transformer with an unavailable or different estimator.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping, Sequence

from .aidc_resource_coupling import Direct96Architecture


@dataclass(frozen=True)
class TrainingFreeze:
    architecture: Direct96Architecture
    learning_rate: float
    seed: int = 20260828
    multitask_weights: tuple[float, float, float] = (1.0, 1.0, 1.0)
    posthoc_quantile_calibration: str = "NONE_V1"

    def validate(self) -> None:
        self.architecture.validate()
        if self.learning_rate not in {1e-4, 3e-4} or self.seed != 20260828:
            raise ValueError("AIDC_MODEL_SELECTION_FREEZE_VIOLATION")
        if self.multitask_weights != (1.0, 1.0, 1.0) or self.posthoc_quantile_calibration != "NONE_V1":
            raise ValueError("AIDC_LOSS_OR_CALIBRATION_FREEZE_VIOLATION")


def train_with_backend(freeze: TrainingFreeze, backend: Callable[..., object] | None, **data: object) -> object:
    freeze.validate()
    if backend is None:
        raise RuntimeError("AIDC_TRANSFORMER_BACKEND_REQUIRED_NO_FALLBACK_MODEL")
    return backend(freeze=freeze, **data)
