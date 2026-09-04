"""Fail-closed COMMON/Day-Ahead/Actual source namespace firewall."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Mapping


class SourceNamespace(str, Enum):
    COMMON_STATIC = "COMMON_STATIC"
    DAYAHEAD_FORECAST = "DAYAHEAD_FORECAST"
    ACTUAL_REALIZED = "ACTUAL_REALIZED"


def _canonical_sha256(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


@dataclass(frozen=True)
class SourceBinding:
    name: str
    path: Path
    namespace: SourceNamespace


class SourceNamespaceFirewall:
    def __init__(self, bindings: Mapping[str, SourceBinding]):
        self.bindings = dict(bindings)
        if set(self.bindings) != {binding.name for binding in self.bindings.values()}:
            raise ValueError("V29_SOURCE_BINDING_NAME_MISMATCH")
        self.actual_open_count = 0
        self.schedule_sha256: str | None = None

    def freeze_schedule(self, schedule_sha256: str) -> None:
        if len(schedule_sha256) != 64 or any(character not in "0123456789abcdef" for character in schedule_sha256):
            raise ValueError("V29_SCHEDULE_SHA_REQUIRED")
        self.schedule_sha256 = schedule_sha256

    def read_bytes(self, name: str, *, verified_schedule_sha256: str | None = None) -> bytes:
        binding = self.bindings[name]
        if binding.namespace is SourceNamespace.ACTUAL_REALIZED:
            if self.schedule_sha256 is None or verified_schedule_sha256 != self.schedule_sha256:
                raise RuntimeError("V29_ACTUAL_NAMESPACE_BEFORE_SCHEDULE_FREEZE")
            self.actual_open_count += 1
        return binding.path.read_bytes()

    def prefreeze_source_sha256(self) -> str:
        records = {
            name: {"namespace": binding.namespace.value, "sha256": _sha256(binding.path)}
            for name, binding in sorted(self.bindings.items())
            if binding.namespace is not SourceNamespace.ACTUAL_REALIZED
        }
        return _canonical_sha256(records)


def materialize_traffic_mobility_namespaces(combined_path: Path, output_root: Path) -> dict[str, Path]:
    """Split a legacy combined file during source preparation, before a run."""

    source = json.loads(combined_path.read_text(encoding="utf-8"))
    forecast = {key: source[key] for key in (
        "day", "forecast_method", "forecast_q10_volume", "forecast_q50_volume",
        "forecast_q90_volume", "traffic_forecast_namespace",
    )}
    actual = {key: source[key] for key in ("day", "actual_volume", "traffic_actual_namespace")}
    engineering = {key: source[key] for key in (
        "day", "mess", "route_authority", "mobility_energy_authority",
        "initial_state_authority", "event_trigger", "local_repair",
    )}
    payloads = {
        "traffic_forecast.json": forecast,
        "traffic_actual.json": actual,
        "engineering_mobility.json": engineering,
    }
    output_root.mkdir(parents=True, exist_ok=True)
    result = {}
    for name, payload in payloads.items():
        path = output_root / name
        path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
        result[name] = path
    return result
