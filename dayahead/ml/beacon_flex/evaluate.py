"""Canonical pooled OOF metrics for BEACON and conventional baselines."""

from __future__ import annotations

import numpy as np


def point_metrics(actual:np.ndarray,mean:np.ndarray,q50:np.ndarray,q90:np.ndarray,q95:np.ndarray,crps:np.ndarray,burst:np.ndarray,body:np.ndarray)->dict[str,float]:
    """Compute pooled metrics; fold averaging is deliberately not used for acceptance."""

    actual=np.asarray(actual,float); denominator=max(actual.sum(),1e-12)
    def wape(mask:np.ndarray,predicted:np.ndarray)->float:
        return float(np.abs(predicted[mask]-actual[mask]).sum()/max(actual[mask].sum(),1e-12))
    return {"Mean_WAPE":float(np.abs(mean-actual).sum()/denominator),"Mean_MAE_GPU_h":float(np.abs(mean-actual).mean()),
        "RMSE_GPU_h":float(np.sqrt(np.square(mean-actual).mean())),"mean_bias_GPU_h":float(np.mean(mean-actual)),
        "aggregate_mass_ratio":float(mean.sum()/denominator),"Q50_WAPE":float(np.abs(q50-actual).sum()/denominator),
        "Q50_MAE_GPU_h":float(np.abs(q50-actual).mean()),"CRPS":float(np.mean(crps)),
        "Burst_WAPE":wape(burst,mean),"Body_Mean_WAPE":wape(body,mean),"Body_Q50_WAPE":wape(body,q50),
        "Body_CRPS":float(np.mean(crps[body])),"Q50_coverage":float(np.mean(actual<=q50)),
        "Q90_coverage":float(np.mean(actual<=q90)),"Q95_coverage":float(np.mean(actual<=q95)),
        "Q50_pinball":float(np.mean(np.maximum(.5*(actual-q50),-.5*(actual-q50)))),
        "Q90_pinball":float(np.mean(np.maximum(.9*(actual-q90),-.1*(actual-q90)))),
        "Q95_pinball":float(np.mean(np.maximum(.95*(actual-q95),-.05*(actual-q95))))}
