"""Fail-closed namespace and read ledger for V33M3."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import hashlib
import json


class CausalityError(RuntimeError):
    """Raised when future or pre-freeze Actual information is requested."""


@dataclass
class CausalityLedger:
    issue_time: datetime
    dday_actual_scats_feature_reads: int = 0
    dday_sumo_realized_feature_reads: int = 0
    post_issue_actual_refresh_calls: int = 0
    rolling_actual_assimilation_after_issue: int = 0
    dayahead_sumo_actual_reads: int = 0
    dayahead_dday_scats_actual_reads: int = 0
    dayahead_post_issue_feature_reads: int = 0
    actual_namespace_open_before_da_freeze: int = 0
    actual_reroute_calls: int = 0
    actual_mess_optimizer_calls: int = 0
    actual_route_change_count: int = 0
    _frozen: bool = False

    def __post_init__(self) -> None:
        if self.issue_time.tzinfo is None:
            raise CausalityError("issue time must be timezone-aware")

    def record_feature_read(self, timestamp: datetime, source: str) -> None:
        if timestamp.tzinfo is None:
            raise CausalityError("feature timestamp must be timezone-aware")
        if timestamp > self.issue_time:
            self.dayahead_post_issue_feature_reads += 1
            if source == "SCATS_ACTUAL":
                self.dday_actual_scats_feature_reads += 1
                self.dayahead_dday_scats_actual_reads += 1
            if source == "SUMO_REALIZED":
                self.dday_sumo_realized_feature_reads += 1
                self.dayahead_sumo_actual_reads += 1
            raise CausalityError("V33M3_TRAFFIC_DATA_CAUSALITY_FAIL")

    def record_actual_refresh(self) -> None:
        self.post_issue_actual_refresh_calls += 1
        raise CausalityError("post-issue Actual refresh is prohibited")

    def record_rolling_assimilation(self) -> None:
        self.rolling_actual_assimilation_after_issue += 1
        raise CausalityError("rolling Actual assimilation is prohibited")

    def freeze(self, payload_sha: str) -> "DayAheadFreeze":
        self.assert_clean()
        self._frozen = True
        return DayAheadFreeze(self.issue_time, payload_sha)

    def open_actual_namespace(self, freeze: "DayAheadFreeze" | None) -> None:
        if not self._frozen or freeze is None or freeze.issue_time != self.issue_time:
            self.actual_namespace_open_before_da_freeze += 1
            raise CausalityError("Actual namespace cannot open before Day-Ahead freeze")

    def assert_clean(self) -> None:
        counters = self.to_dict()
        if any(value != 0 for value in counters.values()):
            raise CausalityError("V33M3_TRAFFIC_DATA_CAUSALITY_FAIL")

    def to_dict(self) -> dict[str, int]:
        return {
            "D_DAY_ACTUAL_SCATS_FEATURE_READS": self.dday_actual_scats_feature_reads,
            "D_DAY_SUMO_REALIZED_FEATURE_READS": self.dday_sumo_realized_feature_reads,
            "POST_ISSUE_ACTUAL_REFRESH_CALLS": self.post_issue_actual_refresh_calls,
            "ROLLING_ACTUAL_ASSIMILATION_AFTER_ISSUE": self.rolling_actual_assimilation_after_issue,
            "DAYAHEAD_SUMO_ACTUAL_READS": self.dayahead_sumo_actual_reads,
            "DAYAHEAD_DDAY_SCATS_ACTUAL_READS": self.dayahead_dday_scats_actual_reads,
            "DAYAHEAD_POST_ISSUE_FEATURE_READS": self.dayahead_post_issue_feature_reads,
            "ACTUAL_NAMESPACE_OPEN_BEFORE_DA_FREEZE": self.actual_namespace_open_before_da_freeze,
            "ACTUAL_REROUTE_CALLS": self.actual_reroute_calls,
            "ACTUAL_MESS_OPTIMIZER_CALLS": self.actual_mess_optimizer_calls,
            "ACTUAL_ROUTE_CHANGE_COUNT": self.actual_route_change_count,
        }


@dataclass(frozen=True)
class DayAheadFreeze:
    issue_time: datetime
    payload_sha: str

    @property
    def token_sha(self) -> str:
        payload = {"issue_time": self.issue_time.isoformat(), "payload_sha": self.payload_sha}
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
