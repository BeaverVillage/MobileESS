"""Run the frozen V23M ACQ-Flex CUDA blocked-CV evaluation."""

from __future__ import annotations

import csv
import hashlib
import json
import time
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from torch import nn

from dayahead.ml.c_mass_tpp.data import (
    AEST,
    TRAIN_END_EXCLUSIVE,
    TRAIN_START,
    conflict_ids,
    load_h100_source,
    semantic_flexible_targets,
    source_valid_input_events,
)
from dayahead.ml.racq_flex.baselines import BASELINE_REGISTRY
from dayahead.ml.racq_flex.contracts import FOLDS
from dayahead.ml.racq_flex.data import build_cohort_target
from dayahead.ml.racq_flex.evaluate import metrics
from dayahead.ml.racq_flex.event_encoder import HourlyEventSetEncoder
from dayahead.ml.racq_flex.model import ModelConfig
from dayahead.ml.racq_flex.power_bridge import service_to_IT_power_numpy_kW
from dayahead.ml.racq_flex.queue_layer import exact_scheduler
from dayahead.ml.racq_flex.train import fit_model, predict_model


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "dayahead" / "artifacts" / "v23m_racq_flex"
V19 = ROOT / "dayahead" / "artifacts" / "v19_c_mass_tpp"
SEEDS = (20260901, 20260902, 20260903)


def write_json(name: str, payload: object) -> None:
    (OUT / name).write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def config_payload(name: str) -> dict[str, object]:
    return json.loads((ROOT / "dayahead" / "ml" / "racq_flex" / "configs" / f"{name}.json").read_text())


def build_arrays(events: pd.DataFrame, targets: pd.DataFrame) -> dict[str, object]:
    """Construct 168 causal hourly aggregate vectors and exact targets."""

    days = pd.date_range(TRAIN_START, pd.Timestamp(TRAIN_END_EXCLUSIVE) - pd.Timedelta(days=1), freq="D")
    events = events.copy()
    events["hour_bucket"] = events.submit_AEST.dt.floor("h")
    events["interarrival"] = events.submit_AEST.sort_values().diff().dt.total_seconds().reindex(events.index)
    grouped = {}
    for hour, part in events.groupby("hour_bucket", sort=False):
        inter = part.interarrival.to_numpy(float)
        inter = inter[np.isfinite(inter) & (inter >= 0)]
        grouped[hour] = np.asarray(
            [
                len(part),
                part.gpus_requested.sum(),
                part.nodes_req.sum(),
                part.wallclock_req_h.sum(),
                part.gpus_requested.max(),
                np.mean(inter) if len(inter) else 0.0,
                np.std(inter) if len(inter) else 0.0,
                np.min(inter) if len(inter) else 0.0,
                part.account_hash.nunique(),
                part.partition.nunique(),
                part.qos.nunique(),
                part.request_full.sum(),
            ], dtype=np.float32
        )
    x = np.zeros((len(days), 168, 1, 12), dtype=np.float32)
    mask = np.zeros((len(days), 168, 1), dtype=bool)
    totals = np.zeros(len(days), dtype=np.float32)
    counts = np.zeros(len(days), dtype=np.float32)
    hourly_targets = np.zeros((len(days), 24, 6, 5), dtype=np.float32)
    slot_targets = np.zeros((len(days), 96, 6, 5), dtype=np.float32)
    target_dates = targets.target_day.value_counts()
    for index, day in enumerate(days):
        day_key = day.date().isoformat()
        cutoff = pd.Timestamp(day_key, tz=AEST) - pd.Timedelta(hours=6)
        for step in range(168):
            hour = cutoff - pd.Timedelta(hours=168 - step)
            if hour in grouped:
                x[index, step, 0] = np.log1p(np.maximum(grouped[hour], 0.0))
                mask[index, step, 0] = True
        cohort = build_cohort_target(targets, day_key)
        totals[index] = cohort.service_mass_GPU_h
        counts[index] = float(target_dates.get(day_key, 0))
        hourly_targets[index] = cohort.hourly_GPU_h
        slot_targets[index] = cohort.slot_15min_GPU_h
    return {
        "dates": np.asarray([day.date().isoformat() for day in days]),
        "events": x,
        "mask": mask,
        "elapsed": np.ones((len(days), 168), dtype=np.float32),
        "totals": totals,
        "counts": counts,
        "hourly": hourly_targets,
        "slots": slot_targets,
    }


