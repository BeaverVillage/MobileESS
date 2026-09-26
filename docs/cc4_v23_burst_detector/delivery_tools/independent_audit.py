"""Read-only forecast replay after CC4-v2.3 evaluation has completed.

Loads every saved classifier and every reused supported tail checkpoint. It
does not call study.compose(), fit any estimator, score model quality, or alter
frozen inputs. The sole output is an append-only INDEPENDENT_AUDIT.json receipt.
"""
from __future__ import annotations

import os

for key in ["OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS"]:
    os.environ[key] = "1"

import gzip
import hashlib
import json
import math
import sys
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT.parent / "cc4_v2_hourly_future_workload"
PARENT = ROOT.parent / "cc4_v22_burst_tail"
BASELINE = ROOT.parent / "cc4_v21_causal_refit_hurdle"
TAIL_ROOT = Path(os.environ.get(
    "CC4_V23_TAIL_CHECKPOINTS",
    "D:/ChatGPT/Mobile ESS 2/cc4_v22_burst_tail_pr/docs/cc4_v22_burst_tail",
))
DETECTORS = ["D1_BASE71_BALANCED", "D2_EXTENDED_BALANCED"]
ROLES = ["DEVELOPMENT", "CALIBRATION", "EXPOSED_EVALUATION", "MAY_HISTORICAL"]
BURST = 860.3532222222221


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def exact(actual, expected, message):
    require(np.array_equal(np.asarray(actual), np.asarray(expected)), message)


def freeze_audit():
    require((ROOT / "EVALUATION_COMPLETE.json").exists(), "EVALUATION_NOT_COMPLETE")
    registration = read_json(ROOT / "CODE_FREEZE.json")
    final = read_json(ROOT / "FINAL_SELECTION_FREEZE.json")
    evaluation = read_json(ROOT / "EVALUATION_COMPLETE.json")
    protocol = read_json(ROOT / "PROTOCOL.json")
    require(registration["code"] == final["code"], "CODE_CHANGED_AFTER_REGISTRATION")
    for name, expected in final["code"].items():
        require(sha(ROOT / name) == expected, "FROZEN_SOURCE_DRIFT: " + name)
    require(
        sha(ROOT / "PROTOCOL.json") == final["protocol_sha256"] == registration["protocol_sha256"],
        "PROTOCOL_HASH_DRIFT",
    )
    require(sha(ROOT / "FINAL_SELECTION_FREEZE.json") == evaluation["freeze_sha256"], "EVALUATION_FREEZE_DRIFT")
    require(sha(ROOT / "PREDICTIONS.parquet") == evaluation["prediction_sha256"], "EVALUATION_OUTPUT_DRIFT")
    require(sha(ROOT / "SELECTION_METRICS.csv") == final["selection_metrics_sha256"], "SELECTION_FILE_DRIFT")
    require(
        pd.Timestamp(registration["time"]) <= pd.Timestamp(final["time"]) <= pd.Timestamp(evaluation["time"]),
        "FREEZE_CHRONOLOGY",
    )
    require(final["current_evaluation_computed"] is False and final["May_previously_exposed"] is True,
            "EXPOSURE_DECLARATION_DRIFT")
    require(protocol["burst_threshold"]["value"] == BURST and protocol["detectors"] == DETECTORS,
            "REGISTERED_DETECTOR_OR_TARGET_DRIFT")
    sources = read_json(ROOT / "SOURCE_MANIFEST.json")["files"]
    for name, expected in sources.items():
        require(sha(ROOT.parent / name) == expected, "INHERITED_SOURCE_DRIFT: " + name)
    return final, evaluation, protocol, len(sources)


