"""Hazard-consistent bounded-body and unbounded-tail severity models."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.stats import beta as beta_distribution
from scipy.stats import genpareto


@dataclass(frozen=True)
class BetaIntervalSeverity:
    """A positive-parameter Beta model on one normalized finite interval."""

    alpha: float
    beta: float

    @classmethod
    def fit(cls, normalized_severity: np.ndarray) -> "BetaIntervalSeverity":
        """Fit pooled method-of-moments parameters without changing interval mass."""

        z = np.clip(np.asarray(normalized_severity, float), 1e-6, 1.0-1e-6)
        if len(z) < 3:
            return cls(1.0, 1.0)
        mean = float(z.mean()); variance = float(z.var(ddof=1))
        common = max(mean*(1-mean)/max(variance,1e-6)-1.0, 2e-3)
        return cls(max(mean*common,1e-3), max((1-mean)*common,1e-3))

    def cdf(self, value: np.ndarray | float) -> np.ndarray:
        """Evaluate a normalized conditional CDF from zero to one."""

        return beta_distribution.cdf(np.clip(value,0.0,1.0),self.alpha,self.beta)

    def ppf(self, probability: np.ndarray | float) -> np.ndarray:
        """Evaluate the bounded conditional quantile function."""

        return beta_distribution.ppf(np.clip(probability,1e-12,1-1e-12),self.alpha,self.beta)


@dataclass(frozen=True)
class GPDTailSeverity:
    """A finite-mean pooled Generalized Pareto excess model above P95."""

    xi: float
    sigma_GPU_h: float

    @classmethod
    def fit(cls, excess_GPU_h: np.ndarray) -> "GPDTailSeverity":
        """Fit a pooled GPD with preregistered ``-0.5 < xi < 0.5`` support."""

        excess = np.maximum(np.asarray(excess_GPU_h,float),0.0)
        if len(excess) < 3 or np.allclose(excess,0):
            return cls(0.0,max(float(excess.mean()) if len(excess) else 1.0,1e-3))
        xi, _, sigma = genpareto.fit(excess,floc=0.0)
        return cls(float(np.clip(xi,-.499,.499)),max(float(sigma),1e-6))

    def cdf(self, excess_GPU_h: np.ndarray | float) -> np.ndarray:
        """Evaluate the nonnegative conditional excess CDF."""

        return genpareto.cdf(np.maximum(excess_GPU_h,0.0),self.xi,loc=0.0,scale=self.sigma_GPU_h)

    def ppf(self, probability: np.ndarray | float) -> np.ndarray:
        """Evaluate the untruncated nonnegative excess quantile function."""

        return genpareto.ppf(np.clip(probability,1e-12,1-1e-12),self.xi,loc=0.0,scale=self.sigma_GPU_h)

    @property
    def mean_GPU_h(self) -> float:
        """Return the finite conditional mean excess in GPU-h."""

        return self.sigma_GPU_h/(1.0-self.xi)


@dataclass(frozen=True)
class SeverityModel:
    """Pooled Beta/Beta/GPD conditional severities; no probability-mass parameters."""

    interval_80_90: BetaIntervalSeverity
    interval_90_95: BetaIntervalSeverity
    tail_95_plus: GPDTailSeverity
    thresholds_GPU_h: np.ndarray

    @classmethod
    def fit(cls, target_GPU_h: np.ndarray, thresholds_GPU_h: np.ndarray) -> "SeverityModel":
        """Fit conditional shapes using outer-training targets only."""

        target=np.asarray(target_GPU_h,float); u80,u90,u95=np.asarray(thresholds_GPU_h,float)[2:]
        z1=(target[(target>u80)&(target<=u90)]-u80)/max(u90-u80,1e-9)
        z2=(target[(target>u90)&(target<=u95)]-u90)/max(u95-u90,1e-9)
        tail=target[target>u95]-u95
        return cls(BetaIntervalSeverity.fit(z1),BetaIntervalSeverity.fit(z2),GPDTailSeverity.fit(tail),np.asarray(thresholds_GPU_h,float))