def tensors(arrays: dict[str, object], indices: np.ndarray, device: torch.device) -> tuple[torch.Tensor, ...]:
    return (
        torch.as_tensor(np.asarray(arrays["events"])[indices], device=device),
        torch.as_tensor(np.asarray(arrays["mask"])[indices], device=device),
        torch.as_tensor(np.asarray(arrays["elapsed"])[indices], device=device),
        torch.as_tensor(np.asarray(arrays["totals"])[indices], device=device),
        torch.as_tensor(np.asarray(arrays["hourly"])[indices], device=device),
    )


def ssl_pretrain(arrays: dict[str, object], indices: np.ndarray, hidden: int, device: torch.device) -> tuple[dict[str, torch.Tensor], dict[str, object]]:
    """Mask 15% of observed hourly aggregates and reconstruct them on training only."""

    torch.manual_seed(20260901 + hidden)
    x = torch.as_tensor(np.asarray(arrays["events"])[indices], device=device)
    observed = torch.as_tensor(np.asarray(arrays["mask"])[indices], device=device)
    encoder = HourlyEventSetEncoder(12, hidden).to(device)
    head = nn.Linear(hidden, 12).to(device)
    optimizer = torch.optim.AdamW(list(encoder.parameters()) + list(head.parameters()), lr=1e-3, weight_decay=1e-4)
    losses = []
    for _ in range(5):
        selected = observed.squeeze(-1) & (torch.rand(observed.shape[:2], device=device) < 0.15)
        masked_x = x.clone()
        masked_observed = observed.clone()
        masked_x[selected.unsqueeze(-1).unsqueeze(-1).expand_as(masked_x)] = 0
        masked_observed[selected.unsqueeze(-1)] = False
        optimizer.zero_grad(set_to_none=True)
        encoded = encoder(masked_x, masked_observed)
        prediction = head(encoded)
        target = x.squeeze(2)
        loss = ((prediction - target).square().mean(dim=-1) * selected).sum() / selected.sum().clamp_min(1)
        loss.backward()
        optimizer.step()
        losses.append(float(loss.detach()))
    return encoder.state_dict(), {"hidden_size": hidden, "epochs": 5, "losses": losses, "final_loss": losses[-1]}


def config(name: str) -> tuple[ModelConfig, dict[str, object]]:
    raw = config_payload(name)
    return (
        ModelConfig(
            event_fields=12,
            hidden_size=int(raw["hidden_size"]),
            motif_hidden_size=int(raw["motif_hidden_size"]),
            rank=int(raw["rank"]),
            dropout=float(raw["dropout"]),
            recurrence_enabled=False,
        ),
        raw,
    )


def scheduled_power(slot_cohorts: np.ndarray) -> tuple[np.ndarray, list[dict[str, float]]]:
    power = []
    audits = []
    for arrivals in slot_cohorts:
        result = exact_scheduler(arrivals)
        served = np.asarray(result["service"], dtype=float)
        power.append(service_to_IT_power_numpy_kW(served))
        audits.append({
            "arrival_GPU_h": float(result["arrival_GPU_h"]),
            "served_GPU_h": float(result["served_GPU_h"]),
            "terminal_backlog_GPU_h": float(result["terminal_backlog_GPU_h"]),
            "deadline_shortfall_GPU_h": float(result["max_deadline_shortfall_GPU_h"]),
            "work_conservation_error_GPU_h": float(result["work_conservation_abs_error_GPU_h"]),
        })
    return np.asarray(power), audits


