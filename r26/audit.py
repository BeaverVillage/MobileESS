"""Append-only JSONL audit records for the R26 controller."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import threading
from typing import Any, Mapping, Optional


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    return value


class AuditLogger:
    """Thread-safe append-only logger; a disabled logger is a valid no-op."""

    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = path
        self._lock = threading.Lock()

    def emit(self, event_type: str, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        record = {
            "schema_version": "r26.audit.v1",
            "timestamp_utc": utc_now(),
            "event_type": event_type,
            **_jsonable(payload),
        }
        if self.path is not None:
            line = json.dumps(record, sort_keys=True, separators=(",", ":"), allow_nan=False)
            with self._lock:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with self.path.open("a", encoding="utf-8", newline="\n") as handle:
                    handle.write(line + "\n")
                    handle.flush()
                    os.fsync(handle.fileno())
        return record


class MemoryAuditLogger(AuditLogger):
    def __init__(self) -> None:
        super().__init__(None)
        self.records: list[Mapping[str, Any]] = []

    def emit(self, event_type: str, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        record = super().emit(event_type, payload)
        self.records.append(record)
        return record
