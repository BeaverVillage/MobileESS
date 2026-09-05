"""Atomic, heartbeat-backed progress evidence for the V39E overnight run."""

from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path
import threading
import time
from typing import Any, Mapping

from dayahead.v39c.freeze import atomic_json


PROGRESS_ROOT = Path("progress")
MASTER_NAME = "V39E_OVERNIGHT_PROGRESS.json"
PREFLIGHT_NAME = "V39E_PREFLIGHT_PROGRESS.json"
CAMPAIGN_NAME = "MAY_CAMPAIGN_PROGRESS.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ProgressTracker:
    """Keep the monitor source current even during long solver calls."""

    def __init__(self, repo: Path, git_head: str, branch: str) -> None:
        self.repo = repo.resolve()
        self.root = self.repo / PROGRESS_ROOT
        self.root.mkdir(parents=True, exist_ok=True)
        self.started = time.time()
        self.lock = threading.Lock()
        self.payload: dict[str, Any] = {
            "artifact_id": "V39E_OVERNIGHT_PROGRESS_V1",
            "phase": "PREFLIGHT",
            "campaign_classification": "PENDING_PREFLIGHT",
            "git_HEAD": git_head,
            "branch": branch,
            "start_time": _now(),
            "last_update": _now(),
            "elapsed_seconds": 0,
            "preflight_READY": 0,
            "preflight_NOT_READY": 0,
            "preflight_missing": 31,
            "preflight_attempt": 1,
            "repair_iteration": 0,
            "last_repair_classification": None,
            "last_repair_commit": None,
            "completed_days": [],
            "running_days": [],
            "pending_days": [f"2025-05-{day:02d}" for day in range(1, 32)],
            "failed_days": [],
            "per_day": {},
            "case_status": {case: 0 for case in ("B0", "B1", "B2", "B3")},
            "worker_PIDs": [os.getpid()],
            "resumable": True,
            "exact_current_blocker": None,
            "latest_completed_day": None,
            "latest_failure": None,
            "temporal_only_days": 0,
            "migration_escalated_days": 0,
            "total_migrations_from_frozen_DA": 0,
            "Actual_temporal_reoptimization_calls": 0,
            "Actual_AIDC_reoptimization_calls": 0,
            "Actual_migration_reoptimization_calls": 0,
            "Actual_WAN_reroute_calls": 0,
            "Fresh_PASS": 0,
            "Fresh_restoration": 0,
            "Fresh_FAIL": 0,
            "overall_progress_percent": 0.0,
            "estimated_remaining_seconds": None,
            "MAY_STARTED": "NO",
            "MAY_COMPLETED": "NO",
        }
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._write_locked()

    def _write_locked(self) -> None:
        self.payload["last_update"] = _now()
        self.payload["elapsed_seconds"] = int(time.time() - self.started)
        atomic_json(self.root / MASTER_NAME, self.payload)
        phase = str(self.payload.get("phase", ""))
        if phase in {"PREFLIGHT", "REPAIR", "DA_FREEZE"}:
            atomic_json(self.root / PREFLIGHT_NAME, self.payload)
        if phase in {"MAY_ACTUAL", "FRESH", "COMPLETE"}:
            atomic_json(self.root / CAMPAIGN_NAME, self.payload)

    def update(self, **values: Any) -> None:
        with self.lock:
            self.payload.update(values)
            self._write_locked()

    def merge(self, values: Mapping[str, Any]) -> None:
        self.update(**dict(values))

    def start_heartbeat(self) -> None:
        if self._thread is not None:
            return

        def beat() -> None:
            while not self._stop.wait(10):
                with self.lock:
                    self._write_locked()

        self._thread = threading.Thread(target=beat, name="v39e-progress", daemon=True)
        self._thread.start()

    def close(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
        with self.lock:
            self._write_locked()


__all__ = [
    "CAMPAIGN_NAME", "MASTER_NAME", "PREFLIGHT_NAME", "PROGRESS_ROOT",
    "ProgressTracker",
]
