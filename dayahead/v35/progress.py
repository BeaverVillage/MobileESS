"""Machine-readable V35 campaign progress heartbeat."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path

from .storage import atomic_json


@dataclass
class Progress:
    current_phase: str
    current_day: str | None
    current_case: str | None
    completed_pass_count: int
    failed_count: int
    retry_count: int
    current_HEAD: str
    current_run_id: str
    May_opened: bool
    last_heartbeat: str = ""

    def write(self, path: Path) -> str:
        self.last_heartbeat = datetime.now(timezone.utc).isoformat()
        return atomic_json(path, asdict(self))
