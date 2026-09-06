from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml


def _expand(value: Any) -> Any:
    if isinstance(value, str):
        return os.path.expandvars(os.path.expanduser(value))
    if isinstance(value, list):
        return [_expand(item) for item in value]
    if isinstance(value, dict):
        return {key: _expand(item) for key, item in value.items()}
    return value


def load_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(path)
    config = yaml.safe_load(path.read_text(encoding='utf-8'))
    if not isinstance(config, dict):
        raise ValueError('pipeline.yaml must be a mapping')
    config = _expand(config)

    interval = int(config['analysis']['interval_minutes'])
    if interval != 5:
        raise ValueError('Stage K5-A is fixed to a 5-minute research grid')

    horizons = [int(v) for v in config['prediction']['horizon_steps']]
    if sorted(set(horizons)) != horizons or any(v <= 0 for v in horizons):
        raise ValueError('horizon_steps must be sorted positive unique integers')

    lags = [int(v) for v in config['features']['lag_steps']]
    if max(lags) < max(horizons):
        raise ValueError('The lag horizon should cover at least the maximum forecast horizon')

    return config
