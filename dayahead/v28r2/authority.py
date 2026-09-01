"""Latest-authority precedence and strict full-node workload eligibility."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


CONTROLLABLE_NODE_CLASSES = (1, 2, 4, 8, 16)
COHORT_IDS = tuple(f"N{nodes:02d}_R{runtime:02d}" for nodes in CONTROLLABLE_NODE_CLASSES for runtime in range(3))
D1_ALLOWED_FIELDS = frozenset(
    {
        "cohort_id",
        "forecast_issue_cutoff",
        "forecast_q50_nodeh",
        "forecast_vintage_id",
        "node_class",
        "runtime_class",
        "target_slot",
    }
)
EXPOST_FIELDS = frozenset(
    {
        "completed",
        "end_time",
        "gpu_nodes_occupied",
        "job_id",
        "jobs_shared",
        "nodes_shared",
        "queued_job_id",
        "realized_end_time",
        "realized_runtime",
        "runtime_hours",
        "shared_job_count",
        "start_time",
        "state_simple",
    }
)
AUTHORITY_PRECEDENCE = (
    "2026-08-29_FINAL_SCIENTIFIC_REFREEZE",
    "V28_FINAL_LIGHTGBM_DECISION",
    "V22SR1_FINAL_OPERATING_SCALE",
    "V24T_C1_THERMAL_AUTHORITY",
    "V16_3_SOLVER_AND_GRID_AUTHORITY",
    "V21_AND_EARLIER_HISTORICAL_EVIDENCE_ONLY",
)


def _empty(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, (list, tuple, set, dict)):
        return len(value) == 0
    try:
        import pandas as pd

        if bool(pd.isna(value)):
            return True
    except (ImportError, TypeError, ValueError):
        pass
    return str(value).strip().casefold() in {"", "none", "null", "nan", "[]", "{}"}


def _h100(value: object) -> bool:
    return any(token.strip().casefold().startswith("gpu-h100") for token in str(value).split(","))


@dataclass(frozen=True)
class WorkloadEligibilityBinding:
    controllable_node_classes: tuple[int, ...] = CONTROLLABLE_NODE_CLASSES
    cohort_ids: tuple[str, ...] = COHORT_IDS
    partial_controllable: bool = False
    partial_reference_embedded: bool = True
    sharing_controllable: bool = False
    individual_queue_injection: bool = False
    initial_backlog_nodeh: float = 0.0

    def validate(self) -> None:
        if self.controllable_node_classes != CONTROLLABLE_NODE_CLASSES or self.cohort_ids != COHORT_IDS:
            raise ValueError("V28R2_FROZEN_COHORT_AXIS_MISMATCH")
        if self.partial_controllable or not self.partial_reference_embedded or self.sharing_controllable:
            raise ValueError("V28R2_PARTIAL_OR_SHARED_ACTUATOR_PROHIBITED")
        if self.individual_queue_injection or self.initial_backlog_nodeh != 0.0:
            raise ValueError("V28R2_D1_FORECAST_COHORT_ONLY_REQUIRED")

    def historical_label_eligible(self, row: Mapping[str, Any]) -> bool:
        """Use ex-post fields only when constructing a historical label."""

        try:
            nodes = int(float(row["gpu_nodes_occupied"]))
            gpus = float(row["gpus_requested"])
            start = row["start_time"]
            end = row["end_time"]
            valid_interval = start is not None and end is not None and end > start
            share = row.get("shared_job_count")
            no_share_count = _empty(share) or float(share) == 0.0
        except (KeyError, TypeError, ValueError):
            return False
        return bool(
            _h100(row.get("partition"))
            and str(row.get("state_simple", "")).upper() == "COMPLETED"
            and valid_interval
            and nodes in CONTROLLABLE_NODE_CLASSES
            and abs(gpus - 4.0 * nodes) <= 1e-9
            and no_share_count
            and _empty(row.get("nodes_shared"))
            and _empty(row.get("jobs_shared"))
        )

    def validate_d1_record(self, record: Mapping[str, Any]) -> None:
        fields = frozenset(record)
        if not fields.issubset(D1_ALLOWED_FIELDS) or fields & EXPOST_FIELDS:
            raise ValueError(f"V28R2_D1_EXPOST_FIELD_PROHIBITED:{sorted(fields-D1_ALLOWED_FIELDS)}")
        if str(record.get("cohort_id")) not in COHORT_IDS:
            raise ValueError("V28R2_D1_UNKNOWN_COHORT")
        slot = int(record.get("target_slot", -1))
        mass = float(record.get("forecast_q50_nodeh", -1.0))
        if not 0 <= slot < 96 or mass < 0:
            raise ValueError("V28R2_D1_SLOT_OR_MASS_INVALID")


def repository_authority_paths(repo: Path) -> dict[str, Path]:
    return {
        "final_refreeze": repo / "dayahead/artifacts/v16/DAYAHEAD_IMPLEMENTATION_AUTHORITY.json",
        "eligibility": repo / "dayahead/artifacts/v16/AIDC_WORKLOAD_ELIGIBILITY_CONTRACT.json",
        "cohorts": repo / "dayahead/artifacts/v16/AIDC_COHORT_CONTRACT.json",
        "admission": repo / "dayahead/artifacts/v16/AIDC_D1_ADMISSION_CONTRACT.json",
        "V28_LightGBM": repo / "dayahead/artifacts/v28_final_dayahead_actual/V28_FINAL_LIGHTGBM_AUTHORITY.json",
        "V22SR1": repo / "dayahead/artifacts/v22s_r1_final_operating_scale/V22SR1_FINAL_IEEE123_AIDC_SCALE.json",
        "V24T": repo / "dayahead/artifacts/v24t_thermal_aware_aidc/V24T_C1_QUASISTATIC_MODEL.json",
    }
