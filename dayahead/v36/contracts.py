"""Closed V36 scope and immutable source authorities."""

from __future__ import annotations

from datetime import timedelta, timezone
from pathlib import Path


AIDC_HEAD = "aa1a113abdd6eb1bc76cf3bfdcb6dcdb29660b2e"
MESS_HEAD = "a5c46a5c8b06e97e9e13a2078cb801fe51b240a9"
INTEGRATION_BASE_HEAD = MESS_HEAD
BRANCH = "codex/v36-apr01-integrated-calibration-freeze"

OFFICIAL_CASES = ("B0", "B1", "B2", "B3")
CALIBRATION_DATES = (
    "2025-04-01", "2025-04-04", "2025-04-07", "2025-04-10",
    "2025-04-13", "2025-04-16", "2025-04-19",
)
PASSES = ("PRE_CALIBRATION", "POST_CALIBRATION")
AEST = timezone(timedelta(hours=10), name="AEST_FIXED_UTC_PLUS_10")
SLOTS = 96
GPU_CAPACITY = 624.0
GPUS_PER_NODE = 4
CENTER_SWING_W_PER_GPU = 547.7239090195797
RW_IT_REFERENCE_KW = 406.77599381381907
EXPANDED_TEMPORAL_JOBS = 339
EXPANDED_TEMPORAL_GPU_HOURS = 14_832
PARTIAL_SHARED_TEMPORAL_JOBS = 336
PARTIAL_SHARED_TEMPORAL_GPU_HOURS = 14_256
PF = 0.95
PF_TAN = 0.3286841051788632
Q_SELECTED_SECONDS = 5576.44921875

DEFAULT_K = 200
K_FALLBACK = (200, 400, 800, "FULL")
BEAM_WIDTH = 2
BEAM_WIDTH_FALLBACK = 4
SEED_WIDTH = 2
STATIC_CANDIDATE_LIBRARY_SHA256 = (
    "6b9006f1d062f2207d4fc77f716cbe24a96735453ac1e460f8433c87f792a443"
)

SOURCE_REPOSITORY = Path(
    r"C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS\github_MobileESS"
)
SOURCE_DATA_REPOSITORY = Path(
    r"C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\MobileESS_v28r2_heavy_backend"
)
LEGACY_V35_WORKTREE = Path(
    r"C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\MobileESS_v33x_fasttrack_grid_deliverable_aidc"
)
FROZEN_MESS_WORKTREE = Path(
    r"C:\codex_mobileess_workspace\MobileESS_v35r3e_r1_beam"
)
KESTREL_ARCHIVE = Path(
    r"C:\Users\kjw39\OneDrive\Desktop\4-2\Mobile ESS\raw데이터\데이터 센터"
    r"\NLR HPC Kestrel Jobs Data\esif.hpc.kestrel.job-anon.zip"
)
ESIF_PUE_PARQUET = Path(
    r"C:\Users\kjw39\OneDrive\Desktop\4-2\Mobile ESS\raw데이터\데이터 센터"
    r"\NLR ESIF PUE  IT Power\esif.influx.buildingData.PUE.combined.parquet"
)
RUNTIME_VENV_PYTHON = Path(
    r"C:\Users\kjw39\AppData\Local\MobileESS\venvs\v35r3d-runtime\Scripts\python.exe"
)
APR01_RUNTIME_CACHE = Path(
    r"C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2"
    r"\MobileESS_v35r3d_kestrel_runtime_authority_closure\dayahead\cache"
    r"\v35r3d_kestrel_runtime_authority_closure"
)

ARTIFACT_DIR = Path("dayahead/artifacts/v36_apr01_integrated_calibration_freeze")
RAW_ROOT = Path("frozen_artifacts/v36_final_schema")
CACHE_ROOT = Path("dayahead/cache/v36_apr01_integrated_calibration_freeze")
LOG_ROOT = Path("logs/v36_apr01_integrated_calibration_freeze")
PHASE = "APR01_19_V36_CALIBRATION"

