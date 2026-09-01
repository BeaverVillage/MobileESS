"""Strong probabilistic GP and empirical-residual baselines for V24M."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from .gp_models import ExactMarginalGP


@dataclass
class DirectHGP:
    """Hurdle exact GP for a nonnegative daily GPU-h target."""

    occurrence_scaler: StandardScaler
    occurrence_model: LogisticRegression | None
    occurrence_constant: float | None
    positive_model: ExactMarginalGP

    @classmethod
    def fit(cls, features: np.ndarray, target: np.ndarray, seed: int) -> "DirectHGP":
        """Fit occurrence and positive log-mass models on training days only."""

        positive = target > 0.0
        scaler = StandardScaler().fit(features)
        if len(np.unique(positive)) < 2:
            occurrence_model = None
            constant = float(positive.mean())
        else:
            occurrence_model = LogisticRegression(
                C=1.0, max_iter=2000, random_state=seed
            ).fit(scaler.transform(features), positive.astype(int))
            constant = None
        positive_model = ExactMarginalGP.fit(
            features[positive], np.log(target[positive]), seed
        )
        return cls(scaler, occurrence_model, constant, positive_model)

    def sample(self, features: np.ndarray, samples: int, seed: int) -> np.ndarray:
        """Draw support-valid daily GPU-h samples."""

        if self.occurrence_model is None:
            probability = np.full(len(features), float(self.occurrence_constant))
        else:
            probability = self.occurrence_model.predict_proba(
                self.occurrence_scaler.transform(features)
            )[:, 1]
        mean, std = self.positive_model.predict(features)
        rng = np.random.default_rng(seed)
        positive = rng.random((len(features), samples)) < probability[:, None]
        return np.where(
            positive,
            np.exp(mean[:, None] + std[:, None] * rng.standard_normal((len(features), samples))),
            0.0,
        )


def empirical_point_distribution(
    point: np.ndarray,
    training_actual: np.ndarray,
    samples: int,
    seed: int,
) -> np.ndarray:
    """Wrap a nonnegative point forecast in a training-only multiplicative residual distribution."""

    positive = training_actual[training_actual > 0.0]
    if len(positive) == 0:
        return np.zeros((len(point), samples))
    scale = positive / max(float(np.mean(positive)), 1e-12)
    rng = np.random.default_rng(seed)
    factors = rng.choice(scale, size=(len(point), samples), replace=True)
    return np.maximum(0.0, point[:, None] * factors)


def analog_joint_samples(
    factors: np.ndarray,
    indices: np.ndarray,
    weights: np.ndarray,
    samples: int,
    seed: int,
) -> dict[str, np.ndarray]:
    """Resample intact historical R/PI/KAPPA/H tuples with undefined-KAPPA flags."""

    rng = np.random.default_rng(seed)
    selected = rng.choice(indices, size=samples, replace=True, p=weights)
    rows = factors[selected]
    kappa_defined = np.isfinite(rows[:, 2])
    kappa = np.where(kappa_defined, rows[:, 2], 1.0)
    return {
        "R_ALL": rows[:, 0],
        "PI_F": rows[:, 1],
        "KAPPA_F": kappa,
        "KAPPA_DEFINED": kappa_defined,
        "H_F": rows[:, 3],
    }
