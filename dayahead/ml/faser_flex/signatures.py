"""Exact truncated tensor signatures and log-signatures for piecewise-linear paths."""

from __future__ import annotations

import numpy as np


def signature_dimension(channels: int, depth: int) -> int:
    """Return the flattened non-scalar truncated tensor-signature dimension."""

    if depth not in (1, 2, 3):
        raise ValueError("V24M_SIGNATURE_DEPTH_UNSUPPORTED")
    return sum(channels**level for level in range(1, depth + 1))


def truncated_signature(path: np.ndarray, depth: int) -> tuple[np.ndarray, ...]:
    """Compute the exact depth<=3 Chen signature of a piecewise-linear path."""

    if path.ndim != 2 or len(path) < 2:
        raise ValueError("V24M_SIGNATURE_PATH_INVALID")
    if depth not in (1, 2, 3):
        raise ValueError("V24M_SIGNATURE_DEPTH_UNSUPPORTED")
    channels = path.shape[1]
    level1 = np.zeros(channels, dtype=np.float64)
    level2 = np.zeros((channels, channels), dtype=np.float64)
    level3 = np.zeros((channels, channels, channels), dtype=np.float64)
    for increment in np.diff(path, axis=0):
        old1 = level1.copy()
        old2 = level2.copy()
        level1 = old1 + increment
        if depth >= 2:
            aa = np.einsum("i,j->ij", increment, increment)
            level2 = old2 + np.einsum("i,j->ij", old1, increment) + 0.5 * aa
        if depth >= 3:
            aaa = np.einsum("i,j,k->ijk", increment, increment, increment)
            level3 = (
                level3
                + np.einsum("ij,k->ijk", old2, increment)
                + 0.5 * np.einsum("i,j,k->ijk", old1, increment, increment)
                + aaa / 6.0
            )
    levels = [level1]
    if depth >= 2:
        levels.append(level2)
    if depth >= 3:
        levels.append(level3)
    return tuple(levels)


def truncated_logsignature(path: np.ndarray, depth: int) -> tuple[np.ndarray, ...]:
    """Compute the exact tensor-log of the depth<=3 truncated Chen signature."""

    signature = truncated_signature(path, depth)
    level1 = signature[0]
    result = [level1]
    if depth >= 2:
        level2 = signature[1] - 0.5 * np.einsum("i,j->ij", level1, level1)
        result.append(level2)
    if depth >= 3:
        sig2 = signature[1]
        sig3 = signature[2]
        level3 = (
            sig3
            - 0.5
            * (
                np.einsum("i,jk->ijk", level1, sig2)
                + np.einsum("ij,k->ijk", sig2, level1)
            )
            + np.einsum("i,j,k->ijk", level1, level1, level1) / 3.0
        )
        result.append(level3)
    return tuple(result)


def flattened_signature(path: np.ndarray, depth: int, log_signature: bool) -> np.ndarray:
    """Return one exact flattened signature representation."""

    levels = (
        truncated_logsignature(path, depth)
        if log_signature
        else truncated_signature(path, depth)
    )
    return np.concatenate([level.reshape(-1) for level in levels])


def batch_signature(paths: np.ndarray, depth: int, log_signature: bool) -> np.ndarray:
    """Compute exact flattened representations for a batch of normalized paths."""

    return np.vstack(
        [flattened_signature(path, depth, log_signature) for path in paths]
    )
