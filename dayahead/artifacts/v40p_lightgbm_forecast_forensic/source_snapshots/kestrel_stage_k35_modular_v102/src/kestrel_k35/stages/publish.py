from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path

from kestrel_k35.context import PipelineContext
from kestrel_k35.utils.files import sha256_file, write_json, zip_review


def write_report(ctx: PipelineContext) -> None:
    validation = json.loads(
        (ctx.report_dir / "validation.json").read_text(encoding="utf-8")
    )
    metrics = validation["metrics"]
    case_metrics = validation["case_metrics"]

    table_lines = [
        "| Case | Flexible jobs | Flexible job share | Flexible GPU-hour | Flexible GPU-hour share |",
        "|---|---:|---:|---:|---:|",
    ]

    for identifier, values in case_metrics.items():
        flexible_job_share = (
            values["flexible_jobs"]
            / metrics["classified_job_rows"]
        )
        flexible_gpu_hour_share = (
            values["flexible_gpu_hours"]
            / metrics["job_gpu_hours"]
        )
        table_lines.append(
            "| "
            f"{identifier} | "
            f"{values['flexible_jobs']:,} | "
            f"{flexible_job_share:.4%} | "
            f"{values['flexible_gpu_hours']:,.3f} | "
            f"{flexible_gpu_hour_share:.4%} |"
        )

    table = "\n".join(table_lines)

    lines = [
        "# Kestrel Stage K3.5 결과 보고서",
        "",
        f"- 실행 태그: `{ctx.run_tag}`",
        f"- 상태: `{validation['status']}`",
        f"- Stage K3 입력: `{ctx.stage_k3_source_dir}`",
        f"- Job 수: {metrics['classified_job_rows']:,}",
        f"- 총 GPU-hour: {metrics['job_gpu_hours']:,.3f}",
        f"- 정확한 5분 GPU-hour: {metrics['exact_dense_gpu_hours']:,.3f}",
        f"- UTC offset 비정상 행: {metrics['utc_offset_nonzero_rows']}",
        f"- fixed+flex 항등식 오류: {metrics['profile_identity_failures']}",
        f"- case nesting 오류: {metrics['flex_nesting_failures']}",
        "",
        "## Flexible workload 민감도",
        "",
        table,
        "",
        "## 해석 제한",
        "",
        "1. queue wait는 실제 SLA가 아니라 관측 기반 flexibility proxy입니다.",
        "2. F15/F30/F60은 실제 training application label이 아닌 민감도 시나리오입니다.",
        "3. 12개 IDC는 실제 trace의 group-preserving multi-site emulation입니다.",
        "4. 정확한 capacity reference는 실제 Melbourne IDC 정격이 아니라 baseline 기반 시나리오입니다.",
        "",
    ]

    (ctx.report_dir / "REPORT.md").write_text(
        "\n".join(lines),
        encoding="utf-8",
    )


def run(ctx: PipelineContext, logger: logging.Logger) -> None:
    write_report(ctx)

    if ctx.publish_dir.exists():
        raise FileExistsError(ctx.publish_dir)

    ctx.publish_dir.mkdir(parents=True)

    for name in ["outputs", "reports", "logs"]:
        shutil.copytree(ctx.run_dir / name, ctx.publish_dir / name)

    shutil.copy2(ctx.config_path, ctx.publish_dir / "pipeline_used.yaml")

    manifest = []
    for path in sorted(ctx.publish_dir.rglob("*")):
        if path.is_file():
            manifest.append(
                {
                    "relative_path": str(path.relative_to(ctx.publish_dir)),
                    "size_bytes": path.stat().st_size,
                    "sha256": sha256_file(path),
                }
            )

    write_json(ctx.publish_dir / "manifest.json", manifest)

    review_zip = (
        ctx.review_root / f"stage_k35_kestrel_review_{ctx.run_tag}.zip"
    )
    zip_review(ctx.publish_dir, review_zip)

    logger.info("Windows 결과 게시: %s", ctx.publish_dir)
    logger.info("검토 ZIP 생성: %s", review_zip)
