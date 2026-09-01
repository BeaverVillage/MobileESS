"""Exact small-sample GP factor marginals and OOF Gaussian-copula dependence."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.special import expit, logit
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import ConstantKernel, Matern, WhiteKernel
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler


@dataclass
class ExactMarginalGP:
    """A fixed-kernel exact GP with training-only feature normalization."""

    scaler: StandardScaler
    model: GaussianProcessRegressor

    @classmethod
    def fit(cls, features: np.ndarray, target: np.ndarray, seed: int) -> "ExactMarginalGP":
        """Fit one exact GP to a transformed dimensionless target."""

        scaler = StandardScaler().fit(features)
        normalized = scaler.transform(features)
        kernel = ConstantKernel(1.0, constant_value_bounds="fixed") * Matern(
            length_scale=2.0, length_scale_bounds="fixed", nu=1.5
        ) + WhiteKernel(noise_level=0.15, noise_level_bounds="fixed")
        model = GaussianProcessRegressor(
            kernel=kernel,
            alpha=1e-6,
            optimizer=None,
            normalize_y=True,
            random_state=seed,
        ).fit(normalized, target)
        return cls(scaler, model)

    def predict(self, features: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Return posterior latent mean and nonnegative standard deviation."""

        mean, std = self.model.predict(self.scaler.transform(features), return_std=True)
        return np.asarray(mean, float), np.maximum(np.asarray(std, float), 1e-8)

    def kernel_min_eigenvalue(self, features: np.ndarray) -> float:
        """Return the minimum symmetric kernel-matrix eigenvalue."""

        matrix = self.model.kernel_(self.scaler.transform(features))
        matrix = 0.5 * (matrix + matrix.T)
        return float(np.linalg.eigvalsh(matrix).min())


@dataclass(frozen=True)
class FactorPosterior:
    """Marginal latent posterior parameters for R, PI, and KAPPA."""

    R_positive_probability: np.ndarray
    R_log_mean: np.ndarray
    R_log_std: np.ndarray
    PI_positive_probability: np.ndarray
    PI_logit_mean: np.ndarray
    PI_logit_std: np.ndarray
    KAPPA_logit_mean: np.ndarray
    KAPPA_logit_std: np.ndarray
    residual_correlation: np.ndarray


@dataclass
class FactorGPModel:
    """Separate exact factor GPs plus an OOF Gaussian residual copula."""

    R_model: ExactMarginalGP
    R_occurrence_scaler: StandardScaler
    R_occurrence_model: LogisticRegression | None
    R_positive_constant: float | None
    PI_occurrence_scaler: StandardScaler
    PI_occurrence_model: LogisticRegression | None
    PI_positive_constant: float | None
    PI_model: ExactMarginalGP
    KAPPA_model: ExactMarginalGP
    residual_correlation: np.ndarray
    copula_projection_magnitude: float

    @staticmethod
    def _fit_occurrence(
        features: np.ndarray, labels: np.ndarray, seed: int
    ) -> tuple[StandardScaler, LogisticRegression | None, float | None]:
        """Fit a training-only PI-positive occurrence classifier."""

        scaler = StandardScaler().fit(features)
        if len(np.unique(labels)) < 2:
            return scaler, None, float(labels.mean())
        model = LogisticRegression(C=1.0, max_iter=2000, random_state=seed)
        model.fit(scaler.transform(features), labels)
        return scaler, model, None

    @staticmethod
    def _occurrence_probability(
        scaler: StandardScaler,
        model: LogisticRegression | None,
        constant: float | None,
        features: np.ndarray,
    ) -> np.ndarray:
        """Return calibrated-prior PI-positive probabilities."""

        if model is None:
            return np.full(len(features), float(constant))
        return model.predict_proba(scaler.transform(features))[:, 1]

    @classmethod
    def fit(
        cls, features: np.ndarray, factors: pd.DataFrame, seed: int
    ) -> "FactorGPModel":
        """Fit marginals and an expanding-OOF residual correlation on training days."""

        r = factors.R_ALL_GPU_h_requested.to_numpy(float)
        r_positive = r > 0.0
        pi = factors.PI_F.to_numpy(float)
        positive = pi > 0.0
        if np.any(pi[positive] >= 1.0):
            raise RuntimeError("V24M_PI_ONE_INFLATION_UNMODELLED")
        defined = factors.KAPPA_DEFINED.to_numpy(bool)
        kappa = factors.loc[defined, "KAPPA_F"].to_numpy(float)
        if np.any((kappa <= 0.0) | (kappa >= 1.0)):
            raise RuntimeError("V24M_KAPPA_LOGIT_SUPPORT")
        r_occ_scaler, r_occ_model, r_occ_constant = cls._fit_occurrence(
            features, r_positive.astype(int), seed
        )
        r_model = ExactMarginalGP.fit(features[r_positive], np.log(r[r_positive]), seed)
        occ_scaler, occ_model, occ_constant = cls._fit_occurrence(
            features, positive.astype(int), seed
        )
        pi_model = ExactMarginalGP.fit(features[positive], logit(pi[positive]), seed)
        k_model = ExactMarginalGP.fit(features[defined], logit(kappa), seed)
        correlation, projection = estimate_oof_copula(features, factors, seed)
        return cls(
            r_model,
            r_occ_scaler,
            r_occ_model,
            r_occ_constant,
            occ_scaler,
            occ_model,
            occ_constant,
            pi_model,
            k_model,
            correlation,
            projection,
        )

    def predict(self, features: np.ndarray) -> FactorPosterior:
        """Return joint latent posterior parameters for causal forecast rows."""

        r_mean, r_std = self.R_model.predict(features)
        pi_mean, pi_std = self.PI_model.predict(features)
        k_mean, k_std = self.KAPPA_model.predict(features)
        probability = self._occurrence_probability(
            self.PI_occurrence_scaler,
            self.PI_occurrence_model,
            self.PI_positive_constant,
            features,
        )
        r_probability = self._occurrence_probability(
            self.R_occurrence_scaler,
            self.R_occurrence_model,
            self.R_positive_constant,
            features,
        )
        return FactorPosterior(
            r_probability,
            r_mean,
            r_std,
            probability,
            pi_mean,
            pi_std,
            k_mean,
            k_std,
            self.residual_correlation,
        )

    def sample(
        self, posterior: FactorPosterior, samples: int, seed: int
    ) -> dict[str, np.ndarray]:
        """Draw support-valid joint factor samples with exact product identity."""

        rng = np.random.default_rng(seed)
        rows = len(posterior.R_log_mean)
        z = rng.multivariate_normal(
            np.zeros(3), posterior.residual_correlation, size=(rows, samples)
        )
        r_positive = rng.random((rows, samples)) < posterior.R_positive_probability[:, None]
        r = np.where(
            r_positive,
            np.exp(
            posterior.R_log_mean[:, None] + posterior.R_log_std[:, None] * z[:, :, 0]
            ),
            0.0,
        )
        positive = rng.random((rows, samples)) < posterior.PI_positive_probability[:, None]
        pi = np.where(
            positive,
            expit(
                posterior.PI_logit_mean[:, None]
                + posterior.PI_logit_std[:, None] * z[:, :, 1]
            ),
            0.0,
        )
        kappa = expit(
            posterior.KAPPA_logit_mean[:, None]
            + posterior.KAPPA_logit_std[:, None] * z[:, :, 2]
        )
        h = r * pi * kappa
        return {"R_ALL": r, "PI_F": pi, "KAPPA_F": kappa, "H_F": h}


