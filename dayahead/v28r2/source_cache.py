"""Atomic, resume-safe cache helpers for April source preparation."""

from __future__ import annotations

import json
import os
from pathlib import Path


def atomic_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    os.replace(temporary, path)


def atomic_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(content)
    os.replace(temporary, path)


def cache_root(repo: Path, day: str | None = None) -> Path:
    if day is not None and day.startswith("2025-05-"):
        return repo / "cache/v28r2_campaign_sources/may_2025"
    return repo / "cache/v28r2_campaign_sources/april_2025"


def day_root(repo: Path, day: str) -> Path:
    return cache_root(repo, day) / "days" / day
