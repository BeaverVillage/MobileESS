"""V16.1 Day-Ahead scientific and implementation authority constants.

This module is intentionally declarative.  Scientific constants are copied from
the 2026-08-28 final pre-code freeze and are not inferred from historical result
bytes.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence


SCIENTIFIC_FRAMEWORK_ID = "V16_1_DA_AIDC_ICPS_BOUNDARYSEP"
TIME_CONTRACT = "DA15_96STEP_TIME_CONTRACT_V1"
AIDC_ML_AUTHORITY = "AIDC_RC_MQT_V2_REFDELTA"
TRAFFIC_SUPPORT_AUTHORITY = "DA_TRAFFIC_SUPPORT_V1"
OPTIMIZATION_AUTHORITY = "DAYAHEAD_OPTIMIZATION_AUTHORITY_V3"
OBJECTIVE_AUTHORITY = "MAX_NORMALIZED_LINE_CURRENT_OBJECTIVE_V1"
SOLVER_AUTHORITY = "CL_MC_BD_V1"
PLANNING_GRID_MODEL = "PHASE_AWARE_LINDISTFLOW_LP_V1"
RESULT_SCHEMA = "DAYAHEAD_AIDC_JOINT_RESULT_SCHEMA_V3_BOUNDARYSEP"
OPENDSS_VALIDATION = "DA96_FRESH_3PH_QSTS_V1"
AIDC_RESOURCE_COUPLING_BLOCK = "AIDC_RESOURCE_COUPLING_BLOCK_V1"
AIDC_LABEL_PROVENANCE = "AIDC_LABEL_ORIGIN_PROVENANCE_V2"
MAPPING_AUTHORITY = "FROZEN_FEEDER_PCC_MAPPING_REUSE_V1"
PHASE_MASK_CONTRACT = "PHASE_PRESENT_MASK_V1"
REALIZED_REPLAY = "FIXED_SCHEDULE_REALIZED_REPLAY_V2"
AIDC_QUANTILE_CALIBRATION = "NONE_V1"
AIDC_NLR_SOURCE_AUTHORITY = "NLR_ESIF_KESTREL_D312_HIERARCHY_V1"
AIDC_WORKLOAD_ELIGIBILITY = "NLR_KESTREL_H100_ELIGIBILITY_V1"
AIDC_POWER_RESPONSE = "NLR_D312_INCREMENTAL_POWER_V1"
AIDC_REFERENCE_DELTA = "AIDC_REFERENCE_DELTA_V16_1_SYSTEM_FIRST"
AIDC_SERVICE_CONTRACT = "REFERENCE_MATCHED_SERVICE_CONSERVATION_V1"
REFERENCE_COMPUTE_SCHEDULE = "REFERENCE_COMPUTE_SCHEDULE_V3"
AIDC_D1_ADMISSION = "D1_ADMISSION_ELIGIBILITY_V1"
AIDC_REFERENCE_FIDELITY = "REFERENCE_BASELINE_FIDELITY_DIAGNOSTIC_V1"
AIDC_REALIZED_DECOMPOSITION = "AIDC_REALIZED_REFERENCE_DECOMPOSITION_V1"

DEFAULT_RAW_ROOT = Path(
    r"C:\Users\kjw39\OneDrive\Desktop\4-2\Mobile ESS\raw데이터"
)

AIDC_SCIENTIFIC_STATUS = "READY_FOR_IMPLEMENTATION"
WAITING_AIDC_AUTHORITY = "WAITING_AIDC_AUTHORITY"
FROZEN_AIDC_MAPPING_AUTHORITY = "AIDC_PCC_MAPPING_CONTRACT_V1_12x4"

NLR_SOURCE_SHA256: Mapping[str, str] = {
    "esif_parquet": "19cd12405dde9144b1a360e8c8418666c399a3d0d15a7f846880d71ab22f9dd4",
    "esif_official_csv_zip": "59e6c0537956b77fb071c6f8211efc3fa4522ca10e5e3d95679aa937627262b1",
    "kestrel_jobs_zip": "3a90f9ac40991712f8718c686fa7b05d7a303a44a87ed1a8f21b403c11efd26f",
    "dataset312_zip": "dcad6de800fb565d850b163902e2eddae48aabd1ed1c7336f9a1cdaf3012f137",
}


@dataclass(frozen=True)
class DimensionAuthority:
    """Ordered AIDC/Rack axes supplied by an authority artifact.

    The algorithm consumes these axes; 12/48 is data in the current frozen
    authority, never a computational constant.
    """

    authority_id: str
    aidc_ids: tuple[str, ...]
    rack_ids_by_aidc: Mapping[str, tuple[str, ...]]
    scientific_eligible: bool
    scientific_status: str

    @property
    def rack_ids(self) -> tuple[str, ...]:
        return tuple(rack for aidc in self.aidc_ids for rack in self.rack_ids_by_aidc[aidc])

    def validate(self, *, production: bool = False) -> None:
        if not self.authority_id or not self.aidc_ids:
            raise ValueError("dimension authority must have an ID and at least one AIDC")
        if len(set(self.aidc_ids)) != len(self.aidc_ids):
            raise ValueError("duplicate AIDC IDs are prohibited")
        if set(self.rack_ids_by_aidc) != set(self.aidc_ids):
            raise ValueError("R_d keys must equal the ordered AIDC axis")
        racks = self.rack_ids
        if not racks or len(set(racks)) != len(racks):
            raise ValueError("Rack IDs must be non-empty and globally unique")
        if any(not self.rack_ids_by_aidc[aidc] for aidc in self.aidc_ids):
            raise ValueError("every AIDC must own at least one Rack")
        if production and not self.scientific_eligible:
            raise ValueError("NON_SCIENTIFIC_AUTHORITY_REJECTED_IN_PRODUCTION")
        if production and self.authority_id != FROZEN_AIDC_MAPPING_AUTHORITY:
            raise ValueError("UNFROZEN_AIDC_MAPPING_REJECTED_IN_PRODUCTION")

    def to_dict(self) -> dict[str, Any]:
        return {
            "authority_id": self.authority_id,
            "aidc_ids": list(self.aidc_ids),
            "rack_ids_by_aidc": {key: list(value) for key, value in self.rack_ids_by_aidc.items()},
            "scientific_eligible": self.scientific_eligible,
            "scientific_status": self.scientific_status,
        }

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any], *, production: bool = False) -> "DimensionAuthority":
        result = cls(
            authority_id=str(payload["authority_id"]),
            aidc_ids=tuple(map(str, payload["aidc_ids"])),
            rack_ids_by_aidc={
                str(key): tuple(map(str, value))
                for key, value in dict(payload["rack_ids_by_aidc"]).items()
            },
            scientific_eligible=bool(payload.get("scientific_eligible", False)),
            scientific_status=str(payload.get("scientific_status", "UNKNOWN")),
        )
        result.validate(production=production)
        return result


def _current_frozen_dimensions() -> DimensionAuthority:
    aidcs = tuple(f"AIDC{index:02d}" for index in range(1, 13))
    racks = {
        aidc: tuple(f"{aidc}_LP{rack:02d}" for rack in range(1, 5))
        for aidc in aidcs
    }
    return DimensionAuthority(
        authority_id=FROZEN_AIDC_MAPPING_AUTHORITY,
        aidc_ids=aidcs,
        rack_ids_by_aidc=racks,
        scientific_eligible=True,
        scientific_status=AIDC_SCIENTIFIC_STATUS,
    )


CURRENT_FROZEN_DIMENSIONS = _current_frozen_dimensions()


def load_dimension_authority(path: Path, *, production: bool = False) -> DimensionAuthority:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("dimension authority root must be an object")
    return DimensionAuthority.from_mapping(payload, production=production)


@dataclass(frozen=True)
class FrozenDigest:
    authority_id: str
    sha256: str
    role: str

    def validate(self) -> None:
        if len(self.sha256) != 64 or any(c not in "0123456789abcdef" for c in self.sha256):
            raise ValueError(f"invalid SHA-256 for {self.authority_id}")


FROZEN_DIGESTS = (
    FrozenDigest(
        "power_artifact_manifest_sha256",
        "7780cc3cd19a7f1dcf8e2d6a35d2872f7742bee200873b69a6c806df557624b5",
        "GRID_BACKGROUND_MAPPING_CONTRACT_V1",
    ),
    FrozenDigest(
        "power_bus_axis_sha256",
        "21e169247b5ea6fad3e1595d749926b27d5cc8257a1a82fac5685c961abb20ea",
        "GRID_BACKGROUND_MAPPING_CONTRACT_V1",
    ),
    FrozenDigest(
        "compiled_bus_phase_mask_sha256",
        "63cd1eecbcf8c7818e3dc87aa40bf79c6168cf6175a919df550d0564237c5a8a",
        "PV_FEEDER_MAPPING_CONTRACT_V1",
    ),
    FrozenDigest(
        "bus_axis_mapping_sha256",
        "16c0a298641cbff1cf9d333984aea56d544e11357a179e6e13379e581cef37a2",
        "PV_FEEDER_MAPPING_CONTRACT_V1",
    ),
    FrozenDigest(
        "service_node_electrical_mapping_v1_csv_sha256",
        "c3763567f6785f182ab151ca0390918017d4e24c2733f6d72d2304bba416322e",
        "AIDC_PCC_MAPPING_CONTRACT_V1/MESS_SERVICE_PCC_MAPPING_CONTRACT_V1",
    ),
    FrozenDigest(
        "Generated_ThreePhase_PCC_v3_dss_sha256",
        "3c3e27020e266dc8f1c4e28e90d49f298d6ca741ef6b54599e44265882cd747c",
        "MESS_SERVICE_PCC_MAPPING_CONTRACT_V1",
    ),
)


AUTHORITY_IDS: Mapping[str, str] = {
    "scientific_framework_id": SCIENTIFIC_FRAMEWORK_ID,
    "time_contract": TIME_CONTRACT,
    "aidc_ml_authority": AIDC_ML_AUTHORITY,
    "traffic_support_authority": TRAFFIC_SUPPORT_AUTHORITY,
    "optimization_authority": OPTIMIZATION_AUTHORITY,
    "objective_authority": OBJECTIVE_AUTHORITY,
    "solver_authority": SOLVER_AUTHORITY,
    "planning_grid_model": PLANNING_GRID_MODEL,
    "result_schema": RESULT_SCHEMA,
    "opendss_validation": OPENDSS_VALIDATION,
    "aidc_resource_coupling_block": AIDC_RESOURCE_COUPLING_BLOCK,
    "aidc_label_provenance": AIDC_LABEL_PROVENANCE,
    "mapping_authority": MAPPING_AUTHORITY,
    "phase_mask_contract": PHASE_MASK_CONTRACT,
    "realized_replay": REALIZED_REPLAY,
    "aidc_quantile_calibration": AIDC_QUANTILE_CALIBRATION,
    "aidc_nlr_source_authority": AIDC_NLR_SOURCE_AUTHORITY,
    "aidc_workload_eligibility": AIDC_WORKLOAD_ELIGIBILITY,
    "aidc_power_response": AIDC_POWER_RESPONSE,
    "aidc_reference_delta": AIDC_REFERENCE_DELTA,
    "aidc_service_contract": AIDC_SERVICE_CONTRACT,
    "reference_compute_schedule": REFERENCE_COMPUTE_SCHEDULE,
    "aidc_d1_admission": AIDC_D1_ADMISSION,
    "aidc_reference_fidelity": AIDC_REFERENCE_FIDELITY,
    "aidc_realized_decomposition": AIDC_REALIZED_DECOMPOSITION,
}


def sha256_file(path: Path, *, block_size: int = 8 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(block_size), b""):
            digest.update(block)
    return digest.hexdigest()


def authority_fingerprint() -> str:
    for item in FROZEN_DIGESTS:
        item.validate()
    payload = {
        "authority_ids": dict(AUTHORITY_IDS),
        "frozen_digests": [asdict(item) for item in FROZEN_DIGESTS],
        "nlr_source_sha256": dict(NLR_SOURCE_SHA256),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def validate_expected_digest(path: Path, expected: str) -> dict[str, object]:
    if not path.is_file():
        return {"path": str(path), "status": "FAIL_MAPPING_AUTHORITY_MISSING"}
    actual = sha256_file(path)
    return {
        "path": str(path),
        "expected_sha256": expected,
        "actual_sha256": actual,
        "status": "PASS" if actual == expected else "FAIL_MAPPING_AUTHORITY_MISMATCH",
    }