def nearest_psd_correlation(matrix: np.ndarray) -> tuple[np.ndarray, float]:
    """Project a symmetric matrix to a unit-diagonal positive-semidefinite correlation."""

    symmetric = 0.5 * (matrix + matrix.T)
    values, vectors = np.linalg.eigh(symmetric)
    clipped = np.maximum(values, 1e-6)
    projected = (vectors * clipped) @ vectors.T
    scale = np.sqrt(np.maximum(np.diag(projected), 1e-12))
    projected = projected / np.outer(scale, scale)
    return projected, float(np.linalg.norm(projected - symmetric, ord="fro"))


def estimate_oof_copula(
    features: np.ndarray, factors: pd.DataFrame, seed: int
) -> tuple[np.ndarray, float]:
    """Estimate residual correlation using expanding training-only OOF blocks."""

    n = len(factors)
    splits = [(max(30, int(n * fraction)), min(n, max(30, int(n * fraction)) + max(10, n // 8))) for fraction in (0.50, 0.65, 0.80)]
    residuals: list[np.ndarray] = []
    for split_index, (end, validation_end) in enumerate(splits):
        if validation_end <= end or end < 20:
            continue
        train = factors.iloc[:end]
        valid = factors.iloc[end:validation_end]
        train_x = features[:end]
        valid_x = features[end:validation_end]
        valid_r_positive = valid.R_ALL_GPU_h_requested.gt(0.0).to_numpy()
        valid_positive = valid.PI_F.gt(0.0).to_numpy()
        valid_defined = valid.KAPPA_DEFINED.to_numpy(bool)
        keep = valid_r_positive & valid_positive & valid_defined
        if not np.any(keep):
            continue
        train_r_positive = train.R_ALL_GPU_h_requested.gt(0.0).to_numpy()
        r_model = ExactMarginalGP.fit(
            train_x[train_r_positive],
            np.log(train.R_ALL_GPU_h_requested.to_numpy(float)[train_r_positive]),
            seed + split_index,
        )
        train_positive = train.PI_F.gt(0.0).to_numpy()
        pi_model = ExactMarginalGP.fit(
            train_x[train_positive],
            logit(train.PI_F.to_numpy(float)[train_positive]),
            seed + split_index,
        )
        train_defined = train.KAPPA_DEFINED.to_numpy(bool)
        k_model = ExactMarginalGP.fit(
            train_x[train_defined],
            logit(train.KAPPA_F.to_numpy(float)[train_defined]),
            seed + split_index,
        )
        r_mean, r_std = r_model.predict(valid_x)
        pi_mean, pi_std = pi_model.predict(valid_x)
        k_mean, k_std = k_model.predict(valid_x)
        block = np.column_stack(
            [
                (np.log(valid.R_ALL_GPU_h_requested.to_numpy(float)) - r_mean) / r_std,
                (logit(valid.PI_F.to_numpy(float)) - pi_mean) / pi_std,
                (logit(valid.KAPPA_F.to_numpy(float)) - k_mean) / k_std,
            ]
        )
        residuals.append(block[keep])
    if sum(len(block) for block in residuals) < 5:
        return np.eye(3), 0.0
    correlation = np.corrcoef(np.vstack(residuals), rowvar=False)
    return nearest_psd_correlation(correlation)
