"""Runtime-axis result schema and reproducible artifact writer."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from .authority import DEFAULT_RAW_ROOT, DimensionAuthority


REQUIRED_DATASETS = {
    "PLANNING_LINE_LOADING_SURROGATE_PU", "PLANNING_VOLTAGE_PU", "BRANCH_P_KW", "BRANCH_Q_KVAR",
    "OPENDSS_LINE_CURRENT_A", "OPENDSS_LINE_LOADING_PU", "OPENDSS_VOLTAGE_PU",
    "MESS_P_KW", "MESS_Q_KVAR", "MESS_ENERGY_KWH", "MESS_LOCATION",
    "LINE_PHASE_PRESENT", "BUS_PHASE_PRESENT", "BENDERS_ITERATION", "GRID_SUBPROBLEM",
    "BENDERS_CUT", "SOLVER_COMPARISON",
    "AIDC_RACK_POWER_KW", "AIDC_RACK_GPU", "AIDC_WORKLOAD_ALLOC",
    "AIDC_RACK_REFDELTA_RESIDUAL_POWER_KW", "AIDC_RACK_REFDELTA_RESIDUAL_GPU",
    "AIDC_FLEX_REF_POWER_KW", "AIDC_FLEX_DA_POWER_KW", "AIDC_FLEX_REF_GPU", "AIDC_FLEX_DA_GPU",
    "AIDC_FLEX_ACT_NATURAL_POWER_KW", "AIDC_FLEX_ACT_NATURAL_GPU",
    "AIDC_RACK_REALIZED_RESIDUAL_POWER_KW", "AIDC_RACK_REALIZED_RESIDUAL_GPU",
    "AIDC_BASE_IT_POWER_KW", "AIDC_TOTAL_IT_POWER_KW", "AIDC_RACK_FLEX_POWER_KW",
    "AIDC_RACK_FLEX_GPU",
}
PAPER_FACING_DATASETS_V16_1 = {
    "AIDC_BASE_IT_POWER_KW", "AIDC_TOTAL_IT_POWER_KW", "AIDC_RACK_FLEX_POWER_KW",
    "AIDC_RACK_GPU", "AIDC_RACK_FLEX_GPU",
}
COMPATIBILITY_ONLY_DATASETS_V16_1 = {"AIDC_RACK_POWER_KW"}
ALLOWED_NAMESPACES = {"FORECAST_PLANNING", "REALIZED_REPLAY"}


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


@dataclass(frozen=True)
class ResultManifest:
    authority_id: str
    source_ids: tuple[str, ...]
    source_sha256: tuple[str, ...]
    timestamp_contract: str
    dimension_authority: Mapping[str, Any]
    namespace: str
    scientific_eligible: bool

    def validate(self, *, production: bool = False) -> None:
        if self.namespace not in ALLOWED_NAMESPACES:
            raise ValueError("forecast planning and realized replay require separate fixed namespaces")
        if not self.source_ids or not self.source_sha256 or any(len(value) != 64 for value in self.source_sha256):
            raise ValueError("source IDs and SHA-256 identities are required")
        DimensionAuthority.from_mapping(self.dimension_authority, production=production)
        if production and not self.scientific_eligible:
            raise ValueError("NON_SCIENTIFIC_RESULT_REJECTED_IN_PRODUCTION")


def write_artifact(path: Path, payload: Mapping[str, Any], manifest: ResultManifest, *, production: bool = False) -> str:
    manifest.validate(production=production)
    if _is_within(path, DEFAULT_RAW_ROOT):
        raise PermissionError("raw authority root is read-only")
    path.parent.mkdir(parents=True, exist_ok=True)
    envelope = {
        "manifest": {**manifest.__dict__, "created_at_utc": datetime.now(timezone.utc).isoformat()},
        "payload": payload,
    }
    encoded = (json.dumps(envelope, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_bytes(encoded)
    temporary.replace(path)
    return hashlib.sha256(encoded).hexdigest()


def validate_dataset_names(names: Sequence[str]) -> None:
    unknown = set(names) - REQUIRED_DATASETS
    if unknown:
        raise ValueError(f"unknown Day-Ahead result datasets: {sorted(unknown)}")


def independent_recalculate(stored: Mapping[str, Sequence[float]]) -> dict[str, object]:
    """Recalculate stored-array extrema without solver or OpenDSS calls."""
    required={"planning_line_loading","opendss_line_loading","opendss_voltage"}
    if not required.issubset(stored): raise ValueError(f"INDEPENDENT_RECALCULATOR_MISSING:{sorted(required-set(stored))}")
    if any(not values for values in (stored[name] for name in required)): raise ValueError("INDEPENDENT_RECALCULATOR_EMPTY_MATRIX")
    return {"planning_rho_max":max(map(float,stored["planning_line_loading"])), "opendss_rho_max":max(map(float,stored["opendss_line_loading"])), "opendss_vmin":min(map(float,stored["opendss_voltage"])), "opendss_vmax":max(map(float,stored["opendss_voltage"])), "solver_call_count":0, "opendss_call_count":0}
