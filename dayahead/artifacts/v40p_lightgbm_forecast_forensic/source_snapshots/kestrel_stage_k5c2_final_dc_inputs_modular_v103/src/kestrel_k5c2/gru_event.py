from __future__ import annotations

import copy
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd


@dataclass
class EventProbabilityResult:
    probabilities: pd.DataFrame
    source: str
    audit: dict


def _load_torch():
    try:
        import torch
        from torch import nn
        import torch.nn.functional as F
        return torch, nn, F
    except Exception:
        return None, None, None


def _model_classes():
    torch, nn, F = _load_torch()
    if torch is None:
        return None

    class GRUEncoder(nn.Module):
        def __init__(self, input_size, hidden_size, num_layers, dropout):
            super().__init__()
            self.gru = nn.GRU(input_size, hidden_size, num_layers=num_layers, batch_first=True, dropout=dropout if num_layers > 1 else 0)
            self.norm = nn.LayerNorm(hidden_size)
            self.out_dim = hidden_size
        def forward(self, x):
            _, h = self.gru(x)
            return self.norm(h[-1])

    class FlexibleNet(nn.Module):
        def __init__(self, input_size, cfg, horizons):
            super().__init__()
            if cfg.get("architecture") != "gru":
                raise ValueError(f"Expected GRU flexible model, got {cfg.get('architecture')}")
            self.encoder = GRUEncoder(input_size, int(cfg["hidden_size"]), int(cfg["num_layers"]), float(cfg["dropout"]))
            d = self.encoder.out_dim
            self.event = nn.Linear(d, horizons)
            self.mag = nn.Linear(d, horizons)
            self.q50 = nn.Linear(d, horizons)
            self.q90_delta = nn.Linear(d, horizons)
        def forward(self, x):
            z = self.encoder(x)
            q50 = F.softplus(self.q50(z))
            q90 = q50 + F.softplus(self.q90_delta(z))
            return {"event_logits": self.event(z), "magnitude_log": F.softplus(self.mag(z)), "q50_scaled": q50, "q90_scaled": q90}
    return FlexibleNet


def _calendar(raw: pd.DataFrame, timezone: str) -> pd.DataFrame:
    local = raw.timestamp_utc.dt.tz_convert(timezone)
    raw["hour_sin"] = np.sin(2 * np.pi * (local.dt.hour + local.dt.minute / 60) / 24)
    raw["hour_cos"] = np.cos(2 * np.pi * (local.dt.hour + local.dt.minute / 60) / 24)
    raw["weekday_sin"] = np.sin(2 * np.pi * local.dt.dayofweek / 7)
    raw["weekday_cos"] = np.cos(2 * np.pi * local.dt.dayofweek / 7)
    raw["weekend"] = (local.dt.dayofweek >= 5).astype(float)
    return raw


def _targets(k5a: Path, main_case: str, horizons: list[int]) -> list[str]:
    td = pd.read_csv(k5a / "outputs/target_dictionary.csv", encoding="utf-8-sig")
    td["horizon_steps"] = pd.to_numeric(td.horizon_steps, errors="raise").astype(int)
    mask = td.source_metric.astype(str).eq(f"arriving_flexible_gpu_hours_{main_case}") & td.target_type.astype(str).str.lower().isin({"cumulative_next_horizon", "cumulative_sum"})
    if "primary_role" in td:
        mask &= td.primary_role.astype(str).str.lower().eq("primary")
    sub = td[mask].sort_values("horizon_steps")
    if sub.horizon_steps.tolist() != horizons:
        raise ValueError(f"Flexible targets differ from configured horizons: {sub[['target_column','horizon_steps']].to_dict('records')}")
    return sub.target_column.astype(str).tolist()


def _fallback_k5b2(k5b2: Path, targets: list[str]) -> EventProbabilityResult:
    p = k5b2 / "predictions/test_2025_frozen_k5b2.parquet"
    cols = set(pd.read_parquet(p).columns)
    if "event_probability" not in cols:
        raise RuntimeError("K5-B2 fallback has no event_probability column")
    df = pd.read_parquet(p, columns=["timestamp_utc", "target_column", "event_probability"])
    df = df[df.target_column.isin(targets)].copy()
    df["timestamp_utc"] = pd.to_datetime(df.timestamp_utc, utc=True)
    df["horizon_steps"] = df.target_column.str.extract(r"_h(\d+)$")[0].astype(int)
    return EventProbabilityResult(df[["timestamp_utc", "horizon_steps", "event_probability"]], "k5b2_event_classifier_fallback", {"rows": len(df)})


