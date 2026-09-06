from __future__ import annotations

import logging
import time

from kestrel_k35.stages import (
    classify,
    exact_profile,
    locate,
    publish,
    summaries,
    validate,
)
from kestrel_k35.utils.files import write_json, zip_review


STAGES = [
    ("locate", locate.run),
    ("classify", classify.run),
    ("exact_profile", exact_profile.run),
    ("summaries", summaries.run),
    ("validate", validate.run),
    ("publish", publish.run),
]


def run_pipeline(ctx, logger: logging.Logger) -> None:
    started = time.time()
    stage_times = {}

    try:
        for name, function in STAGES:
            stage_started = time.time()
            logger.info("===== Stage %s 시작 =====", name)
            function(ctx, logger)
            stage_times[name] = round(time.time() - stage_started, 3)
            logger.info("===== Stage %s 완료: %.3f초 =====", name, stage_times[name])

        write_json(
            ctx.run_dir / "run_complete.json",
            {
                "status": "success",
                "run_tag": ctx.run_tag,
                "elapsed_seconds": round(time.time() - started, 3),
                "stage_seconds": stage_times,
                "publish_dir": str(ctx.publish_dir),
            },
        )

    except Exception as error:
        write_json(
            ctx.run_dir / "run_failed.json",
            {
                "status": "failed",
                "run_tag": ctx.run_tag,
                "elapsed_seconds": round(time.time() - started, 3),
                "stage_seconds": stage_times,
                "error_type": type(error).__name__,
                "error": str(error),
            },
        )
        logger.exception("Stage K3.5 실패")

        try:
            failure_zip = (
                ctx.review_root / f"stage_k35_kestrel_failure_{ctx.run_tag}.zip"
            )
            zip_review(ctx.run_dir, failure_zip)
            logger.info("실패 검토 ZIP: %s", failure_zip)
        except Exception:
            logger.exception("실패 검토 ZIP 생성 실패")

        raise
