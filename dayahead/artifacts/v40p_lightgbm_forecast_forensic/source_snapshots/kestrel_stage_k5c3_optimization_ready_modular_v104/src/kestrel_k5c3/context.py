from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Any

@dataclass
class Inputs:
    k5c2: Path
    k5a: Path
    k5b3: Path

@dataclass
class Context:
    config: dict[str,Any]
    config_path: Path
    package_root: Path
    run_dir: Path
    output_dir: Path
    scenario_dir: Path
    report_dir: Path
    log_dir: Path
    inputs: Inputs|None=None
