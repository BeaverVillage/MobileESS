"""Pure parsing and statistical helpers for V35R3H."""

from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

import numpy as np
import pandas as pd


GPU_COLUMN_RE = re.compile(r"^gpu(\d+)_(.+)$", re.I)


def digest_file(path: Path, algorithm: str, chunk_size: int = 8 * 1024 * 1024) -> str:
    digest = hashlib.new(algorithm)
    with path.open("rb") as stream:
        while chunk := stream.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def digest_bytes(data: bytes, algorithm: str) -> str:
    return hashlib.new(algorithm, data).hexdigest()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def write_csv(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(list(rows)).to_csv(path, index=False, encoding="utf-8", lineterminator="\n")


def table_row_count(data: bytes) -> int:
    lines = data.count(b"\n") + int(bool(data) and not data.endswith(b"\n"))
    return max(lines - 1, 0)


def decode_csv_header(data: bytes, single_machine: bool) -> tuple[str, list[str]]:
    import csv
    import io

    encoding = "cp1252" if single_machine else "utf-8-sig"
    text = data[:262_144].decode(encoding, errors="replace")
    return encoding, next(csv.reader(io.StringIO(text)))


def gpu_type_from_path(name: str) -> str:
    if "/H100/" in name:
        return "H100_CONFIRMED"
    if "/B200/" in name:
        return "B200_CONFIRMED"
    if "/Single_Machine_Dataset/" in name:
        return "NON_TARGET_RTX3060"
    return "GPU_TYPE_UNKNOWN"


def workload_from_path(name: str) -> str:
    if "/Image Generation Diffusion Models/" in name:
        return "IMAGE_GENERATION_DIFFUSION"
    if "/Text Generation LLMs/" in name:
        return "LLM_TEXT_GENERATION"
    if "/Feature Forecasting/" in name:
        return "FEATURE_FORECASTING"
    if "/Image Captioning/" in name:
        return "IMAGE_CAPTIONING"
    if "/Image Classifications/" in name:
        return "IMAGE_CLASSIFICATION"
    if "/Reinforcment Learning/" in name:
        return "REINFORCEMENT_LEARNING"
    if "/Text Generation/" in name:
        return "TEXT_GENERATION"
    return "DOCUMENTATION_OR_UNKNOWN"


def filename_dimensions(name: str) -> dict[str, Any]:
    base = PurePosixPath(name).name

    def capture(pattern: str) -> str | None:
        match = re.search(pattern, base, flags=re.I)
        return match.group(1) if match else None

    zero_stage = capture(r"Deepspeedds_z(\d+)")
    return {
        "batch_size": capture(r"batchsize(\d+)"),
        "model_size": capture(r"(?:ModelSize|Lamma)(\d+[BM]?)"),
        "image_size": capture(r"ImageSize(\d+)"),
        "sequence_length": capture(r"(?:SeqLength|SeqLen|Sequancelength)(\d+)"),
        "parallelism": f"DEEPSPEED_ZERO_STAGE_{zero_stage}" if zero_stage else None,
    }


def quantiles(values: pd.Series) -> dict[str, float | None]:
    numeric = pd.to_numeric(values, errors="coerce")
    finite = numeric[np.isfinite(numeric)]
    if finite.empty:
        return {key: None for key in ("mean", "P01", "P05", "P10", "P25", "P50", "P75", "P90", "P95", "P99", "min", "max", "std")}
    probs = finite.quantile([0.01, 0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95, 0.99])
    return {
        "mean": float(finite.mean()),
        "P01": float(probs.loc[0.01]),
        "P05": float(probs.loc[0.05]),
        "P10": float(probs.loc[0.10]),
        "P25": float(probs.loc[0.25]),
        "P50": float(probs.loc[0.50]),
        "P75": float(probs.loc[0.75]),
        "P90": float(probs.loc[0.90]),
        "P95": float(probs.loc[0.95]),
        "P99": float(probs.loc[0.99]),
        "min": float(finite.min()),
        "max": float(finite.max()),
        "std": float(finite.std(ddof=0)),
    }


def integrate_power_joules(timestamps: pd.Series, power_watts: pd.Series) -> tuple[float, int]:
    time_ns = timestamps.astype("int64").to_numpy()
    power = pd.to_numeric(power_watts, errors="coerce").to_numpy(dtype=float)
    dt = np.diff(time_ns) / 1e9
    valid = (
        np.isfinite(power[:-1])
        & np.isfinite(power[1:])
        & (power[:-1] >= 0)
        & (power[1:] >= 0)
        & np.isfinite(dt)
        & (dt > 0)
    )
    energy = np.sum((power[:-1][valid] + power[1:][valid]) * 0.5 * dt[valid])
    return float(energy), int(valid.sum())


def timebase_summary(timestamps: pd.Series, nominal_interval: float) -> dict[str, Any]:
    valid = timestamps.dropna()
    delta = valid.diff().dt.total_seconds().dropna()
    positive = delta[delta > 0]
    if valid.empty or positive.empty:
        return {
            "duration_seconds": None, "delta_median_seconds": None,
            "delta_P05_seconds": None, "delta_P95_seconds": None,
            "delta_min_seconds": None, "delta_max_seconds": None,
            "duplicate_timestamps": 0, "non_monotonic_rows": 0, "gap_count": 0,
        }
    return {
        "duration_seconds": float((valid.max() - valid.min()).total_seconds()),
        "delta_median_seconds": float(positive.median()),
        "delta_P05_seconds": float(positive.quantile(0.05)),
        "delta_P95_seconds": float(positive.quantile(0.95)),
        "delta_min_seconds": float(positive.min()),
        "delta_max_seconds": float(positive.max()),
        "duplicate_timestamps": int(valid.duplicated().sum()),
        "non_monotonic_rows": int((delta < 0).sum()),
        "gap_count": int((delta > 1.5 * nominal_interval).sum()),
    }


def longest_true_run(mask: pd.Series, interval_seconds: float) -> float:
    values = mask.fillna(False).to_numpy(dtype=bool)
    if not values.size:
        return 0.0
    changes = np.flatnonzero(np.r_[True, values[1:] != values[:-1], True])
    lengths = np.diff(changes)
    states = values[changes[:-1]]
    return float(lengths[states].max(initial=0) * interval_seconds)


def finite_or_none(value: Any) -> Any:
    if isinstance(value, (float, np.floating)) and not math.isfinite(float(value)):
        return None
    return value
