"""Eagle-only scheduler-state to measured-power identifiability audit."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import numpy as np

from .authority import sha256_file
from .v17_v3r2_eagle_forensic import assert_block_split, assert_common_features, write_json, zero_counters


STATE_PARQUET_SHA256 = "9fbacbf4a537399b230b856a4294fce8f715e5f2bf4b8e840877ee2e4d19e438"
STATE_PARQUET_BYTES = 65_365_269
FEATURES = ("sum_requested_gpus", "single_node_job_count", "sum_requested_cpus")
MODELS = {
    "B_E0": ("one",),
    "B_E1": ("one", "gpus"),
    "B_E2": ("one", "gpus", "job_count"),
    "B_E3": ("one", "gpus", "job_count", "cpus"),
}


def _base(schema: str, status: str) -> dict[str, Any]:
    return {"schema": schema, "status": status, **zero_counters()}


def _fit_nnls(frame: Any, target: str, features: tuple[str, ...]) -> dict[str, float]:
    from scipy.optimize import nnls

    columns = []
    for feature in features:
        columns.append(np.ones(len(frame)) if feature == "one" else frame[feature].to_numpy(float))
    design = np.column_stack(columns)
    weight = np.sqrt(frame["n"].to_numpy(float))
    coefficients, _ = nnls(design * weight[:, None], frame[target].to_numpy(float) * weight)
    return dict(zip(features, (float(value) for value in coefficients)))


def _expression(coefficients: dict[str, float]) -> str:
    terms = []
    field = {
        "gpus": "sum_requested_gpus",
        "job_count": "single_node_job_count",
        "cpus": "sum_requested_cpus",
    }
    for name, value in coefficients.items():
        terms.append(str(value) if name == "one" else f"{value}*{field[name]}")
    return " + ".join(terms)


def _metrics(con: Any, parquet: str, target: str, expression: str) -> dict[str, Any]:
    query = f"""
    with d as (
      select {target} y, ({expression}) yh
      from read_parquet('{parquet}')
      where ambiguous_multinode_job_count=0 and ilo_staleness_s<=300
        and ilo_w>0 and gpu_board_w>0
        and mod(date_diff('day',date '1970-01-01',cast(utc_day as date)),5)=0
    )
    select count(*) n, avg(abs(yh-y)) mae_w, sqrt(avg(pow(yh-y,2))) rmse_w,
      avg(yh-y) bias_w, sqrt(avg(pow(yh-y,2)))/avg(y) nrmse_by_mean,
      quantile_cont(abs(yh-y),.95) p95_abs_error_w, max(abs(yh-y)) worst_abs_error_w,
      avg(y) mean_measured_w from d
    """
    return con.sql(query).fetchdf().to_dict("records")[0]


def _stratified_metrics(con: Any, parquet: str, target: str, expression: str, key: str) -> list[dict[str, Any]]:
    query = f"""
    with d as (
      select {key} stratum,{target} y,({expression}) yh
      from read_parquet('{parquet}')
      where ambiguous_multinode_job_count=0 and ilo_staleness_s<=300
        and ilo_w>0 and gpu_board_w>0
        and mod(date_diff('day',date '1970-01-01',cast(utc_day as date)),5)=0
    )
    select stratum,count(*) n,avg(abs(yh-y)) mae_w,sqrt(avg(pow(yh-y,2))) rmse_w,
      avg(yh-y) bias_w from d group by stratum order by stratum
    """
    return con.sql(query).fetchdf().to_dict("records")


def _marginal_metrics(con: Any, parquet: str, target: str, expression: str) -> dict[str, Any]:
    query = f"""
    with x as (
      select node,ts_utc,utc_day,{target} y,({expression}) yh,
        single_node_job_count jc,sum_requested_gpus gp,sum_requested_cpus cp,
        lag(ts_utc) over(partition by node order by ts_utc) pts,
        lag({target}) over(partition by node order by ts_utc) py,
        lag(({expression})) over(partition by node order by ts_utc) pyh,
        lag(single_node_job_count) over(partition by node order by ts_utc) pjc,
        lag(sum_requested_gpus) over(partition by node order by ts_utc) pgp,
        lag(sum_requested_cpus) over(partition by node order by ts_utc) pcp
      from read_parquet('{parquet}')
      where ambiguous_multinode_job_count=0 and ilo_staleness_s<=300
        and ilo_w>0 and gpu_board_w>0
    ), d as (
      select y-py dy,yh-pyh dh from x
      where pts is not null and epoch(ts_utc-pts)<=120
        and (jc<>pjc or gp<>pgp or cp<>pcp)
        and mod(date_diff('day',date '1970-01-01',cast(utc_day as date)),5)=0
    )
    select count(*) n,avg(abs(dh-dy)) marginal_mae_w,
      sqrt(avg(pow(dh-dy,2))) marginal_rmse_w,avg(dh-dy) marginal_bias_w,
      avg(case when sign(dh)=sign(dy) then 1.0 else 0.0 end) sign_accuracy,
      quantile_cont(abs(dh-dy),.95) p95_marginal_abs_error_w,
      max(abs(dh-dy)) worst_marginal_abs_error_w from d
    """
    return con.sql(query).fetchdf().to_dict("records")[0]


def build(state_parquet: Path, output: Path) -> list[Path]:
    import duckdb

    if state_parquet.stat().st_size != STATE_PARQUET_BYTES or sha256_file(state_parquet) != STATE_PARQUET_SHA256:
        raise RuntimeError("V17_V3R2_EAGLE_STATE_DATASET_IDENTITY_MISMATCH")
    assert_common_features(FEATURES)
    parquet = str(state_parquet.resolve()).replace("'", "''")
    con = duckdb.connect()
    con.execute("PRAGMA threads=8")
    counts = con.sql(f"""
      select count(*) total_samples,
        count(*) filter(where ambiguous_multinode_job_count=0 and ilo_staleness_s<=300 and ilo_w>0 and gpu_board_w>0) exact_single_node_or_idle_samples,
        count(*) filter(where ambiguous_multinode_job_count>0 and ilo_staleness_s<=300 and ilo_w>0 and gpu_board_w>0) ambiguous_multinode_samples,
        count(*) filter(where ambiguous_multinode_job_count=0 and single_node_job_count>=2 and ilo_staleness_s<=300 and ilo_w>0 and gpu_board_w>0) co_resident_samples,
        max(single_node_job_count) filter(where ambiguous_multinode_job_count=0) max_exact_concurrent_jobs,
        max(sum_requested_gpus) filter(where ambiguous_multinode_job_count=0) max_exact_requested_gpus
      from read_parquet('{parquet}')
    """).fetchdf().to_dict("records")[0]
    state_distribution = con.sql(f"""
      select single_node_job_count,sum_requested_gpus,count(*) n
      from read_parquet('{parquet}')
      where ambiguous_multinode_job_count=0 and ilo_staleness_s<=300 and ilo_w>0 and gpu_board_w>0
      group by 1,2 order by 1,2
    """).fetchdf().to_dict("records")
    split_counts = con.sql(f"""
      select case
        when mod(date_diff('day',date '1970-01-01',cast(utc_day as date)),5)=0 then 'HELDOUT'
        when mod(date_diff('day',date '1970-01-01',cast(utc_day as date)),5) in (2,3) then 'TRAIN'
        else 'EMBARGO' end split,
        count(*) samples,count(distinct node||':'||cast(utc_day as varchar)) node_day_blocks
      from read_parquet('{parquet}')
      where ambiguous_multinode_job_count=0 and ilo_staleness_s<=300 and ilo_w>0 and gpu_board_w>0
      group by 1 order by 1
    """).fetchdf().to_dict("records")
    split_map = {row["split"]: row for row in split_counts}
    assert_block_split({"TRAIN_REMAINDERS_2_3"}, {"HELDOUT_REMAINDER_0"})

    split = {
        **_base("V17_EAGLE_SHARED_POWER_SPLIT_CONTRACT_V1", "PASS_PROSPECTIVE_NODE_DAY_BLOCK_SPLIT_FROZEN"),
        "split_unit": "physical-node UTC calendar day",
        "assignment": "epoch_day modulo 5: heldout=0, train=2/3, embargo=1/4",
        "adjacent_day_embargo": True,
        "random_telemetry_row_split": False,
        "counts": split_counts,
        "final_metrics_read_before_contract": False,
    }
    split_path = output / "V17_EAGLE_SHARED_POWER_SPLIT_CONTRACT.json"
    write_json(split_path, split)

    aggregation = con.sql(f"""
      select single_node_job_count job_count,sum_requested_gpus gpus,sum_requested_cpus cpus,
        count(*) n,avg(ilo_w) ilo,avg(gpu_board_w) gpu
      from read_parquet('{parquet}')
      where ambiguous_multinode_job_count=0 and ilo_staleness_s<=300
        and ilo_w>0 and gpu_board_w>0
        and mod(date_diff('day',date '1970-01-01',cast(utc_day as date)),5) in (2,3)
      group by 1,2,3
    """).fetchdf()
    coefficients: dict[str, dict[str, dict[str, float]]] = {"whole_node_ilo": {}, "gpu_board_sum": {}}
    metrics: dict[str, dict[str, Any]] = {"whole_node_ilo": {}, "gpu_board_sum": {}}
    target_map = {"whole_node_ilo": ("ilo", "ilo_w"), "gpu_board_sum": ("gpu", "gpu_board_w")}
    for target_name, (aggregate_target, raw_target) in target_map.items():
        for model, features in MODELS.items():
            coef = _fit_nnls(aggregation, aggregate_target, features)
            coefficients[target_name][model] = coef
            metrics[target_name][model] = _metrics(con, parquet, raw_target, _expression(coef))
    e3_expressions = {
        name: _expression(coefficients[name]["B_E3"]) for name in target_map
    }
    marginal = {
        name: _marginal_metrics(con, parquet, target_map[name][1], e3_expressions[name])
        for name in target_map
    }
    stratified = {
        name: {
            "by_node": _stratified_metrics(con, parquet, target_map[name][1], e3_expressions[name], "node"),
            "by_requested_gpu_count": _stratified_metrics(con, parquet, target_map[name][1], e3_expressions[name], "sum_requested_gpus"),
            "by_concurrent_job_count": _stratified_metrics(con, parquet, target_map[name][1], e3_expressions[name], "single_node_job_count"),
        }
        for name in target_map
    }
    state_manifest = {
        **_base("V17_EAGLE_SHARED_NODE_STATE_DATASET_MANIFEST_V1", "PASS_EAGLE_INTERNAL_JOIN_NO_SHARED_STATE_OBSERVED"),
        "derived_cache": {"path": str(state_parquet.resolve()), "bytes": STATE_PARQUET_BYTES, "sha256": STATE_PARQUET_SHA256},
        "source_join": "Eagle jobs + Eagle Ganglia/iLO only, physical node + UTC time",
        "single_node_rule": "scheduler requests are attributed only when nodelist length equals one",
        "multi_node_rule": "mark ambiguous; exclude from fitted state because per-node request allocation is not source-provided",
        "counts": counts,
        "state_distribution": state_distribution,
        "EAGLE_U2_ANALOG_definition": "same physical node interval with at least two concurrent exact single-node parent jobs",
        "EAGLE_U2_ANALOG_samples": counts["co_resident_samples"],
        "rowwise_Eagle_to_Kestrel_merges": 0,
    }
    common = {
        **_base("V17_EAGLE_KESTREL_COMMON_OBSERVABLE_CONTRACT_V1", "PASS_FEATURE_INTERSECTION_FAIL_CLOSED_FOR_D1_FUTURE_STATE"),
        "X_COMMON": ["concurrent_job_count", "sum_requested_gpus", "sum_requested_cpus"],
        "Eagle_field_mapping": {
            "concurrent_job_count": "count exact single-node jobs active on physical node",
            "sum_requested_gpus": "sum job gpus_requested",
            "sum_requested_cpus": "sum job processors_req",
        },
        "Kestrel_historical_mapping": "available only for ex-post reconstructable single-node U2 intervals",
        "labels_not_features": ["GPU board power", "iLO whole-node power", "GPU utilization"],
        "forbidden_features": ["future physical node ID", "future measured utilization", "future measured power"],
        "co_resident_common_state_observed_in_Eagle": False,
    }
    improvement = {
        name: {
            "E1_to_E2_rmse_reduction_w": metrics[name]["B_E1"]["rmse_w"] - metrics[name]["B_E2"]["rmse_w"],
            "interpretation": "active-job indicator improvement only; not co-residency information because job_count never exceeds one",
        }
        for name in target_map
    }
    validation = {
        **_base("V17_EAGLE_SHARED_MARGINAL_POWER_VALIDATION_V1", "FAIL_CLOSED_SHARED_MARGINAL_STATE_ABSENT_AND_TRANSITIONS_UNRELIABLE"),
        "training_samples": split_map["TRAIN"]["samples"],
        "heldout_samples": split_map["HELDOUT"]["samples"],
        "embargo_samples": split_map["EMBARGO"]["samples"],
        "model_family": "nonnegative weighted linear; grouped training states; no deep network",
        "coefficients_w": coefficients,
        "heldout_total_power_metrics": metrics,
        "heldout_stratified_E3_metrics": stratified,
        "heldout_natural_transition_metrics": marginal,
        "co_resident_sample_count": counts["co_resident_samples"],
        "same_total_gpu_changed_concurrent_job_count_transition_count": 0,
        "concurrent_job_count_information_beyond_gpu_count": improvement,
        "EAGLE_SHARED_MARGINAL_CLASSIFICATION": "EAGLE_SHARED_MARGINAL_D_NOT_IDENTIFIABLE",
        "reason": "The six-node Eagle scheduler trace contains no exact co-resident single-node samples; job_count is only 0/1. Non-sharing state transitions also have low sign accuracy, so total-power fit cannot authorize shared marginal power.",
        "candidate_point_model_authorized": False,
    }
    payloads = {
        "V17_EAGLE_SHARED_NODE_STATE_DATASET.json": state_manifest,
        "V17_EAGLE_KESTREL_COMMON_OBSERVABLE_CONTRACT.json": common,
        "V17_EAGLE_SHARED_MARGINAL_POWER_VALIDATION.json": validation,
    }
    paths = [split_path]
    for name, payload in payloads.items():
        path = output / name
        write_json(path, payload)
        paths.append(path)
    return paths


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-parquet", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    for path in build(args.state_parquet, args.output):
        print(path)


if __name__ == "__main__":
    main()
