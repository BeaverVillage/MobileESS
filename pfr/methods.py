"""PFR8 B0-B7 controlled method factory and K9H7_RESULT_V2 identity."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
import hashlib
import json
from typing import Mapping, Optional, Tuple


class MethodContractError(ValueError):
    """Raised when a comparison changes anything beyond its treatment."""


def _hash(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class ComparisonMethod(str, Enum):
    B0 = "B0"
    B1 = "B1"
    B2 = "B2"
    B3 = "B3"
    B4 = "B4"
    B5 = "B5"
    B6 = "B6"
    B7 = "B7"


@dataclass(frozen=True)
class ExperimentAuthority:
    exogenous_inputs_sha256: str
    initial_state_sha256: str
    grid_model_sha256: str
    jobs_sha256: str
    wan_sha256: str
    evaluation_coefficients_sha256: str
    physical_ratings_sha256: str
    fresh_opendss_required: bool = True

    def validate(self) -> None:
        values = (
            self.exogenous_inputs_sha256,
            self.initial_state_sha256,
            self.grid_model_sha256,
            self.jobs_sha256,
            self.wan_sha256,
            self.evaluation_coefficients_sha256,
            self.physical_ratings_sha256,
        )
        if any(len(value) != 64 or any(char not in "0123456789abcdef" for char in value) for value in values):
            raise MethodContractError("shared authority fields must be lowercase SHA-256")
        if not self.fresh_opendss_required:
            raise MethodContractError("Fresh OpenDSS hard safety must be common to B0-B7")

    @property
    def fingerprint(self) -> str:
        self.validate()
        return _hash(asdict(self))


@dataclass(frozen=True)
class MethodConfig:
    comparison_method_id: ComparisonMethod
    label: str
    energy_flexibility: str
    temporal_workload_shift: bool
    spatial_workload_migration: bool
    control_mode: str
    risk_interface: str
    ai_training_aware: bool
    joint_uncertainty: bool
    slow_fast_control: bool
    ac_safety_filter: bool
    authority_fingerprint: str

    def validate(self) -> None:
        if self.energy_flexibility not in {"NONE", "MESS", "STATIONARY_BESS"}:
            raise MethodContractError("unknown energy flexibility")
        if self.control_mode not in {"FIXED", "PERIODIC_MPC", "EVENT_TRIGGERED"}:
            raise MethodContractError("unknown controller mode")
        if self.risk_interface not in {"NONE", "RAW_UNCALIBRATED", "CALIBRATED"}:
            raise MethodContractError("unknown risk interface")
        if len(self.authority_fingerprint) != 64:
            raise MethodContractError("method lacks the shared experiment authority")
        if not self.ac_safety_filter:
            raise MethodContractError("all methods require the same Fresh AC hard safety")


_TREATMENTS: Mapping[ComparisonMethod, Tuple[object, ...]] = {
    ComparisonMethod.B0: ("No flexibility", "NONE", False, False, "FIXED", "NONE", False, False, False),
    ComparisonMethod.B1: ("MESS only", "MESS", False, False, "PERIODIC_MPC", "NONE", False, False, True),
    ComparisonMethod.B2: ("Temporal AI workload shifting only", "NONE", True, False, "PERIODIC_MPC", "NONE", True, False, True),
    ComparisonMethod.B3: ("Spatial AI workload migration only", "NONE", False, True, "PERIODIC_MPC", "NONE", True, False, True),
    ComparisonMethod.B4: ("Stationary BESS plus AI workload", "STATIONARY_BESS", True, True, "PERIODIC_MPC", "NONE", True, False, True),
    ComparisonMethod.B5: ("Joint MESS plus workload periodic MPC", "MESS", True, True, "PERIODIC_MPC", "NONE", True, True, True),
    ComparisonMethod.B6: ("Joint event-triggered raw risk", "MESS", True, True, "EVENT_TRIGGERED", "RAW_UNCALIBRATED", True, True, True),
    ComparisonMethod.B7: ("Full proposed calibrated ICPS", "MESS", True, True, "EVENT_TRIGGERED", "CALIBRATED", True, True, True),
}


class MethodFactory:
    def __init__(self, authority: ExperimentAuthority) -> None:
        authority.validate()
        self.authority = authority

    def create(self, method: ComparisonMethod) -> MethodConfig:
        treatment = _TREATMENTS[method]
        config = MethodConfig(
            comparison_method_id=method,
            label=str(treatment[0]),
            energy_flexibility=str(treatment[1]),
            temporal_workload_shift=bool(treatment[2]),
            spatial_workload_migration=bool(treatment[3]),
            control_mode=str(treatment[4]),
            risk_interface=str(treatment[5]),
            ai_training_aware=bool(treatment[6]),
            joint_uncertainty=bool(treatment[7]),
            slow_fast_control=bool(treatment[8]),
            ac_safety_filter=True,
            authority_fingerprint=self.authority.fingerprint,
        )
        config.validate()
        return config

    def all(self) -> Tuple[MethodConfig, ...]:
        result = tuple(self.create(method) for method in ComparisonMethod)
        if len({item.comparison_method_id for item in result}) != 8:
            raise MethodContractError("B0-B7 registry is incomplete")
        if len({item.authority_fingerprint for item in result}) != 1:
            raise MethodContractError("comparison methods do not share one authority")
        return result


@dataclass(frozen=True)
class K9H7ResultIdentityV2:
    scientific_framework_id: str
    comparison_method_id: str
    controller_id: str
    ablation_id: Optional[str]
    representative_week_id: str
    shared_authority_fingerprint: str
    schema_version: str = "K9H7_RESULT_V2"

    def validate(self) -> None:
        if self.schema_version != "K9H7_RESULT_V2":
            raise MethodContractError("K9H7_RESULT_V1 is historical compatibility only")
        if self.scientific_framework_id != "V13_AI_ICPS":
            raise MethodContractError("unknown current scientific framework")
        if self.comparison_method_id not in {method.value for method in ComparisonMethod}:
            raise MethodContractError("comparison method must be B0-B7")
        if not self.controller_id or not self.representative_week_id:
            raise MethodContractError("controller and representative week identities are required")
        if len(self.shared_authority_fingerprint) != 64:
            raise MethodContractError("result is not bound to shared authority")

    @property
    def result_uid(self) -> str:
        self.validate()
        return _hash(asdict(self))

    @classmethod
    def for_method(
        cls,
        config: MethodConfig,
        *,
        controller_id: str,
        representative_week_id: str,
        ablation_id: Optional[str] = None,
    ) -> "K9H7ResultIdentityV2":
        identity = cls(
            scientific_framework_id="V13_AI_ICPS",
            comparison_method_id=config.comparison_method_id.value,
            controller_id=controller_id,
            ablation_id=ablation_id,
            representative_week_id=representative_week_id,
            shared_authority_fingerprint=config.authority_fingerprint,
        )
        identity.validate()
        return identity
