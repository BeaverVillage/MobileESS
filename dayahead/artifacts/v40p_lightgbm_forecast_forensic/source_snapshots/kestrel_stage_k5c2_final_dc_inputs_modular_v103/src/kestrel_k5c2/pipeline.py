from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

import pandas as pd
import yaml

from .burstgpt import aggregate as aggregate_burstgpt, annualize
from .context import Context
from .gru_event import infer as infer_events
from .locate import locate_inputs
from .power import build_power_parameters, apply_token_aware_inference
from .rack import derive_site_capacities, build_rack_parameters, rack_envelope
from .report import write_report
from .scenarios import build as build_scenarios
from .synthesis import load_k5a, load_k5b2_predictions, build_site_forecasts, add_power_to_fixed_forecast, pue_sensitivity
from .utils import create_review_zip, setup_logger, write_json, sha256_file, write_parquet_checked
from .validate import validate_artifacts


def run(ctx: Context) -> Path:
    for p in [ctx.run_dir, ctx.output_dir, ctx.prediction_dir, ctx.scenario_dir, ctx.report_dir, ctx.log_dir]:
        p.mkdir(parents=True, exist_ok=True)
    logger = setup_logger(ctx.log_dir / "execution.log")
    start = time.time()
    ctx.inputs = locate_inputs(ctx.config, logger)
    shutil.copy2(ctx.config_path, ctx.run_dir / "pipeline_used.yaml")
    write_json(ctx.report_dir / "input_metadata.json", {
        "k5a": ctx.inputs.k5a, "k5b2": ctx.inputs.k5b2, "k5b3": ctx.inputs.k5b3,
        "k4b": ctx.inputs.k4b, "k4d": ctx.inputs.k4d, "burstgpt_files": ctx.inputs.burstgpt_files,
    })

    year = int(ctx.config["analysis"]["year"])
    compression = ctx.config["resources"]["parquet_compression"]
    site, global_df = load_k5a(ctx.inputs.k5a, year)
    site_year = site[site.timestamp_utc.dt.year == year].copy()
    analysis_ts = pd.DatetimeIndex(global_df[global_df.timestamp_utc.dt.year == year].timestamp_utc.drop_duplicates().sort_values())
    actual_sites = sorted(site.idc_id.unique())
    if len(actual_sites) != int(ctx.config["analysis"]["idc_count"]):
        raise ValueError(f"K5-A site count is {len(actual_sites)}, expected {ctx.config['analysis']['idc_count']}")

    logger.info("Aggregating BurstGPT")
    burst = aggregate_burstgpt(ctx.inputs.burstgpt_files, ctx.config, logger)
    write_parquet_checked(burst.trace_5min_site, ctx.output_dir / "burstgpt_token_aware_trace_5min_site.parquet", index=False, compression=compression)
    burst.inventory.to_csv(ctx.output_dir / "burstgpt_file_inventory.csv", index=False, encoding="utf-8-sig")
    burst.schema_audit.to_csv(ctx.output_dir / "burstgpt_schema_audit.csv", index=False, encoding="utf-8-sig")
    burst.group_summary.to_csv(ctx.output_dir / "burstgpt_trace_group_summary.csv", index=False, encoding="utf-8-sig")

    primary_group = ctx.config["burstgpt"]["primary_trace_group"]
    annual = annualize(burst.trace_5min_site, analysis_ts, primary_group, int(ctx.config["analysis"]["interval_minutes"]))
    # Map synthetic BurstGPT partition labels to the exact K5-A IDC identifiers.
    bsites = sorted(annual.idc_id.unique())
    if len(bsites) != len(actual_sites):
        raise ValueError(f"Primary BurstGPT site coverage is {len(bsites)}, expected {len(actual_sites)}")
    mapping = dict(zip(bsites, actual_sites))
    annual["idc_id"] = annual.idc_id.map(mapping)

    capacities = derive_site_capacities(site, ctx.config)
    power = build_power_parameters(ctx.inputs.k4b, site, capacities, ctx.config)
    inference, inf_cons = apply_token_aware_inference(annual, power.inference, ctx.config)
    write_parquet_checked(inference, ctx.output_dir / "idc_inference_token_aware_2025_5min.parquet", index=False, compression=compression)
    inf_cons.to_csv(ctx.output_dir / "inference_token_energy_conservation.csv", index=False, encoding="utf-8-sig")
    if ctx.config["burstgpt"]["robustness_trace_group"] in set(burst.trace_5min_site.trace_group):
        alt = annualize(burst.trace_5min_site, analysis_ts, ctx.config["burstgpt"]["robustness_trace_group"], int(ctx.config["analysis"]["interval_minutes"]))
        alt_sites = sorted(alt.idc_id.unique())
        if len(alt_sites) != len(actual_sites):
            raise ValueError(f"Robustness BurstGPT site coverage is {len(alt_sites)}, expected {len(actual_sites)}")
        alt["idc_id"] = alt.idc_id.map(dict(zip(alt_sites, actual_sites)))
        alt, _ = apply_token_aware_inference(alt, power.inference, ctx.config)
        write_parquet_checked(alt, ctx.output_dir / "idc_inference_token_aware_2025_robustness_trace.parquet", index=False, compression=compression)

    power.paired_scenarios.to_csv(ctx.output_dir / "paired_h100_power_scenarios_corrected.csv", index=False, encoding="utf-8-sig")
    write_json(ctx.report_dir / "power_parameter_audit.json", power.audit)
    capacities.to_csv(ctx.output_dir / "idc_installed_gpu_capacity_proxy.csv", index=False, encoding="utf-8-sig")
    rack = build_rack_parameters(ctx.inputs.k4d, capacities, power.main, power.paired_scenarios, ctx.config)
    rack.to_csv(ctx.output_dir / "rack_equivalent_4pool_parameters.csv", index=False, encoding="utf-8-sig")
    env = rack_envelope(site_year, rack, inference, power.main, ctx.config)
    write_parquet_checked(env, ctx.output_dir / "idc_realized_power_envelope_2025_5min.parquet", index=False, compression=compression)
    write_parquet_checked(pue_sensitivity(env, ctx.config["power"]["pue_sensitivity"]), ctx.output_dir / "idc_power_envelope_pue_sensitivity_2025.parquet", index=False, compression=compression)

    logger.info("Inferring GRU flexible-event probabilities")
    event = infer_events(ctx.inputs.k5a, ctx.inputs.k5b2, ctx.inputs.k5b3, ctx.config, logger)
    write_parquet_checked(event.probabilities, ctx.scenario_dir / "gru_event_probabilities_2025.parquet", index=False, compression=compression)
    write_json(ctx.report_dir / "event_probability_audit.json", event.audit)
    sc = build_scenarios(event.probabilities, site, ctx.config)
    write_parquet_checked(sc.mark_library, ctx.scenario_dir / "flexible_positive_mark_library.parquet", index=False, compression=compression)
    write_parquet_checked(sc.event_hazard_wide, ctx.scenario_dir / "event_hazard_2025_wide.parquet", index=False, compression=compression)
    write_parquet_checked(sc.representative_scenarios, ctx.scenario_dir / "representative_flexible_scenarios.parquet", index=False, compression=compression)
    sc.calibration_audit.groupby("horizon_steps", as_index=False).agg(max_absolute_error=("absolute_error", "max"), mean_absolute_error=("absolute_error", "mean")).to_csv(ctx.scenario_dir / "hazard_calibration_summary.csv", index=False, encoding="utf-8-sig")

    k5b2_pred = load_k5b2_predictions(ctx.inputs.k5b2)
    fixed, flex = build_site_forecasts(site, k5b2_pred, event.probabilities, ctx.config)
    fixed = add_power_to_fixed_forecast(fixed, float(power.main.incremental_it_kw_per_gpu), ctx.config["power"]["pue_sensitivity"])
    write_parquet_checked(fixed, ctx.output_dir / "idc_fixed_forecast_2025_long.parquet", index=False, compression=compression)
    write_parquet_checked(flex, ctx.output_dir / "idc_flexible_deterministic_benchmark_2025_long.parquet", index=False, compression=compression)

    art = {
        "paired": power.paired_scenarios, "rack": rack, "envelope": env, "fixed_forecast": fixed,
        "flex_forecast": flex, "event_probabilities": event.probabilities, "hazard_audit": sc.calibration_audit,
        "inference_conservation": inf_cons, "site_capacities": capacities,
        "inference": inference, "burst_group_summary": burst.group_summary,
        "event_audit": event.audit,
    }
    validation = validate_artifacts(art, ctx.config)
    write_json(ctx.report_dir / "validation.json", validation)
    write_report(ctx.report_dir / "REPORT.md", art, validation, event.source, ctx.config)
    write_json(ctx.report_dir / "run_timing.json", {"elapsed_seconds": time.time() - start})
    shutil.copy2(ctx.package_root / "generate_flexible_scenarios.py", ctx.run_dir / "generate_flexible_scenarios.py")
    if validation["status"] != "success":
        raise RuntimeError(f"Stage K5-C2 validation failed: {validation['checks']}")

    manifest = []
    for p in sorted(ctx.run_dir.rglob("*")):
        if p.is_file():
            manifest.append({"relative_path": str(p.relative_to(ctx.run_dir)), "size_bytes": p.stat().st_size, "sha256": sha256_file(p)})
    write_json(ctx.run_dir / "manifest.json", manifest)
    review = Path(ctx.config["paths"]["work_root"]) / f"stage_k5c2_final_dc_inputs_review_{ctx.run_dir.name.split('stage_k5c2_')[-1]}.zip"
    rows = create_review_zip(ctx.run_dir, review, float(ctx.config["resources"]["review_max_file_mb"]), bool(ctx.config["resources"]["review_include_large_files"]))
    pd.DataFrame(rows).to_csv(ctx.report_dir / "review_zip_inventory.csv", index=False, encoding="utf-8-sig")
    create_review_zip(ctx.run_dir, review, float(ctx.config["resources"]["review_max_file_mb"]), bool(ctx.config["resources"]["review_include_large_files"]))
    logger.info("Stage K5-C2 success: %s", ctx.run_dir)
    logger.info("Review ZIP: %s", review)
    return review
