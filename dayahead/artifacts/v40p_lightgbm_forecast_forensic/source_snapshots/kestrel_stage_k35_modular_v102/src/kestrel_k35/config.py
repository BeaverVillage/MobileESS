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
        raise FileNotFoundError(f"설정 파일이 없습니다: {path}")

    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise ValueError("pipeline.yaml 최상위 구조는 mapping이어야 합니다.")

    config = _expand(config)
    cases = config.get("flexibility_cases", [])
    case_ids = [str(case["case_id"]) for case in cases]

    if not cases:
        raise ValueError("flexibility_cases가 비어 있습니다.")
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("flexibility case_id가 중복됐습니다.")

    return config
