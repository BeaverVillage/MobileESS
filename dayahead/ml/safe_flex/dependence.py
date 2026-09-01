"""Training-only audit of daily workload-component dependence."""

from __future__ import annotations

import pandas as pd


def dependence_audit(frame: pd.DataFrame) -> dict[str, object]:
    """Select preregistered D0/D1/D2 using component correlation evidence."""

    columns = ["H_K_pending_GPU_h", "H_G_GPU_h", "H_N_GPU_h"]
    correlation = frame[columns].corr(method="spearman")
    off_diagonal = [abs(correlation.iloc[i, j]) for i in range(3) for j in range(i + 1, 3)]
    selected = "D2_DAY_LEVEL_BOOTSTRAP_TUPLE_COUPLING" if max(off_diagonal) >= 0.20 else "D0_CONDITIONAL_INDEPENDENCE"
    return {
        "variables": columns,
        "spearman_correlation": correlation.to_dict(),
        "maximum_absolute_off_diagonal": float(max(off_diagonal)),
        "candidates": ["D0_CONDITIONAL_INDEPENDENCE", "D1_GAUSSIAN_RESIDUAL_COPULA", "D2_DAY_LEVEL_BOOTSTRAP_TUPLE_COUPLING"],
        "selected_inner_validation_rule": selected,
        "selection_data": "PRE_APRIL_TRAINING_ONLY",
    }

