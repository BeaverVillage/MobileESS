"""Shared, forecast-only experiment utilities; no production imports."""
import hashlib
import json
import os
from pathlib import Path

for key in ('OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'NUMEXPR_NUM_THREADS'):
    os.environ[key] = '1'
os.environ['PYTHONDONTWRITEBYTECODE'] = '1'

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
TZ = 'Etc/GMT-10'  # Frozen modeled clock: UTC+10, no DST; not host Asia/Seoul.
SEEDS = [20260924, 20260925, 20260926]
ROLES = ['TRAIN', 'DEVELOPMENT', 'CALIBRATION', 'EXPOSED_EVALUATION', 'MAY_HISTORICAL']


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def clean(value):
    if isinstance(value, dict):
        return {str(k): clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, np.ndarray)):
        return [clean(v) for v in value]
    if isinstance(value, (np.integer, np.bool_)):
        return value.item()
    if isinstance(value, (float, np.floating)):
        return float(value) if np.isfinite(value) else None
    return value


def dump(name, value, exclusive=False):
    path = ROOT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x' if exclusive else 'w', encoding='utf-8', newline='\n') as stream:
        json.dump(clean(value), stream, ensure_ascii=False, indent=2, default=str, allow_nan=False)
        stream.write('\n')


def now():
    return pd.Timestamp.now(tz='UTC').isoformat()


def issue(day):
    return pd.Timestamp(str(day), tz=TZ) - pd.Timedelta(hours=6)


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def finite_residual(y, q90):
    """One score per calibration day per hour, with a finite-sample rank.

    Temporal exchangeability is NOT assumed as an empirical fact. No simultaneous
    24-hour or distribution-free time-series coverage claim is made.
    """
    require(y.ndim == 2 and y.shape == q90.shape and y.shape[1] == 24, 'calibration shape')
    n = len(y)
    rank = int(np.ceil(.9 * (n + 1)))
    require(1 <= rank <= n, 'insufficient finite calibration support')
    residual = y - q90
    return np.sort(residual, axis=0)[rank - 1], rank


def corrected(q, delta):
    out = q.copy()
    # Support and quantile-order constraint only. NO upper bound or capacity.
    out[..., 1] = np.maximum(out[..., 0], np.maximum(0., out[..., 1] + delta))
    return out


def metrics(y, q50, q90):
    y, q50, q90 = (np.asarray(v, dtype=float) for v in (y, q50, q90))
    total = y.sum()
    e50, e90 = y - q50, y - q90
    n = y.size
    cov = np.mean(y <= q90) if n else np.nan
    return dict(N_hours=n, actual_GPUh=total, Q50_coverage=np.mean(y <= q50) if n else np.nan,
                Q90_coverage=cov, calibration_error=abs(cov - .90),
                Q90_pinball=np.maximum(.9 * e90, -.1 * e90).mean() if n else np.nan,
                Q50_pinball=(.5 * abs(e50)).mean() if n else np.nan,
                Q50_MAE=abs(e50).mean() if n else np.nan,
                Q50_RMSE=np.sqrt(np.mean(e50 ** 2)) if n else np.nan,
                requirement_ratio=q90.sum() / total if total else np.nan,
                excess_reserve_proxy=np.maximum(q90 - y, 0).sum() / total if total else np.nan,
                Q90_sum_GPUh=q90.sum())


def source_record(path, purpose):
    path = Path(path).resolve()
    return dict(path=str(path), sha256=sha(path), bytes=path.stat().st_size, purpose=purpose)
