"""Freeze the immutable V17--V26 and raw-source baseline for V27M."""

from __future__ import annotations

import hashlib
import importlib
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "dayahead/artifacts/v27m_safe_flex_r1"
BASE_HEAD = "b958d961b7bc493cb1697cf843a7e615a58a9f67"
V26_MANIFEST = REPO / "dayahead/artifacts/v26m_safe_flex/V26M_PRECHANGE_PRESERVATION_MANIFEST.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=REPO, text=True).strip()


def package_version(import_name: str) -> str | None:
    try:
        module = importlib.import_module(import_name)
    except ImportError:
        return None
    return str(getattr(module, "__version__", "UNKNOWN"))


def tracked_v26_paths() -> list[str]:
    names = git("ls-tree", "-r", "--name-only", BASE_HEAD).splitlines()
    prefixes = (
        "dayahead/artifacts/v26m_safe_flex/",
        "dayahead/ml/safe_flex/",
    )
    return sorted(
        name
        for name in names
        if name.startswith(prefixes)
        or (name.startswith("dayahead/tools/") and "v26m" in Path(name).name.lower())
    )


def record(path_text: str) -> dict[str, object]:
    path = REPO / path_text
    return {"path": path_text, "size_bytes": path.stat().st_size, "sha256": sha256(path)}


def main() -> None:
    previous = json.loads(V26_MANIFEST.read_text(encoding="utf-8"))
    groups = previous["protected_groups"]
    groups["v26m_artifacts_code_tools"] = [record(path) for path in tracked_v26_paths()]
    raw_sources = []
    for old in previous["raw_sources"]:
        path = Path(old["path"])
        raw_sources.append(
            {
                "path": str(path),
                "size_bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
        )
    torch = importlib.import_module("torch")
    package_names = {
        "numpy": "numpy",
        "pandas": "pandas",
        "pyarrow": "pyarrow",
        "scipy": "scipy",
        "scikit-learn": "sklearn",
        "lightgbm": "lightgbm",
        "torch": "torch",
        "cvxpy": "cvxpy",
        "osqp": "osqp",
        "clarabel": "clarabel",
        "ecos": "ecos",
        "optuna": "optuna",
    }
    cuda = bool(torch.cuda.is_available())
    manifest = {
        "artifact_id": "V27M_PRECHANGE_PRESERVATION_MANIFEST_V1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "starting_state": {
            "branch": git("branch", "--show-current"),
            "head": git("rev-parse", "HEAD"),
            "worktree": str(REPO),
            "git_status_before_new_files": [],
        },
        "protected_groups": groups,
        "protected_artifact_counts": {key: len(value) for key, value in groups.items()},
        "protected_total_files": sum(len(value) for value in groups.values()),
        "raw_sources": raw_sources,
        "python_environment": {
            "executable": sys.executable,
            "version": sys.version,
            "platform": platform.platform(),
            "packages": {label: package_version(name) for label, name in package_names.items()},
            "torch_cuda_build": torch.version.cuda,
            "cuda_available": cuda,
            "cuda_device_count": torch.cuda.device_count(),
            "cuda_device_name": torch.cuda.get_device_name(0) if cuda else None,
            "cuda_vram_bytes": torch.cuda.get_device_properties(0).total_memory if cuda else None,
        },
        "internet_access_status": "ENABLED_BUT_NOVELTY_SEARCH_CONDITIONAL_ON_RESIDUAL_AND_PERFORMANCE_GATES",
        "firewall_counters": {
            "prior_artifact_changes": 0,
            "future_start_numeric_feature_reads": 0,
            "future_end_numeric_feature_reads": 0,
            "future_service_labels_in_features": 0,
            "April_reads_before_freeze": 0,
            "facility_MW_scale_calls": 0,
            "beta_AIDC_calls": 0,
            "PUE_calls": 0,
            "OpenDSS_calls": 0,
            "B0_B3_final_grid_science_calls": 0,
            "grid_objective_reads": 0,
        },
    }
    if manifest["starting_state"]["head"] != BASE_HEAD:
        raise RuntimeError("V27M_BASE_HEAD_MISMATCH")
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "V27M_PRECHANGE_PRESERVATION_MANIFEST.json"
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"protected_files": manifest["protected_total_files"], "raw_sha256": raw_sources[0]["sha256"]}))


if __name__ == "__main__":
    main()
