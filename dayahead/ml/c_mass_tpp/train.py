from __future__ import annotations

import copy
import math
import time
from dataclasses import asdict, dataclass

import numpy as np
import torch
from torch.nn import functional as F

from .data import DailySample, event_feature_matrix
from .losses import burst_labels, negative_binomial_nll
from .mass_head import pinball_loss, tweedie_deviance
from .model import CMASSTPP, CMASSTPPConfig
from .pretrain import PretrainingResult, pretrain_event_encoder


@dataclass
class TrainingResult:
    model: CMASSTPP
    macro_mean: np.ndarray
    macro_std: np.ndarray
    variance_power: float
    p50: float
    p90: float
    pretraining: dict[str, object]
    epochs: int
    elapsed_seconds: float
    final_training_loss: float
    variant: str
    seed: int


def inverse_softplus(value: float) -> float:
    value = max(float(value), 1e-6)
    return math.log(math.expm1(value)) if value < 20 else value


def select_tweedie_variance_power(
    samples: list[DailySample], train_index: np.ndarray
) -> tuple[float, dict[str, float]]:
    split = max(14, int(len(train_index) * 0.8))
    inner_train = train_index[:split]
    inner_validation = train_index[split:]
    if len(inner_validation) == 0:
        inner_validation = train_index[-14:]
        inner_train = train_index[:-14]
    train_target = np.asarray([samples[i].daily_mass_GPU_h for i in inner_train])
    train_dow = np.asarray([
        np.datetime64(samples[i].date).astype("datetime64[D]").astype(object).weekday()
        for i in inner_train
    ])
    global_mean = float(train_target.mean())
    prediction = []
    actual = []
    for index in inner_validation:
        dow = np.datetime64(samples[index].date).astype("datetime64[D]").astype(object).weekday()
        group = train_target[train_dow == dow]
        prediction.append(float(group.mean()) if len(group) else global_mean)
        actual.append(samples[index].daily_mass_GPU_h)
    y = torch.tensor(actual, dtype=torch.float32)
    mu = torch.tensor(prediction, dtype=torch.float32)
    scores = {
        str(power): float(tweedie_deviance(y, mu, power)) for power in (1.3, 1.5, 1.7)
    }
    return float(min(scores, key=scores.get)), scores


def _normalizer(samples: list[DailySample], indices: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    matrix = np.stack([samples[i].macro_features for i in indices])
    mean = matrix.mean(axis=0).astype(np.float32)
    std = matrix.std(axis=0).astype(np.float32)
    std[std < 1e-6] = 1.0
    return mean, std


def _macro(sample: DailySample, mean: np.ndarray, std: np.ndarray) -> torch.Tensor:
    return torch.from_numpy(((sample.macro_features - mean) / std).astype(np.float32))


def _batch(
    samples: list[DailySample],
    indices: np.ndarray,
    macro_mean: np.ndarray,
    macro_std: np.ndarray,
) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]:
    selected = [samples[int(index)] for index in indices]
    maximum = max(len(sample.micro_event_features) for sample in selected)
    features = torch.zeros(len(selected), maximum, selected[0].micro_event_features.shape[1])
    ages = torch.zeros(len(selected), maximum)
    mask = torch.zeros(len(selected), maximum, dtype=torch.bool)
    macro = torch.stack([_macro(sample, macro_mean, macro_std) for sample in selected])
    for row, sample in enumerate(selected):
        length = len(sample.micro_event_features)
        features[row, :length] = torch.from_numpy(sample.micro_event_features)
        ages[row, :length] = torch.from_numpy(sample.micro_event_ages_h)
        mask[row, :length] = True
    return features, ages, macro, mask


def _initialize_output_biases(model: CMASSTPP, samples: list[DailySample], train_index: np.ndarray) -> None:
    mass = np.asarray([samples[i].daily_mass_GPU_h for i in train_index])
    counts = np.asarray([len(samples[i].target_event_mass_GPU_h) for i in train_index])
    scale = model.config.mass_scale_GPU_h
    with torch.no_grad():
        model.mass_head.mean_raw.bias.fill_(inverse_softplus(float(mass.mean() / scale)))
        model.mass_head.q50_raw.bias.fill_(inverse_softplus(float(np.quantile(mass, 0.5) / scale)))
        increment = max(float((np.quantile(mass, 0.9) - np.quantile(mass, 0.5)) / scale), 1e-6)
        model.mass_head.q90_increment_raw.bias.fill_(inverse_softplus(increment))
        model.count_mean.bias.fill_(inverse_softplus(float(counts.mean())))


