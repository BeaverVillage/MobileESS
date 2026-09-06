from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path

from .context import PipelineContext
from .utils import copy_or_link, sha256_file, write_json


K35_REQUIRED = [
    "outputs/kestrel_12idc_jobs_flexibility.parquet",
    "outputs/kestrel_12idc_exact_active_5min_dense.parquet",
    "reports/validation.json",
]
K4B_REQUIRED = [
    "outputs/nlr_genai_run_power_features.csv",
    "outputs/training_kestrel_mapping_parameters.csv",
    "reports/validation.json",
]


def _successful(stage_dir: Path, required: list[str]) -> bool:
    if not all((stage_dir / rel).exists() for rel in required):
        return False
    try:
        payload = json.loads(
            (stage_dir / "reports/validation.json").read_text(encoding="utf-8")
        )
    except Exception:
        return False
    return payload.get("status") == "success"


def _latest(search_root: Path, token: str, required: list[str]) -> Path | None:
    candidates: list[Path] = []
    if not search_root.exists():
        return None
    for validation in search_root.rglob("reports/validation.json"):
        stage_dir = validation.parent.parent
        if token not in stage_dir.name.lower():
            continue
        if _successful(stage_dir, required):
            candidates.append(stage_dir)
    if not candidates:
        return None
    return max(
        candidates,
        key=lambda path: (path / "reports/validation.json").stat().st_mtime,
    )


def locate_inputs(ctx: PipelineContext, logger: logging.Logger) -> None:
    paths = ctx.config["paths"]
    explicit_k35 = str(paths.get("stage_k35_input_dir", "")).strip()
    k35 = (
        Path(explicit_k35)
        if explicit_k35
        else _latest(Path(paths["stage_k35_search_root"]), "k35", K35_REQUIRED)
    )
    if k35 is None or not _successful(k35, K35_REQUIRED):
        raise FileNotFoundError("Successful Stage K3.5 result not found")

    explicit_k4b = str(paths.get("stage_k4b_input_dir", "")).strip()
    k4b = (
        Path(explicit_k4b)
        if explicit_k4b
        else _latest(Path(paths["stage_k4b_search_root"]), "k4b", K4B_REQUIRED)
    )
    if k4b is None and bool(paths.get("require_k4b_power_scenarios", True)):
        raise FileNotFoundError("Successful Stage K4-B result not found")
    if k4b is not None and not _successful(k4b, K4B_REQUIRED):
        raise FileNotFoundError(f"Invalid Stage K4-B result: {k4b}")

    free_gib = shutil.disk_usage(ctx.run_dir).free / 1024**3
    minimum = float(ctx.config["resources"]["minimum_free_disk_gib"])
    if free_gib < minimum:
        raise OSError(f"Free disk {free_gib:.2f} GiB < {minimum:.2f} GiB")

    source_jobs = k35 / "outputs/kestrel_12idc_jobs_flexibility.parquet"
    source_dense = k35 / "outputs/kestrel_12idc_exact_active_5min_dense.parquet"
    copy_inputs = bool(paths.get("copy_inputs_to_wsl", True))
    ctx.jobs_path = copy_or_link(
        source_jobs, ctx.input_dir / source_jobs.name, copy_inputs
    )
    ctx.dense_path = copy_or_link(
        source_dense, ctx.input_dir / source_dense.name, copy_inputs
    )
    ctx.stage_k35_source_dir = k35
    ctx.stage_k4b_source_dir = k4b

    if k4b is not None:
        candidate = k4b / "outputs/kestrel_12idc_training_power_5min.parquet"
        if candidate.exists():
            # The K4-B power table is used only for timestamp lineage.
            # Query it in place to avoid copying a multi-million-row Parquet.
            ctx.k4b_training_power_path = candidate

    metadata = {
        "stage_k35_source_dir": str(k35),
        "stage_k4b_source_dir": str(k4b) if k4b else None,
        "jobs_source": str(source_jobs),
        "dense_source": str(source_dense),
        "jobs_runtime_path": str(ctx.jobs_path),
        "dense_runtime_path": str(ctx.dense_path),
        "jobs_size_bytes": source_jobs.stat().st_size,
        "dense_size_bytes": source_dense.stat().st_size,
        "jobs_sha256": sha256_file(source_jobs),
        "dense_sha256": sha256_file(source_dense),
        "k4b_training_power_path": (
            str(ctx.k4b_training_power_path)
            if ctx.k4b_training_power_path
            else None
        ),
        "disk_free_gib": round(free_gib, 2),
    }
    write_json(ctx.report_dir / "input_metadata.json", metadata)
    logger.info("Stage K3.5 input: %s", k35)
    logger.info("Stage K4-B input: %s", k4b)
    logger.info("Jobs input: %s", ctx.jobs_path)
    logger.info("Dense input: %s", ctx.dense_path)