def data_audit():
    with np.load(BASE / "DATA.npz", allow_pickle=False) as source:
        x, y, days = (source[name].copy() for name in ["X", "y", "days"])
    days = days.astype(str)
    ledger = pd.read_csv(BASE / "DAY_LEDGER.csv")
    exact(days, ledger.target_day.astype(str), "LEDGER_ALIGNMENT")
    require(len(days) == 443 and np.all(days[1:] > days[:-1]), "DATE_POPULATION_OR_ORDER")
    issue = pd.to_datetime(ledger.issue_time, utc=True)
    matured = pd.to_datetime(ledger.label_matured_at, utc=True)
    require((issue.diff().dropna() > pd.Timedelta(0)).all(), "NONCHRONOLOGICAL_ISSUES")
    oos = np.flatnonzero(days >= "2024-09-01")
    require(len(oos) == 273, "OOS_POPULATION")
    train = np.flatnonzero(ledger.split.eq("TRAIN") & ledger.eligible)
    positive = y[train][y[train] > 0]
    require(float(np.quantile(positive, 0.95)) == BURST, "TRAIN_THRESHOLD_RECONSTRUCTION")
    require((matured.iloc[train] < issue.iloc[oos[0]]).all(), "THRESHOLD_LABEL_IMMATURITY")
    with np.load(BASELINE / "predictions" / "LGBM_weighted_c1_s20260924.npz", allow_pickle=False) as source:
        baseline = source["q"].copy()
    with np.load(ROOT / "FEATURES.npz", allow_pickle=False) as source:
        extended = source["X_extended" if "X_extended" in source.files else "X"].copy()
    feature_receipt = read_json(ROOT / "FEATURE_RECEIPT.json")
    require(sha(ROOT / "FEATURES.npz") == feature_receipt["feature_sha256"], "FEATURE_ARTIFACT_HASH")
    require(sha(ROOT / "causal_features.py") == feature_receipt["feature_source_sha256"], "FEATURE_SOURCE_HASH")
    exact(extended[:, :, :71], x, "INHERITED_71_FEATURES_CHANGED")
    require(np.isfinite(extended).all() and np.isfinite(baseline[oos]).all(), "NONFINITE_SOURCE")
    sys.path.insert(0, str(ROOT))
    from causal_features import build_features

    rebuilt, names, audit, membership = build_features(BASE)
    exact(extended, rebuilt, "FEATURE_VALUE_RECONSTRUCTION")
    require(names == read_json(ROOT / "FEATURE_NAMES.json"), "FEATURE_NAME_RECONSTRUCTION")
    require(membership == read_json(ROOT / "FEATURE_MEMBERSHIP.json"), "FEATURE_MEMBERSHIP_RECONSTRUCTION")
    require(audit == read_json(ROOT / "FEATURE_AVAILABILITY_AUDIT.json"), "FEATURE_AVAILABILITY_RECONSTRUCTION")
    return x, extended, y, days, ledger, issue, matured, oos, baseline


def valid_probability(values, message):
    require(values.shape == (24,) and np.isfinite(values).all()
            and ((values >= 0) & (values <= 1)).all(), message)


