"""Read-only recursive raw-data discovery and preservation manifests."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq

from .contracts import ARTIFACT_ROOT, BRANCH, RAW_ROOT, START_HEAD
from .utils import environment_audit, git_output, sha256_file, write_json


PROTECTED_PATHS = (
    "dayahead/artifacts/v17_candidate",
    "dayahead/artifacts/v18_aidc_physical_refreeze",
    "dayahead/artifacts/v18r1_aidc_physical_coherence_repair",
    "dayahead/artifacts/v18r2_aidc_forecast_magnitude_refreeze",
    "dayahead/artifacts/v19_c_mass_tpp",
    "dayahead/artifacts/v20_independent_authorities",
    "dayahead/artifacts/v21_pre_science_integration",
    "dayahead/artifacts/v22s_melbourne_12site_scale",
    "dayahead/artifacts/v22s_r1_final_operating_scale",
    "dayahead/artifacts/v23m_racq_flex",
    "dayahead/ml",
)


def _parquet_columns(path: Path) -> list[str]:
    """Read only parquet metadata and return physical column names."""
    try:
        return list(pq.ParquetFile(path).schema_arrow.names)
    except Exception:
        return []


def classify_file(path: Path) -> list[str]:
    """Classify a raw file by content metadata and conservative path hints."""
    roles: list[str] = []
    columns = {name.lower() for name in _parquet_columns(path)}
    if {"ts", "it_power_kw", "pue"}.issubset(columns):
        roles.append("NLR_ESIF_DC_POWER_METRICS")
    if {"ts", "outdoor_air_temp", "outdoor_air_humidity"}.issubset(columns):
        roles.append("NLR_ESIF_OUTSIDE_WEATHER")
    lower = path.name.lower()
    if lower.endswith(".csv") and lower == "4384652.csv":
        roles.append("NOAA_GLOBAL_HOURLY_CANDIDATE")
    if "kestrel" in str(path).lower():
        roles.append("NLR_KESTREL_WORKLOAD_PROVENANCE_ONLY")
    return roles


def inventory_raw_data(raw_root: Path = RAW_ROOT) -> dict[str, Any]:
    """Hash every raw source recursively without modifying any source bytes."""
    if not raw_root.is_dir():
        raise FileNotFoundError(raw_root)
    records: list[dict[str, Any]] = []
    for path in sorted((p for p in raw_root.rglob("*") if p.is_file()), key=str):
        before = path.stat()
        digest = sha256_file(path)
        after = path.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise RuntimeError(f"raw source changed while hashing: {path}")
        records.append(
            {
                "relative_path": str(path.relative_to(raw_root)),
                "absolute_path": str(path.resolve()),
                "file_size_bytes": before.st_size,
                "extension": path.suffix.lower(),
                "sha256": digest,
                "mtime_ns": before.st_mtime_ns,
                "roles": classify_file(path),
            }
        )
    return {
        "artifact_id": "V24T_RAW_DATA_INVENTORY",
        "root": str(raw_root.resolve()),
        "file_count": len(records),
        "total_bytes": sum(item["file_size_bytes"] for item in records),
        "source_modified_count": 0,
        "duplicate_files_deleted": 0,
        "files": records,
    }


def protected_tree_shas(repo: Path) -> dict[str, str | None]:
    """Record immutable Git tree/blob SHAs at the V23M start commit."""
    result: dict[str, str | None] = {}
    for path in PROTECTED_PATHS:
        try:
            result[path] = git_output(repo, "rev-parse", f"{START_HEAD}:{path}")
        except Exception:
            result[path] = None
    return result


def write_prechange_manifests(repo: Path, raw_root: Path = RAW_ROOT) -> dict[str, Any]:
    """Create the raw inventory and V24T prechange preservation manifest."""
    inventory = inventory_raw_data(raw_root)
    write_json(repo / ARTIFACT_ROOT / "V24T_RAW_DATA_INVENTORY.json", inventory)
    manifest = {
        "artifact_id": "V24T_PRECHANGE_PRESERVATION_MANIFEST",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "repository_branch": git_output(repo, "branch", "--show-current"),
        "head_at_generation": git_output(repo, "rev-parse", "HEAD"),
        "required_start_head": START_HEAD,
        "required_branch": BRANCH,
        "worktree": str(repo.resolve()),
        "git_status_short": git_output(repo, "status", "--short"),
        "protected_tree_sha_at_start_head": protected_tree_shas(repo),
        "raw_data": {
            "root": inventory["root"],
            "file_count": inventory["file_count"],
            "total_bytes": inventory["total_bytes"],
            "inventory_sha256": sha256_file(
                repo / ARTIFACT_ROOT / "V24T_RAW_DATA_INVENTORY.json"
            ),
            "source_modified_count": 0,
        },
        "environment": environment_audit(),
        "firewall": {
            "lightgbm_modifications": 0,
            "racq_modifications": 0,
            "faser_modifications": 0,
            "grid_result_reads": 0,
            "opendss_calls": 0,
            "beta_aidc_calls": 0,
            "gpu_h_scaling_calls": 0,
        },
    }
    write_json(
        repo / ARTIFACT_ROOT / "V24T_PRECHANGE_PRESERVATION_MANIFEST.json",
        manifest,
    )
    return manifest


if __name__ == "__main__":
    write_prechange_manifests(Path.cwd())
