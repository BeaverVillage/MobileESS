"""Frozen contracts for the V35R3G Dataset 302 forensic."""

from __future__ import annotations

import os
from pathlib import Path


PARENT_HEAD = "8b3808a92930709a4df01365653b96b7bdb3a0df"
BRANCH = "codex/v35r3g-kestrel-h100-operational-energy-forensic"
DATASET_ID = 302
DATASET_DOI = "10.7799/3023270"
ARCHIVE_SHA256 = "3a90f9ac40991712f8718c686fa7b05d7a303a44a87ed1a8f21b403c11efd26f"
ARCHIVE_BYTES = 731_139_558

DEFAULT_DATA_ROOT = Path(
    r"C:\Users\kjw39\OneDrive\Desktop\4-2\Mobile ESS\raw데이터\데이터 센터"
)
DATA_ROOT = Path(os.environ.get("DATASET302_DATA_ROOT", DEFAULT_DATA_ROOT))
AUTHORITY_ROOT = DATA_ROOT / "NLR_scheduler_authority"
ARCHIVE = DATA_ROOT / "NLR HPC Kestrel Jobs Data" / "esif.hpc.kestrel.job-anon.zip"
DATACARD = AUTHORITY_ROOT / "01_Kestrel_job_trace" / "datacard.md"
SLURM_SACCT_SNAPSHOT = AUTHORITY_ROOT / "06_official_web_docs" / "Slurm_sacct.html"
H100_LOCAL_DOC = AUTHORITY_ROOT / "04_NLR_HPC_docs_repo" / "h100buildrun" / "about.md"
HPCODA_DESCRIPTOR = (
    AUTHORITY_ROOT
    / "07_hpc-oda-commons"
    / "src"
    / "hpc_oda_commons"
    / "datasets"
    / "descriptors"
    / "job-runtime"
    / "nlr_kestrel.yml"
)

ARTIFACT_DIRNAME = "v35r3g_kestrel_h100_operational_energy_forensic"
CACHE_DIRNAME = ARTIFACT_DIRNAME
LOG_DIRNAME = ARTIFACT_DIRNAME

ISSUE_TIME_LOCAL = "2025-03-31T18:00:00+10:00"
ISSUE_TIME_UTC = "2025-03-31T08:00:00+00:00"
GPUS_PER_H100_NODE = 4
H100_PARTITION_PREFIX = "gpu-h100"

# The archive never exposes the installed AcctGatherEnergyType or sensor
# selection.  A generic Slurm field definition cannot resolve a site-specific
# sensor boundary, so the science must fail closed.
PHYSICAL_BOUNDARY = (
    "SLURM_NODE_LEVEL_MONITORING_SENSOR_BOUNDARY_EXACT_PLUGIN_AND_COMPONENTS_UNKNOWN"
)
HIGHEST_AUTHORITY = "E0_ENERGY_FIELD_PRESENT_ONLY"
PRIMARY_CLASSIFICATION = "V35R3G_PREISSUE_H100_POSITIVE_ENERGY_EMPTY"
MODELABILITY = "NOT_MODELABLE_NO_POSITIVE_ENERGY"
CAUSAL_H100_POWER_MODEL_NEXT = "NO"
SHARED_H100_POWER_NEXT = "DEFER"

CONDITIONAL_ARTIFACTS = (
    "V35R3G_ENERGY_DERIVED_POWER.parquet",
    "V35R3G_ENERGY_DERIVED_POWER_SUMMARY.json",
    "V35R3G_FULL_NODE_EXCLUSIVE_H100_LABELS.parquet",
)

REQUIRED_ARTIFACTS = (
    "V35R3G_START_STATE.json",
    "V35R3G_ISOLATION_AUDIT.json",
    "V35R3G_SOURCE_AUTHORITY.json",
    "V35R3G_ROW_GRANULARITY_AUDIT.json",
    "V35R3G_DUPLICATE_IDENTIFIER_AUDIT.csv",
    "V35R3G_ENERGY_FIELD_CENSUS.json",
    "V35R3G_ENERGY_UNIT_RECONCILIATION.json",
    "V35R3G_CONSUMED_ENERGY_PHYSICAL_BOUNDARY.json",
    "V35R3G_SLURM_ENERGY_ATTRIBUTION_CONTRACT.json",
    "V35R3G_H100_IDENTIFICATION_CONTRACT.json",
    "V35R3G_SHARING_SEMANTICS.json",
    "V35R3G_FULL_NODE_H100_CONTRACT.json",
    "V35R3G_ENERGY_VALIDITY_CONTRACT.json",
    "V35R3G_FUTURE_POWER_MODEL_CAUSAL_FIREWALL.json",
    "V35R3G_GLOBAL_ENERGY_CENSUS.json",
    "V35R3G_GLOBAL_ENERGY_CENSUS.csv",
    "V35R3G_PREISSUE_CAUSAL_ENERGY_CENSUS.json",
    "V35R3G_PREISSUE_CAUSAL_ENERGY_CENSUS.csv",
    "V35R3G_RECENCY_COVERAGE.csv",
    "V35R3G_LABEL_RECENCY_AUDIT.json",
    "V35R3G_POWER_PLAUSIBILITY_AUDIT.csv",
    "V35R3G_FULL_NODE_EXCLUSIVE_H100_AUTHORITY.json",
    "V35R3G_PARTIAL_EXCLUSIVE_H100_AUDIT.json",
    "V35R3G_SHARED_H100_ENERGY_AUDIT.json",
    "V35R3G_SHARED_ENERGY_CONSERVATION.json",
    "V35R3G_SPATIAL_TEMPORAL_COVERAGE_MATRIX.csv",
    "V35R3G_POWER_MODELABILITY_AUDIT.json",
    "V35R3G_FUTURE_POWER_QUERY_FEATURES.json",
    "V35R3G_APR01_FEATURE_DOMAIN_COVERAGE.json",
    "V35R3G_AUTHORITY_DECISION.json",
    "V35R3G_NEXT_STEP_DECISION.json",
    "V35R3G_COMPUTE_ACCOUNTING.json",
    "V35R3G_REPAIR_LOG.json",
    "V35R3G_TEST_REPORT.json",
    "V35R3G_FINAL_REVIEW.json",
    "V35R3G_FINAL_REVIEW.md",
)

SOURCE_COLUMNS = (
    "id",
    "job_id",
    "array_pos",
    "user_hash",
    "account_hash",
    "partition",
    "state",
    "state_simple",
    "submit_time",
    "start_time",
    "end_time",
    "nodes_req",
    "nodes_used",
    "processors_req",
    "processors_used",
    "wallclock_req",
    "wallclock_used",
    "nodelist",
    "cpu_energy_tdp_estimated_max_watt_hours",
    "cpu_energy_tdp_estimated_used_watt_hours",
    "consumed_energy_joules",
    "consumed_energy_raw_joules",
    "consumed_energy_raw_watt_hours",
    "qos",
    "gpus_requested",
    "gpu_nodes_occupied",
    "shared_job_count",
    "nodes_shared",
    "jobs_shared",
)
