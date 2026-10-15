"""Sparse preparation of the independent verifier's outward interval arrays.

Only scalar arithmetic is memoized. Every direction, reachable site and bound
is still evaluated from the current matrices. No producer or verdict cache.
"""
from fractions import Fraction as Q
from functools import lru_cache
import numpy as np


@lru_cache(maxsize=16384)
def _enclosure(numerator, denominator):
    x = Q(numerator, denominator)
    y = float(x)
    return (y if Q(y) <= x else np.nextafter(y, -np.inf),
            y if Q(y) >= x else np.nextafter(y, np.inf))


def enclosure(x):
    # Fraction.__hash__ computes a modular inverse. Integer-ratio keys avoid
    # that cost while retaining the complete exact scalar identity.
    return _enclosure(x.numerator, x.denominator)


def interval(vectors, ts, reach, points, limit):
    K = len(vectors)
    U, _, N = reach.shape
    pl = np.zeros((K, U, N)); ph = pl.copy()
    ql = pl.copy(); qh = pl.copy(); common = pl.copy()
    zero = Q(0)
    for k, vector in enumerate(vectors):
        for coordinate, coefficient in vector.items():
            u, axis_site = divmod(coordinate, 3 * N)
            axis, site = divmod(axis_site, N)
            if axis == 1:
                pl[k, u, site], ph[k, u, site] = enclosure(coefficient)
            elif axis == 2:
                ql[k, u, site], qh[k, u, site] = enclosure(coefficient)
            if axis == 0:
                discharge = vector.get(coordinate + N, zero)
                if (coefficient.numerator == -discharge.numerator
                        and coefficient.denominator == discharge.denominator):
                    continue
                total = coefficient + discharge
                if total > 0:
                    common[k, u, site] = enclosure(total * limit)[1]
            elif axis == 1 and coordinate - N not in vector and coefficient > 0:
                common[k, u, site] = enclosure(coefficient * limit)[1]
    value = np.zeros_like(pl)
    for x, y in points:
        xl, xh = enclosure(x); yl, yh = enclosure(y)
        p = np.nextafter(np.maximum.reduce([pl*xl, pl*xh, ph*xl, ph*xh]), np.inf)
        q = np.nextafter(np.maximum.reduce([ql*yl, ql*yh, qh*yl, qh*yh]), np.inf)
        value = np.maximum(value, np.nextafter(p+q, np.inf))
    value = np.nextafter(value+common, np.inf)
    upper = np.zeros(K)
    times = np.asarray(ts)
    for u in range(U):
        upper = np.nextafter(upper + np.max(np.where(reach[u, times], value[:, u, :], 0), axis=1), np.inf)
    return upper
