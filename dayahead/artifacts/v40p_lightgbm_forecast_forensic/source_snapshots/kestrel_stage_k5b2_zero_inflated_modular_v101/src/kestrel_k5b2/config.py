from __future__ import annotations
from pathlib import Path
from typing import Any
import os, yaml

def _expand(value: Any) -> Any:
    if isinstance(value, dict): return {k: _expand(v) for k, v in value.items()}
    if isinstance(value, list): return [_expand(v) for v in value]
    if isinstance(value, str): return os.path.expandvars(os.path.expanduser(value))
    return value

def load_config(path: Path) -> dict[str, Any]:
    with path.open('r', encoding='utf-8') as handle: config=yaml.safe_load(handle)
    if not isinstance(config, dict): raise ValueError(f'Invalid YAML config: {path}')
    return _expand(config)
