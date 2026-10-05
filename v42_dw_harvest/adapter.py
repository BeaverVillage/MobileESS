"""Reuse every original physical row; independently compute exact projection."""
from fractions import Fraction as F
import numpy as np
from v42_dw_root.run import exact_rc


def exact_projection(block, x):
    coefficients, error = block.exact_coupling(x, np.asarray(block.B @ x).ravel())
    objective = sum((F(float(block.d['objective'][j])) * F(float(x[j]))
                     for j in np.flatnonzero(block.d['objective'])), F(0))
    assert error <= 1e-12
    return coefficients, objective


class Adapter:
    def __init__(self, validator, snapshot):
        self.validator, self.snapshot = validator, snapshot
        self.block = validator.block

    def audit(self, values):
        if not all(np.isfinite(v) for v in values):
            return dict(PASS=False)
        r = self.validator.audit(values)
        return dict(PASS=r['local_PASS'] and r['physical_PASS'] and r['integral'], original=r)

    def exact(self, values):
        x = np.asarray(values, dtype=np.float64)
        a, c = exact_projection(self.block, x)
        snap = self.snapshot
        true = exact_rc(self.block, x, np.asarray(snap.true_dual), snap.convexity_dual[self.validator.unit])
        search = exact_rc(self.block, x, np.asarray(snap.smoothed_dual), snap.smoothed_convexity_dual[self.validator.unit])
        return self.block.column(x)[2], a, c, true, search
