"""Exact V16 resource-coupling, scaling and quantile-head contracts.

The scientific trainer may use a tensor backend, but these backend-independent
helpers define the only allowed branch delta between Vanilla and Proposed.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

AUTHORITY_ID = "AIDC_RESOURCE_COUPLING_BLOCK_V1"


def softplus(value: float) -> float:
    value = float(value)
    return value + math.log1p(math.exp(-value)) if value > 0 else math.log1p(math.exp(value))


def monotone_quantiles(a: float, b: float, c: float) -> tuple[float, float, float]:
    q10 = softplus(a)
    q50 = q10 + softplus(b)
    q90 = q50 + softplus(c)
    return q10, q50, q90


@dataclass(frozen=True)
class PositiveTargetScaler:
    scale: float
    mean_subtraction: float = 0.0

    def validate(self) -> None:
        if self.scale <= 0 or self.mean_subtraction != 0:
            raise ValueError("TARGET_SCALING_MUST_BE_POSITIVE_ONLY_WITHOUT_CENTERING")

    def transform(self, values: Sequence[float]) -> tuple[float, ...]:
        self.validate()
        return tuple(float(value) / self.scale for value in values)

    def inverse(self, values: Sequence[float]) -> tuple[float, ...]:
        self.validate()
        return tuple(float(value) * self.scale for value in values)


@dataclass(frozen=True)
class Direct96Architecture:
    lookback: int
    feature_count: int
    d_model: int
    encoder_layers: int
    attention_heads: int
    dropout: float
    proposed: bool

    def validate(self) -> None:
        if self.lookback not in {672, 1344}:
            raise ValueError("DIRECT96_LOOKBACK_NOT_FROZEN")
        if self.d_model not in {64, 128} or self.encoder_layers not in {2, 3}:
            raise ValueError("DIRECT96_HYPERPARAMETER_OUTSIDE_FREEZE")
        if self.attention_heads not in {4, 8} or self.d_model % self.attention_heads:
            raise ValueError("DIRECT96_ATTENTION_HEAD_CONTRACT")
        if self.dropout not in {0.1, 0.2} or self.feature_count <= 0:
            raise ValueError("DIRECT96_FEATURE_OR_DROPOUT_CONTRACT")

    def contract(self) -> dict[str, object]:
        self.validate()
        return {
            "authority_id": AUTHORITY_ID,
            "past_shape": [self.lookback, self.feature_count],
            "memory_shape": [self.lookback, self.d_model],
            "decoder_latent_shape": [96, self.d_model],
            "decoder_mode": "ONE_PASS_NON_AUTOREGRESSIVE_CROSS_ATTENTION",
            "causal_decoder_mask": False,
            "fixed_sinusoidal_positional_encoding": True,
            "gpu_to_power_gated_residual": self.proposed,
            "flex_to_gpu_or_power_direct_injection": False,
            "vanilla_delta": "H_P=H" if not self.proposed else "equations_9e_9f_only",
            "quantile_parameterization": "q10=softplus(a);q50=q10+softplus(b);q90=q50+softplus(c)",
        }
