"""V39C immutable boundaries and expected engineering invariants."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path


IMPLEMENTATION_ID = "V39C_GANG_AWARE_AIDC_GPU_CAPACITY_REFREEZE_V1"
CLASSIFICATION = "POSTHOC_ENGINEERING_CAPACITY_REFREEZE"
CAPACITY_SEMANTICS = "SYNTHETIC_H100_EQUIVALENT_SITE_COMPUTE_CAPACITY"
START_HEAD = "46edb9a6637de430d08f0bd8948758e28d3262ab"
V39A_HEAD = "b78fa725e8f98ef43091dd67a8a642275de7f963"
V39A_FINGERPRINT = (
    "43a4c15aa88bc84cc0433ca20a81410b0885a3a90f70b64bd480e6e483bc3f76"
)
BRANCH = "codex/v39c-gang-aware-aidc-gpu-capacity-refreeze"

ARTIFACT_ROOT = Path("dayahead/artifacts/v39c_aidc_gpu_capacity_refreeze")
V37_DAY_ROOT = Path("dayahead/artifacts/v37_r4a_per_day_aidc/days")
V39A_ARTIFACT_ROOT = Path("dayahead/artifacts/v39a_causal_aidc_site_placement_power")
V39B_ARTIFACT_ROOT = Path("dayahead/artifacts/v39b_preimplementation_diagnostic")
V38_ARTIFACT_ROOT = Path("dayahead/artifacts/v38_aidc_spatiotemporal_wan")

V22_WEIGHT_PATH = Path(
    "dayahead/artifacts/v22s_r1_final_operating_scale/"
    "V22SR1_PRIMARY_SITE_WEIGHTS.csv"
)
V22_WEIGHT_SHA256 = (
    "1fb7931dcc86b190af7e9cc0e18b3466897ea66a35a79e53e452b36524a6e63b"
)
LEGACY_MAPPING_PATH = V38_ARTIFACT_ROOT / "V38_AIDC_GPU_CAPACITY_MAPPING.json"
LEGACY_MAPPING_SHA256 = (
    "2ddd1efa51920b74c45b27ed58b408b432eccf6a8c95e12217b3b18b0b737570"
)
LEGACY_CAPACITY_SOURCE_SHA256 = (
    "4546c0672a4d25aa5c7c92ea90fb90ec8d3c009dda426939179b293abdeb83c0"
)
LEGACY_PROVENANCE_PATH = Path(
    "dayahead/artifacts/v16/RACK_POWER_CAPACITY_PROVENANCE_AUDIT_V1.json"
)
LEGACY_RACK_CONTRACT_PATH = Path("dayahead/artifacts/v16/AIDC_RACK_MAPPING_CONTRACT.json")

PREMAY_NORMALIZED_HISTORY = Path(
    r"C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2"
    r"\MobileESS_v35r3d_kestrel_runtime_authority_closure\dayahead\cache"
    r"\v35r3d_kestrel_runtime_authority_closure\kestrel_preissue_normalized.parquet"
)
PREMAY_NORMALIZED_HISTORY_SHA256 = (
    "2a8cf4ac8f86a30d0a7dcf999e2064316b556194f8bbc291f09cc85a2d7e101f"
)
PREMAY_CUTOFF = "2025-03-31T00:00:00+10:00"

GPU_TOTAL = 624
GPU_PER_NODE = 4
NODE_TOTAL = 156
MINIMUM_NODES_PER_SITE = 8
MINIMUM_GPU_PER_SITE = 32
EXTRA_BLOCK_NODES = 8
EXTRA_BLOCK_GPU = 32
SOLVER_SEED = 20260905
SOLVER_THREADS = 1
SLOTS = 96
TEMPORAL_MODES = ("RW", "RSP")
EXPECTED_DATES = tuple(
    (date(2025, 5, 1) + timedelta(days=offset)).isoformat()
    for offset in range(31)
)

EXPECTED_WEIGHT_ORDER = (
    "AIDC05", "AIDC12", "AIDC10", "AIDC03", "AIDC08", "AIDC06",
    "AIDC01", "AIDC07", "AIDC11", "AIDC09", "AIDC02", "AIDC04",
)
EXPECTED_TOP_SEVEN = EXPECTED_WEIGHT_ORDER[:7]
EXPECTED_NODE_CAPACITY = {
    "AIDC01": 16,
    "AIDC02": 8,
    "AIDC03": 16,
    "AIDC04": 8,
    "AIDC05": 20,
    "AIDC06": 16,
    "AIDC07": 8,
    "AIDC08": 16,
    "AIDC09": 8,
    "AIDC10": 16,
    "AIDC11": 8,
    "AIDC12": 16,
}
EXPECTED_GPU_CAPACITY = {
    site: nodes * GPU_PER_NODE for site, nodes in EXPECTED_NODE_CAPACITY.items()
}
LEGACY_GPU_CAPACITY = {
    "AIDC01": 42,
    "AIDC02": 75,
    "AIDC03": 77,
    "AIDC04": 34,
    "AIDC05": 53,
    "AIDC06": 68,
    "AIDC07": 21,
    "AIDC08": 62,
    "AIDC09": 139,
    "AIDC10": 17,
    "AIDC11": 12,
    "AIDC12": 24,
}

assert GPU_TOTAL == NODE_TOTAL * GPU_PER_NODE
assert sum(EXPECTED_NODE_CAPACITY.values()) == NODE_TOTAL
assert sum(EXPECTED_GPU_CAPACITY.values()) == GPU_TOTAL