def train_cmass(
    samples: list[DailySample],
    train_index: np.ndarray,
    variant: str,
    seed: int,
    k_max: int,
    pretraining_features: np.ndarray | None = None,
    pretraining_submit_seconds: np.ndarray | None = None,
    config_overrides: dict[str, object] | None = None,
    epochs: int = 6,
) -> TrainingResult:
    if variant not in {"V19-A", "V19-B", "V19-C"}:
        raise ValueError(variant)
    torch.manual_seed(seed)
    np.random.seed(seed)
    config_values: dict[str, object] = {
        "k_max": k_max,
        "use_burst_head": variant == "V19-C",
    }
    config_values.update(config_overrides or {})
    config = CMASSTPPConfig(**config_values)
    model = CMASSTPP(config)
    _initialize_output_biases(model, samples, train_index)
    pretraining_report: dict[str, object] = {
        "enabled": variant in {"V19-B", "V19-C"},
        "status": "NOT_REQUESTED_FOR_VARIANT",
    }
    if variant in {"V19-B", "V19-C"}:
        if pretraining_features is None or pretraining_submit_seconds is None:
            raise ValueError("pretraining arrays required")
        report: PretrainingResult = pretrain_event_encoder(
            model.event_encoder,
            pretraining_features,
            pretraining_submit_seconds,
            seed,
            epochs=2,
        )
        pretraining_report = {"enabled": True, "status": "PASS", **asdict(report)}
    variance_power, inner_scores = select_tweedie_variance_power(samples, train_index)
    pretraining_report["nested_inner_tweedie_scores"] = inner_scores
    macro_mean, macro_std = _normalizer(samples, train_index)
    train_mass = np.asarray([samples[i].daily_mass_GPU_h for i in train_index])
    p50 = float(np.quantile(train_mass, 0.5))
    p90 = float(np.quantile(train_mass, 0.9))
    optimizer = torch.optim.Adam(model.parameters(), lr=2e-3, weight_decay=1e-5)
    rng = np.random.default_rng(seed)
    event_subset = train_index[
        np.unique(np.linspace(0, len(train_index) - 1, min(10, len(train_index))).astype(int))
    ]
    started = time.perf_counter()
    last_loss = float("nan")
    for epoch in range(epochs):
        model.train()
        losses = []
        order = rng.permutation(train_index)
        for start in range(0, len(order), 16):
            batch_index = order[start : start + 16]
            batch_features, batch_ages, batch_macro, batch_mask = _batch(
                samples, batch_index, macro_mean, macro_std
            )
            output = model.forward_batch(
                batch_features,
                batch_ages,
                batch_macro,
                batch_mask,
                decode_events=False,
            )
            target = torch.tensor(
                [samples[int(index)].daily_mass_GPU_h for index in batch_index],
                dtype=torch.float32,
            )
            target_count = torch.tensor(
                [len(samples[int(index)].target_event_mass_GPU_h) for index in batch_index],
                dtype=torch.float32,
            )
            mass_loss = tweedie_deviance(target, output["mean"], variance_power)
            quantile_loss = pinball_loss(target, output["q50"], 0.5) + pinball_loss(
                target, output["q90"], 0.9
            )
            count_loss = negative_binomial_nll(
                target_count, output["count_mean"], output["count_dispersion"]
            )
            burst_loss = torch.zeros(())
            if variant == "V19-C":
                burst_loss = F.cross_entropy(
                    output["burst_logits"], burst_labels(target, p50, p90)
                )
            loss = mass_loss + 0.0002 * quantile_loss + 0.01 * count_loss + 0.05 * burst_loss
            optimizer.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 5.0)
            optimizer.step()
            losses.append(float(loss.detach()))
        # Deterministic sparse event-set supervision: all events on selected days,
        # all K_max queries, and no target mass truncation.
        for index in event_subset:
            sample = samples[int(index)]
            output = model.forward_one(
                torch.from_numpy(sample.micro_event_features),
                torch.from_numpy(sample.micro_event_ages_h),
                _macro(sample, macro_mean, macro_std),
                decode_events=True,
            )
            n = len(sample.target_event_mass_GPU_h)
            activity = output["activity_logit"][0]
            count_consistency = (
                torch.sigmoid(activity).sum() - output["count_mean"][0]
            ).abs()
            if n:
                selected = torch.topk(activity, k=min(n, activity.numel()), sorted=False).indices
                actual_order = np.argsort(sample.target_event_time_h, kind="mergesort")
                predicted_order = selected[torch.argsort(output["arrival_h"][0, selected])]
                length = min(len(actual_order), len(predicted_order))
                ai = torch.from_numpy(actual_order[:length]).long()
                pi = predicted_order[:length]
                event_loss = (
                    torch.abs(output["arrival_h"][0, pi] - torch.from_numpy(sample.target_event_time_h)[ai]).mean() / 24.0
                    + F.cross_entropy(output["tier_logits"][0, pi], torch.from_numpy(sample.target_event_tier)[ai])
                    + F.cross_entropy(output["latency_logits"][0, pi], torch.from_numpy(sample.target_event_latency)[ai])
                    + torch.abs(
                        torch.log1p(output["event_mass_mean"][0, pi])
                        - torch.log1p(torch.from_numpy(sample.target_event_mass_GPU_h)[ai])
                    ).mean()
                )
            else:
                event_loss = F.binary_cross_entropy_with_logits(activity, torch.zeros_like(activity))
            loss = 0.05 * event_loss + 0.001 * count_consistency
            optimizer.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 5.0)
            optimizer.step()
        last_loss = float(np.mean(losses))
    return TrainingResult(
        model=model,
        macro_mean=macro_mean,
        macro_std=macro_std,
        variance_power=variance_power,
        p50=p50,
        p90=p90,
        pretraining=pretraining_report,
        epochs=epochs,
        elapsed_seconds=float(time.perf_counter() - started),
        final_training_loss=last_loss,
        variant=variant,
        seed=seed,
    )


