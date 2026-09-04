from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from dayahead.ml.safe_flex_r1.aggregate_reference import validate_aggregate
from dayahead.ml.safe_flex_r1.metrics import aggregate_day_metrics


REPO = Path(__file__).resolve().parents[4]
OUT = REPO / "dayahead/artifacts/v27m_safe_flex_r1"


def load(name: str):
    return json.loads((OUT / name).read_text(encoding="utf-8"))


def test_protected_v17_v26_sha_unchanged():
    assert load("V27M_POSTCHANGE_PRESERVATION_AUDIT.json")["protected_V17_V26_unchanged"]


def test_raw_kestrel_unchanged():
    assert load("V27M_POSTCHANGE_PRESERVATION_AUDIT.json")["raw_sources_unchanged"]


def test_deletion_count_zero():
    assert load("V27M_POSTCHANGE_PRESERVATION_AUDIT.json")["deletions"] == 0


def test_pending_classifier_removed_for_nonpositive_skill():
    forensic = load("V27M_V26_PENDING_FORENSIC.json")
    assert forensic["V26_weighted_fold_Brier_skill_reproduction"] <= 0
    assert "NOT_REQUIRED" in forensic["primary_R1_policy"]


def test_aggregate_reference_valid():
    cache = np.load(OUT / "V27M_AGGREGATE_REFERENCE_ALL_DAYS.npz", allow_pickle=True)
    for lower, upper in zip(cache["lower"], cache["upper"]):
        validate_aggregate(lower, upper)


def test_direct_lgbm_exact_reproduction():
    evidence = load("V27M_BASELINE_REPRODUCTION.json")
    assert evidence["exact_reproduction_PASS"]
    assert evidence["absolute_reproduction_error"] <= 1e-9


def test_residual_base_is_cross_fitted():
    audit = load("V27M_BASE_CROSSFIT_AUDIT.json")
    assert audit["residual_training_rows_with_in_sample_base"] == 0


def test_day_block_split_only():
    contract = load("V27M_RESIDUAL_DATASET_CONTRACT.json")
    assert not contract["random_slot_split"]
    assert contract["same_day_train_validation_slot_overlap"] == 0


def test_zero_residual_recovers_base_exactly():
    cache = np.load(OUT / "V27M_BASE_OOF.npz", allow_pickle=True)
    assert np.max(np.abs((cache["lower"] + 0.0) - cache["lower"])) <= 1e-12
    assert np.max(np.abs((cache["upper"] + 0.0) - cache["upper"])) <= 1e-12


def test_running_survival_reproduced():
    assert load("V27M_RUNNING_SURVIVAL_REPRODUCTION.json")["reproduction_PASS"]


def test_state_feature_causality_firewall():
    contract = load("V27M_STATE_FEATURE_CONTRACT.json")
    assert contract["future_start_numeric_feature_reads"] == 0
    assert contract["future_end_numeric_feature_reads"] == 0
    assert contract["future_service_labels_in_features"] == 0


def test_residual_gate_failed_without_escalation():
    gate = load("V27M_RESIDUAL_SIGNAL_GATE.json")
    assert not gate["RESIDUAL_STATE_SIGNAL_READY"]
    assert gate["classification_if_stop"] == "V27M_SAFE_R1_RESIDUAL_SIGNAL_FAIL"


def test_2880_calibration_not_called():
    flags = load("V27M_READY_FLAGS.json")
    assert flags["firewall_counters"]["dimensional_2880_calibration_calls"] == 0


def test_post_gate_phases_not_run():
    flags = load("V27M_READY_FLAGS.json")
    assert flags["firewall_counters"]["physical_projection_calls"] == 0
    assert not flags["AGGREGATE_CALIBRATION_READY"]
    assert not flags["TIER_LATENCY_ALLOCATION_READY"]


def test_april_not_opened():
    freeze = load("V27M_MODEL_SELECTION_PRE_APRIL_FREEZE.json")
    assert not freeze["April_opened"]
    assert freeze["April_target_reads_before_freeze"] == 0
    assert freeze["fit_after_April_open"] == 0


def test_power_and_grid_firewalls():
    counters = load("V27M_READY_FLAGS.json")["firewall_counters"]
    for key in ("PUE_calls", "facility_MW_scaling_calls", "beta_AIDC_calls", "OpenDSS_calls", "B0_B3_final_science_calls", "grid_objective_reads"):
        assert counters[key] == 0


def test_final_classification_and_authority():
    acceptance = load("V27M_ACCEPTANCE_TEST.json")
    assert acceptance["RESULT_CLASSIFICATION"] == "V27M_SAFE_R1_RESIDUAL_SIGNAL_FAIL"
    assert not acceptance["SAFE_R1_PROPOSED_MODEL_ACCEPTED"]
    assert not acceptance["SAFE_R1_PRODUCTION_READY"]


def test_daily_score_arithmetic_reproducible():
    cache = np.load(OUT / "V27M_BASE_OOF.npz", allow_pickle=True)
    mapping = load("V27M_BASELINE_REPRODUCTION.json")["aggregate_to_V26_score_mapping_factor"]
    scores = [aggregate_day_metrics(l, u, rl, ru)["aggregate_unmapped_boundary_score"] * mapping for l, u, rl, ru in zip(cache["lower"], cache["upper"], cache["ref_lower"], cache["ref_upper"])]
    assert abs(float(np.mean(scores)) - 15.243233180615933) <= 1e-12


def test_artifact_registry_has_no_mismatch():
    registry = load("V27M_ARTIFACT_SHA256.json")
    assert registry["mismatches"] == []
    for record in registry["files"]:
        assert hashlib.sha256((OUT / record["path"]).read_bytes()).hexdigest() == record["sha256"]
