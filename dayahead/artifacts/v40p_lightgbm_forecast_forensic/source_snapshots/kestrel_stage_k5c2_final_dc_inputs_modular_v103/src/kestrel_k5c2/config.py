from __future__ import annotations

from pathlib import Path
from typing import Any
import yaml


def load_config(path: Path) -> dict[str, Any]:
    cfg = yaml.safe_load(path.read_text(encoding="utf-8"))
    required = ["paths", "analysis", "power", "burstgpt", "scenarios", "resources"]
    miss = [k for k in required if k not in cfg]
    if miss:
        raise KeyError(f"Missing config sections: {miss}")
    return cfg
