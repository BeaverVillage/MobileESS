"""Freeze immutable V17--V25M state before V26M SAFE-Flex work."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "dayahead" / "artifacts" / "v26m_safe_flex"
START_HEAD = "377f147f007151c53ebbe8ca3fb2cdd616bc3e5b"
EXPECTED_BRANCH = "codex/v26m-safe-flex"
RAW_KESTREL = Path(r"C:\Users\kjw39\OneDrive\Desktop\4-2\Mobile ESS\raw데이터\데이터 센터\NLR HPC Kestrel Jobs Data\esif.hpc.kestrel.job-anon.zip")
GROUPS = {
    "v17_candidate": ROOT / "dayahead/artifacts/v17_candidate",
    "v17_forensic": ROOT / "dayahead/artifacts/v17_flexibility_funnel_forensic",
    "v18": ROOT / "dayahead/artifacts/v18_aidc_physical_refreeze",
    "v18r1": ROOT / "dayahead/artifacts/v18r1_aidc_physical_coherence_repair",
    "v18r2": ROOT / "dayahead/artifacts/v18r2_aidc_forecast_magnitude_refreeze",
    "v19": ROOT / "dayahead/artifacts/v19_c_mass_tpp",
    "v20": ROOT / "dayahead/artifacts/v20_independent_authorities",
    "v21": ROOT / "dayahead/artifacts/v21_pre_science_integration",
    "v22s": ROOT / "dayahead/artifacts/v22s_melbourne_12site_scale",
    "v22sr1": ROOT / "dayahead/artifacts/v22s_r1_final_operating_scale",
    "v23m": ROOT / "dayahead/artifacts/v23m_racq_flex",
    "v24m": ROOT / "dayahead/artifacts/v24m_faser_flex",
    "v25m": ROOT / "dayahead/artifacts/v25m_beacon_flex",
    "prior_c_mass_code": ROOT / "dayahead/ml/c_mass_tpp",
    "prior_racq_code": ROOT / "dayahead/ml/racq_flex",
    "prior_faser_code": ROOT / "dayahead/ml/faser_flex",
    "prior_beacon_code": ROOT / "dayahead/ml/beacon_flex",
}


def sha256(path: Path) -> str:
    """Return the byte-level SHA256 digest of one source or protected artifact."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def git(*args: str) -> str:
    """Run one read-only Git query in the V26M worktree."""

    return subprocess.check_output(["git", *args], cwd=ROOT, text=True, encoding="utf-8").strip()


def inventory(directory: Path) -> list[dict[str, object]]:
    """Return the immutable file inventory for one protected historical group."""

    if not directory.is_dir():
        raise RuntimeError(f"V26M_PROTECTED_DIRECTORY_MISSING:{directory}")
    return [{"path": path.relative_to(ROOT).as_posix(), "size_bytes": path.stat().st_size, "sha256": sha256(path)}
            for path in sorted(directory.rglob("*")) if path.is_file()]


def package_versions() -> dict[str, str | None]:
    """Return scientific, survival, and solver package versions."""

    result: dict[str, str | None] = {}
    for name in ("numpy", "pandas", "pyarrow", "scipy", "scikit-learn", "lightgbm", "torch", "lifelines", "scikit-survival", "cvxpy", "osqp", "clarabel", "ecos", "pytz", "tzdata"):
        try:
            result[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            result[name] = None
    return result


def cuda_environment() -> dict[str, object]:
    """Return actual PyTorch CUDA and VRAM availability."""

    try:
        import torch
    except ImportError:
        return {"torch_available": False, "cuda_available": False}
    available = bool(torch.cuda.is_available())
    payload: dict[str, object] = {"torch_available": True, "torch_version": torch.__version__, "torch_cuda_build": torch.version.cuda,
                                  "cuda_available": available, "cuda_device_count": int(torch.cuda.device_count())}
    if available:
        properties = torch.cuda.get_device_properties(0)
        payload.update({"cuda_device_name": torch.cuda.get_device_name(0), "cuda_vram_bytes": int(properties.total_memory)})
    return payload


def main() -> None:
    """Validate the clean base and write the V26M preservation manifest."""

    head, branch = git("rev-parse", "HEAD"), git("branch", "--show-current")
    status = git("status", "--porcelain").splitlines()
    expected_untracked = {"?? dayahead/ml/safe_flex/", "?? dayahead/tools/build_v26m_prechange.py"}
    if head != START_HEAD or branch != EXPECTED_BRANCH:
        raise RuntimeError(f"V26M_START_STATE_MISMATCH:{branch}:{head}")
    if set(status) != expected_untracked:
        raise RuntimeError(f"V26M_PRECHANGE_DIRTY:{status}")
    if not RAW_KESTREL.is_file():
        raise RuntimeError(f"V26M_RAW_SOURCE_MISSING:{RAW_KESTREL}")
    protected = {name: inventory(path) for name, path in GROUPS.items()}
    counts = {name: len(records) for name, records in protected.items()}
    OUT.mkdir(parents=True, exist_ok=True)
    payload = {
        "artifact_id": "V26M_PRECHANGE_PRESERVATION_MANIFEST_V1", "created_utc": datetime.now(timezone.utc).isoformat(),
        "starting_state": {"branch": branch, "head": head, "worktree": str(ROOT.resolve()), "git_status_before_new_files": []},
        "protected_groups": protected, "protected_artifact_counts": counts, "protected_total_files": sum(counts.values()),
        "raw_sources": [{"path": str(RAW_KESTREL), "size_bytes": RAW_KESTREL.stat().st_size, "sha256": sha256(RAW_KESTREL)}],
        "python_environment": {"executable": sys.executable, "version": sys.version, "platform": platform.platform(), "packages": package_versions(), **cuda_environment()},
        "internet_access_status": "ENABLED_BUT_NOVELTY_SEARCH_CONDITIONAL_ON_ORACLE_GATE",
        "firewall_counters": {"prior_artifact_changes": 0, "future_timestamp_value_reads": 0, "exact_squeue_claims": 0,
            "fixed_528_training_uses": 0, "April_target_reads_before_freeze": 0, "facility_MW_scale_calls": 0,
            "beta_AIDC_calls": 0, "PUE_loss_calls": 0, "OpenDSS_calls": 0, "B0_B3_final_grid_science_calls": 0,
            "grid_objective_reads": 0, "thermal_branch_merge_calls": 0},
    }
    path = OUT / "V26M_PRECHANGE_PRESERVATION_MANIFEST.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"path": str(path), "sha256": sha256(path), "protected_total_files": sum(counts.values()), "counts": counts}))


if __name__ == "__main__":
    main()
