"""Day-ahead, Actual, and PI namespace-separated input bundles."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Mapping

from .time_contract import SLOTS_PER_DAY, canonical_axis, dayahead_cutoff


DAYAHEAD_NAMESPACE = "DAYAHEAD_FORECAST_ONLY"
ACTUAL_NAMESPACE = "ACTUAL_REALIZED_AFTER_SCHEDULE_FREEZE"
PI_NAMESPACE = "PERFECT_INFORMATION_SEPARATE_EXPOST"


@dataclass
class InputNamespaceGate:
    schedule_sha256: str | None = None
    schedule_frozen: bool = False
    actual_namespace_open: bool = False
    counters: dict[str, int] = field(default_factory=lambda: {
        "future_actual_reads_before_DA_freeze": 0,
        "actual_namespace_open_before_DA_freeze": 0,
    })

    def freeze_schedule(self, payload: Mapping[str, Any]) -> str:
        if self.actual_namespace_open:
            raise RuntimeError("V28_CANNOT_FREEZE_AFTER_ACTUAL_NAMESPACE_OPEN")
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
        self.schedule_sha256 = hashlib.sha256(encoded).hexdigest()
        self.schedule_frozen = True
        return self.schedule_sha256

    def open_actual(self, expected_schedule_sha256: str) -> None:
        if not self.schedule_frozen or not self.schedule_sha256:
            self.counters["actual_namespace_open_before_DA_freeze"] += 1
            raise RuntimeError("V28_ACTUAL_NAMESPACE_BEFORE_SCHEDULE_FREEZE")
        if expected_schedule_sha256 != self.schedule_sha256:
            raise RuntimeError("V28_FROZEN_SCHEDULE_SHA_MISMATCH")
        self.actual_namespace_open = True

    def assert_actual_access_allowed(self) -> None:
        if not self.actual_namespace_open:
            self.counters["future_actual_reads_before_DA_freeze"] += 1
            raise RuntimeError("V28_ACTUAL_READ_BEFORE_DA_FREEZE")


def validate_bundle(bundle: Mapping[str, Any], *, day: str, namespace: str) -> None:
    if namespace not in {DAYAHEAD_NAMESPACE, ACTUAL_NAMESPACE, PI_NAMESPACE}:
        raise ValueError(f"V28_UNKNOWN_INPUT_NAMESPACE:{namespace}")
    if bundle.get("operating_day") != day or bundle.get("namespace") != namespace:
        raise ValueError("V28_INPUT_BUNDLE_IDENTITY_MISMATCH")
    timestamps = tuple(bundle.get("timestamps", ()))
    if len(timestamps) != SLOTS_PER_DAY:
        raise ValueError("V28_INPUT_BUNDLE_NOT_96_SLOTS")
    expected = tuple(value.isoformat() for value in canonical_axis(day))
    if timestamps != expected:
        raise ValueError("V28_INPUT_BUNDLE_TIME_AXIS_MISMATCH")
    if namespace == DAYAHEAD_NAMESPACE:
        if bundle.get("forecast_cutoff") != dayahead_cutoff(day).isoformat():
            raise ValueError("V28_DAYAHEAD_CUTOFF_MISMATCH")
        if any(key.startswith("actual_") or key.startswith("realized_") for key in bundle):
            raise ValueError("V28_ACTUAL_FIELD_IN_DAYAHEAD_BUNDLE")


def bundle_identity(bundle: Mapping[str, Any]) -> str:
    validate_bundle(bundle, day=str(bundle["operating_day"]), namespace=str(bundle["namespace"]))
    return hashlib.sha256(
        json.dumps(bundle, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()
