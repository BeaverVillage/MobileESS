"""Real PyTorch Direct96 backend for the V16 AIDC G5/G6 freeze."""

from __future__ import annotations

import hashlib
import json
import math
import os
import random
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Mapping, Sequence

import numpy as np

from .aidc_ml_data import Direct96Samples
from .aidc_resource_coupling import Direct96Architecture


SELECTION_SEED = 20260828
PRODUCTION_SEED = 20260828
QUANTILES = (0.1, 0.5, 0.9)
HPO_EPOCHS = 3


@dataclass(frozen=True)
class HPOCandidate:
    candidate_id: str
    lookback: int
    d_model: int
    encoder_layers: int
    attention_heads: int
    dropout: float
    learning_rate: float

    def validate(self, feature_count: int, *, proposed: bool) -> Direct96Architecture:
        if self.learning_rate not in {1e-4, 3e-4}:
            raise ValueError("AIDC_HPO_LEARNING_RATE_OUTSIDE_FROZEN_SPACE")
        architecture = Direct96Architecture(
            lookback=self.lookback,
            feature_count=feature_count,
            d_model=self.d_model,
            encoder_layers=self.encoder_layers,
            attention_heads=self.attention_heads,
            dropout=self.dropout,
            proposed=proposed,
        )
        architecture.validate()
        return architecture

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


FROZEN_HPO_CANDIDATES = (
    HPOCandidate("C00", 672, 64, 2, 4, 0.1, 3e-4),
    HPOCandidate("C01", 672, 128, 3, 8, 0.2, 1e-4),
    HPOCandidate("C02", 1344, 64, 2, 4, 0.2, 3e-4),
)


def _torch_modules() -> tuple[object, object, object]:
    try:
        import torch
        from torch import nn
        from torch.nn import functional as functional
    except ImportError as exc:
        raise RuntimeError("AIDC_TRANSFORMER_BACKEND_REQUIRED_NO_FALLBACK_MODEL") from exc
    return torch, nn, functional


def set_deterministic_seed(seed: int) -> None:
    torch, _, _ = _torch_modules()
    os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = True
    torch.use_deterministic_algorithms(True, warn_only=False)
    if torch.cuda.is_available():
        torch.backends.cuda.enable_flash_sdp(False)
        torch.backends.cuda.enable_mem_efficient_sdp(False)
        torch.backends.cuda.enable_math_sdp(True)


def _positional_encoding(length: int, d_model: int) -> object:
    torch, _, _ = _torch_modules()
    position = torch.arange(length, dtype=torch.float32).unsqueeze(1)
    divisor = torch.exp(torch.arange(0, d_model, 2, dtype=torch.float32) * (-math.log(10000.0) / d_model))
    result = torch.zeros(length, d_model, dtype=torch.float32)
    result[:, 0::2] = torch.sin(position * divisor)
    result[:, 1::2] = torch.cos(position * divisor)
    return result