def replay_models(x, extended, y, days, ledger, issue, matured, oos, protocol):
    """Independently reconstruct membership/weights/alpha and saved predictions."""
    risk = {name: np.full(y.shape, np.nan) for name in DETECTORS + ["D0_OLD"]}
    levels = protocol["tail_quantile_grid"]
    grid = read_json(PARENT / "PROTOCOL.json")["C2"]["grid"]
    require(grid == [0.1, 0.25, 0.5, 0.75, 0.9] and levels == [0.5, 0.75, 0.9], "TAIL_LEVEL_DRIFT")
    selected_columns = [grid.index(level) for level in levels]
    manifest = {row["path"]: row["sha256"] for row in read_json(PARENT / "MODEL_CHECKPOINT_MANIFEST.json")["files"]}
    tail = np.full((*y.shape, len(levels)), np.nan)
    supported = np.zeros(len(days), dtype=bool)
    classifier_count = tail_count = numeric_weight_count = 0
    membership_hashes = {}
    model_hashes = {}
    for sequence, i in enumerate(oos, 1):
        day = str(days[i])
        cutoff = issue.iloc[i]
        ids = np.flatnonzero((matured < cutoff) & (issue < cutoff) & ledger.split.ne("PURGE"))
        age = (cutoff - pd.to_datetime(days[ids], utc=True)).total_seconds() / 86400
        day_weights = np.asarray(np.exp2(-np.maximum(age, 0) / 30), dtype=np.float64)
        target = (y[ids].reshape(-1) > BURST).astype(int)
        hourly_weights = np.repeat(day_weights, 24)
        require(np.unique(target).size == 2, "CLASS_SUPPORT: " + day)
        alpha = float(hourly_weights[target == 0].sum() / hourly_weights[target == 1].sum())
        require(np.isfinite(alpha) and alpha > 0, "INVALID_BALANCE_FACTOR: " + day)
        folder = ROOT / "fits" / day
        receipt = read_json(folder / "RECEIPT.json")
        require(pd.Timestamp(receipt["issue"]) == cutoff and receipt["day_index"] == int(i), "FIT_ISSUE: " + day)
        require(receipt["N_train_days"] == len(ids) and receipt["alpha"] == alpha, "ALPHA_OR_SUPPORT: " + day)
        require(pd.Timestamp(receipt["latest_maturity"]) == matured.iloc[ids].max(), "LATEST_MATURITY: " + day)
        with np.load(folder / "TRAIN_MEMBERSHIP.npz", allow_pickle=False) as recorded:
            exact(recorded["day_indices"], ids, "TRAIN_MEMBERSHIP: " + day)
            exact(recorded["weights"], day_weights, "RECENCY_WEIGHTS: " + day)
            exact(recorded["burst_flat_indices"], np.flatnonzero(target), "CLASS_LABEL_MEMBERSHIP: " + day)
        require((matured.iloc[ids] < cutoff).all() and (issue.iloc[ids] < cutoff).all(), "IMMATURE_TRAIN: " + day)
        require(sha(folder / "TRAIN_MEMBERSHIP.npz") == receipt["membership_sha256"], "MEMBERSHIP_HASH: " + day)
        membership_hashes[day] = receipt["membership_sha256"]
        numeric_weight_count += len(day_weights)
        require(receipt["feature_sha256"] == sha(ROOT / "FEATURES.npz"), "FIT_FEATURE_HASH: " + day)
        raw_path = ROOT / "raw" / (day + ".npz")
        require(sha(raw_path) == receipt["prediction_sha256"], "RAW_PREDICTION_HASH: " + day)
        with np.load(raw_path, allow_pickle=False) as data:
            raw = {name: data[name].copy() for name in data.files}
        require(set(raw) == set(DETECTORS + ["D0_OLD", "tail", "tail_supported"]), "RAW_SCHEMA: " + day)
        require(set(receipt["models"]) == {name + ".txt.gz" for name in DETECTORS}, "CLASSIFIER_MANIFEST: " + day)
        for name, features in zip(DETECTORS, [x, extended]):
            model_path = folder / (name + ".txt.gz")
            digest = sha(model_path)
            require(digest == receipt["models"][model_path.name], "CLASSIFIER_HASH: " + day + "/" + name)
            model = lgb.Booster(model_str=gzip.decompress(model_path.read_bytes()).decode())
            require(model.num_feature() == features.shape[2], "CLASSIFIER_FEATURE_WIDTH: " + day + "/" + name)
            q = np.asarray(model.predict(features[i], num_threads=1), dtype=float)
            valid_probability(q, "UNADJUSTED_CLASSIFIER_PROBABILITY: " + day + "/" + name)
            # Independent inverse class-prior odds reconstruction. No use of
            # study.corrected_probability() or any fitted-model quality metric.
            prediction = q / (alpha - (alpha - 1) * q)
            valid_probability(prediction, "ADJUSTED_CLASSIFIER_PROBABILITY: " + day + "/" + name)
            exact(raw[name], prediction, "CLASSIFIER_PROBABILITY_REPLAY: " + day + "/" + name)
            risk[name][i] = prediction
            model_hashes[day + "/" + name] = digest
            classifier_count += 1

        old_receipt = read_json(PARENT / "fits" / day / "MEMBERSHIP.json")
        exact(old_receipt["train_day_indices"], ids, "TAIL_TRAIN_MEMBERSHIP: " + day)
        exact(old_receipt["tail_flat_indices"], np.flatnonzero(target), "TAIL_LABEL_MEMBERSHIP: " + day)
        tail_days = np.unique(np.repeat(ids, 24)[target.astype(bool)]).size
        support = bool(target.sum() >= 50 and tail_days >= 10)
        require(support == old_receipt["tail_supported"], "INHERITED_TAIL_SUPPORT: " + day)
        require(raw["tail_supported"].shape == () and raw["tail_supported"].dtype == np.dtype(bool)
                and bool(raw["tail_supported"]) == support, "TAIL_SUPPORT: " + day)
        supported[i] = support
        with np.load(PARENT / "raw" / (day + ".npz"), allow_pickle=False) as old_raw:
            old_risk = old_raw["risk"].copy()
            old_bound = old_raw["tail"].copy()
        valid_probability(old_risk, "OLD_DETECTOR_PROBABILITY: " + day)
        exact(raw["D0_OLD"], old_risk, "OLD_DETECTOR_DRIFT: " + day)
        risk["D0_OLD"][i] = old_risk
        full = np.full((24, len(grid)), BURST)
        expected_sources = set()
        if support:
            for k, quantile in enumerate(grid):
                relative = f"fits/{day}/tail_{quantile}.txt.gz"
                expected_sources.add(relative)
                model_path = TAIL_ROOT / relative
                digest = sha(model_path)
                require(digest == manifest[relative] == receipt["tail_sources"][relative], "TAIL_SOURCE_HASH: " + relative)
                model = lgb.Booster(model_str=gzip.decompress(model_path.read_bytes()).decode())
                require(model.num_feature() == 71, "TAIL_FEATURE_WIDTH: " + relative)
                full[:, k] = np.maximum(BURST, np.expm1(model.predict(x[i], num_threads=1)))
                tail_count += 1
            full = np.maximum.accumulate(full, axis=1)
        require(set(receipt["tail_sources"]) == expected_sources, "TAIL_SOURCE_POPULATION: " + day)
        require(np.isfinite(full).all() and (full >= BURST).all(), "TAIL_FINITE_SUPPORT: " + day)
        exact(raw["tail"], full[:, selected_columns], "TAIL_QUANTILE_REPLAY: " + day)
        tail[i] = full[:, selected_columns]
        u = 1 - 0.1 / np.maximum(old_risk, np.finfo(float).tiny)
        reference_bound = np.asarray([
            np.interp(level, np.r_[0.0, grid], np.r_[BURST, row])
            for level, row in zip(u, full)
        ])
        exact(reference_bound, old_bound, "INHERITED_UNCONDITIONAL_TAIL_REPLAY: " + day)
        if sequence % 39 == 0 or sequence == len(oos):
            print(f"AUDIT_REPLAY {sequence}/{len(oos)} classifier_models={classifier_count} tail_models={tail_count}", flush=True)
    counts = dict(
        exact_training_memberships=len(oos), exact_recency_weight_vectors=len(oos),
        exact_numeric_training_weights=numeric_weight_count, exact_class_balance_factors=len(oos),
        exact_classifier_model_replays=classifier_count, exact_classifier_probability_values=classifier_count * 24,
        exact_frozen_tail_model_replays=tail_count, exact_frozen_tail_quantile_values=tail_count * 24,
        exact_parent_tail_bound_replays=len(oos), exact_old_detector_replays=len(oos),
        classifier_maximum_absolute_replay_difference=0.0,
        training_membership_digest=hashlib.sha256(json.dumps(membership_hashes, sort_keys=True).encode()).hexdigest(),
        classifier_digest=hashlib.sha256(json.dumps(model_hashes, sort_keys=True).encode()).hexdigest(),
    )
    return risk, tail, supported, counts


