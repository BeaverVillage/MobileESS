"""D-1 forecast-cohort admission firewall, isolated from historical labels."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from .aidc_labels import HISTORICAL_ELIGIBILITY_EXPOST_FIELDS

AUTHORITY_ID = "D1_ADMISSION_ELIGIBILITY_V1"
EXPOST_DENYLIST = HISTORICAL_ELIGIBILITY_EXPOST_FIELDS | frozenset({
    "completed", "realized_runtime", "realized_end_time", "job_id", "queued_job_id",
})
ALLOWED_FIELDS = frozenset({
    "cohort_id", "target_slot", "forecast_q50_nodeh", "forecast_issue_cutoff",
    "forecast_vintage_id", "node_class", "runtime_class",
})


@dataclass(frozen=True)
class ForecastCohortAdmission:
    cohort_id: str
    arrivals_q50_nodeh: tuple[float, ...]
    initial_backlog_nodeh: float = 0.0
    individual_queued_job_injection_count: int = 0

    def validate(self) -> None:
        if len(self.arrivals_q50_nodeh) != 96 or any(value < 0 for value in self.arrivals_q50_nodeh):
            raise ValueError("D1_FORECAST_COHORT_REQUIRES_96_NONNEGATIVE_ARRIVALS")
        if self.initial_backlog_nodeh != 0:
            raise ValueError("D1_ADMISSION_REQUIRES_B_B1_ZERO")
        if self.individual_queued_job_injection_count != 0:
            raise ValueError("D1_INDIVIDUAL_QUEUED_JOB_INJECTION_PROHIBITED")


def validate_admission_record(record: Mapping[str, object]) -> None:
    forbidden = sorted(set(record) & EXPOST_DENYLIST)
    if forbidden:
        raise ValueError(f"FAIL_AIDC_D1_ADMISSION_CAUSALITY:{','.join(forbidden)}")
    unknown = sorted(set(record) - ALLOWED_FIELDS)
    if unknown:
        raise ValueError(f"D1_ADMISSION_FIELD_NOT_AUTHORIZED:{','.join(unknown)}")


def contract_artifact() -> dict[str, object]:
    return {
        "authority_id": AUTHORITY_ID,
        "mode": "FORECAST_COHORT_ONLY",
        "initial_backlog_nodeh": 0.0,
        "individual_queued_job_injection_count": 0,
        "allowed_fields": sorted(ALLOWED_FIELDS),
        "expost_field_denylist": sorted(EXPOST_DENYLIST),
    }
