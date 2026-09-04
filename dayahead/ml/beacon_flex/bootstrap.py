"""Paired seven-day block bootstrap for V25M acceptance differences."""

from __future__ import annotations

import numpy as np


def paired_block_CI(difference:np.ndarray,replicates:int=10000,seed:int=20260901)->tuple[float,float]:
    """Return a 95% CI for the mean paired difference using seven-day blocks."""

    values=np.asarray(difference,float); blocks=[np.arange(i,min(i+7,len(values))) for i in range(0,len(values),7)]
    rng=np.random.default_rng(seed); output=np.empty(replicates)
    for index in range(replicates):
        chosen=np.concatenate([blocks[i] for i in rng.integers(0,len(blocks),len(blocks))])
        output[index]=values[chosen].mean()
    return tuple(map(float,np.quantile(output,[.025,.975])))

