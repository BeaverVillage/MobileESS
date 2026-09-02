"""Strict D-1 18:00 causal sample contract."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone


FIXED_AEST = timezone(timedelta(hours=10), name="AEST_FIXED_UTC_PLUS_10")
TARGET_STEPS = 288
LINK_COUNT = 509
RESOLUTION = timedelta(minutes=5)


@dataclass(frozen=True)
class CausalDayAheadSample:
    forecast_day: date
    issue_time: datetime
    max_input_timestamp: datetime
    target_start: datetime
    target_end: datetime
    source_days_used: tuple[date, ...]

    def __post_init__(self) -> None:
        expected_issue = datetime.combine(
            self.forecast_day - timedelta(days=1), time(18, 0), FIXED_AEST
        )
        expected_start = datetime.combine(self.forecast_day, time(0, 0), FIXED_AEST)
        expected_end = expected_start + (TARGET_STEPS - 1) * RESOLUTION
        if self.issue_time != expected_issue:
            raise ValueError("issue_time must be D-1 18:00 fixed AEST")
        if self.max_input_timestamp > self.issue_time:
            raise ValueError("max_input_timestamp exceeds issue_time")
        if self.target_start != expected_start or self.target_end != expected_end:
            raise ValueError("target axis must span D 00:00 through D 23:55")
        if any(day >= self.forecast_day for day in self.source_days_used):
            raise ValueError("source days must precede forecast day")

    @property
    def target_timestamps(self) -> tuple[datetime, ...]:
        return tuple(self.target_start + step * RESOLUTION for step in range(TARGET_STEPS))


def causal_sample_contract(forecast_day: date, source_days_used: tuple[date, ...]) -> CausalDayAheadSample:
    issue = datetime.combine(forecast_day - timedelta(days=1), time(18, 0), FIXED_AEST)
    start = datetime.combine(forecast_day, time(0, 0), FIXED_AEST)
    return CausalDayAheadSample(
        forecast_day=forecast_day,
        issue_time=issue,
        max_input_timestamp=issue - RESOLUTION,
        target_start=start,
        target_end=start + (TARGET_STEPS - 1) * RESOLUTION,
        source_days_used=tuple(source_days_used),
    )
