"""Continuous body-tail splicing and exact baseline-recovery construction."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np

from .base_reconciliation import ReconciledBase
from .severity import SeverityModel


ArrayFunction = Callable[[np.ndarray], np.ndarray]


@dataclass(frozen=True)
class SplicedDistribution:
    """One nonnegative continuous CDF with hazard-fixed interval masses."""

    base: ReconciledBase
    thresholds_GPU_h: np.ndarray
    exceedance_probabilities: np.ndarray
    interval_80_90_cdf: ArrayFunction
    interval_90_95_cdf: ArrayFunction
    tail_95_plus_cdf: ArrayFunction

    def cdf(self, value_GPU_h: np.ndarray | float) -> np.ndarray:
        """Evaluate the body-scaled and hazard-consistent spliced CDF."""

        h=np.asarray(value_GPU_h,float); u80,u90,u95=np.asarray(self.thresholds_GPU_h,float)[2:]
        p80,p90,p95=np.asarray(self.exceedance_probabilities,float)[2:]
        output=np.zeros_like(h,dtype=float)
        body=h<=u80
        f80=max(float(self.base.cdf(u80)),1e-12)
        output[body]=(1-p80)*self.base.cdf(h[body])/f80
        middle1=(h>u80)&(h<=u90)
        z1=(h[middle1]-u80)/max(u90-u80,1e-12)
        output[middle1]=1-p80+(p80-p90)*self.interval_80_90_cdf(z1)
        middle2=(h>u90)&(h<=u95)
        z2=(h[middle2]-u90)/max(u95-u90,1e-12)
        output[middle2]=1-p90+(p90-p95)*self.interval_90_95_cdf(z2)
        tail=h>u95
        output[tail]=1-p95+p95*self.tail_95_plus_cdf(h[tail]-u95)
        return output


def spliced_from_severity(base: ReconciledBase, thresholds: np.ndarray, probabilities: np.ndarray, severity: SeverityModel) -> SplicedDistribution:
    """Create a splice whose severity shapes cannot alter hazard masses."""

    return SplicedDistribution(base,np.asarray(thresholds,float),np.asarray(probabilities,float),
        severity.interval_80_90.cdf,severity.interval_90_95.cdf,severity.tail_95_plus.cdf)


def baseline_recovery_distribution(base: ReconciledBase, thresholds: np.ndarray) -> SplicedDistribution:
    """Build the exact no-correction splice from base conditional interval CDFs."""

    thresholds=np.asarray(thresholds,float); u80,u90,u95=thresholds[2:]
    probabilities=np.asarray([1-float(base.cdf(value)) for value in thresholds])
    f80,f90,f95=map(lambda u:float(base.cdf(u)),(u80,u90,u95))
    def cdf1(z:np.ndarray)->np.ndarray:
        h=u80+np.asarray(z)*(u90-u80)
        return (base.cdf(h)-f80)/max(f90-f80,1e-12)
    def cdf2(z:np.ndarray)->np.ndarray:
        h=u90+np.asarray(z)*(u95-u90)
        return (base.cdf(h)-f90)/max(f95-f90,1e-12)
    def cdf3(y:np.ndarray)->np.ndarray:
        return (base.cdf(u95+np.asarray(y))-f95)/max(1-f95,1e-12)
    return SplicedDistribution(base,thresholds,probabilities,cdf1,cdf2,cdf3)

