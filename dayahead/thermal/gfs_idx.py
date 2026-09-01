"""NOAA GFS `.idx` parser and exact byte-range selection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class IdxMessage:
    """One indexed GRIB2 message byte range and semantic identity."""

    number: int
    start: int
    end: int
    variable: str
    level: str
    raw_line: str

    @property
    def byte_count(self) -> int:
        """Return inclusive message size [bytes]."""
        return self.end - self.start + 1

    @property
    def range_header(self) -> str:
        """Return an HTTP Range header value for this message only."""
        return f"bytes={self.start}-{self.end}"


def parse_idx(text: str, object_size: int) -> list[IdxMessage]:
    """Parse wgrib2-style IDX text using the next offset as each message end."""
    raw: list[tuple[int, int, str, str, str]] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        parts = line.split(":")
        if len(parts) < 6:
            raise ValueError(f"malformed idx line: {line!r}")
        raw.append((int(parts[0]), int(parts[1]), parts[3], parts[4], line))
    if not raw:
        raise ValueError("empty idx")
    if any(raw[i][1] >= raw[i + 1][1] for i in range(len(raw) - 1)):
        raise ValueError("idx offsets are not strictly increasing")
    if object_size <= raw[-1][1]:
        raise ValueError("object size does not contain final indexed message")
    result: list[IdxMessage] = []
    for i, (number, start, variable, level, line) in enumerate(raw):
        end = raw[i + 1][1] - 1 if i + 1 < len(raw) else object_size - 1
        result.append(IdxMessage(number, start, end, variable, level, line))
    return result


def select_messages(
    messages: Iterable[IdxMessage], required: dict[str, str]
) -> dict[str, IdxMessage]:
    """Select exactly one message for each required variable and exact level."""
    selected: dict[str, IdxMessage] = {}
    for message in messages:
        if message.variable in required and message.level == required[message.variable]:
            if message.variable in selected:
                raise ValueError(
                    f"duplicate exact IDX match for {message.variable}:{message.level}"
                )
            selected[message.variable] = message
    missing = sorted(set(required) - set(selected))
    if missing:
        raise ValueError(f"missing required IDX messages: {missing}")
    return selected
