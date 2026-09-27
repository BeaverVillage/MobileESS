"""A proper zero-atom/lognormal distribution, not a Tweedie approximation."""
import numpy as np
from scipy.special import ndtr, ndtri


def validate(p, mu, sigma):
    p, mu = np.broadcast_arrays(np.asarray(p, float), np.asarray(mu, float))
    if not (np.isfinite(p).all() and np.isfinite(mu).all() and np.isfinite(sigma)
            and sigma > 0 and ((p >= 0) & (p <= 1)).all()):
        raise ValueError('INVALID_DISTRIBUTION_PARAMETERS')
    return p, mu


def quantiles(p, mu, sigma, taus=(.5, .9)):
    p, mu = validate(p, mu, sigma)
    out = []
    for tau in taus:
        if not 0 < tau < 1: raise ValueError('INVALID_TAU')
        positive = tau > 1 - p
        q = np.zeros(p.shape)
        u = (tau - 1 + p[positive]) / p[positive]
        with np.errstate(over='raise', invalid='raise'):
            q[positive] = np.exp(mu[positive] + sigma * ndtri(u))
        if not np.isfinite(q).all(): raise ValueError('NONFINITE_QUANTILE')
        out.append(q)
    return np.stack(out, -1)


def cdf(y, p, mu, sigma):
    p, mu = validate(p, mu, sigma)
    y, p, mu = np.broadcast_arrays(np.asarray(y, float), p, mu)
    ans = np.zeros(y.shape)
    zero = y == 0
    positive = y > 0
    ans[zero] = 1 - p[zero]
    ans[positive] = 1 - p[positive] + p[positive] * ndtr((np.log(y[positive]) - mu[positive]) / sigma)
    return ans


def burst_probability(threshold, p, mu, sigma):
    p, mu = validate(p, mu, sigma)
    if not threshold > 0: raise ValueError('INVALID_BURST_THRESHOLD')
    return p * ndtr((mu - np.log(threshold)) / sigma)


def hybrid(base, distributional, risk, threshold):
    return np.where((risk >= threshold)[..., None], distributional, base)


def ensemble(base, deep, weight):
    if not 0 <= weight <= 1: raise ValueError('INVALID_ENSEMBLE_WEIGHT')
    return (1 - weight) * base + weight * deep
