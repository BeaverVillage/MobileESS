"""Fixed-AEST D-1 time and resolution contracts for the 96-slot problem."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Iterable, Sequence


FIXED_AEST = timezone(timedelta(hours=10), name="fixed-AEST")
SLOT_MINUTES = 15
SLOT_HOURS = 0.25
SLOTS_PER_DAY = 96
ISSUANCE_HOUR = 18


class InputContractError(ValueError):
    pass


def operating_axis(operating_date: date) -> tuple[datetime, ...]:
    start = datetime.combine(operating_date, time.min, tzinfo=FIXED_AEST)
    return tuple(start + timedelta(minutes=SLOT_MINUTES * index) for index in range(SLOTS_PER_DAY))


def issuance_cutoff(operating_date: date) -> datetime:
    prior = operating_date - timedelta(days=1)
    return datetime.combine(prior, time(ISSUANCE_HOUR), tzinfo=FIXED_AEST)


def require_causal_timestamp(observed_at: datetime, operating_date: date) -> None:
    if observed_at.tzinfo is None:
        raise InputContractError("naive timestamps are prohibited")
    if observed_at.astimezone(FIXED_AEST) > issuance_cutoff(operating_date):
        raise InputContractError("future actual/read after the D-1 cutoff is prohibited")


def pwc_30_to_15(values: Sequence[float]) -> tuple[float, ...]:
    if len(values) != 48:
        raise InputContractError("the AEMO Day-Ahead trajectory must contain 48 half-hours")
    return tuple(float(value) for value in values for _ in range(2))


def average_5_to_15(values: Sequence[float]) -> tuple[float, ...]:
    if len(values) != 288:
        raise InputContractError("realized five-minute input must contain 288 values")
    return tuple(sum(float(value) for value in values[i : i + 3]) / 3.0 for i in range(0, 288, 3))


def sum_energy_5_to_15(values_kwh: Sequence[float]) -> tuple[float, ...]:
    if len(values_kwh) % 3:
        raise InputContractError("five-minute mobility-energy profile length must be divisible by three")
    return tuple(sum(float(value) for value in values_kwh[i : i + 3]) for i in range(0, len(values_kwh), 3))


@dataclass(frozen=True)
class ForecastVintage:
    product: str
    issue_time: datetime
    target_times: tuple[datetime, ...]
    vintage_id: str

    def validate(self, operating_date: date) -> None:
        if self.issue_time.tzinfo is None:
            raise InputContractError("forecast issue time must be timezone-aware")
        axis = operating_axis(operating_date)
        if tuple(t.astimezone(FIXED_AEST) for t in self.target_times) != axis:
            raise InputContractError("forecast vintage is not one complete next-day trajectory")


def select_latest_complete_vintage(
    vintages: Iterable[ForecastVintage], operating_date: date, product: str
) -> ForecastVintage:
    cutoff = issuance_cutoff(operating_date)
    eligible = []
    for vintage in vintages:
        if vintage.product != product:
            continue
        try:
            vintage.validate(operating_date)
        except InputContractError:
            continue
        if vintage.issue_time.astimezone(FIXED_AEST) <= cutoff:
            eligible.append(vintage)
    if not eligible:
        raise InputContractError("FAIL_AEMO_COMPLETE_VINTAGE_NOT_FOUND")
    return max(eligible, key=lambda item: item.issue_time.astimezone(timezone.utc))
