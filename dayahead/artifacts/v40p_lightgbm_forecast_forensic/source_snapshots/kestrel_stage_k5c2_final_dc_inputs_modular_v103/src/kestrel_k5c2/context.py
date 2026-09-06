from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class Inputs:
    k5a: Path
    k5b2: Path
    k5b3: Path
    k4b: Path
    k4d: Path
    burstgpt_files: list[Path]


@dataclass
class Context:
    config: dict[str, Any]
    config_path: Path
    package_root: Path
    run_dir: Path
    output_dir: Path
    prediction_dir: Path
    scenario_dir: Path
    report_dir: Path
    log_dir: Path
    inputs: Inputs | None = None
