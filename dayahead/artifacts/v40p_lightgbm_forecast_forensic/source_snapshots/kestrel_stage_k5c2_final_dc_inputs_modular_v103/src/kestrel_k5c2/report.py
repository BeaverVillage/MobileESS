from __future__ import annotations

from pathlib import Path
import pandas as pd


def write_report(path: Path, art: dict, validation: dict, event_source: str, cfg: dict) -> None:
    paired = art["paired"]
    main = paired[paired.scenario == "median"].iloc[0]
    env = art["envelope"]
    text = f"""# Stage K5-C2 Report

## Status

**{validation['status']}**

## Scientific role

This stage assembles candidate optimization inputs. Technical integrity is validated, but flexible-event probability calibration and full 48-step fixed-load trajectory construction remain follow-on tasks. It does not retrain forecasting models. Fixed GPU demand uses the selected K5-B2 forecast. Flexible arrivals are represented by a stochastic marked-event generator conditioned on `{event_source}` event scores and development-period positive job-size marks.

## Main H100 paired power scenario

- Representative utilization: {main.representative_utilization:.6f}
- Paired empirical run: {main.paired_run_id}
- Idle IT power: {main.idle_it_kw_per_gpu:.6f} kW/GPU
- Incremental IT power: {main.incremental_it_kw_per_gpu:.6f} kW/GPU
- Gross IT power: {main.gross_it_kw_per_gpu:.6f} kW/GPU
- Effective IT power at representative utilization: {main.effective_it_kw_per_gpu_at_u_ref:.6f} kW/GPU

The low/median/high scenarios are ranked by paired effective power, not by independent marginal quantiles.

## Rack-equivalent deliverability

- IDC count: {env.idc_id.nunique()}
- Rack-equivalent pools per IDC: {cfg['analysis']['rack_pool_count']}
- Main constraints: H100-equivalent GPU capacity and rack power cap
- Thermal constraints: not imposed in the main result
- Observed active-GPU exceedance rate relative to the derived deliverable cap: {env.observed_active_exceeds_deliverable.mean():.6%}

## Inference trace

BurstGPT 1 and 2 are treated as one continuous trace group when their axes permit it. BurstGPT 3 remains a separate robustness trace. Repeated annual alignment is explicitly flagged and is not used as an ML test set. Request energy is conserved while being redistributed across time and all 12 virtual sites using input/output token work. The runtime validation requires complete 12-site coverage.

## Flexible scenarios

The GRU outputs uncalibrated cumulative event scores interpreted provisionally as probabilities of at least one positive flexible arrival by 15, 30, 60, 120, and 240 minutes. After cumulative-maximum monotonicity correction, they are converted to a non-homogeneous Poisson hazard so that the cumulative event probabilities are recovered at all five knots. Positive GPU-hour marks are sampled from the pre-2025 empirical mark library. Scenario paths are generated on demand rather than materializing an infeasibly large origin × scenario × horizon cube.

## Main output files

- `outputs/idc_realized_power_envelope_2025_5min.parquet`
- `outputs/idc_fixed_forecast_2025_long.parquet`
- `outputs/idc_flexible_deterministic_benchmark_2025_long.parquet`
- `outputs/idc_inference_token_aware_2025_5min.parquet`
- `outputs/rack_equivalent_4pool_parameters.csv`
- `scenarios/gru_event_probabilities_2025.parquet`
- `scenarios/event_hazard_2025_wide.parquet`
- `scenarios/flexible_positive_mark_library.parquet`
- `scenarios/representative_flexible_scenarios.parquet`

## Scope statements

- The 12 IDCs are virtual sites created by deterministic partitioning of real traces, not 12 independently measured Melbourne data centers.
- Eagle supplies relative rack heterogeneity, not Kestrel H100 absolute power.
- NLR GenAI supplies the H100 training/inference IT-power scale.
- NLR PUE is not a Melbourne measurement; constant PUE is retained as the main case.
- Flexible point forecasts remain benchmark inputs. The stochastic generator is provisional until out-of-fold probability calibration is added.
- The fixed forecast table contains five horizon knots (15/30/60/120/240 min), not a complete 48-step trajectory; the optimization interface must interpolate or generate the 5-minute path causally.
"""
    path.write_text(text, encoding="utf-8")
