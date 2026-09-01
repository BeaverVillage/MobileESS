"""Deterministic supporting traffic pipeline for the D-1 Day-Ahead run."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from statistics import mean
from typing import Iterable, Mapping, Sequence
from zoneinfo import ZoneInfo

from .input_contract import FIXED_AEST, InputContractError, operating_axis, require_causal_timestamp


MELBOURNE = ZoneInfo("Australia/Melbourne")


@dataclass(frozen=True)
class ScatsObservation:
    scats_id: str
    local_civil_time: datetime
    value: float
    observed_at: datetime
    fold: int = 0


@dataclass(frozen=True)
class RouteForecast:
    route_id: str
    target_times: tuple[datetime, ...]
    q10_minutes: tuple[float, ...]
    q50_minutes: tuple[float, ...]
    q90_minutes: tuple[float, ...]
    expected_minutes: tuple[float, ...]
    safe_minutes: tuple[float, ...]
    reachable: tuple[bool, ...]
    namespace: str = "TRAFFIC_DA_FORECAST"

    def validate(self, operating_date: date) -> None:
        axis = operating_axis(operating_date)
        if self.namespace != "TRAFFIC_DA_FORECAST" or self.target_times != axis:
            raise InputContractError("traffic forecast namespace/axis mismatch")
        arrays = (self.q10_minutes, self.q50_minutes, self.q90_minutes, self.expected_minutes, self.safe_minutes, self.reachable)
        if any(len(values) != 96 for values in arrays):
            raise InputContractError("route forecast must contain exactly 96 slots")
        for q10, q50, q90, safe in zip(self.q10_minutes, self.q50_minutes, self.q90_minutes, self.safe_minutes):
            if not (0 <= q10 <= q50 <= q90 <= safe):
                raise InputContractError("traffic quantiles/Safe ETA are not ordered")


def localize_scats_time(local_civil_time: datetime, *, fold: int = 0) -> datetime:
    """Resolve Melbourne civil time first, then convert to fixed AEST.

    Non-existent spring-forward wall times fail closed. Ambiguous fall-back times
    require the source-provided ``fold`` bit.
    """
    if local_civil_time.tzinfo is not None:
        raise InputContractError("SCATS local civil time must be naive before localization")
    candidate = local_civil_time.replace(tzinfo=MELBOURNE, fold=fold)
    round_trip = candidate.astimezone(ZoneInfo("UTC")).astimezone(MELBOURNE)
    if round_trip.replace(tzinfo=None) != local_civil_time or round_trip.fold != fold:
        raise InputContractError("NONEXISTENT_OR_UNRESOLVED_SCATS_CIVIL_TIME")
    return candidate.astimezone(FIXED_AEST)


def aggregate_scats_15min(
    observations: Iterable[ScatsObservation], operating_date: date
) -> tuple[dict[tuple[str, datetime], float], dict[str, object]]:
    buckets: dict[tuple[str, datetime], list[float]] = defaultdict(list)
    duplicates = 0
    for row in observations:
        require_causal_timestamp(row.observed_at, operating_date)
        stamp = localize_scats_time(row.local_civil_time, fold=row.fold)
        slot = stamp.replace(minute=(stamp.minute // 15) * 15, second=0, microsecond=0)
        key = (row.scats_id, slot)
        duplicates += int(bool(buckets[key]))
        buckets[key].append(float(row.value))
    aggregated = {key: mean(values) for key, values in sorted(buckets.items())}
    axis = set(operating_axis(operating_date))
    sensor_ids = sorted({key[0] for key in buckets})
    missing = {sensor: 96 - sum((sensor, slot) in aggregated for slot in axis) for sensor in sensor_ids}
    return aggregated, {
        "authority_id": "TRAFFIC_DA_CANONICAL_15MIN_V1",
        "duplicate_rows_aggregated": duplicates,
        "missing_slots_by_scats": missing,
        "aggregation": "arithmetic mean within deterministic fixed-AEST 15-minute buckets",
    }


def known_future_calendar(axis: Sequence[datetime], *, public_holidays: Iterable[date] = ()) -> tuple[dict[str, object], ...]:
    holidays = set(public_holidays)
    return tuple({
        "time_of_day_slot": stamp.hour * 4 + stamp.minute // 15,
        "day_of_week": stamp.weekday(),
        "weekend": stamp.weekday() >= 5,
        "public_holiday": stamp.date() in holidays,
    } for stamp in axis)


def assert_separate_namespaces(forecast_namespace: str, actual_namespace: str) -> None:
    if forecast_namespace == actual_namespace:
        raise InputContractError("forecast and actual/evaluation namespaces must be separate")
    if forecast_namespace != "TRAFFIC_DA_FORECAST" or actual_namespace != "TRAFFIC_DA_ACTUAL":
        raise InputContractError("unrecognized traffic namespace")