def build_transformer(
    candidate: HPOCandidate,
    *,
    feature_count: int,
    target_count: int,
    proposed: bool,
) -> object:
    torch, nn, functional = _torch_modules()
    architecture = candidate.validate(feature_count, proposed=proposed)

    class AIDCDirect96(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.architecture = architecture
            self.proposed = proposed
            self.target_count = target_count
            self.past_projection = nn.Linear(feature_count, candidate.d_model)
            self.future_projection = nn.Linear(6, candidate.d_model)
            encoder_layer = nn.TransformerEncoderLayer(
                d_model=candidate.d_model,
                nhead=candidate.attention_heads,
                dim_feedforward=4 * candidate.d_model,
                dropout=candidate.dropout,
                activation="gelu",
                batch_first=True,
                norm_first=True,
            )
            self.encoder = nn.TransformerEncoder(encoder_layer, num_layers=candidate.encoder_layers)
            decoder_layer = nn.TransformerDecoderLayer(
                d_model=candidate.d_model,
                nhead=candidate.attention_heads,
                dim_feedforward=4 * candidate.d_model,
                dropout=candidate.dropout,
                activation="gelu",
                batch_first=True,
                norm_first=True,
            )
            self.decoder = nn.TransformerDecoder(decoder_layer, num_layers=1)
            self.gpu_head = nn.Linear(candidate.d_model, 3)
            self.work_head = nn.Linear(candidate.d_model, (target_count - 2) * 3)
            self.power_head = nn.Linear(candidate.d_model, 3)
            if proposed:
                self.gpu_to_power_gate = nn.Linear(candidate.d_model, candidate.d_model)
                self.gpu_to_power_value = nn.Linear(candidate.d_model, candidate.d_model)
            self.register_buffer("past_position", _positional_encoding(candidate.lookback, candidate.d_model))
            self.register_buffer("future_position", _positional_encoding(96, candidate.d_model))

        def forward(self, past: object, future: object) -> object:
            memory = self.encoder(self.past_projection(past) + self.past_position.unsqueeze(0))
            query = self.future_projection(future) + self.future_position.unsqueeze(0)
            hidden = self.decoder(query, memory)
            power_hidden = hidden
            if self.proposed:
                gate = torch.sigmoid(self.gpu_to_power_gate(hidden))
                value = torch.tanh(self.gpu_to_power_value(hidden))
                power_hidden = hidden + gate * value
            power = self.power_head(power_hidden).unsqueeze(2)
            gpu = self.gpu_head(hidden).unsqueeze(2)
            work = self.work_head(hidden).reshape(hidden.shape[0], 96, self.target_count - 2, 3)
            raw = torch.cat((power, gpu, work), dim=2)
            q10 = functional.softplus(raw[..., 0])
            q50 = q10 + functional.softplus(raw[..., 1])
            q90 = q50 + functional.softplus(raw[..., 2])
            return torch.stack((q10, q50, q90), dim=-1)

    return AIDCDirect96()


def pinball_loss(prediction: object, target: object) -> object:
    torch, _, _ = _torch_modules()
    quantiles = torch.as_tensor(QUANTILES, device=prediction.device, dtype=prediction.dtype)
    error = target.unsqueeze(-1) - prediction
    return torch.maximum(quantiles * error, (quantiles - 1.0) * error).mean()


def normalized_mean_pinball(prediction: np.ndarray, target: np.ndarray) -> float:
    quantiles = np.asarray(QUANTILES, dtype=np.float64)
    error = target[..., None] - prediction
    value = np.maximum(quantiles * error, (quantiles - 1.0) * error)
    return float(np.mean(value))


def _batch_size(candidate: HPOCandidate) -> int:
    if candidate.lookback == 1344:
        return 2
    return 4 if candidate.d_model == 128 else 8


def train_transformer(
    candidate: HPOCandidate,
    samples: Direct96Samples,
    *,
    proposed: bool,
    seed: int,
    include_validation_in_fit: bool,
    epochs: int = HPO_EPOCHS,
) -> tuple[object, dict[str, object]]:
    torch, _, _ = _torch_modules()
    if seed != SELECTION_SEED:
        raise ValueError("AIDC_MODEL_SELECTION_OR_PRODUCTION_SEED_VIOLATION")
    set_deterministic_seed(seed)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = build_transformer(
        candidate,
        feature_count=len(samples.feature_names),
        target_count=len(samples.target_names),
        proposed=proposed,
    ).to(device)
    train_x = np.asarray(samples.train_x, dtype=np.float32)
    train_future = np.asarray(samples.train_future, dtype=np.float32)
    train_y = np.asarray(samples.train_y, dtype=np.float32)
    if include_validation_in_fit:
        train_x = np.concatenate((train_x, np.asarray(samples.validation_x, dtype=np.float32)))
        train_future = np.concatenate((train_future, np.asarray(samples.validation_future, dtype=np.float32)))
        train_y = np.concatenate((train_y, np.asarray(samples.validation_y, dtype=np.float32)))
    optimizer = torch.optim.AdamW(model.parameters(), lr=candidate.learning_rate, weight_decay=1e-4)
    batch_size = _batch_size(candidate)
    losses: list[float] = []
    model.train()
    for epoch in range(epochs):
        generator = torch.Generator(device="cpu").manual_seed(seed + epoch)
        order = torch.randperm(len(train_x), generator=generator).tolist()
        epoch_loss = 0.0
        batch_count = 0
        for start in range(0, len(order), batch_size):
            indices = order[start : start + batch_size]
            past = torch.as_tensor(train_x[indices], device=device)
            future = torch.as_tensor(train_future[indices], device=device)
            target = torch.as_tensor(train_y[indices], device=device)
            optimizer.zero_grad(set_to_none=True)
            prediction = model(past, future)
            loss = pinball_loss(prediction, target)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
            optimizer.step()
            epoch_loss += float(loss.detach().cpu())
            batch_count += 1
        losses.append(epoch_loss / max(batch_count, 1))
    metadata = {
        "device": str(device),
        "cuda_name": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
        "torch_version": torch.__version__,
        "cuda_version": torch.version.cuda,
        "epochs": epochs,
        "batch_size": batch_size,
        "epoch_training_loss": losses,
        "fit_sample_count": int(len(train_x)),
        "include_april_in_fit": include_validation_in_fit,
        "deterministic_algorithms_enabled": torch.are_deterministic_algorithms_enabled(),
        "flash_sdp_enabled": torch.backends.cuda.flash_sdp_enabled() if torch.cuda.is_available() else None,
        "memory_efficient_sdp_enabled": (
            torch.backends.cuda.mem_efficient_sdp_enabled() if torch.cuda.is_available() else None
        ),
        "math_sdp_enabled": torch.backends.cuda.math_sdp_enabled() if torch.cuda.is_available() else None,
    }
    return model, metadata


def predict_transformer(model: object, samples: Direct96Samples) -> np.ndarray:
    torch, _, _ = _torch_modules()
    device = next(model.parameters()).device
    model.eval()
    values: list[np.ndarray] = []
    with torch.no_grad():
        for start in range(0, len(samples.validation_x), 8):
            past = torch.as_tensor(np.asarray(samples.validation_x[start : start + 8], dtype=np.float32), device=device)
            future = torch.as_tensor(np.asarray(samples.validation_future[start : start + 8], dtype=np.float32), device=device)
            values.append(model(past, future).detach().cpu().numpy())
    result = np.concatenate(values, axis=0)
    if result.shape != (len(samples.validation_days), 96, len(samples.target_names), 3):
        raise RuntimeError(f"DIRECT96_OUTPUT_SHAPE_INVALID:{result.shape}")
    if not np.isfinite(result).all():
        raise RuntimeError("DIRECT96_OUTPUT_NONFINITE")
    if np.any(result[..., 0] > result[..., 1]) or np.any(result[..., 1] > result[..., 2]):
        raise RuntimeError("DIRECT96_QUANTILE_ORDER_VIOLATION")
    return result


def architecture_delta_contract(candidate: HPOCandidate, feature_count: int, target_count: int) -> dict[str, object]:
    vanilla = candidate.validate(feature_count, proposed=False).contract()
    proposed = candidate.validate(feature_count, proposed=True).contract()
    ignored = {"gpu_to_power_gated_residual", "vanilla_delta"}
    common_equal = all(vanilla[key] == proposed[key] for key in vanilla if key not in ignored)
    vanilla_model = build_transformer(candidate, feature_count=feature_count, target_count=target_count, proposed=False)
    proposed_model = build_transformer(candidate, feature_count=feature_count, target_count=target_count, proposed=True)
    vanilla_names = set(vanilla_model.state_dict())
    proposed_names = set(proposed_model.state_dict())
    added = sorted(proposed_names - vanilla_names)
    removed = sorted(vanilla_names - proposed_names)
    allowed_prefixes = ("gpu_to_power_gate.", "gpu_to_power_value.")
    coupling_only = common_equal and not removed and all(name.startswith(allowed_prefixes) for name in added)
    return {
        "authority_id": "AIDC_RESOURCE_COUPLING_BLOCK_V1",
        "status": "PASS" if coupling_only else "FAIL",
        "common_architecture_fields_equal": common_equal,
        "vanilla_removed_parameter_names": removed,
        "proposed_added_parameter_names": added,
        "allowed_delta": "GPU_TO_POWER_GATED_RESIDUAL_ONLY",
    }


def canonical_state_sha256(model: object) -> str:
    digest = hashlib.sha256()
    for name, tensor in sorted(model.state_dict().items()):
        array = tensor.detach().cpu().contiguous().numpy()
        digest.update(name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(array.dtype).encode("ascii"))
        digest.update(b"\0")
        digest.update(json.dumps(list(array.shape), separators=(",", ":")).encode("ascii"))
        digest.update(b"\0")
        digest.update(array.tobytes(order="C"))
    return digest.hexdigest()


def config_sha256(payload: Mapping[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def save_production_weights(path: Path, model: object, config: Mapping[str, object]) -> dict[str, str]:
    torch, _, _ = _torch_modules()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    payload = {
        "state_dict": {name: tensor.detach().cpu() for name, tensor in model.state_dict().items()},
        "config": dict(config),
    }
    torch.save(payload, temporary)
    temporary.replace(path)
    file_sha = hashlib.sha256(path.read_bytes()).hexdigest()
    state_sha = canonical_state_sha256(model)
    cfg_sha = config_sha256(config)
    final = hashlib.sha256(f"{state_sha}:{cfg_sha}".encode("ascii")).hexdigest()
    return {
        "weights_file_sha256": file_sha,
        "canonical_state_sha256": state_sha,
        "config_sha256": cfg_sha,
        "final_weight_config_fingerprint": final,
    }


def verify_saved_weight_fingerprint(path: Path) -> dict[str, str]:
    torch, _, _ = _torch_modules()
    payload = torch.load(path, map_location="cpu", weights_only=False)
    state = payload["state_dict"]
    digest = hashlib.sha256()
    for name, tensor in sorted(state.items()):
        array = tensor.detach().cpu().contiguous().numpy()
        digest.update(name.encode("utf-8")); digest.update(b"\0")
        digest.update(str(array.dtype).encode("ascii")); digest.update(b"\0")
        digest.update(json.dumps(list(array.shape), separators=(",", ":")).encode("ascii")); digest.update(b"\0")
        digest.update(array.tobytes(order="C"))
    state_sha = digest.hexdigest()
    cfg_sha = config_sha256(payload["config"])
    return {
        "weights_file_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "canonical_state_sha256": state_sha,
        "config_sha256": cfg_sha,
        "final_weight_config_fingerprint": hashlib.sha256(f"{state_sha}:{cfg_sha}".encode("ascii")).hexdigest(),
    }
