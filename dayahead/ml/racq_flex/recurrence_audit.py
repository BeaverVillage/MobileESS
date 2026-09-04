"""Pure recurrence-gate decision used by audits and unit tests."""

from __future__ import annotations


def recurrence_gate(
    median_recurring_GPU_h_share: float,
    median_R2_relative_brier_improvement: float,
    bootstrap_CI95: tuple[float, float],
    account_hash_stability_pass: bool,
) -> bool:
    """Apply the preregistered four-part RACQ recurrence gate."""

    return bool(
        median_recurring_GPU_h_share >= 0.20
        and median_R2_relative_brier_improvement >= 0.02
        and bootstrap_CI95[0] > 0.0
        and account_hash_stability_pass
    )
