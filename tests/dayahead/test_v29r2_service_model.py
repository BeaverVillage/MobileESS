from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import numpy as np

from dayahead.v29r2.service_model import (
    FEATURE_NAMES,
    RELIABILITY_TARGET,
    _sigmoid,
    conformal_quantile,
)


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "dayahead/artifacts/v29r2_anchor_aware_trust_noregret"


def test_service_feature_contract_is_cutoff_observable() -> None:
    assert FEATURE_NAMES == (
        "partition_hash", "nodes_req", "gpus_requested", "wallclock_req_hours",
        "qos_hash", "submit_epoch_days", "queue_age_hours", "submit_hour",
        "submit_day_of_week", "submit_month",
    )
    assert not {"start_time", "end_time", "wallclock_used", "nodes_used", "state"} & set(FEATURE_NAMES)


def test_bounded_link_and_finite_sample_conformal_quantile() -> None:
    values = _sigmoid(np.asarray([-100.0, 0.0, 100.0]))
    assert np.all(values >= 0) and np.all(values <= 1)
    assert values[1] == .5
    residuals = range(1, 20)
    # ceil((19 + 1) * .9) = 18, using the conservative higher order statistic.
    assert conformal_quantile(residuals, RELIABILITY_TARGET) == 18.0


def test_frozen_service_authority_passes_causal_coverage_and_nondegeneracy() -> None:
    causal = json.loads((OUT / "V29R2_EXEC_SERVICE_CAUSAL_AUDIT.json").read_text(encoding="utf-8"))
    metrics = json.loads((OUT / "V29R2_EXEC_SERVICE_MODEL_METRICS.json").read_text(encoding="utf-8"))
    authority = json.loads((OUT / "V29R2_EXEC_SERVICE_MODEL_AUTHORITY.json").read_text(encoding="utf-8"))
    assert causal["FIT_ROWS_WITH_LABEL_AVAILABLE_AFTER_CUTOFF"] == 0
    assert causal["APRIL_LABEL_ROWS_IN_PREAPRIL_FIT"] == 0
    assert causal["APRIL_SUBMIT_ROWS_IN_PREAPRIL_FIT"] == 0
    assert causal["future_actual_feature_count"] == 0
    assert metrics["status"] == authority["status"] == "PASS"
    assert metrics["aggregate_lower_bound_coverage"] >= RELIABILITY_TARGET
    assert metrics["lower_bound_degenerate"] is False
    assert metrics["lower_bound_nonzero_cohort_day_count"] > 0
    assert authority["downstream_bridge_authorized"] is True


def test_rolling_origin_bounds_hold_at_optimizer_cohort_level() -> None:
    with (OUT / "V29R2_EXEC_SERVICE_ROLLING_ORIGIN.csv").open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert rows
    assert all(row["aggregation_level"] == "D_DAY_X_COHORT" for row in rows)
    assert all(row["April_rows_used"] == "0" for row in rows)
    for row in rows:
        requested, nominal, lower = map(float, (row["H_REQ"], row["H_NOM"], row["H_LOW"]))
        assert 0 <= lower <= nominal + 1e-9 <= requested + 1e-9


def test_final_service_model_files_match_frozen_sha() -> None:
    authority = json.loads((OUT / "V29R2_EXEC_SERVICE_MODEL_AUTHORITY.json").read_text(encoding="utf-8"))
    for name, record in authority["model_files"].items():
        if isinstance(record, dict):
            path = OUT / name
            assert hashlib.sha256(path.read_bytes()).hexdigest() == record["sha256"]
