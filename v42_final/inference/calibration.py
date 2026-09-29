"""Inference-only extraction from SHA-verified Runtime source. Training methods excluded."""
import numpy as np
from scipy.special import expit
EPS = 0.01
CENTERS = expit(np.arange(-30.0, 30.0001, 0.1))
LOGITS = np.arange(-30.0, 30.0001, 0.1)

class ProbabilityMap:

    def __init__(self, state=None):
        self.state = state or {'family': 'NONE'}

    def logsf(self, logs):
        logs = np.asarray(logs, float)
        kind = self.state['family']
        if kind == 'NONE':
            return logs
        if kind == 'LOGISTIC':
            with np.errstate(divide='ignore', invalid='ignore'):
                logp = np.log(-np.expm1(logs))
                z = self.state['a'] * (logp - logs) + self.state['b']
            logistic = -np.logaddexp(0, z)
            ls = np.logaddexp(np.log(EPS) + logs, np.log1p(-EPS) + logistic)
            lf = np.logaddexp(np.log(EPS) + logp, np.log1p(-EPS) - np.logaddexp(0, -z))
            return np.where(lf < np.log(0.5), np.log1p(-np.exp(lf)), ls)
        sx = np.array(self.state['s'])
        hy = np.array(self.state['h'])
        s = np.exp(logs)
        idx = np.clip(np.searchsorted(sx, s, side='right') - 1, 0, len(sx) - 2)
        slopes = np.diff(hy) / np.diff(sx)
        value = hy[idx] + slopes[idx] * (s - sx[idx])
        with np.errstate(divide='ignore'):
            result = np.log(value)
        result = np.where(idx == len(slopes) - 1, np.log1p(slopes[-1] * np.expm1(logs)), result)
        return np.where(idx == 0, logs + np.log(slopes[0]), result)

    def inverse_logsf(self, target):
        target = np.asarray(target, float)
        kind = self.state['family']
        if kind == 'NONE':
            return target
        if kind == 'ISOTONIC':
            sx = np.array(self.state['s'])
            hy = np.array(self.state['h'])
            u = np.exp(target)
            raw = np.interp(u, hy, sx)
            with np.errstate(divide='ignore'):
                out = np.log(raw)
            slope = (hy[1] - hy[0]) / (sx[1] - sx[0])
            last = (hy[-1] - hy[-2]) / (sx[-1] - sx[-2])
            out = np.where(u >= hy[-2], np.log1p(np.expm1(target) / last), out)
            return np.where(u <= hy[1], target - np.log(slope), out)
        hi = np.zeros_like(target)
        lo = np.minimum(target - 100.0, -100.0)
        while np.any(self.logsf(lo) > target):
            lo = np.where(self.logsf(lo) > target, 2 * lo, lo)
        for _ in range(65):
            mid = (lo + hi) / 2
            below = self.logsf(mid) < target
            lo = np.where(below, mid, lo)
            hi = np.where(below, hi, mid)
        return (lo + hi) / 2

def maps_quantiles(model, par, mapobj, continuation, quantiles=(0.5, 0.7, 0.8, 0.9, 0.95)):
    return np.column_stack([model.inverse_logsf(par, mapobj.inverse_logsf(np.array(np.log1p(-q))), continuation) for q in quantiles])