def predict_cmass(
    result: TrainingResult,
    samples: list[DailySample],
    indices: np.ndarray,
    decode_events: bool = True,
) -> list[dict[str, object]]:
    result.model.eval()
    records: list[dict[str, object]] = []
    with torch.no_grad():
        for index in indices:
            sample = samples[int(index)]
            output = result.model.forward_one(
                torch.from_numpy(sample.micro_event_features),
                torch.from_numpy(sample.micro_event_ages_h),
                _macro(sample, result.macro_mean, result.macro_std),
                decode_events=decode_events,
            )
            record: dict[str, object] = {
                "index": int(index),
                "date": sample.date,
                "mean": float(output["mean"][0]),
                "q50": float(output["q50"][0]),
                "q90": float(output["q90"][0]),
                "count_mean": float(output["count_mean"][0]),
                "burst_probability": torch.softmax(output["burst_logits"], -1)[0].numpy(),
            }
            if decode_events:
                query_count = output["activity_logit"].shape[-1]
                count = min(query_count, max(0, int(round(record["count_mean"]))))
                activity = output["activity_logit"][0]
                selected = torch.topk(activity, k=count, sorted=False).indices if count else torch.zeros(0, dtype=torch.long)
                record.update(
                    {
                        "arrival_h_all": output["arrival_h"][0].numpy(),
                        "tier_probability_all": torch.softmax(output["tier_logits"][0], -1).numpy(),
                        "latency_probability_all": torch.softmax(output["latency_logits"][0], -1).numpy(),
                        "event_mass_mean_all": output["event_mass_mean"][0].numpy(),
                        "event_mass_q50_all": output["event_mass_q50"][0].numpy(),
                        "event_mass_q90_all": output["event_mass_q90"][0].numpy(),
                        "selected_index": selected.numpy(),
                        "mass_identity_mean_error": float(abs(output["event_mass_mean"].sum() - output["mean"][0])),
                        "mass_identity_q50_error": float(abs(output["event_mass_q50"].sum() - output["q50"][0])),
                        "mass_identity_q90_error": float(abs(output["event_mass_q90"].sum() - output["q90"][0])),
                    }
                )
            records.append(record)
    return records


def clone_with_overrides(result: TrainingResult, overrides: dict[str, object]) -> CMASSTPPConfig:
    values = asdict(result.model.config)
    values.update(overrides)
    return CMASSTPPConfig(**values)
