"""V13.2 January 2025 independent-daily initialization authority."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, timedelta
import hashlib
import json
from typing import Any, Iterable


METHODS = tuple(f"B{index}" for index in range(8))
ELECTRICAL_STRESS_METHODS = tuple(f"B{index:02d}" for index in range(10))
START_DATE = date(2025, 1, 1)
END_DATE = date(2025, 1, 31)
MESS_IDS = ("MESS01", "MESS02", "MESS03", "MESS04")
MESS_LOCATIONS = ("STA09", "IDC12", "STA07", "STA11")


class DailyInitializationError(ValueError):
    pass


@dataclass(frozen=True)
class CanonicalDailyPre:
    mess_energy_kwh: tuple[float, float, float, float] = (760.0, 760.0, 760.0, 760.0)
    mess_locations: tuple[str, str, str, str] = MESS_LOCATIONS
    mess_phase: tuple[str, str, str, str] = ("STAY", "STAY", "STAY", "STAY")
    mess_in_transit: tuple[bool, bool, bool, bool] = (False, False, False, False)
    mess_remaining_travel_steps: tuple[int, int, int, int] = (0, 0, 0, 0)
    mobility_profile_empty: bool = True
    ai_queue_empty: bool = True
    ai_running_empty: bool = True
    ai_migration_restart_checkpoint_empty: bool = True
    wan_inventory_empty: bool = True
    wan_pipeline_empty: bool = True
    compute_debt_gpu_hours: float = 0.0
    energy_debt_kwh: float = 0.0
    rebound_state: float = 0.0
    active_slow_plan: None = None
    last_slow_replan: str = "INITIALIZATION"
    risk_state: str = "INITIALIZED"

    def validate(self) -> None:
        if len(set(MESS_IDS)) != 4 or len(self.mess_locations) != 4:
            raise DailyInitializationError("canonical MESS axis must contain four units")
        if any(value != 760.0 for value in self.mess_energy_kwh):
            raise DailyInitializationError("each MESS must cold-start at 760 kWh")
        if self.mess_locations != MESS_LOCATIONS:
            raise DailyInitializationError("canonical MESS location order changed")
        if any(self.mess_in_transit) or any(self.mess_remaining_travel_steps):
            raise DailyInitializationError("daily PRE cannot contain an active movement")
        if self.compute_debt_gpu_hours != 0.0 or self.energy_debt_kwh != 0.0:
            raise DailyInitializationError("daily PRE debt must be zero")
        if self.active_slow_plan is not None:
            raise DailyInitializationError("daily PRE cannot persist a slow plan")

    def payload(self) -> dict[str, Any]:
        self.validate()
        return asdict(self)

    def sha256(self) -> str:
        encoded = json.dumps(self.payload(), sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


def january_dates() -> tuple[str, ...]:
    count = (END_DATE - START_DATE).days + 1
    return tuple((START_DATE + timedelta(days=offset)).isoformat() for offset in range(count))


def build_daily_pre_artifacts(authority_document_sha256: str) -> tuple[dict[str, Any], dict[str, Any]]:
    return build_calendar_daily_pre_artifacts(
        authority_document_sha256,
        calendar_dates=january_dates(),
        campaign_id="JAN2025",
        schema_prefix="JAN2025",
    )


def build_calendar_daily_pre_artifacts(
    authority_document_sha256: str,
    *,
    calendar_dates: Iterable[str],
    campaign_id: str,
    schema_prefix: str = "CALENDAR_PERIOD",
    methods: Iterable[str] = METHODS,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if len(authority_document_sha256) != 64:
        raise DailyInitializationError("authority SHA-256 is required")
    dates = tuple(str(value) for value in calendar_dates)
    if not dates or len(set(dates)) != len(dates):
        raise DailyInitializationError("calendar dates must be nonempty and unique")
    if not campaign_id or not schema_prefix:
        raise DailyInitializationError("campaign identity is required")
    method_axis = tuple(str(value) for value in methods)
    if method_axis not in {METHODS, ELECTRICAL_STRESS_METHODS}:
        raise DailyInitializationError(
            "method axis must be historical B0-B7 or electrical-stress B00-B09"
        )
    canonical = CanonicalDailyPre()
    canonical_hash = canonical.sha256()
    rows = [
        {
            "calendar_date": calendar_date,
            "day_index": day_index,
            "comparison_method_id": method,
            "daily_episode_id": f"{campaign_id}-D{day_index:02d}-{method}",
            "controller_burn_in_steps": 0,
            "daily_state_reset": True,
            "cross_day_state_carryover": False,
            "method_independent_pre_sha256": canonical_hash,
        }
        for day_index, calendar_date in enumerate(dates, 1)
        for method in method_axis
    ]
    manifest = {
        "schema_version": f"{schema_prefix}_DAILY_CANONICAL_PRE_MANIFEST_V13_13",
        "status": "PASS",
        "authority_document_sha256": authority_document_sha256,
        "campaign_id": campaign_id,
        "calendar_dates": list(dates),
        "methods": list(method_axis),
        "daily_episode_count": len(rows),
        "scored_issues_per_episode": 288,
        "committed_scored_issue_target": len(rows) * 288,
        "canonical_pre": canonical.payload(),
        "canonical_pre_sha256": canonical_hash,
        "episodes": rows,
    }
    certificate = certify_daily_pre_identity(manifest)
    return manifest, certificate


def certify_daily_pre_identity(manifest: dict[str, Any]) -> dict[str, Any]:
    rows: Iterable[dict[str, Any]] = manifest.get("episodes", ())
    rows = tuple(rows)
    dates = tuple(manifest.get("calendar_dates", ()))
    methods = tuple(manifest.get("methods", ()))
    if (
        not dates
        or methods not in {METHODS, ELECTRICAL_STRESS_METHODS}
        or len(rows) != len(dates) * len(methods)
    ):
        raise DailyInitializationError(
            "daily population must use the complete B0-B7 or B00-B09 axis"
        )
    if len(set(dates)) != len(dates):
        raise DailyInitializationError("daily population contains duplicate dates")
    for calendar_date in dates:
        daily = tuple(row for row in rows if row["calendar_date"] == calendar_date)
        if tuple(row["comparison_method_id"] for row in daily) != METHODS:
            raise DailyInitializationError(f"method axis mismatch on {calendar_date}")
        if len({row["method_independent_pre_sha256"] for row in daily}) != 1:
            raise DailyInitializationError(f"same-date PRE identity mismatch on {calendar_date}")
        if any(not row["daily_state_reset"] or row["cross_day_state_carryover"] for row in daily):
            raise DailyInitializationError(f"daily reset contract mismatch on {calendar_date}")
    return {
        "schema_version": "CALENDAR_DAILY_INITIAL_STATE_IDENTITY_CERTIFICATE_V13_13",
        "status": "PASS",
        "calendar_date_count": len(dates),
        "methods_per_date": len(methods),
        "daily_episode_count": len(rows),
        "same_date_b0_b7_pre_identity": True,
        "same_date_all_methods_pre_identity": True,
        "method_ids": list(methods),
        "controller_burn_in_steps": 0,
        "daily_state_reset": True,
        "cross_day_state_carryover": False,
        "canonical_pre_sha256": manifest["canonical_pre_sha256"],
        "authority_document_sha256": manifest["authority_document_sha256"],
    }
