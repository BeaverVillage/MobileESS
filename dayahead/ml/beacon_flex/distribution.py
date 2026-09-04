"""Deterministic predictive sampling and summaries from one BEACON CDF."""

from __future__ import annotations

import numpy as np
from scipy.stats import qmc

from .severity import SeverityModel
from .splice import SplicedDistribution


def sobol_uniforms(samples:int=4096,seed:int=20260901)->np.ndarray:
    """Return reproducible open-unit Sobol points for one-dimensional inversion."""

    exponent=int(np.log2(samples))
    if 2**exponent!=samples:
        raise ValueError("V25M_SOBOL_SAMPLE_COUNT_NOT_POWER_OF_TWO")
    return np.clip(qmc.Sobol(1,scramble=True,seed=seed).random_base2(exponent).ravel(),1e-12,1-1e-12)


def sample_splice(distribution:SplicedDistribution,severity:SeverityModel,uniforms:np.ndarray)->np.ndarray:
    """Invert the four splice masses without truncating the unbounded GPD tail."""

    u=np.asarray(uniforms,float); thresholds=np.asarray(distribution.thresholds_GPU_h,float)
    u80,u90,u95=thresholds[2:]; p80,p90,p95=np.asarray(distribution.exceedance_probabilities,float)[2:]
    output=np.zeros_like(u); body=u<1-p80
    f80=float(distribution.base.cdf(u80))
    base_probability=u[body]*f80/max(1-p80,1e-12)
    output[body]=distribution.base.quantile(base_probability)
    first=(u>=1-p80)&(u<1-p90)
    conditional=(u[first]-(1-p80))/max(p80-p90,1e-12)
    output[first]=u80+(u90-u80)*severity.interval_80_90.ppf(conditional)
    second=(u>=1-p90)&(u<1-p95)
    conditional=(u[second]-(1-p90))/max(p90-p95,1e-12)
    output[second]=u90+(u95-u90)*severity.interval_90_95.ppf(conditional)
    tail=u>=1-p95; conditional=(u[tail]-(1-p95))/max(p95,1e-12)
    output[tail]=u95+severity.tail_95_plus.ppf(conditional)
    if not np.all(np.isfinite(output)) or np.any(output<0):
        raise RuntimeError("V25M_INVALID_PREDICTIVE_SAMPLE")
    return output


def ensemble_crps(samples:np.ndarray,actual:float)->float:
    """Compute exact ensemble CRPS in O(M log M) for one daily target."""

    ordered=np.sort(np.asarray(samples,float)); count=len(ordered)
    first=np.mean(np.abs(ordered-float(actual)))
    coefficients=2*np.arange(1,count+1)-count-1
    pair=float(np.dot(coefficients,ordered))/(count*count)
    return float(first-pair)


def risk_summary(samples:np.ndarray,u90:float)->dict[str,float]:
    """Derive mean, quantiles, expected excess and CTM90 from identical samples."""

    values=np.asarray(samples,float); exceed=values>u90
    return {"mean_GPU_h":float(values.mean()),"Q50_GPU_h":float(np.quantile(values,.5)),
            "Q90_GPU_h":float(np.quantile(values,.9)),"Q95_GPU_h":float(np.quantile(values,.95)),
            "expected_excess_u90_GPU_h":float(np.maximum(values-u90,0).mean()),
            "conditional_tail_mean_u90_GPU_h":float(values[exceed].mean()) if np.any(exceed) else float(u90)}