def replay_composition(final, risk, tail, supported, baseline, y, days, ledger, issue, matured, oos, protocol):
    require(set(final["choices"]) == {"C1", "C2"}, "FINAL_FAMILIES")
    outputs = {"C0": (baseline.copy(), risk["D0_OLD"], 0.1)}
    pool_entries = 0
    pool_count = 0
    for family in ["C1", "C2"]:
        config = final["choices"][family]["config"]
        require(config["family"] == family and config["detector"] in DETECTORS
                and config["threshold"] in protocol["threshold_grid"], "FROZEN_CONFIGURATION")
        threshold = config["threshold"]
        probabilities = risk[config["detector"]]
        quantiles = baseline.copy()
        proof = read_json(ROOT / (family + "_CALIBRATION_MEMBERSHIP.json"))
        if family == "C1":
            require(config["tail_quantile"] is None and len(proof) == len(oos), "C1_RECEIPT_POPULATION")
            require([row["day"] for row in proof] == days[oos].tolist(), "C1_RECEIPT_ORDER")
        else:
            require(config["tail_quantile"] in protocol["tail_quantile_grid"] and proof == [], "C2_RECIPE")
        for position, i in enumerate(oos):
            selected_hours = probabilities[i] >= threshold
            if family == "C1":
                previous = [int(j) for j in oos if j < i and matured.iloc[j] < issue.iloc[i]
                            and ledger.split.iloc[j] != "PURGE"]
                pool = [(j, hour) for j in previous for hour in range(24) if probabilities[j, hour] >= threshold]
                source_days = np.asarray([j for j, _ in pool], dtype=np.int64)
                source_hours = np.asarray([hour for _, hour in pool], dtype=np.int64)
                support = len(pool) >= 50 and len(set(source_days.tolist())) >= 10
                delta = 0.0
                if support:
                    residuals = y[source_days, source_hours] - baseline[source_days, source_hours, 1]
                    require(np.isfinite(residuals).all(), "NONFINITE_CALIBRATION_RESIDUAL")
                    rank = math.ceil(0.9 * (len(residuals) + 1))
                    require(1 <= rank <= len(residuals), "FINITE_SAMPLE_RANK")
                    delta = max(0.0, float(np.sort(residuals)[rank - 1]))
                saved = proof[position]
                exact(saved["pool_day_indices"], source_days, "RESIDUAL_DAY_MEMBERSHIP: " + days[i])
                exact(saved["pool_hours"], source_hours, "RESIDUAL_HOUR_MEMBERSHIP: " + days[i])
                require(pd.Timestamp(saved["issue"]) == issue.iloc[i] and saved["supported"] == support
                        and saved["delta"] == delta, "RESIDUAL_CORRECTION: " + days[i])
                require((matured.iloc[source_days] < issue.iloc[i]).all()
                        and (issue.iloc[source_days] < issue.iloc[i]).all(), "IMMATURE_RESIDUAL_POOL")
                quantiles[i, selected_hours, 1] = baseline[i, selected_hours, 1] + delta
                pool_count += 1
                pool_entries += len(pool)
            elif supported[i]:
                selected_tail = protocol["tail_quantile_grid"].index(config["tail_quantile"])
                quantiles[i, selected_hours, 1] = np.maximum(
                    baseline[i, selected_hours, 1], tail[i, selected_hours, selected_tail])
            exact(quantiles[i, :, 0], baseline[i, :, 0], "Q50_CHANGED: " + days[i])
            exact(quantiles[i, ~selected_hours], baseline[i, ~selected_hours], "OUTSIDE_GATE_CHANGED: " + days[i])
            require(np.isfinite(quantiles[i]).all() and (quantiles[i, :, 1] >= quantiles[i, :, 0]).all(),
                    "INVALID_COMPOSED_QUANTILES")
        outputs[family] = quantiles, probabilities, threshold

    expected_frames = []
    for role in ROLES:
        ids = np.flatnonzero(ledger.split.eq(role) & ledger.eligible)
        for model in ["C0", "C1", "C2"]:
            q, p, threshold = outputs[model]
            expected_frames.append(pd.DataFrame(dict(
                day=np.repeat(days[ids], 24), hour=np.tile(np.arange(24), len(ids)), role=role, model=model,
                actual=y[ids].reshape(-1), Q50=q[ids, :, 0].reshape(-1), Q90=q[ids, :, 1].reshape(-1),
                risk=p[ids].reshape(-1), threshold=threshold,
            )))
    expected = pd.concat(expected_frames, ignore_index=True)
    actual = pd.read_parquet(ROOT / "PREDICTIONS.parquet")
    keys = ["day", "hour", "role", "model"]
    require(set(actual.columns) == set(expected.columns) and len(actual) == len(expected), "OUTPUT_SCHEMA_OR_POPULATION")
    require(not actual.duplicated(keys).any(), "DUPLICATE_OUTPUT_ROWS")
    pd.testing.assert_frame_equal(
        actual[expected.columns].sort_values(keys).reset_index(drop=True),
        expected.sort_values(keys).reset_index(drop=True),
        check_dtype=False, check_exact=True, obj="independent full forecast replay",
    )
    return dict(
        independently_reconstructed_prediction_rows=len(expected), compared_columns=expected.columns.tolist(),
        exact_causal_residual_pools=pool_count, exact_causal_residual_pool_entries=pool_entries,
        exact_C2_gate_applications=len(oos), outside_gate_unchanged=True, Q50_unchanged=True,
        C0_predictions_exactly_inherited=True, feature_membership_reconstructed=True,
        feature_availability_reconstructed=True, calls_to_study_compose=0,
    )


