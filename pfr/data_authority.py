"""Dataset-role and measured-parameter boundaries for PFR1.

This module intentionally contains no downloader and no row-wise cross-source
join helper.  Independent public traces remain independent authorities.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Mapping, Sequence


class DataAuthorityError(ValueError):
    pass


class DatasetRole(str, Enum):
    MAIN_OPERATIONAL = "MAIN_OPERATIONAL"
    MEASURED_POWER_UTILIZATION = "MEASURED_POWER_UTILIZATION"
    OPTIONAL_SEMANTIC = "OPTIONAL_SEMANTIC"
    OPTIONAL_SENSITIVITY = "OPTIONAL_SENSITIVITY"


class AuthorityKind(str, Enum):
    MEASURED = "MEASURED"
    SOURCE_DERIVED = "SOURCE_DERIVED"
    MODELED = "MODELED"
    UNRESOLVED = "UNRESOLVED"


@dataclass(frozen=True)
class DatasetAuthority:
    dataset_family: str
    role: DatasetRole
    source_identity: str
    sha256: str | None
    measured_fields: tuple[str, ...]
    modeled_or_unresolved_fields: tuple[str, ...] = ()
    optimizer_input_allowed: bool = False
    calibration_only: bool = False
    evaluation_only: bool = False

    def validate(self) -> None:
        if not self.dataset_family or not self.source_identity:
            raise DataAuthorityError("dataset family and source identity are required")
        overlap = set(self.measured_fields).intersection(self.modeled_or_unresolved_fields)
        if overlap:
            raise DataAuthorityError(f"fields cannot be both measured and modeled: {overlap}")
        if self.dataset_family == "KESTREL_F30":
            if self.role is not DatasetRole.MAIN_OPERATIONAL:
                raise DataAuthorityError("Kestrel F30 must remain MAIN_OPERATIONAL")
            architecture_claims = {
                field
                for field in self.measured_fields
                if field.lower() in {"model_family", "architecture", "neural_network"}
            }
            if architecture_claims:
                raise DataAuthorityError("Kestrel does not measure AI architecture identity")


def validate_dataset_contract(records: Iterable[DatasetAuthority]) -> None:
    records = tuple(records)
    for record in records:
        record.validate()
    kestrel = [record for record in records if record.dataset_family == "KESTREL_F30"]
    if len(kestrel) != 1:
        raise DataAuthorityError("exactly one Kestrel MAIN_OPERATIONAL authority is required")


def reject_row_wise_cross_dataset_merge(*dataset_families: str) -> None:
    """Fail closed on synthetic joint records from independent traces."""

    normalized = {family.strip().upper() for family in dataset_families if family.strip()}
    if len(normalized) > 1:
        raise DataAuthorityError(
            "row-wise cross-dataset merge is prohibited; use explicit adapters and roles"
        )


@dataclass(frozen=True)
class PowerUtilizationPoint:
    timestamp_offset_seconds: float
    node_power_w: float
    mean_gpu_utilization_percent: float

    def validate(self) -> None:
        if self.timestamp_offset_seconds < 0:
            raise DataAuthorityError("timestamp offset must be nonnegative")
        if self.node_power_w < 0:
            raise DataAuthorityError("measured node power must be nonnegative")
        if not 0 <= self.mean_gpu_utilization_percent <= 100:
            raise DataAuthorityError("GPU utilization must be within [0, 100]")


@dataclass(frozen=True)
class MeasuredPowerUtilizationEnvelope:
    """Measured envelope only; it is not a throughput curve."""

    gpu_type: str
    source_identity: str
    source_sha256: str
    points: tuple[PowerUtilizationPoint, ...]
    throughput_target_status: AuthorityKind = AuthorityKind.UNRESOLVED

    def validate(self) -> None:
        if self.gpu_type not in {"H100", "B200"}:
            raise DataAuthorityError("the current measured node authority is H100/B200 only")
        if len(self.source_sha256) != 64:
            raise DataAuthorityError("source SHA-256 is required")
        if not self.points:
            raise DataAuthorityError("at least one measured point is required")
        previous = -1.0
        for point in self.points:
            point.validate()
            if point.timestamp_offset_seconds < previous:
                raise DataAuthorityError("measured points must be time ordered")
            previous = point.timestamp_offset_seconds
        if self.throughput_target_status is not AuthorityKind.UNRESOLVED:
            raise DataAuthorityError(
                "this dataset binding has no measured throughput target; keep it unresolved"
            )

    @property
    def power_domain_w(self) -> tuple[float, float]:
        self.validate()
        powers = [point.node_power_w for point in self.points]
        return min(powers), max(powers)


@dataclass(frozen=True)
class FixedInferenceLoad:
    site_id: str
    power_kw: float
    source_identity: str
    flexible: bool = False

    def validate(self) -> None:
        if self.power_kw < 0:
            raise DataAuthorityError("inference background power must be nonnegative")
        if self.flexible:
            raise DataAuthorityError("online inference is fixed background in the first-paper model")

    def with_flexibility(self, flexible: bool) -> "FixedInferenceLoad":
        if flexible:
            raise DataAuthorityError("online inference flexibility is outside PFR0-PFR2")
        return self


def measured_field_flags(
    measured: Sequence[str], modeled_or_unresolved: Sequence[str]
) -> Mapping[str, AuthorityKind]:
    overlap = set(measured).intersection(modeled_or_unresolved)
    if overlap:
        raise DataAuthorityError(f"ambiguous measured/modeled fields: {overlap}")
    return {
        **{field: AuthorityKind.MEASURED for field in measured},
        **{field: AuthorityKind.UNRESOLVED for field in modeled_or_unresolved},
    }