# Content SHA-256 and Git blob IDs are both frozen.  Content hashes are over
# exact `git show` bytes and therefore fail closed on line-ending drift.
SCIENCE_AUTHORITIES = {
    "AIDC": {
        "commit": AIDC_HEAD,
        "path": "dayahead/artifacts/v35r3j_aidc_it_scale_consistency_freeze/V35R3J_EXPANDED_AIDC_POWER_CONTRACT.json",
        "sha256": "81b1c89bd86820d75219d79c81b47c568aece49e1a03d3f843517d3e48f7b846",
        "git_blob": "4ef2daca0b02ebeadaa7ac61ebf6404905ed2da1",
    },
    "MESS": {
        "commit": MESS_HEAD,
        "path": "dayahead/artifacts/v35r3e_r1_adaptive_beam_sequential_coordination/V35R3E_R1_PRODUCTION_SEARCH_CONTRACT.json",
        "sha256": "db68a86b41007ef4397ad30e09bb3e22f629f725723b2bdf35cff624b39538d9",
        "git_blob": "51ba686a1dc8b884bf46838b71c924ce6703de7b",
    },
    "C1": {
        "commit": MESS_HEAD,
        "path": "dayahead/artifacts/v24t_thermal_aware_aidc/V24T_C1_QUASISTATIC_MODEL.json",
        "sha256": "02a19e6c2d8cb44ec6b90ff1a4c98f21d5e848cda2dc34f2aaf2f959f9e6579e",
        "git_blob": "4bdeea1c701ed0819d771b3aff0c70f5a17866a3",
    },
    "PLANNING": {
        "commit": MESS_HEAD,
        "path": "dayahead/v34/integrated_mess.py",
        "sha256": "bcaba241f2bec6245aebca4c30a5f709e9e243427600c5f8bd182b33a319f7ee",
        "git_blob": "f79993b5eb650ef2c343d381ec98b74054998933",
    },
    "FRESH": {
        "commit": MESS_HEAD,
        "path": "dayahead/v28r2/opendss_backend.py",
        "sha256": "55ad4be7175088ea24dbb611313635736f182f4d945f6f9b416b2ddec2c29956",
        "git_blob": "c9b577e06805673e705984193f374b7b00b307cf",
    },
    "TRAFFIC": {
        "commit": MESS_HEAD,
        "path": "dayahead/v35/traffic_authority.py",
        "sha256": "eac6bc458ca5aa667f3dfd6680c5aa2222c9a640b4a6e7dc8f92d1c825595f0e",
        "git_blob": "a364708b30b58574d5e7d28e9577eac6b04c344a",
    },
    "SAFE_ETA": {
        "commit": MESS_HEAD,
        "path": "dayahead/artifacts/v33m3_causal_dayahead_traffic/V33M3_SAFE_ETA_CALIBRATION.json",
        "sha256": "353f124bdda33b1fd408f4f810b762f433bbe25d8c5c13b191fe1b0d6e36ff99",
        "git_blob": "cb0f32d0e4095e71bac985f0cbdfdf3da8037587",
    },
    "IDC_LOCATION": {
        "commit": MESS_HEAD,
        "path": "dayahead/artifacts/v16/AIDC_RACK_MAPPING_CONTRACT.json",
        "sha256": "d33444a19cfc6c4761f2e1b9a8adb88203b05cffc1d4a798e7b61c5add265d5b",
        "git_blob": "bf2ed473ddfd751b2f0363559b04d58240bda073",
    },
    "OBJECTIVE": {
        "commit": MESS_HEAD,
        "path": "dayahead/artifacts/v35_april_may_final/V35_SCIENCE_FREEZE.json",
        "sha256": "66464e16f5f1ba4500a98b612f83fac489c3c3b8262d473150521bab5649092f",
        "git_blob": "9be8c17068cd4fa21e8640870e31478627fc7990",
    },
    "CASES": {
        "commit": MESS_HEAD,
        "path": "dayahead/v35/contracts.py",
        "sha256": "fd78857af4fc122a70584e96b3fccc722f01f1e2d5ad393ac585d0f96bfad981",
        "git_blob": "cc8f03c7ec35e18c3aa3cfae418462abb9312f55",
    },
}

SCHEMA_VERSION = "V36_MAY_OUTPUT_SCHEMA_V1"
SCHEMA_IDS = {
    name: f"V36_{name}_V1" for name in (
        "RUN_PROVENANCE", "INPUT_AUTHORITY", "AIDC_SCHEDULER_LEDGER",
        "AIDC_POWER_96", "IDC_FACILITY_96", "MESS_TRAJECTORY_96",
        "MESS_MOVE_EVENTS", "MESS_SEARCH_TRACE", "PLANNING_BUS_PHASE_96",
        "PLANNING_LINE_PHASE_96", "PLANNING_SYSTEM_96",
        "FRESH_BUS_PHASE_96", "FRESH_LINE_PHASE_96", "FRESH_SYSTEM_96",
        "PLANNING_FRESH_VOLTAGE_RESIDUAL", "PLANNING_FRESH_CURRENT_RESIDUAL",
        "PLANNING_FRESH_SYSTEM_RESIDUAL", "OBJECTIVE", "PHYSICAL_GATES",
        "SOLVER_RUNS", "COMPUTE_SUMMARY", "DATE_OUTPUT_MANIFEST",
        "DATE_COMPLETENESS_GATE",
    )
}
