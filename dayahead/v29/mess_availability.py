"""Canonical deterministic MESS connection-delay semantics."""

from __future__ import annotations

import copy
from typing import Mapping


CONNECTION_DELAY_SLOTS = 1


def normalize_mess_record(record: Mapping[str, object]) -> dict[str, object]:
    """Return a copy with exactly one unavailable slot after each transit."""

    result = copy.deepcopy(dict(record))
    modes = list(map(str, result["mode"]))
    available = list(map(bool, result["available"]))
    if len(modes) != 96 or len(available) != 96:
        raise ValueError("V29_MESS_AVAILABILITY_AXIS")
    source_modes = tuple(modes)
    for slot in range(1, 96):
        if source_modes[slot - 1] == "TRANSIT" and source_modes[slot] == "CONNECTED":
            modes[slot] = "CONNECTION_DELAY"
            available[slot] = False
    result["mode"] = modes
    result["available"] = available
    return result


def connection_delay_slots(record: Mapping[str, object]) -> tuple[int, ...]:
    normalized = normalize_mess_record(record)
    return tuple(index for index, mode in enumerate(normalized["mode"]) if mode == "CONNECTION_DELAY")
