"""Mathematical error summaries for C1 endpoint-secant equalities."""

from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from dayahead.v28r2.c1_affine import AffineCoefficient


def summarize(coefficients: Iterable[AffineCoefficient], *, site_rating_kw: float, aggregate_rating_kw: float) -> dict[str, object]:
    rows = tuple(coefficients)
    by_slot: dict[int, float] = defaultdict(float)
    for row in rows:
        by_slot[row.slot] += row.maximum_error_kw
    max_site = max(row.maximum_error_kw for row in rows)
    max_aggregate = max(by_slot.values())
    min_conservatism = min(row.minimum_conservatism_kw for row in rows)
    site_threshold = 0.01 * site_rating_kw
    aggregate_threshold = 0.01 * aggregate_rating_kw
    passed = min_conservatism >= -1e-9 and max_site <= site_threshold and max_aggregate <= aggregate_threshold
    return {
        "status": "PASS" if passed else "FAIL_C1_AFFINE_SURROGATE_CERTIFICATION",
        "coefficient_count": len(rows),
        "minimum_conservatism_kw": min_conservatism,
        "maximum_site_error_kw": max_site,
        "maximum_aggregate_error_kw": max_aggregate,
        "site_error_threshold_kw": site_threshold,
        "aggregate_error_threshold_kw": aggregate_threshold,
        "C1_AFFINE_CONSERVATISM_READY": min_conservatism >= -1e-9,
        "C1_AFFINE_ERROR_READY": max_site <= site_threshold and max_aggregate <= aggregate_threshold,
    }
