"""Fixed causal burst features from committed PR63 authorities only.

The first 71 columns are preserved exactly. No model is fitted here. Newly
derived workload features consume only strictly mature observations; missing
workload is never silently interpreted as observed zero workload.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path

import numpy as np
import pandas as pd

TZ = "Etc/GMT-10"
BURST_THRESHOLD = 860.3532222222221
WINDOWS_HOURS = (6, 12, 24)
PAST_HOURS = 168
PAST_COLUMNS = [
    "all_job_submit_count", "maturity_gated_GPUh", "mature_mask",
    "maturity_age_hours", "hour_sin", "hour_cos", "weekday_sin", "weekday_cos",
]


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def modeled_issue(day):
    return (pd.Timestamp(str(day), tz=TZ) - pd.Timedelta(hours=6)).tz_convert("UTC")


def _known_stats(values, mask):
    valid = np.asarray(values, dtype=np.float64)[np.asarray(mask, dtype=bool)]
    if not len(valid):
        return dict(sum=0.0, mean=0.0, maximum=0.0, variance=0.0, count=0, missing=1)
    require(np.isfinite(valid).all() and (valid >= 0).all(), "INVALID_OBSERVED_WORKLOAD")
    return dict(sum=float(valid.sum()), mean=float(valid.mean()), maximum=float(valid.max()),
                variance=float(valid.var(ddof=0)), count=len(valid), missing=0)


def issue_features(past, target_day, issue_time, labels, label_days,
                   label_matured_at, label_splits, burst_threshold=BURST_THRESHOLD):
    """Pure as-of feature computation, with no current/future label access.

    Returns (new_columns[24,F], names, exact_membership, feature_specification).
    `past` is the immutable PR63 [336,8] issue snapshot, not a raw future stream.
    Strict new-workload maturity is mature_mask==1 AND maturity_age_hours>0.
    """
    issue_time = pd.Timestamp(issue_time).tz_convert("UTC")
    require(issue_time == modeled_issue(target_day), "ISSUE_CLOCK_DRIFT")
    require(float(burst_threshold) == BURST_THRESHOLD, "FIXED_TRAIN_BURST_THRESHOLD_DRIFT")
    past = np.asarray(past)
    labels = np.asarray(labels)
    label_days = np.asarray(label_days).astype(str)
    availability = pd.DatetimeIndex(pd.to_datetime(label_matured_at, utc=True))
    splits = np.asarray(label_splits).astype(str)
    require(past.shape == (336, 8), "PAST_SHAPE")
    require(labels.shape == (len(label_days), 24) and len(availability) == len(label_days)
            and len(splits) == len(label_days), "HISTORICAL_LABEL_ALIGNMENT")
    require(np.isfinite(past[:, 0]).all() and (past[:, 0] >= 0).all(), "INVALID_SUBMIT_COUNTS")
    require(np.isin(past[:, 2], [0, 1]).all(), "INVALID_MATURITY_MASK")
    require(np.isfinite(past[:, 3]).all() and (past[:, 3] >= 0).all(), "INVALID_MATURITY_AGE")
    half_mature = (past[:, 2] == 1) & (past[:, 3] > 0)
    require(np.isfinite(past[half_mature, 1]).all() and (past[half_mature, 1] >= 0).all(),
            "INVALID_MATURE_HALFHOUR_WORKLOAD")
    # Every pair is one complete clock hour. A partial hour is unavailable.
    hourly_mature = half_mature.reshape(PAST_HOURS, 2).all(axis=1)
    safe_half_work = np.where(half_mature, past[:, 1], 0.0).astype(np.float64)
    hourly_work = safe_half_work.reshape(PAST_HOURS, 2).sum(axis=1)
    hourly_work = np.where(hourly_mature, hourly_work, 0.0)
    hourly_arrivals = past[:, 0].astype(np.float64).reshape(PAST_HOURS, 2).sum(axis=1)
    hourly_burst = hourly_mature & (hourly_work > burst_threshold)
    hourly_ends = pd.date_range(issue_time - pd.Timedelta(hours=PAST_HOURS - 1),
                               periods=PAST_HOURS, freq="h")
    require(hourly_ends[-1] == issue_time, "RECENT_WINDOW_BOUNDARY")

    # No target-day label is selected merely because an input timestamp is bad:
    # both the arrival-day interval and its entire label must precede the issue.
    day_starts = pd.DatetimeIndex(pd.to_datetime(label_days)).tz_localize(TZ).tz_convert("UTC")
    day_ends = day_starts + pd.Timedelta(days=1)
    historical = np.flatnonzero((availability < issue_time) & (day_ends < issue_time) & (splits != "PURGE"))
    historical_y = labels[historical]
    require(np.isfinite(historical_y).all() and (historical_y >= 0).all(), "INVALID_MATURE_DAILY_LABEL")
    historical_burst = historical_y > burst_threshold
    historical_dow = pd.DatetimeIndex(day_starts[historical]).tz_convert(TZ).dayofweek.to_numpy()
    target_dow = pd.Timestamp(str(target_day)).weekday()

    columns, names, specs = [], [], []

    def add(name, value, family, description):
        names.append("burst_" + name)
        columns.append(np.broadcast_to(np.asarray(value, dtype=np.float64), (24,)).copy())
        specs.append(dict(name=names[-1], family=family, definition=description,
                          feature_available_time="issue_time (conservative upper bound)",
                          target_hours="0..23"))

    long_work = _known_stats(hourly_work, hourly_mature)
    long_arrival_mean = float(hourly_arrivals.mean())
    for stat in ("sum", "mean", "maximum", "variance"):
        add("work_168h_" + stat, long_work[stat], "recent_workload", "Mature complete-hour GPUh " + stat + " in [issue-168h, issue).")
    add("work_168h_mature_hours", long_work["count"], "recent_support", "Number of complete hours with both half-hour workloads strictly mature.")
    add("work_168h_mature_fraction", long_work["count"] / PAST_HOURS, "recent_support", "Mature complete-hour support divided by 168.")
    add("work_168h_missing", long_work["missing"], "recent_support", "1 when no complete-hour workload is observable.")
    add("arrivals_168h_mean", long_arrival_mean, "recent_arrivals", "All-job arrivals per clock hour over 168 observed hours.")
    add("arrivals_168h_maximum", float(hourly_arrivals.max()), "recent_arrivals", "Maximum observed all-job hourly arrivals in seven days.")
    add("arrivals_168h_variance", float(hourly_arrivals.var(ddof=0)), "recent_arrivals", "Population variance of all-job hourly arrivals in seven days.")

    for window in WINDOWS_HOURS:
        recent = slice(PAST_HOURS - window, PAST_HOURS)
        preceding = slice(PAST_HOURS - 2 * window, PAST_HOURS - window)
        current = _known_stats(hourly_work[recent], hourly_mature[recent])
        previous = _known_stats(hourly_work[preceding], hourly_mature[preceding])
        arrivals = hourly_arrivals[recent]
        old_arrivals = hourly_arrivals[preceding]
        prefix = str(window) + "h_"
        for stat in ("sum", "mean", "maximum", "variance"):
            add("work_" + prefix + stat, current[stat], "recent_workload", f"{stat} of observable complete-hour GPUh in [issue-{window}h, issue); unobserved hours omitted, not counted as zero.")
        add("work_" + prefix + "mature_hours", current["count"], "recent_support", f"Complete-hour workload support in the last {window} hours.")
        add("work_" + prefix + "mature_fraction", current["count"] / window, "recent_support", f"Observable complete-hour workload fraction in the last {window} hours.")
        add("work_" + prefix + "missing", current["missing"], "recent_support", "1 when current workload-window statistics are unavailable; their numeric placeholder is zero.")
        for stat, value in [("sum", arrivals.sum()), ("mean", arrivals.mean()), ("maximum", arrivals.max()), ("variance", arrivals.var(ddof=0))]:
            add("arrivals_" + prefix + stat, float(value), "recent_arrivals", f"{stat} of observed all-job hourly submit counts in [issue-{window}h, issue).")
        burst_count = int(hourly_burst[recent].sum())
        add("count_" + str(window) + "h", burst_count, "recent_bursts", f"Strictly mature complete hours above the fixed TRAIN burst threshold in the last {window} hours; workload support is explicit.")
        add("frequency_" + str(window) + "h", burst_count / current["count"] if current["count"] else 0.0, "recent_bursts", "Observed burst count divided by mature hourly support; zero placeholder if unavailable.")
        add("work_" + prefix + "previous_mature_fraction", previous["count"] / window, "acceleration_support", f"Mature support fraction of preceding [{2*window}h,{window}h) window.")
        acceleration_valid = current["count"] > 0 and previous["count"] > 0
        add("work_" + prefix + "acceleration", current["mean"] - previous["mean"] if acceleration_valid else 0.0,
            "acceleration", "Difference between observed current-window and preceding-window mean hourly GPUh; no inferred workloads.")
        add("work_" + prefix + "acceleration_valid", int(acceleration_valid), "acceleration_support", "Both disjoint workload windows have positive observed support.")
        add("arrivals_" + prefix + "acceleration", float(arrivals.mean() - old_arrivals.mean()), "acceleration", "Difference between current and preceding all-job arrival rates; both count windows fully observable.")
        work_ratio_valid = current["count"] > 0 and long_work["count"] > 0 and long_work["mean"] > 0
        add("work_" + prefix + "to_168h_ratio", current["mean"] / long_work["mean"] if work_ratio_valid else 0.0,
            "relative_level", "Current observed hourly GPUh mean divided by seven-day observed mean; no epsilon or inferred denominator.")
        add("work_" + prefix + "ratio_valid", int(work_ratio_valid), "relative_support", "Current and long-term workloads observed and long-term mean strictly positive.")
        add("work_" + prefix + "denominator_observed_zero", int(long_work["count"] > 0 and long_work["mean"] == 0),
            "relative_support", "Separates an observed zero long-term denominator from unavailable workload support.")
        arrival_ratio_valid = long_arrival_mean > 0
        add("arrivals_" + prefix + "to_168h_ratio", float(arrivals.mean()) / long_arrival_mean if arrival_ratio_valid else 0.0,
            "relative_level", "Observed current all-job arrival rate divided by observed seven-day arrival rate.")
        add("arrivals_" + prefix + "ratio_valid", int(arrival_ratio_valid), "relative_support", "Seven-day all-job arrival denominator is positive; all count windows are observable.")

    recent_positions = np.flatnonzero(hourly_burst)
    latest_recent = hourly_ends[recent_positions[-1]] if len(recent_positions) else None
    add("time_since_recent_burst_hours", (issue_time - latest_recent).total_seconds() / 3600 if latest_recent is not None else 0.0,
        "burst_recency", "Hours since end of the latest observable burst arrival-hour within seven days; zero placeholder when unseen.")
    add("recent_burst_seen", int(latest_recent is not None), "burst_recency_support", "At least one fully mature burst hour observed in the seven-day snapshot.")

    history_row, history_hour = np.where(historical_burst)
    latest_history = None
    latest_history_source = None
    if len(history_row):
        history_ends = day_starts[historical[history_row]] + pd.to_timedelta(history_hour + 1, unit="h")
        position = int(np.argmax(history_ends.asi8))
        latest_history = history_ends[position]
        latest_history_source = dict(day_index=int(historical[history_row[position]]), hour=int(history_hour[position]))
    observed_latest = [value for value in (latest_recent, latest_history) if value is not None]
    latest = max(observed_latest) if observed_latest else None
    add("time_since_last_observed_burst_hours", (issue_time - latest).total_seconds() / 3600 if latest is not None else 0.0,
        "burst_recency", "Hours since the newest burst arrival-hour among recent mature half-hour pairs and strictly mature historical whole-day labels; dataset-start truncation applies.")
    add("historical_burst_seen", int(latest is not None), "burst_recency_support", "At least one burst is observable in either causal source; unknown age has a separate flag.")

    def frequency_features(name, count, support, definition):
        count = np.broadcast_to(np.asarray(count, dtype=np.float64), (24,))
        support = np.broadcast_to(np.asarray(support, dtype=np.float64), (24,))
        frequency = np.divide(count, support, out=np.zeros(24), where=support > 0)
        add(name + "_frequency", frequency, "historical_frequency", definition + " Unsmoothed empirical rate; zero placeholder if no support.")
        add(name + "_support_hours", support, "historical_frequency_support", "Exact number of strictly mature label hours contributing to this frequency.")
        add(name + "_missing", (support == 0).astype(int), "historical_frequency_support", "1 when no eligible causal historical label supports this frequency.")

    frequency_features("global", int(historical_burst.sum()), int(historical_burst.size), "All hours from earlier full-day labels mature strictly before issue, excluding historical PURGE days.")
    frequency_features("target_hour", historical_burst.sum(axis=0), len(historical), "Earlier fully mature observations at the known target hour-of-day.")
    weekday_rows = historical_dow == target_dow
    same_weekday = historical_burst[weekday_rows]
    frequency_features("target_weekday", int(same_weekday.sum()), int(same_weekday.size), "Earlier fully mature observations on the known target weekday, all 24 hours.")
    frequency_features("target_hour_weekday", same_weekday.sum(axis=0), int(weekday_rows.sum()), "Earlier fully mature observations sharing the known target hour and weekday.")

    x = np.stack(columns, axis=1).astype(np.float32)
    require(np.isfinite(x).all() and len(set(names)) == len(names), "DERIVED_FEATURE_FINITE_OR_NAME")
    require((availability[historical] < issue_time).all(), "HISTORICAL_FEATURE_LEAK")
    receipt = dict(
        target_day=str(target_day), issue_time=issue_time.isoformat(),
        feature_available_time=issue_time.isoformat(),
        past_halfhour_start=(issue_time - pd.Timedelta(days=7)).isoformat(),
        past_halfhour_end_exclusive=issue_time.isoformat(),
        all_job_count_source_halfhour_indices="0..335 (all completed arrival bins)",
        strictly_mature_halfhour_indices=np.flatnonzero(half_mature).tolist(),
        strictly_mature_complete_hour_indices=np.flatnonzero(hourly_mature).tolist(),
        historical_full_day_indices=historical.tolist(),
        historical_full_day_maturity_latest=availability[historical].max().isoformat() if len(historical) else None,
        historical_target_weekday_day_indices=historical[weekday_rows].tolist(),
        latest_recent_burst_hour_index=int(recent_positions[-1]) if len(recent_positions) else None,
        latest_historical_burst_source=latest_history_source,
        historical_purge_days_excluded=True,
    )
    return x, names, receipt, specs


def build_features(base_dir):
    """Return (X_extended[443,24,F], feature_names, audit, exact_membership)."""
    base = Path(base_dir).resolve()
    with np.load(base / "DATA.npz", allow_pickle=False) as data:
        original, past, labels, days = (data[key].copy() for key in ("X", "past", "y", "days"))
    days = days.astype(str)
    ledger = pd.read_csv(base / "DAY_LEDGER.csv")
    contract = json.loads((base / "FEATURE_CONTRACT.json").read_text(encoding="utf-8"))
    threshold_authority = json.loads((base / "TARGET_RECONSTRUCTION_AUDIT.json").read_text(encoding="utf-8"))
    names_original = contract["feature_names"]
    require(float(threshold_authority["TRAIN_positive_Q95_burst_threshold_GPUh"]) == BURST_THRESHOLD, "THRESHOLD_AUTHORITY_DRIFT")
    require(np.array_equal(days, ledger.target_day.astype(str)), "DAY_ALIGNMENT")
    require(original.shape == (len(days), 24, 71) and original.dtype == np.dtype("float32")
            and past.shape == (len(days), 336, 8) and labels.shape == (len(days), 24), "SOURCE_ARRAY_SHAPES")
    require(len(names_original) == 71 and np.isfinite(original).all(), "INHERITED_FEATURE_CONTRACT")
    proof = pd.read_parquet(base / "FEATURE_MATURITY_PROOF.parquet")
    require((pd.to_datetime(proof.feature_available_at, utc=True) <= pd.to_datetime(proof.issue_time, utc=True)).all(),
            "INHERITED_FEATURE_AVAILABILITY")
    require(len(proof) == len(days) * 71 and set(proof.feature) == set(names_original), "INHERITED_PROOF_COMPLETENESS")
    issues = pd.to_datetime(ledger.issue_time, utc=True)
    matured = pd.to_datetime(ledger.label_matured_at, utc=True)
    outputs, memberships, final_names, final_specs = [], [], None, None
    for index, day in enumerate(days):
        current, names, membership, specs = issue_features(
            past[index], day, issues.iloc[index], labels, days, matured, ledger.split.to_numpy(), BURST_THRESHOLD)
        if final_names is None:
            final_names, final_specs = names, specs
        require(names == final_names and specs == final_specs, "FEATURE_SCHEMA_CHANGED_BY_ISSUE")
        outputs.append(current)
        memberships.append(membership)
    additional = np.stack(outputs)
    combined = np.concatenate([original, additional], axis=2)
    all_names = names_original + final_names
    require(np.array_equal(combined[:, :, :71], original), "BASELINE_FEATURE_DRIFT")
    source_names = ["DATA.npz", "DAY_LEDGER.csv", "FEATURE_CONTRACT.json", "FEATURE_MATURITY_PROOF.parquet", "TARGET_RECONSTRUCTION_AUDIT.json", "prepare.py"]
    audit = dict(
        PASS=True, purpose="Fixed burst-detector feature development; raw LightGBM baseline remains unchanged",
        rows=len(days) * 24, days=len(days), shape=list(combined.shape), dtype=str(combined.dtype),
        inherited_feature_count=71, new_feature_count=len(final_names), feature_names=all_names,
        existing_71_features_exactly_preserved=True,
        extended_array_sha256=hashlib.sha256(combined.tobytes(order="C")).hexdigest(),
        feature_names_sha256=hashlib.sha256(json.dumps(all_names, separators=(",", ":")).encode()).hexdigest(),
        source_sha256={name: sha(base / name) for name in source_names},
        feature_module_sha256=sha(Path(__file__)),
        modeled_clock=TZ, issue_rule="D-1 18:00 fixed UTC+10; all recent windows end exactly at issue",
        burst_threshold=BURST_THRESHOLD, threshold_source="Unchanged PR63/64/67 TRAIN positive-hour empirical95th percentile; fixed supplied constant, never recomputed from evaluation",
        past_columns=PAST_COLUMNS,
        past_workload_precision="Inherited float32 half-hour GPUh; complete-hour sums computed in float64 then features stored float32",
        recent_windows_hours=list(WINDOWS_HOURS), corresponding_halfhour_bins=[12, 24, 48],
        recent_workload_rule="Only mature_mask==1 and maturity_age_hours>0; both half-hour bins must qualify for an hourly workload; unavailable hours omitted with explicit support/missing flags",
        counts_rule="All-job submit counts, including CPU jobs, observable in completed half-hour arrival bins; these are not GPU-only counts",
        acceleration_rule="Current-window mean minus immediately preceding disjoint equal-duration window mean; workload valid only with support in both",
        ratio_rule="Recent observed mean divided by 168h observed mean only with positive denominator and positive workload support; no epsilon, explicit validity/zero-denominator flags",
        history_rule="Committed hourly target labels used only when whole-day maturity<issue AND arrival-day end<issue; exclude PURGE days; exact row indices preserved",
        historical_rate_rule="Unsmoothed empirical global/hour/weekday/hour+weekday burst fractions plus exact support and missingness; all conditioning calendar values known at issue",
        unseen_last_burst="Numeric age placeholder0 with separate seen flag; history truncated at committed dataset start plus seven-day recent snapshot",
        new_feature_availability="Conservative issue_time upper bound for every added feature; exact support/masks and stricter workload cutoffs in FEATURE_MEMBERSHIP.json",
        new_feature_hour_availability_checks=len(days) * 24 * len(final_names),
        ingestion_provenance="Logical event-time/as-of reconstruction only; actual telemetry ingestion latency and mutable request versions unverified",
        model_fitting_performed=False, comparison_metrics_accessed=False,
        feature_specification=final_specs,
    )
    return combined, all_names, audit, memberships


def _write_once_json(path, value):
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write("\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", type=Path, default=Path(__file__).resolve().parent.parent / "cc4_v2_hourly_future_workload")
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parent)
    args = parser.parse_args()
    destinations = [args.output / name for name in ["FEATURES.npz", "FEATURE_NAMES.json", "FEATURE_AUDIT.json", "FEATURE_MEMBERSHIP.json"]]
    require(not any(path.exists() for path in destinations), "FEATURE_OUTPUT_ALREADY_EXISTS")
    x, names, audit, membership = build_features(args.base)
    args.output.mkdir(parents=True, exist_ok=True)
    buffer = io.BytesIO()
    np.savez_compressed(buffer, X_extended=x, feature_names=np.asarray(names), days=np.asarray([row["target_day"] for row in membership]))
    with destinations[0].open("xb") as stream:
        stream.write(buffer.getvalue())
    audit["FEATURES_npz_sha256"] = sha(destinations[0])
    _write_once_json(destinations[1], names)
    _write_once_json(destinations[2], audit)
    _write_once_json(destinations[3], membership)
    print(json.dumps(dict(PASS=True, shape=list(x.shape), new_features=len(names)-71,
                         extended_array_sha256=audit["extended_array_sha256"])), flush=True)


if __name__ == "__main__":
    main()
