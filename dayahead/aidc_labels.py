"""V16 source-backed AIDC P_IT_REF/G_REF/W_F lineage and split contracts."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from enum import Enum
from typing import Iterable, Mapping, Sequence


class LabelOrigin(str, Enum):
    OBSERVED_RAW = "OBSERVED_RAW"
    SOURCE_DERIVED = "SOURCE_DERIVED"
    MODEL_DERIVED = "MODEL_DERIVED"
    SYNTHETIC = "SYNTHETIC"


ALLOWED_MAIN_ORIGINS = {LabelOrigin.OBSERVED_RAW, LabelOrigin.SOURCE_DERIVED}


@dataclass(frozen=True)
class TargetLineage:
    target: str
    label_origin: LabelOrigin
    depends_on: tuple[str, ...]
    derivation_rule: str
    source_file_sha256: tuple[str, ...]
    source_system_id: str
    timestamp_axis_id: str
    first_timestamp: str | None
    last_timestamp: str | None
    required_coverage_end: str = "2025-06-25T23:45:00+10:00"

    def audit(self) -> dict[str, object]:
        failures: list[str] = []
        if self.label_origin not in ALLOWED_MAIN_ORIGINS:
            failures.append("MODEL_DERIVED_OR_SYNTHETIC_MAIN_TARGET")
        if not self.source_file_sha256 or any(len(value) != 64 for value in self.source_file_sha256):
            failures.append("SOURCE_SHA256_MISSING")
        if not self.source_system_id or not self.timestamp_axis_id:
            failures.append("SOURCE_SYSTEM_OR_TIME_AXIS_MISSING")
        elif "UNRESOLVED" in self.timestamp_axis_id:
            failures.append("SOURCE_TIMESTAMP_AXIS_UNRESOLVED")
        coverage_complete = False
        if self.last_timestamp is not None:
            try:
                coverage_complete = (
                    datetime.fromisoformat(self.last_timestamp).date()
                    >= datetime.fromisoformat(self.required_coverage_end).date()
                )
            except ValueError:
                coverage_complete = False
        if not coverage_complete:
            failures.append("REQUIRED_JUN25_COVERAGE_MISSING")
        return {**asdict(self), "status": "PASS" if not failures else "FAIL", "failures": failures}


def dependency_firewall(lineages: Sequence[TargetLineage]) -> dict[str, object]:
    by_target = {item.target: item for item in lineages}
    failures: list[str] = []
    failure_id = {
        "P_IT_REF": "FAIL_AIDC_P_REF_LABEL",
        "G_REF": "FAIL_AIDC_G_REF_LABEL",
        "W_F": "FAIL_AIDC_W_LABEL",
    }
    for required in ("P_IT_REF", "G_REF", "W_F"):
        if required not in by_target:
            failures.append(failure_id[required])
            continue
        audit = by_target[required].audit()
        if audit["status"] != "PASS":
            failures.append(failure_id[required])
    p = by_target.get("P_IT_REF")
    g = by_target.get("G_REF")
    if p and g and ("G_REF" in p.depends_on or "P_IT_REF" in g.depends_on):
        failures.append("FAIL_RESOURCE_COUPLING_TARGET_INDEPENDENCE")
    allowed_sources = {
        "P_IT_REF": "NLR_ESIF_FACILITY_POWER",
        "G_REF": "NLR_KESTREL_SCHEDULER",
        "W_F": "NLR_KESTREL_SCHEDULER",
    }
    for target, expected in allowed_sources.items():
        if target in by_target and by_target[target].source_system_id != expected:
            failures.append("FAIL_AIDC_SOURCE_HIERARCHY")
    if len({item.timestamp_axis_id for item in lineages}) != 1:
        failures.append("FAIL_AIDC_JOINT_LABEL_ALIGNMENT")
    failures = sorted(set(failures))
    return {
        "authority_id": "AIDC_LABEL_ORIGIN_PROVENANCE_V2",
        "targets": {item.target: item.audit() for item in lineages},
        "resource_coupling_claim_eligible": not failures,
        "status": "PASS" if not failures else "FAIL",
        "failures": failures,
        "on_failure": "STOP_C4_AND_REQUIRE_PROSPECTIVE_SCIENTIFIC_REFREEZE",
    }


SPLIT_CONTRACT: Mapping[str, object] = {
    "phase_a_training_start": "2024-08-19",
    "phase_a_train_end": "2025-03-31",
    "phase_a_validation_start": "2025-04-01",
    "phase_a_validation_end": "2025-04-30",
    "production_refit_start": "2024-08-19",
    "production_refit_end": "2025-04-30",
    "production_refit_count": 1,
    "primary_locked_test_start": "2025-05-01",
    "primary_locked_test_end": "2025-05-31",
    "independent_replication_start": "2025-06-01",
    "independent_replication_end": "2025-06-25",
    "production_seed": 20260828,
    "robustness_seeds": [20260829, 20260830],
    "posthoc_quantile_calibration": "NONE_V1",
    "best_seed_selection_prohibited": True,
}

HISTORICAL_ELIGIBILITY_EXPOST_FIELDS = frozenset({
    "state_simple", "gpu_nodes_occupied", "shared_job_count", "nodes_shared",
    "jobs_shared", "start_time", "end_time", "runtime_hours",
})


def h100_partition(value: object) -> bool:
    return any(token.strip().casefold().startswith("gpu-h100") for token in str(value).split(","))


def historical_label_eligible(row: Mapping[str, object]) -> bool:
    """HISTORICAL_LABEL_ELIGIBILITY_V1; never call from D-1 admission."""
    try:
        nodes = int(row["gpu_nodes_occupied"])
        gpus = int(row["gpus_requested"])
        runtime = float(row["runtime_hours"])
    except (KeyError, TypeError, ValueError):
        return False
    sharing_count = row.get("shared_job_count")
    no_count = sharing_count is None or str(sharing_count).strip() in {"", "0", "0.0", "nan", "None"}
    nodes_shared = row.get("nodes_shared")
    jobs_shared = row.get("jobs_shared")
    empty = lambda value: value is None or str(value).strip().casefold() in {"", "[]", "{}", "nan", "none"}
    return (
        h100_partition(row.get("partition"))
        and str(row.get("state_simple", "")).upper() == "COMPLETED"
        and runtime > 0
        and nodes in {1, 2, 4, 8, 16}
        and gpus == 4 * nodes
        and no_count and empty(nodes_shared) and empty(jobs_shared)
    )
