"""Immutable V24T scientific, time, unit, and source-boundary contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path


START_HEAD = "1322b563c78bb0522e5633ed0524f3865bc154fd"
BRANCH = "codex/v24t-thermal-aware-aidc"
RAW_ROOT = Path(r"C:\Users\kjw39\OneDrive\Desktop\4-2\Mobile ESS\raw데이터\데이터 센터")
ARTIFACT_ROOT = Path("dayahead/artifacts/v24t_thermal_aware_aidc")
FIXED_AEST = timezone(timedelta(hours=10), name="fixed-AEST")
REFERENCE_PUE = 1.30
GFS_CYCLE_UTC = 6
GFS_LEADS = tuple(range(8, 33))
GFS_VARIABLES = {
    "TMP": "2 m above ground",
    "DPT": "2 m above ground",
    "RH": "2 m above ground",
    "PRES": "surface",
    "UGRD": "10 m above ground",
    "VGRD": "10 m above ground",
}
AUTHORIZED_DAYS = tuple(
    date.fromisoformat(value)
    for value in (
        "2025-04-02",
        "2025-04-03",
        "2025-04-12",
        "2025-04-13",
        "2025-04-15",
        "2025-04-22",
        "2025-04-23",
    )
)
LABEL = "MEASURED_NLR_THERMAL_RESPONSE_TRANSFER_WITH_MELBOURNE_WEATHER_FORCING"
TRANSFER_LABEL = "MELBOURNE_INFORMED_THERMAL_EQUIVALENT_AIDC_CASE"
NORMALIZATION_LABEL = "REFERENCE_PUE_ENERGY_NORMALIZATION"
GFS_BASE = "https://noaa-gfs-bdp-pds.s3.amazonaws.com"
DOWNLOAD_CAP_BYTES = 20 * 1024**3


@dataclass(frozen=True)
class D1ForecastWindow:
    """One fixed-AEST operating day and its causal 06Z GFS authority."""

    operating_day: date

    @property
    def cutoff(self) -> datetime:
        """Return D-1 18:00 fixed AEST (08:00 UTC)."""
        return datetime.combine(
            self.operating_day - timedelta(days=1), time(18), tzinfo=FIXED_AEST
        )

    @property
    def initialization_utc(self) -> datetime:
        """Return D-1 06:00 UTC initialization, two hours before cutoff."""
        prior = self.operating_day - timedelta(days=1)
        return datetime.combine(prior, time(GFS_CYCLE_UTC), tzinfo=timezone.utc)

    def validate(self) -> None:
        """Fail if the cycle, cutoff, or lead contract is not causal."""
        if self.cutoff.astimezone(timezone.utc).hour != 8:
            raise ValueError("fixed-AEST D-1 cutoff must equal 08:00 UTC")
        if self.initialization_utc >= self.cutoff.astimezone(timezone.utc):
            raise ValueError("forecast initialization must precede the D-1 cutoff")
        if GFS_LEADS != tuple(range(8, 33)):
            raise ValueError("GFS leads must be exactly f008 through f032")


def artifact_path(name: str) -> Path:
    """Return a path under the isolated V24T artifact root."""
    if Path(name).name != name:
        raise ValueError("artifact name must be a basename")
    return ARTIFACT_ROOT / name
