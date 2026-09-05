"""V39L durable liveness envelope around the frozen V39E progress schema."""

from __future__ import annotations

from datetime import datetime, timezone
import os
import time
from typing import Any

from dayahead.v39e.progress import (
    CAMPAIGN_NAME,
    MASTER_NAME,
    PREFLIGHT_NAME,
    ProgressTracker,
)

from .infrastructure import (
    ORCHESTRATOR_TOKENS,
    campaign_fingerprint,
    current_process_identity,
    durable_atomic_json,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class V39LProgressTracker(ProgressTracker):
    """Keep V39E data fields while adding the V39L liveness contract."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self._v39l_ready = False
        super().__init__(*args, **kwargs)
        identity = current_process_identity()
        fingerprint = campaign_fingerprint(self.repo)
        with self.lock:
            self.payload.update({
                "orchestrator_pid": os.getpid(),
                "orchestrator_parent_pid": identity.get("parent_pid"),
                "orchestrator_creation_time_utc": identity.get("creation_time_utc"),
                "orchestrator_command_line": identity.get("command_line"),
                "orchestrator_command_identity": "V39L_DETACHED_MAY_RESUME_V1",
                "orchestrator_command_match_tokens": list(ORCHESTRATOR_TOKENS),
                "current_campaign_fingerprint": fingerprint[
                    "campaign_fingerprint_sha256"
                ],
                "campaign_fingerprint_inputs": fingerprint,
                "heartbeat_period_seconds": 10,
                "active_worker_PIDs": [],
                "active_dates": [],
            })
            self._v39l_ready = True
            self._write_locked()

    def _write_locked(self) -> None:
        if not self._v39l_ready:
            super()._write_locked()
            return
        self.payload["last_update"] = _now()
        self.payload["heartbeat_timestamp_utc"] = self.payload["last_update"]
        self.payload["active_dates"] = list(self.payload.get("running_days", []))
        worker_pids = self.payload.get("worker_PIDs", [])
        if isinstance(worker_pids, dict):
            values = worker_pids.values()
        else:
            values = worker_pids
        self.payload["active_worker_PIDs"] = [
            int(pid) for pid in values if int(pid) != os.getpid()
        ]
        self.payload["elapsed_seconds"] = int(time.time() - self.started)
        durable_atomic_json(self.root / MASTER_NAME, self.payload)
        phase = str(self.payload.get("phase", ""))
        if phase in {"PREFLIGHT", "REPAIR", "DA_FREEZE"}:
            durable_atomic_json(self.root / PREFLIGHT_NAME, self.payload)
        if phase in {"MAY_ACTUAL", "FRESH", "COMPLETE"}:
            durable_atomic_json(self.root / CAMPAIGN_NAME, self.payload)


__all__ = ["V39LProgressTracker"]