def infer(k5a: Path, k5b2: Path, k5b3: Path, cfg: dict, logger) -> EventProbabilityResult:
    horizons = list(map(int, cfg["analysis"]["horizons_steps"]))
    targets = _targets(k5a, cfg["analysis"]["main_flexibility_case"], horizons)
    torch, _, _ = _load_torch()
    model_paths = sorted((k5b3 / "models/flexible").glob("*.pt"))
    if torch is None or not model_paths:
        logger.warning("GRU event inference unavailable; falling back to K5-B2 event classifier")
        return _fallback_k5b2(k5b2, targets)

    checkpoint0 = torch.load(model_paths[0], map_location="cpu", weights_only=False)
    features = list(checkpoint0["features"])
    mc = dict(checkpoint0["model_config"])
    context = int(mc["context_steps"])
    workload = k5a / "outputs/kestrel_global_5min_workload.parquet"
    available = set(pd.read_parquet(workload).columns)
    base_features = [f for f in features if f not in {"hour_sin", "hour_cos", "weekday_sin", "weekday_cos", "weekend"}]
    missing = set(base_features) - available
    if missing:
        raise KeyError(f"K5-A workload missing GRU features: {sorted(missing)}")
    raw = pd.read_parquet(workload, columns=["timestamp_utc"] + base_features)
    raw["timestamp_utc"] = pd.to_datetime(raw.timestamp_utc, utc=True)
    raw = raw.sort_values("timestamp_utc").drop_duplicates("timestamp_utc").reset_index(drop=True)
    raw = _calendar(raw, cfg["analysis"]["local_timezone"])
    for f in features:
        raw[f] = pd.to_numeric(raw[f], errors="coerce").fillna(0).astype(np.float32)

    dev = pd.read_parquet(k5a / "outputs/kestrel_ml_development_2024.parquet", columns=["timestamp_utc"])
    dev["timestamp_utc"] = pd.to_datetime(dev.timestamp_utc, utc=True)
    dev_end = dev.timestamp_utc.max()
    fit_mask = raw.timestamp_utc <= dev_end
    xfit = raw.loc[fit_mask, features].to_numpy(np.float64)
    mean = np.nanmean(xfit, axis=0).astype(np.float32)
    std = np.nanstd(xfit, axis=0).astype(np.float32)
    std = np.where(std < 1e-6, 1.0, std).astype(np.float32)

    year = int(cfg["analysis"]["year"])
    test_mask = (raw.timestamp_utc.dt.year == year)
    origins = np.flatnonzero(test_mask.to_numpy())
    origins = origins[origins >= context - 1]
    values = raw[features].to_numpy(np.float32)
    timestamps = raw.timestamp_utc.iloc[origins].reset_index(drop=True)

    class SequenceOnly(torch.utils.data.Dataset):
        def __len__(self):
            return len(origins)
        def __getitem__(self, idx):
            i = int(origins[idx])
            x = values[i - context + 1:i + 1]
            x = ((x - mean) / std).astype(np.float32, copy=False)
            return torch.from_numpy(x)

    device = torch.device("cuda" if bool(cfg["resources"]["use_cuda_if_available"]) and torch.cuda.is_available() else "cpu")
    ds = SequenceOnly()
    dl = torch.utils.data.DataLoader(ds, batch_size=int(cfg["resources"]["inference_batch_size"]), shuffle=False,
        num_workers=int(cfg["resources"]["dataloader_workers"]), pin_memory=bool(cfg["resources"]["pin_memory"]),
        persistent_workers=int(cfg["resources"]["dataloader_workers"]) > 0)
    FlexibleNet = _model_classes()
    seed_probs = []
    model_audit = []
    for path in model_paths:
        ck = torch.load(path, map_location="cpu", weights_only=False)
        if list(ck["features"]) != features:
            raise ValueError(f"Feature mismatch across K5-B3 models: {path}")
        model = FlexibleNet(len(features), dict(ck["model_config"]), len(horizons))
        model.load_state_dict(ck["state_dict"])
        model.to(device).eval()
        chunks = []
        with torch.no_grad():
            for xb in dl:
                xb = xb.to(device, non_blocking=True)
                with torch.amp.autocast(device_type=device.type, dtype=torch.float16, enabled=device.type == "cuda"):
                    out = model(xb)
                chunks.append(torch.sigmoid(out["event_logits"]).float().cpu().numpy())
        pr = np.concatenate(chunks, axis=0)
        seed_probs.append(pr)
        model_audit.append({"path": str(path), "seed": ck.get("seed"), "epochs": ck.get("epochs"), "rows": len(pr)})
        model.to("cpu")
        logger.info("GRU event probability inferred with %s", path.name)
    arr = np.mean(np.stack(seed_probs), axis=0)
    # Cumulative event probability must be nondecreasing with horizon.
    raw_violations = int(np.sum(np.diff(arr, axis=1) < -1e-7))
    arr = np.maximum.accumulate(np.clip(arr, 1e-6, 1 - 1e-6), axis=1)
    frames = []
    for j, h in enumerate(horizons):
        frames.append(pd.DataFrame({"timestamp_utc": timestamps, "horizon_steps": h, "target_column": targets[j], "event_probability": arr[:, j]}))
    out = pd.concat(frames, ignore_index=True)
    audit = {
        "source": "k5b3_gru_ensemble", "device": str(device), "models": model_audit,
        "context_steps": context, "feature_count": len(features), "rows_per_horizon": len(timestamps),
        "raw_monotonicity_violations": raw_violations,
        "raw_monotonicity_violation_fraction": raw_violations / max(len(timestamps) * max(len(horizons) - 1, 1), 1),
        "monotonicity_postprocess": "cumulative_max",
        "probability_calibration": "not_calibrated; ranking model output only",
        "development_scaler_end": dev_end,
    }
    return EventProbabilityResult(out, "k5b3_gru_ensemble", audit)
