"""Post-evaluation audit only; no fitting, selection, or outcome scoring.

Run only after EVALUATION_COMPLETE.json exists.  The original receipt weights
were abbreviated pandas.Index strings.  This audit preserves those receipts
and appends full, deterministically reconstructed numeric vectors.
"""
from __future__ import annotations

import ast
import hashlib
import io
import json
import math
import sys
import tarfile
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read_json(path):
    return Path(path).read_text(encoding="utf-8")


def json_value(path):
    return json.loads(read_json(path))


def immutable_json(path, payload):
    """Append once; repeat audits must agree without rewriting the receipt."""
    path = Path(path)
    if path.exists():
        prior = json_value(path)
        require(
            {key: value for key, value in prior.items() if key != "time"} == payload,
            "EXISTING_AUDIT_RECEIPT_DIFFERS: " + path.name,
        )
        return
    output = dict(time=pd.Timestamp.now(tz="UTC").isoformat(), **payload)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(output, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write("\n")


def immutable_npz(path, arrays):
    """Preserve an existing artifact; equality is checked on every full array."""
    path = Path(path)
    if path.exists():
        with np.load(path, allow_pickle=False) as previous:
            require(set(previous.files) == set(arrays), "EXISTING_WEIGHT_KEYS_DIFFER")
            for key, value in arrays.items():
                require(
                    previous[key].dtype == value.dtype
                    and np.array_equal(previous[key], value),
                    "EXISTING_WEIGHT_VECTOR_DIFFERS: " + key,
                )
        return
    buffer = io.BytesIO()
    np.savez_compressed(buffer, **arrays)
    with path.open("xb") as stream:
        stream.write(buffer.getvalue())


def historical_functions(study):
    """Execute only the two immutable PR64 function definitions, never its CLI."""
    source_path = study.PARENT / "experiment.py"
    parsed = ast.parse(read_json(source_path), filename=str(source_path))
    definitions = [
        node
        for node in parsed.body
        if isinstance(node, ast.FunctionDef) and node.name in {"membership", "weights"}
    ]
    require(
        len(definitions) == 2
        and {node.name for node in definitions} == {"membership", "weights"},
        "INHERITED_FUNCTION_DEFINITIONS",
    )
    namespace = dict(
        np=np,
        pd=pd,
        L=study.L,
        AV=study.AV,
        ISS=study.ISS,
        DAYS=study.DAYS,
        TRAIN=study.TR,
        TZ=study.TZ,
        require=require,
    )
    module = ast.Module(body=definitions, type_ignores=[])
    exec(compile(module, str(source_path), "exec"), namespace)
    function_sha256 = {
        node.name: hashlib.sha256(ast.get_source_segment(read_json(source_path), node).encode("utf-8")).hexdigest()
        for node in definitions
    }
    return namespace["membership"], namespace["weights"], function_sha256


def audit_numeric_weights(study, y, threshold):
    original_membership, original_weights, function_hashes = historical_functions(study)
    arrays = {
        "target_days": np.asarray(study.DAYS[study.OOS], dtype="U10"),
        "issue_times_UTC": np.asarray(
            [str(study.ISS.iloc[i]) for i in study.OOS], dtype="U32"
        ),
    }
    original_string_receipts = 0
    new_string_receipts = 0
    expected_tail_support = {}
    full_numeric_values = 0
    with tarfile.open(study.PARENT / "FIT_AUDIT_BUNDLE.tar.gz", "r:gz") as bundle:
        for i in study.OOS:
            day = str(study.DAYS[i])
            cutoff = study.ISS.iloc[i]
            original_ids = np.asarray(original_membership("weighted", cutoff), dtype=np.int64)
            current_ids = np.asarray(study.membership(int(i)), dtype=np.int64)
            require(np.array_equal(original_ids, current_ids), "TEMPORAL_MEMBERSHIP_CHANGED: " + day)
            historical_vector = original_weights("weighted", original_ids, cutoff)
            current_vector = study.weights(current_ids, int(i))
            weights = np.asarray(current_vector, dtype=np.float64)
            require(
                np.array_equal(np.asarray(historical_vector, dtype=np.float64), weights),
                "TEMPORAL_WEIGHTS_CHANGED: " + day,
            )
            require(
                weights.shape == current_ids.shape
                and np.isfinite(weights).all()
                and ((weights > 0) & (weights <= 1)).all(),
                "INVALID_RECONSTRUCTED_WEIGHTS: " + day,
            )
            require(
                (study.AV.iloc[current_ids] < cutoff).all()
                and (study.ISS.iloc[current_ids] < cutoff).all()
                and study.L.split.iloc[current_ids].ne("PURGE").all(),
                "INVALID_RECONSTRUCTED_MEMBERSHIP: " + day,
            )
            name = f"fits/LGBM_weighted_c1_s20260924/{day}/MEMBERSHIP.json"
            member = bundle.extractfile(name)
            require(member is not None, "MISSING_INHERITED_RECEIPT: " + day)
            old = json.load(member)
            current = json_value(study.ROOT / "fits" / day / "MEMBERSHIP.json")
            require(old["train_days"] == study.DAYS[current_ids].tolist(), "INHERITED_DAYS: " + day)
            require(
                np.array_equal(np.asarray(current["train_day_indices"], dtype=np.int64), current_ids),
                "CURRENT_DAYS: " + day,
            )
            # The abbreviated strings cannot be parsed into complete vectors.
            # Compare their known representation, then retain separately proven
            # full numeric equality of the original and current computations.
            require(
                isinstance(old["weights"], str) and old["weights"] == str(historical_vector),
                "INHERITED_WEIGHT_REPRESENTATION: " + day,
            )
            require(
                isinstance(current["weights"], str) and current["weights"] == str(current_vector),
                "CURRENT_WEIGHT_REPRESENTATION: " + day,
            )
            original_string_receipts += 1
            new_string_receipts += 1
            tail = y[current_ids].reshape(-1) > threshold
            tail_indices = np.flatnonzero(tail)
            require(
                np.array_equal(np.asarray(current["tail_flat_indices"], dtype=np.int64), tail_indices),
                "TAIL_TRAINING_MEMBERSHIP: " + day,
            )
            distinct_tail_days = np.unique(np.repeat(current_ids, 24)[tail]).size
            supported = bool(tail.sum() >= 50 and distinct_tail_days >= 10)
            require(bool(current["tail_supported"]) == supported, "TAIL_SUPPORT_RECEIPT: " + day)
            expected_tail_support[int(i)] = supported
            arrays["train_day_indices_" + day] = current_ids
            arrays["weights_" + day] = weights
            full_numeric_values += len(weights)
    provenance = dict(
        PASS=True,
        meaning="Full numeric vectors deterministically reconstructed from frozen membership, source functions and issue times; not originally logged numeric vectors.",
        original_receipts_preserved=True,
        original_weights_serialization="pandas.Index abbreviated string via JSON default=str; never parsed as full numeric evidence",
        exact_original_vs_current_memberships=len(study.OOS),
        exact_original_vs_current_weight_vectors=len(study.OOS),
        total_numeric_weights=full_numeric_values,
        original_string_receipts_checked=original_string_receipts,
        current_string_receipts_checked=new_string_receipts,
        vector_index="Each weights_<target-day> corresponds exactly to train_day_indices_<target-day>; these indices address DAY_MEMBERSHIP.csv / immutable PR63 DAY_LEDGER.csv.",
        hourly_expansion="Each day weight is repeated 24 times in target-hour order, exactly as the unchanged training code.",
        numeric_dtype="float64",
        original_function_sha256=function_hashes,
        original_source_sha256=sha(study.PARENT / "experiment.py"),
        current_source_sha256=sha(ROOT / "study.py"),
        source_manifest_sha256=sha(ROOT / "SOURCE_MANIFEST.json"),
        immutable_day_ledger_sha256=sha(study.BASE / "DAY_LEDGER.csv"),
        inherited_fit_bundle_sha256=sha(study.PARENT / "FIT_AUDIT_BUNDLE.tar.gz"),
        TEMPORAL_POLICY_CHANGED=False,
        model_predictions_changed=False,
    )
    return arrays, provenance, expected_tail_support


def reconstruct_outputs(study, y, baseline, threshold, expected_tail_support):
    """Separate specification replay; deliberately does not call compose()."""
    require(baseline.shape == (*y.shape, 2), "BASELINE_SHAPE")
    risk = np.full(y.shape, np.nan, dtype=np.float64)
    tails = {}
    supports = {}
    for i in study.OOS:
        day = str(study.DAYS[i])
        with np.load(ROOT / "raw" / (day + ".npz"), allow_pickle=False) as raw:
            probability = np.asarray(raw["risk"])
            tail = np.asarray(raw["tail"])
            support = np.asarray(raw["supported"])
            require(
                probability.shape == (24,)
                and np.isfinite(probability).all()
                and ((probability >= 0) & (probability <= 1)).all(),
                "INVALID_RAW_RISK: " + day,
            )
            require(
                tail.shape == (24,) and np.isfinite(tail).all() and (tail >= threshold).all(),
                "INVALID_RAW_TAIL: " + day,
            )
            require(support.shape == () and support.dtype == np.dtype(bool), "INVALID_RAW_SUPPORT: " + day)
            require(bool(support) == expected_tail_support[int(i)], "RAW_TAIL_SUPPORT_DRIFT: " + day)
            risk[i] = probability
            tails[int(i)] = tail.copy()
            supports[int(i)] = bool(support)

    stored_pools = json_value(ROOT / "CALIBRATION_MEMBERSHIP.json")
    by_day = {entry["target_day"]: entry for entry in stored_pools}
    require(
        len(by_day) == len(stored_pools) == len(study.OOS)
        and set(by_day) == set(study.DAYS[study.OOS]),
        "CALIBRATION_RECEIPT_POPULATION",
    )
    predictions = {name: baseline.copy() for name in ["C0", "C1", "C2"]}
    calibration_rows = 0
    gate = 0.10
    require(study.GATE == gate, "AUDIT_GATE_SPECIFICATION_DRIFT")
    for i in study.OOS:
        day = str(study.DAYS[i])
        issue_time = study.ISS.iloc[i]
        eligible_sources = [
            int(j)
            for j in study.OOS
            if j < i and study.AV.iloc[j] < issue_time and study.L.split.iloc[j] != "PURGE"
        ]
        pool = [
            (j, hour)
            for j in eligible_sources
            for hour in range(24)
            if risk[j, hour] >= gate
        ]
        source_days = np.asarray([row[0] for row in pool], dtype=np.int64)
        source_hours = np.asarray([row[1] for row in pool], dtype=np.int64)
        unique_days = len(set(source_days.tolist()))
        supported = len(pool) >= 50 and unique_days >= 10
        delta = 0.0
        if supported:
            residuals = y[source_days, source_hours] - baseline[source_days, source_hours, 1]
            require(np.isfinite(residuals).all(), "NONFINITE_CALIBRATION_RESIDUAL: " + day)
            rank = math.ceil(0.90 * (len(residuals) + 1))
            require(1 <= rank <= len(residuals), "CALIBRATION_RANK: " + day)
            delta = max(0.0, float(np.sort(residuals)[rank - 1]))
        receipt = by_day[day]
        require(pd.Timestamp(receipt["issue"]) == issue_time, "CALIBRATION_ISSUE: " + day)
        require(
            np.array_equal(np.asarray(receipt["pool_day_indices"], dtype=np.int64), source_days)
            and np.array_equal(np.asarray(receipt["pool_hours"], dtype=np.int64), source_hours),
            "CALIBRATION_POOL_DRIFT: " + day,
        )
        require(
            receipt["N_days"] == unique_days
            and bool(receipt["supported"]) == supported
            and receipt["delta"] == delta,
            "CALIBRATION_CORRECTION_DRIFT: " + day,
        )
        require(
            (study.AV.iloc[source_days] < issue_time).all()
            and (study.ISS.iloc[source_days] < issue_time).all(),
            "IMMATURE_RECONSTRUCTED_RESIDUAL: " + day,
        )
        calibration_rows += len(pool)
        for hour in range(24):
            if risk[i, hour] >= gate:
                predictions["C1"][i, hour, 1] = baseline[i, hour, 1] + delta
                if supports[int(i)]:
                    predictions["C2"][i, hour, 1] = max(baseline[i, hour, 1], tails[int(i)][hour])
        for model in ["C1", "C2"]:
            require(
                np.array_equal(predictions[model][i, :, 0], baseline[i, :, 0]),
                "Q50_CHANGED: " + day,
            )
            outside = risk[i] < gate
            require(
                np.array_equal(predictions[model][i, outside], baseline[i, outside]),
                "OUTSIDE_GATE_CHANGED: " + day,
            )

    # Read authoritative prediction output only after the final freeze and
    # evaluation marker exist.  This calculates equality, never model metrics.
    expected_rows = []
    roles = ["DEVELOPMENT", "CALIBRATION", "EXPOSED_EVALUATION", "MAY_HISTORICAL"]
    for role in roles:
        selected = np.flatnonzero(study.L.split.eq(role) & study.L.eligible)
        for model in ["C0", "C1", "C2"]:
            q = predictions[model]
            expected_rows.append(
                pd.DataFrame(
                    dict(
                        day=np.repeat(study.DAYS[selected], 24),
                        hour=np.tile(np.arange(24), len(selected)),
                        role=role,
                        model=model,
                        actual=y[selected].reshape(-1),
                        Q50=q[selected, :, 0].reshape(-1),
                        Q90=q[selected, :, 1].reshape(-1),
                        risk=risk[selected].reshape(-1),
                    )
                )
            )
    expected = pd.concat(expected_rows, ignore_index=True)
    actual = pd.read_parquet(ROOT / "PREDICTIONS.parquet")
    keys = ["day", "hour", "role", "model"]
    require(set(actual.columns) == set(expected.columns), "PREDICTION_SCHEMA_DRIFT")
    require(not actual.duplicated(keys).any(), "DUPLICATE_PREDICTION_ROWS")
    require(len(actual) == len(expected), "PREDICTION_POPULATION_DRIFT")
    pd.testing.assert_frame_equal(
        actual[expected.columns].sort_values(keys).reset_index(drop=True),
        expected.sort_values(keys).reset_index(drop=True),
        check_dtype=False,
        check_exact=True,
        obj="independent C0/C1/C2 prediction replay",
    )
    return dict(
        raw_forecast_days=len(study.OOS),
        finite_probability_checks=24 * len(study.OOS),
        finite_tail_bound_checks=24 * len(study.OOS),
        exact_residual_pools=len(stored_pools),
        exact_residual_pool_entries=calibration_rows,
        exact_output_rows=len(actual),
        compared_columns=expected.columns.tolist(),
        direct_current_label_gating=False,
        C0_exactly_inherited=True,
        Q50_unchanged_all_arms=True,
        outside_risk_gate_exactly_unchanged=True,
        sparse_tail_support_backoff_verified=True,
        all_full_day_training_and_residual_labels_strictly_mature=True,
        composition_reimplemented_independently=True,
        calls_to_study_compose=0,
    )


def main():
    require((ROOT / "EVALUATION_COMPLETE.json").exists(), "EVALUATION_NOT_COMPLETE; audit must not run yet")
    require((ROOT / "FINAL_SELECTION_FREEZE.json").exists(), "FINAL_SELECTION_NOT_FROZEN")
    sys.path.insert(0, str(ROOT))
    import study

    # Root's transparent pre-selection amendment repairs receipt verification;
    # this runs the registered primary validation before independent checks.
    study.verify()
    require(json_value(ROOT / "VALIDATION.json")["PASS"] is True, "PRIMARY_VALIDATION_FAILED")
    marker = json_value(ROOT / "EVALUATION_COMPLETE.json")
    require(marker["prediction_sha256"] == sha(ROOT / "PREDICTIONS.parquet"), "EVALUATION_PREDICTION_HASH_DRIFT")
    require(marker["freeze_sha256"] == sha(ROOT / "FINAL_SELECTION_FREEZE.json"), "EVALUATION_FREEZE_HASH_DRIFT")
    require(
        pd.Timestamp(json_value(ROOT / "FINAL_SELECTION_FREEZE.json")["time"]) <= pd.Timestamp(marker["time"]),
        "FREEZE_AFTER_EVALUATION",
    )
    with np.load(study.BASE / "DATA.npz", allow_pickle=False) as data:
        y = data["y"].copy()
    with np.load(study.PARENT / "predictions" / "LGBM_weighted_c1_s20260924.npz", allow_pickle=False) as source:
        baseline = source["q"].copy()
    protocol = json_value(ROOT / "PROTOCOL.json")
    threshold = float(protocol["burst_threshold"]["value"])
    training = y[study.TR]
    require(float(np.quantile(training[training > 0], 0.95)) == threshold, "TRAIN_ONLY_BURST_THRESHOLD_DRIFT")
    require(np.isfinite(y).all() and (y >= 0).all(), "INVALID_TARGET_ARRAY")
    require(np.isfinite(baseline[study.OOS]).all(), "INVALID_INHERITED_BASELINE")

    arrays, provenance, tail_support = audit_numeric_weights(study, y, threshold)
    replay = reconstruct_outputs(study, y, baseline, threshold, tail_support)

    # No audit artifacts are created until every substantive check passes.
    numeric_path = ROOT / "RECONSTRUCTED_NUMERIC_TEMPORAL_MEMBERSHIP.npz"
    immutable_npz(numeric_path, arrays)
    provenance.update(artifact=numeric_path.name, artifact_sha256=sha(numeric_path))
    immutable_json(ROOT / "TEMPORAL_WEIGHT_RECONSTRUCTION.json", provenance)
    receipt = dict(
        PASS=True,
        purpose="Independent post-evaluation audit; no fitting, selection, or outcome metric calculation",
        primary_study_verify_passed=True,
        **replay,
        temporal_weight_reconstruction_manifest_sha256=sha(ROOT / "TEMPORAL_WEIGHT_RECONSTRUCTION.json"),
        prediction_sha256=sha(ROOT / "PREDICTIONS.parquet"),
        evaluation_complete_sha256=sha(ROOT / "EVALUATION_COMPLETE.json"),
        final_selection_freeze_sha256=sha(ROOT / "FINAL_SELECTION_FREEZE.json"),
        effective_study_source_sha256=sha(ROOT / "study.py"),
        auditor_source_sha256=sha(Path(__file__)),
        audit_readme_sha256=sha(Path(__file__).with_name("AUDIT_README.md")),
        outcomes_used_for_decisions=False,
        original_receipts_unchanged=True,
        model_predictions_changed=False,
        TEMPORAL_POLICY_CHANGED=False,
        NEW_ARCHITECTURE_SEARCHED=False,
        PRODUCTION_PROMOTED=False,
    )
    immutable_json(ROOT / "INDEPENDENT_AUDIT.json", receipt)
    print(
        json.dumps(
            dict(
                PASS=True,
                temporal_vectors=len(study.OOS),
                prediction_rows=replay["exact_output_rows"],
                receipt="INDEPENDENT_AUDIT.json",
            )
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
