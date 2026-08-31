from __future__ import annotations

import numpy as np
import torch


def deterministic_sinkhorn(
    cost: torch.Tensor,
    epsilon: float = 0.05,
    iterations: int = 40,
) -> torch.Tensor:
    """Balanced entropic OT for computationally small event sets."""
    if cost.ndim != 2:
        raise ValueError("cost must be a matrix")
    n, m = cost.shape
    if n == 0 or m == 0:
        return torch.zeros_like(cost)
    log_kernel = -cost / epsilon
    log_a = torch.full((n,), -np.log(n), device=cost.device, dtype=cost.dtype)
    log_b = torch.full((m,), -np.log(m), device=cost.device, dtype=cost.dtype)
    u = torch.zeros_like(log_a)
    v = torch.zeros_like(log_b)
    for _ in range(iterations):
        u = log_a - torch.logsumexp(log_kernel + v.unsqueeze(0), dim=1)
        v = log_b - torch.logsumexp(log_kernel + u.unsqueeze(1), dim=0)
    return torch.exp(log_kernel + u.unsqueeze(1) + v.unsqueeze(0))


def monotone_chunked_match(
    predicted_time: np.ndarray,
    actual_time: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Memory-bounded 1-D OT-equivalent monotone matching.

    Every actual event participates.  The shorter side is quantile-expanded;
    there is no event truncation or dropped service mass.
    """
    predicted_time = np.asarray(predicted_time, dtype=float)
    actual_time = np.asarray(actual_time, dtype=float)
    if len(predicted_time) == 0 or len(actual_time) == 0:
        return np.zeros(0, dtype=np.int64), np.zeros(0, dtype=np.int64)
    length = max(len(predicted_time), len(actual_time))
    p_order = np.argsort(predicted_time, kind="mergesort")
    a_order = np.argsort(actual_time, kind="mergesort")
    p_index = np.floor(np.linspace(0, len(p_order), length, endpoint=False)).astype(int)
    a_index = np.floor(np.linspace(0, len(a_order), length, endpoint=False)).astype(int)
    return p_order[np.minimum(p_index, len(p_order) - 1)], a_order[np.minimum(a_index, len(a_order) - 1)]

