from __future__ import annotations
from pathlib import Path
import pandas as pd, yaml
from .context import Context

def load(config_path: Path, package_root: Path) -> Context:
    cfg=yaml.safe_load(config_path.read_text(encoding="utf-8"))
    stamp=pd.Timestamp.utcnow().strftime("%Y%m%d_%H%M%S")
    run_dir=Path(cfg["paths"]["result_parent"])/f"stage_k5c3_{stamp}"
    return Context(cfg,config_path,package_root,run_dir,run_dir/"outputs",run_dir/"scenarios",run_dir/"reports",run_dir/"logs")
