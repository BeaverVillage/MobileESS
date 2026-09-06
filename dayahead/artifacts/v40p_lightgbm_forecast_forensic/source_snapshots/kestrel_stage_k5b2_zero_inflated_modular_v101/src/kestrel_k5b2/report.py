from __future__ import annotations
from .utils import dataframe_to_markdown

def write_report(ctx,data,res,validation):
    sel=res.selection[['target_column','family','selected_method','selection_metric','selected_validation_mae']].copy()
    frozen=res.frozen_metrics[res.frozen_metrics.method=='selected_prediction'][['target_column','family','mae','underprediction_mean','asymmetric_loss','positive_mae','positive_peak_mae']]
    wf=res.walkforward_metrics[res.walkforward_metrics.calendar_month=='ALL'][['target_column','family','mae','underprediction_mean','asymmetric_loss','positive_mae','positive_peak_mae']]
    text=f"""# Stage K5-B2 Report

## Status

**{validation['status']}**

## Method

- Fixed workload: persistence plus signed residual LightGBM; persistence is retained unless OOF MAE improves by the configured minimum margin.
- Flexible GPU-hour arrivals: zero-inflated hurdle and Tweedie models; model selection uses validation-only asymmetric loss with higher penalty on underprediction.
- Peak metric: p95 among positive events, not the unconditional p95.
- Frozen evaluation: models trained on 2024 only and tested on 2025.
- Operational sensitivity: monthly expanding-window refitting during 2025, with horizon purge at every month boundary.

## Validation-selected methods

{dataframe_to_markdown(sel,30)}

## Frozen 2025 selected-model metrics

{dataframe_to_markdown(frozen,30)}

## 2025 walk-forward selected-model metrics

{dataframe_to_markdown(wf,30)}

## Interpretation

The frozen holdout remains the primary generalization test. Walk-forward results are a separate operational sensitivity and must not be reported as the same test protocol. The flexible model is selected using an asymmetric operational loss; all ordinary MAE and event metrics are retained to make this assumption transparent.
"""
    (ctx.report_dir/'REPORT.md').write_text(text,encoding='utf-8')