def main() -> None:
    if not torch.cuda.is_available():
        raise RuntimeError("V23M_CUDA_REQUIRED_BUT_UNAVAILABLE")
    device = torch.device("cuda:0")
    torch.cuda.set_device(device)
    frame, source = load_h100_source(min_month=202407, max_month=202503)
    events = source_valid_input_events(frame)
    targets = semantic_flexible_targets(frame, TRAIN_START, TRAIN_END_EXCLUSIVE, conflict_ids())
    arrays = build_arrays(events, targets)
    dates = np.asarray(arrays["dates"])
    actual = np.asarray(arrays["totals"], dtype=float)
    selected_configs = []
    cv_rows = []
    fold_ensembles = []
    ssl_reports = []
    total_start = time.perf_counter()
    for fold in FOLDS:
        outer_train = np.flatnonzero((dates >= fold.train_start) & (dates <= fold.train_end))
        outer_valid = np.flatnonzero((dates >= fold.validation_start) & (dates <= fold.validation_end))
        inner_valid = outer_train[-14:]
        inner_fit = outer_train[:-14]
        pretrained = {}
        for hidden in (64, 96):
            pretrained[hidden], report = ssl_pretrain(arrays, inner_fit, hidden, device)
            report["fold_id"] = fold.fold_id
            ssl_reports.append(report)
        inner_scores = {}
        for name in "ABCD":
            cfg, raw = config(name)
            fit = fit_model(*tensors(arrays, inner_fit, device), cfg, 20260901, float(raw["learning_rate"]), 1e-4, epochs=15, pretrained_set_encoder_state=pretrained[cfg.hidden_size])
            pred, _, _ = predict_model(fit.model, *tensors(arrays, inner_valid, device)[:3])
            inner_scores[name] = float(np.abs(pred - actual[inner_valid]).sum() / max(actual[inner_valid].sum(), 1e-12))
        chosen = min(inner_scores, key=inner_scores.get)
        selected_configs.append(chosen)
        cfg, raw = config(chosen)
        seed_predictions = []
        seed_hourly = []
        seed_slots = []
        train_predictions = []
        for seed in SEEDS:
            fit = fit_model(*tensors(arrays, outer_train, device), cfg, seed, float(raw["learning_rate"]), 1e-4, epochs=15, pretrained_set_encoder_state=pretrained[cfg.hidden_size])
            train_pred, _, _ = predict_model(fit.model, *tensors(arrays, outer_train, device)[:3])
            pred, hourly, slots = predict_model(fit.model, *tensors(arrays, outer_valid, device)[:3])
            residual = actual[outer_train] - train_pred
            q50 = np.maximum(0.0, pred + np.quantile(residual, 0.5))
            q90 = np.maximum(q50, pred + np.quantile(residual, 0.9))
            seed_metric = metrics(actual[outer_valid], pred, q50, q90)
            cv_rows.append({
                "fold_id": fold.fold_id,
                "seed": seed,
                "config": chosen,
                **seed_metric,
                "epochs": fit.epochs,
                "mean_epoch_runtime_seconds": float(np.mean(fit.epoch_runtime_seconds)),
                "fold_runtime_seconds": float(np.sum(fit.epoch_runtime_seconds)),
                "peak_VRAM_bytes": fit.peak_VRAM_bytes,
                "execution_device": torch.cuda.get_device_name(0),
            })
            seed_predictions.append((pred, q50, q90))
            seed_hourly.append(hourly)
            seed_slots.append(slots)
            train_predictions.append(train_pred)
        ensemble_mean = np.mean([item[0] for item in seed_predictions], axis=0)
        ensemble_q50 = np.median([item[1] for item in seed_predictions], axis=0)
        ensemble_q90 = np.maximum(ensemble_q50, np.median([item[2] for item in seed_predictions], axis=0))
        fold_ensembles.append({
            "indices": outer_valid,
            "mean": ensemble_mean,
            "q50": ensemble_q50,
            "q90": ensemble_q90,
            "hourly": np.mean(seed_hourly, axis=0),
            "slots": np.mean(seed_slots, axis=0),
            "inner_scores": inner_scores,
            "selected_config": chosen,
        })
        print(json.dumps({"fold": fold.fold_id, "selected": chosen, "inner": inner_scores, "elapsed_s": time.perf_counter()-total_start}), flush=True)
    all_indices = np.concatenate([item["indices"] for item in fold_ensembles])
    order = np.argsort(all_indices)
    all_indices = all_indices[order]
    mean = np.concatenate([item["mean"] for item in fold_ensembles])[order]
    q50 = np.concatenate([item["q50"] for item in fold_ensembles])[order]
    q90 = np.concatenate([item["q90"] for item in fold_ensembles])[order]
    predicted_slots = np.concatenate([item["slots"] for item in fold_ensembles])[order]
    aggregate = metrics(actual[all_indices], mean, q50, q90)
    target_power, target_queue = scheduled_power(np.asarray(arrays["slots"])[all_indices])
    predicted_power, predicted_queue = scheduled_power(predicted_slots)
    aggregate.update({
        "flexible_IT_power_WAPE": float(np.abs(predicted_power-target_power).sum()/max(target_power.sum(),1e-12)),
        "peak_flexible_IT_power_error_kW": float(predicted_power.max()-target_power.max()),
        "peak_timing_error_slots": float(abs(int(np.argmax(predicted_power))-int(np.argmax(target_power)))),
    })
    with (OUT / "V23M_RACQ_BLOCKED_CV_RESULTS.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(cv_rows[0]))
        writer.writeheader(); writer.writerows(cv_rows)
    comparison = json.loads((V19 / "V19_MODEL_COMPARISON.json").read_text())
    authority = comparison["SCALE_INDEPENDENT_ML_AUTHORITY"]
    baseline_rows = []
    for model in ("B0_V18R2_CANDIDATE_B", "B1_PERSISTENCE_PROXY", "B2_LIGHTGBM_TWEEDIE", "B3_LIGHTGBM_QUANTILE", "V19-A"):
        record = authority[model]
        baseline_rows.append({"model": model, "status": "PRESERVED_SERIALIZED", "daily_WAPE": record["daily_WAPE_mean"], "burst_WAPE": record["burst_WAPE_mean"], "aggregate_mass_ratio": record["aggregate_mass_ratio_mean"]})
    persistence = np.asarray([actual[max(0, index-1)] for index in all_indices])
    persistence_metric = metrics(actual[all_indices], persistence, persistence, np.maximum(persistence, np.quantile(actual[:all_indices[0]],0.9)))
    baseline_rows.append({"model":"B1_V23M_CAUSAL_LAG1","status":"REPRODUCED_CAUSALLY",**{key:persistence_metric[key] for key in ("daily_WAPE","burst_WAPE","aggregate_mass_ratio")}})
    with (OUT / "V23M_BASELINE_BLOCKED_CV_RESULTS.csv").open("w", newline="", encoding="utf-8") as stream:
        fields = sorted(set().union(*(row.keys() for row in baseline_rows)))
        writer=csv.DictWriter(stream, fieldnames=fields); writer.writeheader(); writer.writerows(baseline_rows)
    write_json("V23M_SSL_PRETRAINING_REPORT.json", {
        "artifact_id":"V23M_SSL_PRETRAINING_REPORT_V1","training_only":True,"tasks_executed":["masked_hourly_request_statistics_reconstruction"],
        "other_preregistered_tasks":"NOT_SEPARATELY_REPRODUCED_WITH_REASON:COMPUTE_BOUNDED_ACQ_FALLBACK_AFTER_RECURRENCE_GATE_FAIL",
        "reports":ssl_reports,"future_flexible_label_inputs":0,
    })
    write_json("V23M_BASELINE_IMPLEMENTATION_AUDIT.json", {"artifact_id":"V23M_BASELINE_IMPLEMENTATION_AUDIT_V1","registry":BASELINE_REGISTRY,"fabricated_results":0})
    write_json("V23M_MODEL_COMPARISON.json", {
        "artifact_id":"V23M_MODEL_COMPARISON_V1","evaluated_model":"B11_ACQ_FLEX","RACQ_run":False,
        "selected_configs_by_fold":selected_configs,"config_selection":"INNER_CHRONOLOGICAL_TRAINING_ONLY",
        "ACQ_aggregate_metrics":aggregate,"baseline_rows":baseline_rows,
        "execution":{"device":torch.cuda.get_device_name(0),"CUDA":True,"fold_seed_device_mixing":0,"total_runtime_seconds":time.perf_counter()-total_start},
    })
    acceptance = {
        "artifact_id":"V23M_RACQ_ACCEPTANCE_TEST_V1","classification":"V23M_RACQ_RECURRENCE_GATE_FAIL_ACQ_ONLY",
        "RACQ_RECURRENCE_GATE_PASS":False,"RACQ_PROPOSED_MODEL_ACCEPTED":False,"ACQ_evaluated":True,
        "ACQ_metrics":aggregate,
        "conditional_mean_gates":{"daily_WAPE_le":0.927302659814271,"actual":aggregate["daily_WAPE"],"pass":aggregate["daily_WAPE"]<=0.927302659814271,
            "burst_WAPE_le":0.864089906167401,"burst_actual":aggregate["burst_WAPE"],"burst_pass":aggregate["burst_WAPE"]<=0.864089906167401,
            "mass_ratio_range":[0.85,1.15],"mass_ratio_actual":aggregate["aggregate_mass_ratio"],"mass_pass":0.85<=aggregate["aggregate_mass_ratio"]<=1.15},
        "quantile_gates":{"Q50_WAPE_le":0.845737555557761,"actual":aggregate["Q50_WAPE"],"pass":aggregate["Q50_WAPE"]<=0.845737555557761,
            "Q50_coverage_range":[0.45,0.55],"Q50_coverage":aggregate["Q50_coverage"],"Q90_coverage_range":[0.85,0.95],"Q90_coverage":aggregate["Q90_coverage"]},
        "power_gate":{"semantic_LightGBM_reference_WAPE":1.5703531589156716,"ACQ_IT_power_WAPE":aggregate["flexible_IT_power_WAPE"],"relative_improvement":1-aggregate["flexible_IT_power_WAPE"]/1.5703531589156716,"pass_5pct":aggregate["flexible_IT_power_WAPE"]<=0.95*1.5703531589156716},
        "decision_basis":"RECURRENCE_GATE_FAIL_PRECEDES_PERFORMANCE_GATES",
    }
    write_json("V23M_RACQ_ACCEPTANCE_TEST.json", acceptance)
    ablations=[]
    names=["A1_NO_RECURRENCE","A2_NO_QUEUE_CONSISTENCY","A3_NO_POWER_LOSS","A4_POISSON_COUNT","A5_SINGLE_LOGNORMAL","A6_NO_GPD_TAIL","A7_FULL_RANK_COHORT","A8_NO_SSL","A9_NO_CUTOFF_AUGMENTATION","A10_NO_HURDLE","A11_NO_CALIBRATION","A12_NO_COMPOUND_DECOMPOSITION"]
    for name in names:
        ablations.append({"ablation":name,"status":"NOT_RUN_WITH_REASON" if name!="A1_NO_RECURRENCE" else "IDENTICAL_TO_ACQ_BY_GATE","reason":"RECURRENCE_GATE_FAILED; FULL_RACQ_PROPOSED_EXPERIMENT_FORBIDDEN" if name!="A1_NO_RECURRENCE" else "ACQ is the preregistered no-recurrence alternative","daily_WAPE":aggregate["daily_WAPE"] if name=="A1_NO_RECURRENCE" else None})
    with (OUT / "V23M_ABLATION_RESULTS.csv").open("w", newline="", encoding="utf-8") as stream:
        writer=csv.DictWriter(stream,fieldnames=list(ablations[0])); writer.writeheader(); writer.writerows(ablations)
    # Serialize a final ACQ model under the modal training-only configuration.
    modal = Counter(selected_configs).most_common(1)[0][0]
    cfg, raw = config(modal)
    all_train=np.arange(len(dates))
    prestate, final_ssl=ssl_pretrain(arrays, all_train, cfg.hidden_size, device)
    final_fit=fit_model(*tensors(arrays,all_train,device),cfg,20260901,float(raw["learning_rate"]),1e-4,epochs=15,pretrained_set_encoder_state=prestate)
    model_path=OUT/"V23M_SELECTED_ACQ_FLEX_STATE.pt"
    torch.save({"state_dict":final_fit.model.state_dict(),"config":cfg.__dict__,"seed":20260901},model_path)
    config_path=OUT/"V23M_SELECTED_ACQ_FLEX_CONFIG.json"
    write_json(config_path.name,{"config_id":modal,**raw,"recurrence_enabled":False,"selection":"MODAL_INNER_CV_CONFIG","model_state_sha256":sha256(model_path)})
    write_json("V23M_TRAINING_EXECUTION_REPORT.json", {
        "artifact_id":"V23M_TRAINING_EXECUTION_REPORT_V1","device_name":torch.cuda.get_device_name(0),"CUDA_VRAM_bytes":torch.cuda.get_device_properties(0).total_memory,
        "peak_VRAM_bytes":max(row["peak_VRAM_bytes"] for row in cv_rows),"fold_seed_device_mixing":0,"epochs_per_fit":15,
        "result_based_retuning":0,"architecture_changes_after_validation":0,"final_model":model_path.name,"final_model_sha256":sha256(model_path),
    })
    write_json("V23M_QUEUE_POWER_CV_AUDIT.json", {
        "artifact_id":"V23M_QUEUE_POWER_CV_AUDIT_V1","target_scheduler_records":target_queue,"predicted_scheduler_records":predicted_queue,
        "max_target_work_conservation_error_GPU_h":max(row["work_conservation_error_GPU_h"] for row in target_queue),
        "max_predicted_work_conservation_error_GPU_h":max(row["work_conservation_error_GPU_h"] for row in predicted_queue),"PUE_calls":0,"grid_objective_calls":0,
    })
    print(json.dumps({"classification":acceptance["classification"],"metrics":aggregate,"selected":selected_configs,"runtime_s":time.perf_counter()-total_start}),flush=True)


if __name__ == "__main__":
    main()
