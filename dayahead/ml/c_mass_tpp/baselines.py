from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import torch
from lightgbm import LGBMRegressor
from torch import nn
from torch.nn import functional as F

from .data import DailySample
from .encoder import CausalContinuousTimeEncoder
from .device import DEVICE


@dataclass
class BaselinePrediction:
    mean: np.ndarray
    q50: np.ndarray
    q90: np.ndarray
    metadata: dict[str, object]


def _dow(date: str) -> int:
    return int(np.datetime64(date).astype("datetime64[D]").astype(object).weekday())


def v18r2_candidate_b(
    samples: list[DailySample], train_index: np.ndarray, validation_index: np.ndarray
) -> BaselinePrediction:
    train_mass = np.asarray([samples[i].daily_mass_GPU_h for i in train_index])
    train_dow = np.asarray([_dow(samples[i].date) for i in train_index])
    global_q = np.quantile(train_mass, [0.5, 0.9])
    q50, q90 = [], []
    for index in validation_index:
        group = train_mass[train_dow == _dow(samples[index].date)]
        q = np.quantile(group, [0.5, 0.9]) if len(group) >= 3 else global_q
        q50.append(float(q[0]))
        q90.append(float(max(q[1], q[0])))
    q50_array = np.asarray(q50)
    return BaselinePrediction(
        mean=q50_array.copy(),
        q50=q50_array,
        q90=np.asarray(q90),
        metadata={"implementation": "V18R2_CANDIDATE_B_EXACT_DOW_EMPIRICAL_QUANTILE_RULE"},
    )


def persistence_proxy(
    samples: list[DailySample], train_index: np.ndarray, validation_index: np.ndarray
) -> BaselinePrediction:
    train_proxy = np.asarray([samples[i].proxy_history_28d_GPU_h[-7] for i in train_index])
    train_target = np.asarray([samples[i].daily_mass_GPU_h for i in train_index])
    scale = float(train_target.sum() / max(train_proxy.sum(), 1e-9))
    prediction = np.asarray(
        [samples[i].proxy_history_28d_GPU_h[-7] * scale for i in validation_index], dtype=float
    )
    residual = train_target - train_proxy * scale
    q50_res, q90_res = np.quantile(residual, [0.5, 0.9])
    return BaselinePrediction(
        mean=np.maximum(prediction, 0.0),
        q50=np.maximum(prediction + q50_res, 0.0),
        q90=np.maximum(prediction + max(q90_res, q50_res), 0.0),
        metadata={"implementation": "D_MINUS_7_REQUESTED_SERVICE_PROXY_TRAINING_SCALE"},
    )


def _matrix(samples: list[DailySample], indices: np.ndarray) -> np.ndarray:
    return np.stack([samples[i].macro_features for i in indices])


def lightgbm_baselines(
    samples: list[DailySample], train_index: np.ndarray, validation_index: np.ndarray, seed: int
) -> dict[str, BaselinePrediction]:
    x_train = _matrix(samples, train_index)
    x_validation = _matrix(samples, validation_index)
    y_train = np.asarray([samples[i].daily_mass_GPU_h for i in train_index])
    common = dict(
        n_estimators=120,
        learning_rate=0.035,
        num_leaves=7,
        min_child_samples=12,
        max_depth=3,
        reg_lambda=1.0,
        random_state=seed,
        deterministic=True,
        verbosity=-1,
        n_jobs=1,
    )
    mean_model = LGBMRegressor(objective="tweedie", tweedie_variance_power=1.5, **common)
    q50_model = LGBMRegressor(objective="quantile", alpha=0.5, **common)
    q90_model = LGBMRegressor(objective="quantile", alpha=0.9, **common)
    mean_model.fit(x_train, y_train)
    q50_model.fit(x_train, y_train)
    q90_model.fit(x_train, y_train)
    mean = np.maximum(mean_model.predict(x_validation), 0.0)
    q50 = np.maximum(q50_model.predict(x_validation), 0.0)
    q90 = np.maximum(q90_model.predict(x_validation), q50)
    parameters = int(
        sum(model.booster_.num_model_per_iteration() * model.booster_.num_trees() for model in (mean_model, q50_model, q90_model))
    )
    metadata = {
        "source": "lightgbm.LGBMRegressor",
        "features": "18 causal macro request/calendar features",
        "tree_count_proxy": parameters,
    }
    return {
        "B2_LIGHTGBM_TWEEDIE": BaselinePrediction(mean, q50, q90, {**metadata, "objective": "tweedie_mean_plus_quantile_heads"}),
        "B3_LIGHTGBM_QUANTILE": BaselinePrediction(q50.copy(), q50, q90, {**metadata, "objective": "quantile_Q50_Q90; Q50 is point forecast"}),
    }


class PatchTSTLite(nn.Module):
    """Small faithful patch-token Transformer over the 28-day proxy history."""

    def __init__(self, patch_length: int = 4, hidden_dim: int = 16) -> None:
        super().__init__()
        self.patch_length = patch_length
        self.patch = nn.Linear(patch_length, hidden_dim)
        layer = nn.TransformerEncoderLayer(
            hidden_dim, nhead=2, dim_feedforward=32, dropout=0.0, batch_first=True
        )
        self.encoder = nn.TransformerEncoder(layer, num_layers=1)
        self.head = nn.Linear(hidden_dim, 3)

    def forward(self, history: torch.Tensor) -> torch.Tensor:
        patches = history.unfold(1, self.patch_length, self.patch_length)
        hidden = self.encoder(self.patch(patches)).mean(dim=1)
        raw = self.head(hidden)
        mean = F.softplus(raw[:, 0])
        q50 = F.softplus(raw[:, 1])
        q90 = q50 + F.softplus(raw[:, 2])
        return torch.stack((mean, q50, q90), dim=-1)


