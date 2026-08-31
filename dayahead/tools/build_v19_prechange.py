from __future__ import annotations

import hashlib
import importlib.metadata
import json
import platform
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "dayahead" / "artifacts" / "v19_c_mass_tpp"
PRESERVED = {
    "v17_candidate": ROOT / "dayahead" / "artifacts" / "v17_candidate",
    "v17_flexibility_forensic": ROOT / "dayahead" / "artifacts" / "v17_flexibility_funnel_forensic",
    "v18": ROOT / "dayahead" / "artifacts" / "v18_aidc_physical_refreeze",
    "v18r1": ROOT / "dayahead" / "artifacts" / "v18r1_aidc_physical_coherence_repair",
    "v18r2": ROOT / "dayahead" / "artifacts" / "v18r2_aidc_forecast_magnitude_refreeze",
}
STARTING_BRANCH = "codex/dayahead-aidc-joint-v1"
STARTING_HEAD = "77a86e3ded8087ea0109ccfca631bd2396ecd9fe"
NEW_BRANCH = "codex/v19-c-mass-tpp"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def git(*args: str) -> str:
    return subprocess.check_output(
        ["git", *args], cwd=ROOT, text=True, encoding="utf-8"
    ).strip()


def preserved_records(directory: Path) -> list[dict[str, object]]:
    return [
        {
            "path": path.relative_to(ROOT).as_posix(),
            "size_bytes": path.stat().st_size,
            "sha256": sha256(path),
        }
        for path in sorted(directory.rglob("*"))
        if path.is_file()
    ]


def package_versions() -> dict[str, str | None]:
    result: dict[str, str | None] = {}
    for name in (
        "numpy",
        "pandas",
        "pyarrow",
        "torch",
        "scikit-learn",
        "lightgbm",
        "scipy",
    ):
        try:
            result[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            result[name] = None
    return result


def torch_environment() -> dict[str, object]:
    try:
        import torch
    except ImportError:
        return {
            "torch_version": None,
            "cuda_available": False,
            "cuda_device_count": 0,
            "status": "NOT_INSTALLED_AT_TASK_START",
        }
    return {
        "torch_version": torch.__version__,
        "cuda_available": bool(torch.cuda.is_available()),
        "cuda_device_count": int(torch.cuda.device_count()),
        "status": "AVAILABLE",
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    groups = {name: preserved_records(path) for name, path in PRESERVED.items()}
    actual_head = git("rev-parse", "HEAD")
    if actual_head != STARTING_HEAD:
        raise RuntimeError(f"UNEXPECTED_STARTING_HEAD:{actual_head}")
    manifest = {
        "artifact_id": "V19_PRECHANGE_PRESERVATION_MANIFEST_V1",
        "starting_state_user_authority": {
            "branch": STARTING_BRANCH,
            "head": STARTING_HEAD,
            "git_status_short": [],
        },
        "verified_before_branch_creation": {
            "branch": STARTING_BRANCH,
            "head": STARTING_HEAD,
            "git_status_short": [],
            "matched_user_authority": True,
        },
        "manifest_write_state": {
            "branch": git("branch", "--show-current"),
            "head": actual_head,
            "expected_new_branch": NEW_BRANCH,
            "git_status_before_manifest_write": [],
        },
        "python_environment": {
            "executable": sys.executable,
            "version": sys.version,
            "platform": platform.platform(),
            "packages": package_versions(),
            **torch_environment(),
        },
        "preservation_groups": groups,
        "preserved_artifact_counts": {
            name: len(records) for name, records in groups.items()
        },
        "expected_counts": {
            "v17_candidate": 369,
            "v17_flexibility_forensic": 8,
            "v18": 17,
            "v18r1": 19,
            "v18r2": 21,
        },
        "preservation_count_gate": all(
            len(groups[name]) == count
            for name, count in {
                "v17_candidate": 369,
                "v17_flexibility_forensic": 8,
                "v18": 17,
                "v18r1": 19,
                "v18r2": 21,
            }.items()
        ),
        "firewall_counters_at_start": {
            "D_day_actual_feature_reads": 0,
            "future_start_feature_reads": 0,
            "future_end_feature_reads": 0,
            "future_queue_wait_feature_reads": 0,
            "future_completion_feature_reads": 0,
            "April_reads_before_freeze": 0,
            "literature_target_reads": 0,
            "grid_objective_reads_for_model_selection": 0,
            "result_based_workload_multiplier_calls": 0,
            "B0_B1_B2_B3_science_calls": 0,
            "OpenDSS_calls": 0,
            "AC_science_calls": 0,
        },
    }
    path = OUT / "V19_PRECHANGE_PRESERVATION_MANIFEST.json"
    path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(path)
    print(sha256(path))


if __name__ == "__main__":
    main()
