from __future__ import annotations

import logging
import shutil
from pathlib import Path

from kestrel_k35.context import PipelineContext
from kestrel_k35.utils.files import copy_file_verified, sha256_file, write_json


JOBS_FILE = "kestrel_12idc_jobs.parquet"
CONSERVATIVE_FILE = "kestrel_12idc_baseline_active_5min.parquet"


def _find_latest(search_root: Path) -> Path:
    candidates = []

    for jobs_path in search_root.rglob(JOBS_FILE):
        outputs_dir = jobs_path.parent
        if (outputs_dir / CONSERVATIVE_FILE).exists():
            candidates.append(outputs_dir.parent)

    if not candidates:
        raise FileNotFoundError(
            f"Stage K3 정상 출력 폴더를 찾지 못했습니다: {search_root}"
        )

    return max(
        candidates,
        key=lambda path: (path / "outputs" / JOBS_FILE).stat().st_mtime,
    )


def run(ctx: PipelineContext, logger: logging.Logger) -> None:
    explicit = str(
        ctx.config["paths"].get("stage_k3_input_dir", "")
    ).strip()

    stage_dir = (
        Path(explicit)
        if explicit
        else _find_latest(Path(ctx.config["paths"]["stage_k3_search_root"]))
    )

    jobs_source = stage_dir / "outputs" / JOBS_FILE
    conservative_source = stage_dir / "outputs" / CONSERVATIVE_FILE

    if not jobs_source.exists():
        raise FileNotFoundError(jobs_source)
    if not conservative_source.exists():
        raise FileNotFoundError(conservative_source)

    ctx.stage_k3_source_dir = stage_dir
    ctx.jobs_source = jobs_source
    ctx.conservative_source = conservative_source

    if ctx.config["paths"].get("copy_inputs_to_wsl", True):
        ctx.jobs_local = ctx.input_dir / JOBS_FILE
        ctx.conservative_local = ctx.input_dir / CONSERVATIVE_FILE
        copy_file_verified(jobs_source, ctx.jobs_local)
        copy_file_verified(conservative_source, ctx.conservative_local)
    else:
        ctx.jobs_local = jobs_source
        ctx.conservative_local = conservative_source

    free_gib = shutil.disk_usage(ctx.run_dir).free / 1024**3
    minimum = float(ctx.config["resources"]["minimum_free_disk_gib"])

    if free_gib < minimum:
        raise OSError(
            f"WSL 디스크 여유 공간 부족: {free_gib:.2f} GiB < {minimum:.2f} GiB"
        )

    write_json(
        ctx.report_dir / "input_metadata.json",
        {
            "stage_k3_source_dir": str(stage_dir),
            "jobs_source": str(jobs_source),
            "conservative_source": str(conservative_source),
            "jobs_local": str(ctx.jobs_local),
            "conservative_local": str(ctx.conservative_local),
            "jobs_size_bytes": ctx.jobs_local.stat().st_size,
            "conservative_size_bytes": ctx.conservative_local.stat().st_size,
            "jobs_sha256": sha256_file(ctx.jobs_local),
            "conservative_sha256": sha256_file(ctx.conservative_local),
            "disk_free_gib": round(free_gib, 2),
        },
    )

    logger.info("Stage K3 입력 폴더: %s", stage_dir)
