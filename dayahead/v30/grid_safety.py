"""Pre-April no-regret margin and phase-current recourse safety model."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

import numpy as np


def derive_margin(repo: Path) -> tuple[list[dict[str, object]], dict[str, object]]:
    path = repo / "dayahead/artifacts/v29r2_anchor_aware_trust_noregret/V29R2_TRUST_CERT_FIDELITY_RESULTS.csv"
    with path.open(encoding="utf-8-sig", newline="") as stream:
        raw = list(csv.DictReader(stream))
    selected = [row for row in raw if abs(float(row["rho_AIDC"]) - 1.0) <= 1e-12]
    if not selected or any(row["day"] >= "2025-04-01" or int(row["April_rows_used"]) != 0 for row in selected):
        raise RuntimeError("V30_NOREGRET_MARGIN_PREAPRIL_FIREWALL")
    rows: list[dict[str, object]] = []
    daily_bounds = []
    for row in selected:
        candidate_error = float(row["current_error_max_pu"])
        # Both candidate and anchor use the certified model.  With no signed
        # pairwise residual ledger, triangle inequality is the valid one-sided
        # finite-support bound: e_c - e_a <= |e_c| + |e_a| <= 2 max|e|.
        bound = 2.0 * candidate_error
        daily_bounds.append(bound)
        rows.append({
            "day": row["day"], "rho_AIDC": 1.0,
            "candidate_max_abs_current_error_pu": candidate_error,
            "anchor_max_abs_current_error_bound_pu": candidate_error,
            "one_sided_candidate_minus_anchor_error_bound_pu": bound,
            "formula": "2*max_abs_planning_minus_Fresh_current_error_pu",
            "April_rows_used": 0,
        })
    margin = max(daily_bounds)
    decision = {
        "artifact_id": "V30_NOREGRET_MARGIN_DECISION_V1",
        "status": "PASS",
        "V30_NOREGRET_SAFETY_MARGIN_PU": margin,
        "formula": "max_preApril_day(2 * rho1_candidate_max_abs_planning_minus_Fresh_current_error_pu)",
        "interpretation": "one-sided candidate-minus-anchor mismatch bound by triangle inequality",
        "sample_day_count": len(selected),
        "sample_slot_support": len(selected) * 96,
        "first_day": min(row["day"] for row in selected),
        "last_day": max(row["day"] for row in selected),
        "April_rows_used": 0,
        "zero_displacement_zero_margin": True,
        "robust_constraint": "planning_delta_rho + margin * normalized_control_L1_displacement <= 0",
    }
    return rows, decision


@dataclass(frozen=True)
class PhaseCurrentSafety:
    branch_names: tuple[str, ...]
    site_sensitivity: np.ndarray
    anchor_loading: np.ndarray
    margin_pu: float

    def validate(self) -> None:
        if self.site_sensitivity.shape != (96, 12, len(self.branch_names)):
            raise ValueError("V30_CURRENT_SENSITIVITY_AXIS")
        if self.anchor_loading.shape != (96, len(self.branch_names)):
            raise ValueError("V30_CURRENT_ANCHOR_AXIS")
        if self.margin_pu < 0 or not np.isfinite(self.site_sensitivity).all():
            raise ValueError("V30_CURRENT_SAFETY_FINITE")


def load_phase_current_safety(cache_root: Path, margin_pu: float) -> PhaseCurrentSafety:
    paths = sorted((cache_root / "data").glob("*CURRENT_SENSITIVITY*.npz"))
    if len(paths) != 1:
        raise RuntimeError("V30_CURRENT_CACHE_AUTHORITY")
    cache = np.load(paths[0], allow_pickle=False)
    controls = tuple(map(str, cache["control_names"]))
    if len(controls) < 12 or not all(name.startswith("AIDC") for name in controls[:12]):
        raise RuntimeError("V30_AIDC_CONTROL_AXIS")
    result = PhaseCurrentSafety(
        tuple(map(str, cache["branch_names"])),
        np.asarray(cache["current_sensitivity_pu_per_control"], dtype=float)[:, :12, :],
        np.asarray(cache["anchor_current_loading_pu"], dtype=float),
        float(margin_pu),
    )
    result.validate()
    return result


def phase_aware_site_scores(safety: PhaseCurrentSafety, slot: int) -> np.ndarray:
    """Conservative max-branch phase-current gradient used by the LP."""

    sensitivity = safety.site_sensitivity[slot]
    active = safety.anchor_loading[slot] >= np.quantile(safety.anchor_loading[slot], 0.95)
    if not np.any(active):
        active = np.ones(len(safety.branch_names), dtype=bool)
    return np.max(sensitivity[:, active], axis=1)