class EventAggregateBaseline(nn.Module):
    """Computationally feasible RMTPP-style continuous-time event baseline."""

    def __init__(self, event_dim: int, hidden_dim: int = 16) -> None:
        super().__init__()
        self.encoder = CausalContinuousTimeEncoder(event_dim, hidden_dim)
        self.head = nn.Linear(hidden_dim, 3)

    def forward(self, features: torch.Tensor, ages: torch.Tensor) -> torch.Tensor:
        raw = self.head(self.encoder(features, ages))
        mean = F.softplus(raw[:, 0])
        q50 = F.softplus(raw[:, 1])
        q90 = q50 + F.softplus(raw[:, 2])
        return torch.stack((mean, q50, q90), dim=-1)


class THPWindowBaseline(nn.Module):
    """THP-style causal attention pooling without O(N^2) event self-attention."""

    def __init__(self, event_dim: int, hidden_dim: int = 16) -> None:
        super().__init__()
        self.embedding = nn.Sequential(nn.Linear(event_dim + 1, hidden_dim), nn.SiLU())
        self.query = nn.Parameter(torch.zeros(hidden_dim))
        self.head = nn.Linear(hidden_dim, 3)

    def forward(self, features: torch.Tensor, ages: torch.Tensor) -> torch.Tensor:
        if features.ndim == 2:
            features = features.unsqueeze(0)
            ages = ages.unsqueeze(0)
        hidden = self.embedding(torch.cat((features, torch.log1p(ages).unsqueeze(-1)), dim=-1))
        score = (hidden * self.query).sum(-1) / math.sqrt(hidden.shape[-1])
        pooled = (torch.softmax(score, dim=-1).unsqueeze(-1) * hidden).sum(1)
        raw = self.head(pooled)
        mean = F.softplus(raw[:, 0])
        q50 = F.softplus(raw[:, 1])
        q90 = q50 + F.softplus(raw[:, 2])
        return torch.stack((mean, q50, q90), dim=-1)


def _train_deep_baseline(
    model: nn.Module,
    samples: list[DailySample],
    train_index: np.ndarray,
    validation_index: np.ndarray,
    seed: int,
    mode: str,
    epochs: int = 30,
) -> BaselinePrediction:
    torch.manual_seed(seed)
    model = model.to(DEVICE)
    optimizer = torch.optim.Adam(model.parameters(), lr=3e-3)
    scale = 528.0 * 24.0
    for _ in range(epochs):
        for index in train_index:
            sample = samples[int(index)]
            if mode == "patch":
                x = torch.from_numpy(np.log1p(sample.proxy_history_28d_GPU_h)[None, :]).to(DEVICE)
                prediction = model(x) * scale
            else:
                prediction = model(
                    torch.from_numpy(sample.micro_event_features).to(DEVICE),
                    torch.from_numpy(sample.micro_event_ages_h).to(DEVICE),
                ) * scale
            target = torch.tensor([sample.daily_mass_GPU_h], device=DEVICE)
            loss = F.smooth_l1_loss(prediction[:, 0], target, beta=1000.0)
            loss = loss + 0.2 * F.l1_loss(prediction[:, 1], target)
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
    values = []
    with torch.no_grad():
        for index in validation_index:
            sample = samples[int(index)]
            if mode == "patch":
                prediction = model(
                    torch.from_numpy(np.log1p(sample.proxy_history_28d_GPU_h)[None, :]).to(DEVICE)
                ) * scale
            else:
                prediction = model(
                    torch.from_numpy(sample.micro_event_features).to(DEVICE),
                    torch.from_numpy(sample.micro_event_ages_h).to(DEVICE),
                ) * scale
            values.append(prediction[0].detach().cpu().numpy())
    array = np.asarray(values)
    return BaselinePrediction(
        mean=array[:, 0],
        q50=array[:, 1],
        q90=array[:, 2],
        metadata={"parameters": sum(parameter.numel() for parameter in model.parameters()), "epochs": epochs, "execution_device": str(DEVICE)},
    )


def deep_baselines(
    samples: list[DailySample], train_index: np.ndarray, validation_index: np.ndarray, seed: int
) -> dict[str, BaselinePrediction]:
    return {
        "B4_PATCHTST_LITE": _train_deep_baseline(
            PatchTSTLite(), samples, train_index, validation_index, seed, "patch", epochs=8
        ),
        "B5_RMTPP_LONG_HORIZON_ADAPTATION": _train_deep_baseline(
            EventAggregateBaseline(9), samples, train_index, validation_index, seed, "event", epochs=2
        ),
        "B6_THP_LONG_HORIZON_ADAPTATION": _train_deep_baseline(
            THPWindowBaseline(9), samples, train_index, validation_index, seed, "event", epochs=2
        ),
    }