def main():
    final, evaluation, protocol, source_count = freeze_audit()
    x, extended, y, days, ledger, issue, matured, oos, baseline = data_audit()
    risk, tail, supported, counts = replay_models(x, extended, y, days, ledger, issue, matured, oos, protocol)
    composition = replay_composition(final, risk, tail, supported, baseline, y, days, ledger, issue, matured, oos, protocol)
    # Check the seals once more after replay; no historical or frozen input is
    # written by this auditor, including the primary VALIDATION.json receipt.
    for name, digest in final["code"].items():
        require(sha(ROOT / name) == digest, "SOURCE_CHANGED_DURING_AUDIT")
    require(sha(ROOT / "PREDICTIONS.parquet") == evaluation["prediction_sha256"], "OUTPUT_CHANGED_DURING_AUDIT")
    require(sha(ROOT / "FINAL_SELECTION_FREEZE.json") == evaluation["freeze_sha256"], "FREEZE_CHANGED_DURING_AUDIT")
    receipt = dict(
        PASS=True, purpose="Independent post-evaluation saved-model and causal composition replay; no refitting or quality-metric selection",
        inherited_source_hashes_checked=source_count, frozen_source_hashes_checked=len(final["code"]),
        **counts, **composition,
        feature_shape=list(extended.shape), inherited_feature_columns_exactly_unchanged=71,
        prediction_sha256=sha(ROOT / "PREDICTIONS.parquet"), final_freeze_sha256=sha(ROOT / "FINAL_SELECTION_FREEZE.json"),
        evaluation_complete_sha256=sha(ROOT / "EVALUATION_COMPLETE.json"),
        independent_auditor_source_sha256=sha(Path(__file__)), feature_artifact_sha256=sha(ROOT / "FEATURES.npz"),
        models_refitted=0, model_choices_changed=False, outcome_quality_metrics_computed=False,
        TEMPORAL_POLICY_CHANGED=False, BASE_MODEL_CHANGED=False, PRODUCTION_PROMOTED=False,
    )
    destination = ROOT / "INDEPENDENT_AUDIT.json"
    if destination.exists():
        previous = read_json(destination)
        require({key: value for key, value in previous.items() if key != "time"} == receipt, "EXISTING_AUDIT_RECEIPT_DIFFERS")
    else:
        with destination.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(dict(time=pd.Timestamp.now(tz="UTC").isoformat(), **receipt), stream,
                      indent=2, ensure_ascii=False, allow_nan=False)
            stream.write("\n")
    print(json.dumps(dict(PASS=True, classifier_replays=counts["exact_classifier_model_replays"],
                          tail_replays=counts["exact_frozen_tail_model_replays"],
                          prediction_rows=composition["independently_reconstructed_prediction_rows"])), flush=True)


if __name__ == "__main__":
    main()
