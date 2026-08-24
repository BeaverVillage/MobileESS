"""Frozen January-2025 calibration authority for the PFR5 event-risk monitor."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
import hashlib
import json
import math
from pathlib import Path
from typing import Mapping

from .risk import RiskFamily


SCHEMA_VERSION = "PFR5_EVENT_RISK_CALIBRATION_JAN2025_V1"
AUTHORITY_ID = "JAN2025_B6_RAW_DAY_BLOCK_JOINT_UNDERPREDICTION_V1"
RISK_FAMILY_SCALES: Mapping[str, float] = {
    RiskFamily.SOC.value: 100.0,
    RiskFamily.DEADLINE.value: 1.0,
    RiskFamily.GPU.value: 32.0,
    RiskFamily.WAN.value: 1.0,
    RiskFamily.VOLTAGE.value: 0.01,
    RiskFamily.THERMAL.value: 0.10,
}


class RiskCalibrationContractError(ValueError):
    """Raised when a calibrated B7/B8 run lacks a frozen valid authority."""


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class FrozenRiskCalibration:
    authority_id: str
    alpha: float
    source_method: str
    source_period: str
    calibration_dates: tuple[str, ...]
    finite_sample_rank: int
    normalized_joint_quantile: float
    predeclared_scales: Mapping[str, float]
    calibrated_increments: Mapping[str, float]
    source_audit_sha256: str
    artifact_sha256: str
    february_labels_used_for_fit: bool = False
    march_outcomes_read: bool = False

    def validate(self) -> None:
        if self.authority_id != AUTHORITY_ID:
            raise RiskCalibrationContractError("risk calibration authority ID mismatch")
        if self.source_method != "B6" or self.source_period != "2025-01":
            raise RiskCalibrationContractError(
                "event-risk calibration must use January-2025 B6 raw risk"
            )
        if self.february_labels_used_for_fit or self.march_outcomes_read:
            raise RiskCalibrationContractError(
                "February/March labels are prohibited from January calibration fit"
            )
        expected_dates = tuple(
            (date(2025, 1, 1) + timedelta(days=offset)).isoformat()
            for offset in range(31)
        )
        if self.calibration_dates != expected_dates:
            raise RiskCalibrationContractError("risk calibration date axis is not January 2025")
        if not 0.0 < self.alpha < 1.0:
            raise RiskCalibrationContractError("risk calibration alpha must lie in (0,1)")
        expected_rank = min(
            math.ceil((len(self.calibration_dates) + 1) * (1.0 - self.alpha)),
            len(self.calibration_dates),
        )
        if self.finite_sample_rank != expected_rank:
            raise RiskCalibrationContractError("finite-sample calibration rank mismatch")
        if set(self.predeclared_scales) != set(RISK_FAMILY_SCALES):
            raise RiskCalibrationContractError("risk calibration scale family axis mismatch")
        if set(self.calibrated_increments) != set(RISK_FAMILY_SCALES):
            raise RiskCalibrationContractError("risk calibration increment family axis mismatch")
        if not math.isfinite(self.normalized_joint_quantile) or self.normalized_joint_quantile < 0.0:
            raise RiskCalibrationContractError("normalized joint quantile is invalid")
        for family, frozen_scale in RISK_FAMILY_SCALES.items():
            scale = float(self.predeclared_scales[family])
            increment = float(self.calibrated_increments[family])
            if not math.isclose(scale, frozen_scale, rel_tol=0.0, abs_tol=1e-12):
                raise RiskCalibrationContractError(
                    f"predeclared risk scale changed for {family}"
                )
            expected_increment = self.normalized_joint_quantile * scale
            if not math.isfinite(increment) or not math.isclose(
                increment, expected_increment, rel_tol=1e-12, abs_tol=1e-12
            ):
                raise RiskCalibrationContractError(
                    f"calibrated risk increment mismatch for {family}"
                )
        if len(self.source_audit_sha256) != 64 or len(self.artifact_sha256) != 64:
            raise RiskCalibrationContractError("risk calibration fingerprints are invalid")

    def increment(self, family: RiskFamily) -> float:
        self.validate()
        return float(self.calibrated_increments[family.value])


def load_frozen_risk_calibration(path: Path) -> FrozenRiskCalibration:
    path = path.resolve()
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != SCHEMA_VERSION or payload.get("status") != "FROZEN":
        raise RiskCalibrationContractError("risk calibration artifact is not frozen")
    calibration = FrozenRiskCalibration(
        authority_id=str(payload.get("authority_id", "")),
        alpha=float(payload.get("alpha", float("nan"))),
        source_method=str(payload.get("source_method", "")),
        source_period=str(payload.get("source_period", "")),
        calibration_dates=tuple(str(value) for value in payload.get("calibration_dates", ())),
        finite_sample_rank=int(payload.get("finite_sample_rank", -1)),
        normalized_joint_quantile=float(
            payload.get("normalized_joint_quantile", float("nan"))
        ),
        predeclared_scales={
            str(key): float(value)
            for key, value in payload.get("predeclared_scales", {}).items()
        },
        calibrated_increments={
            str(key): float(value)
            for key, value in payload.get("calibrated_increments", {}).items()
        },
        source_audit_sha256=str(payload.get("source_audit_sha256", "")),
        artifact_sha256=file_sha256(path),
        february_labels_used_for_fit=bool(
            payload.get("february_labels_used_for_fit", True)
        ),
        march_outcomes_read=bool(payload.get("march_outcomes_read", True)),
    )
    calibration.validate()
    return calibration
