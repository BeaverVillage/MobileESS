from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .context import Inputs
from .utils import latest_parent_with_file


def _explicit_or_latest(explicit: str, root: Path, rel: str, token: str) -> Path:
    if str(explicit).strip():
        p = Path(explicit)
        if not p.exists():
            raise FileNotFoundError(f"Explicit {token} path does not exist: {p}")
        return p
    p = latest_parent_with_file(root, rel, token)
    if p is None:
        p = latest_parent_with_file(root, rel, None)
    if p is None:
        raise FileNotFoundError(f"Could not locate {token} result containing {rel} under {root}")
    return p


def _discover_burstgpt(root: Path, explicit: list[str], prefer_without: bool) -> list[Path]:
    if explicit:
        paths = [Path(x) for x in explicit]
    else:
        allowed = {".csv", ".zip", ".gz", ".parquet"}
        paths = [p for p in root.rglob("*") if p.is_file() and "burstgpt" in p.name.lower() and (p.suffix.lower() in allowed or p.name.lower().endswith(".csv.gz"))]
    paths = [p for p in paths if p.exists()]
    if prefer_without:
        preferred = [p for p in paths if "without" in p.name.lower() and "fail" in p.name.lower()]
        if preferred:
            paths = preferred
        else:
            paths = [p for p in paths if not re.search(r"with[_ -]?fail|failed", p.name.lower())]
    paths = sorted(set(paths), key=lambda p: str(p).lower())
    if not paths:
        raise FileNotFoundError(f"No BurstGPT files found under {root}")
    return paths


def locate_inputs(cfg: dict[str, Any], logger) -> Inputs:
    paths = cfg["paths"]
    processed = Path(paths["processed_root"])
    raw = Path(paths["raw_root"])
    ex = paths.get("explicit", {})
    k5a = _explicit_or_latest(ex.get("k5a_run", ""), processed, "outputs/kestrel_12idc_5min_workload.parquet", "stage_k5a")
    k5b2 = _explicit_or_latest(ex.get("k5b2_run", ""), processed, "predictions/test_2025_frozen_k5b2.parquet", "stage_k5b2")
    k5b3 = _explicit_or_latest(ex.get("k5b3_run", ""), processed, "predictions/test_2025_frozen_dl.parquet", "stage_k5b3")
    k4b = _explicit_or_latest(ex.get("k4b_run", ""), processed, "outputs/nlr_genai_run_power_features.parquet", "stage_k4b")
    k4d = _explicit_or_latest(ex.get("k4d_run", ""), processed, "allnodes/rack_equivalent_pool_factors.csv", "stage_k4d")
    burst = _discover_burstgpt(raw, ex.get("burstgpt_files", []), bool(cfg["burstgpt"]["prefer_without_failures"]))
    for name, value in [("K5-A", k5a), ("K5-B2", k5b2), ("K5-B3", k5b3), ("K4-B", k4b), ("K4-D", k4d)]:
        logger.info("Located %s: %s", name, value)
    for p in burst:
        logger.info("Located BurstGPT: %s", p)
    return Inputs(k5a, k5b2, k5b3, k4b, k4d, burst)
