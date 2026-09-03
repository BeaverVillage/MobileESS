"""Run only the invalidated repaired Apr-01--20 V35 case-days."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sys
import uuid

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from dayahead.v35.campaign import ARTIFACT_RELATIVE, CACHE_RELATIVE, finalize_calibration, run_phase
from dayahead.v35.contracts import CALIBRATION_DAYS, PHASE_CALIBRATION
from dayahead.v35.execution import DEFAULT_SOURCE_REPO, git_head
from dayahead.v35.progress import Progress
from dayahead.v35r2.forensic import APR01_20, require_apr01_20


def main() -> None:
    if tuple(CALIBRATION_DAYS) != tuple(APR01_20):
        raise RuntimeError("V35R2_CALIBRATION_SCOPE_DRIFT")
    artifact_root = REPO / ARTIFACT_RELATIVE
    cache_root = REPO / CACHE_RELATIVE
    run_id = f"v35r2-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
    progress = Progress(
        PHASE_CALIBRATION,
        None,
        None,
        0,
        0,
        0,
        git_head(REPO),
        run_id,
        False,
    )
    progress.write(artifact_root / "V35_PROGRESS.json")
    for index, day in enumerate(APR01_20, 1):
        require_apr01_20(day)
        print(f"V35R2_DAY_START {index}/20 {day}", flush=True)
        result = run_phase(
            repo=REPO,
            source_repo=DEFAULT_SOURCE_REPO,
            artifact_root=artifact_root,
            phase=PHASE_CALIBRATION,
            days=(day,),
            progress=progress,
            retry_limit=5,
        )
        print(
            f"V35R2_DAY_PASS {index}/20 {day} "
            f"attempt={result[0]['attempt']} elapsed={result[0]['elapsed_seconds']:.1f}s",
            flush=True,
        )
    print("V35R2_REBUILD_CORRECTION_START", flush=True)
    _candidates, summary = finalize_calibration(REPO, artifact_root, cache_root)
    print(
        f"V35R2_REBUILD_CORRECTION_PASS residual_count={summary['count']}",
        flush=True,
    )


if __name__ == "__main__":
    main()

