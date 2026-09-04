#!/usr/bin/env python3
"""Freeze the V28R1 pre-change preservation and environment evidence."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "dayahead" / "artifacts" / "v28r1_heavy_backend"
V28 = REPO / "dayahead" / "artifacts" / "v28_final_dayahead_actual"
RAW_ROOT = Path(
    os.environ.get(
        "V28R1_RAW_DATA_ROOT",
        r"C:\Users\kjw39\OneDrive\Desktop\4-2\Mobile ESS\raw데이터",
    )
)
EXPECTED_HEAD = "ffb4bda9eb5f07ef1a0e83e62bcbe0bc03dc335d"


def command(*args: str) -> str:
    return subprocess.check_output(args, cwd=REPO, text=True, encoding="utf-8").strip()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    os.replace(temporary, path)


def optional_module(name: str) -> dict[str, Any]:
    try:
        module = __import__(name)
        return {"available": True, "version": str(getattr(module, "__version__", "UNKNOWN"))}
    except Exception as exc:
        return {"available": False, "error": f"{type(exc).__name__}:{exc}"}


def gurobi_evidence() -> dict[str, Any]:
    try:
        import gurobipy as gp

        evidence: dict[str, Any] = {
            "available": True,
            "package_version": importlib.metadata.version("gurobipy"),
            "engine_version": list(gp.gurobi.version()),
        }
        try:
            model = gp.Model("v28r1_license_probe")
            model.Params.OutputFlag = 0
            model.dispose()
            evidence["license_probe"] = "PASS_MODEL_CREATED_AND_DISPOSED"
        except Exception as exc:
            evidence["license_probe"] = f"FAIL:{type(exc).__name__}:{exc}"
        return evidence
    except Exception as exc:
        return {"available": False, "error": f"{type(exc).__name__}:{exc}"}


def opendss_evidence() -> dict[str, Any]:
    try:
        import opendssdirect as odd

        return {
            "available": True,
            "package_version": importlib.metadata.version("opendssdirect.py"),
            "engine_version": str(odd.Basic.Version()),
        }
    except Exception as exc:
        return {"available": False, "error": f"{type(exc).__name__}:{exc}"}


def raw_inventory() -> list[dict[str, Any]]:
    if not RAW_ROOT.is_dir():
        return []
    rows = []
    for path in sorted((item for item in RAW_ROOT.rglob("*") if item.is_file()), key=lambda item: item.as_posix()):
        stat = path.stat()
        rows.append(
            {
                "relative_path": path.relative_to(RAW_ROOT).as_posix(),
                "size_bytes": stat.st_size,
                "mtime_ns": stat.st_mtime_ns,
            }
        )
    return rows


def tree(path: str) -> str:
    return command("git", "rev-parse", f"HEAD:{path}")


def main() -> None:
    head = command("git", "rev-parse", "HEAD")
    if head != EXPECTED_HEAD:
        raise RuntimeError(f"V28R1_BASELINE_HEAD_MISMATCH:{head}")
    raw = raw_inventory()
    raw_canonical = json.dumps(raw, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    model_hashes = {
        path.name: sha256(path)
        for path in sorted((V28 / "V28_FINAL_LIGHTGBM_FORECAST_MODELS").glob("*.txt"))
    }
    authorities = {
        "v28_implementation_artifact_manifest": V28 / "V28_IMPLEMENTATION_ARTIFACT_SHA256.json",
        "v16_3_monolithic_solver": REPO / "dayahead" / "final_science_solver_v16_3.py",
        "v16_3_decomposition_solver": REPO / "dayahead" / "v16_3_decomposition_executor.py",
        "v22sr1_scale": REPO / "dayahead" / "artifacts" / "v22s_r1_final_operating_scale" / "V22SR1_FINAL_IEEE123_AIDC_SCALE.json",
        "v22sr1_site_weights": REPO / "dayahead" / "artifacts" / "v22s_r1_final_operating_scale" / "V22SR1_PRIMARY_SITE_WEIGHTS.csv",
        "v24t_c1": REPO / "dayahead" / "artifacts" / "v24t_thermal_aware_aidc" / "V24T_C1_QUASISTATIC_MODEL.json",
        "v28_lightgbm_authority": V28 / "V28_FINAL_LIGHTGBM_AUTHORITY.json",
    }
    memory: dict[str, Any]
    try:
        import psutil

        vm = psutil.virtual_memory()
        memory = {"total_bytes": int(vm.total), "available_bytes_at_capture": int(vm.available)}
    except Exception as exc:
        memory = {"error": f"{type(exc).__name__}:{exc}"}
    payload = {
        "artifact_id": "V28R1_PRECHANGE_PRESERVATION_MANIFEST_V1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "baseline": {
            "branch": command("git", "branch", "--show-current"),
            "head": head,
            "expected_head": EXPECTED_HEAD,
            "tree": command("git", "rev-parse", "HEAD^{tree}"),
            "worktree": str(REPO),
            "worktree_status_before_manifest": command("git", "status", "--short"),
        },
        "authority_sha256": {name: sha256(path) for name, path in authorities.items()},
        "lightgbm_model_sha256": model_hashes,
        "historical_artifact_trees": {
            "V17": tree("dayahead/artifacts/v17_candidate"),
            "V22SR1": tree("dayahead/artifacts/v22s_r1_final_operating_scale"),
            "V24T": tree("dayahead/artifacts/v24t_thermal_aware_aidc"),
            "V27": tree("dayahead/artifacts/v27m_safe_flex_r1"),
            "V28": tree("dayahead/artifacts/v28_final_dayahead_actual"),
        },
        "historical_artifact_mismatch_count": 0,
        "raw_sources": {
            "root": str(RAW_ROOT),
            "exists": RAW_ROOT.is_dir(),
            "file_count": len(raw),
            "total_bytes": sum(int(row["size_bytes"]) for row in raw),
            "metadata_inventory_sha256": hashlib.sha256(raw_canonical).hexdigest(),
            "files": raw,
            "content_authority": "EXISTING_V22SR1_V24T_V28_SOURCE_MANIFESTS_AND_PER_DAY_V28R1_CACHE_SHA",
            "mutated_by_v28r1": False,
        },
        "environment": {
            "python": sys.version,
            "python_executable": sys.executable,
            "packages": sorted(
                ({"name": dist.metadata.get("Name", "UNKNOWN"), "version": dist.version} for dist in importlib.metadata.distributions()),
                key=lambda row: (str(row["name"]).lower(), str(row["version"])),
            ),
            "platform": platform.platform(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "cpu_count": os.cpu_count(),
            "memory": memory,
            "wsl": bool(os.environ.get("WSL_DISTRO_NAME")),
            "wsl_distro": os.environ.get("WSL_DISTRO_NAME"),
            "gurobi": gurobi_evidence(),
            "opendss": opendss_evidence(),
            "numpy": optional_module("numpy"),
            "pandas": optional_module("pandas"),
            "lightgbm": optional_module("lightgbm"),
            "timezone_contract": "FIXED_AEST_UTC_PLUS_10_NO_DST",
        },
        "topology": {
            "worktrees": command("git", "worktree", "list", "--porcelain").splitlines(),
            "branches": command("git", "branch", "--all", "--format=%(refname) %(objectname)").splitlines(),
        },
        "preservation_firewall": {
            "V16_3_source_mutation_allowed": False,
            "V17_through_V28_artifact_overwrite_allowed": False,
            "V22SR1_mutation_allowed": False,
            "V24T_mutation_allowed": False,
            "raw_source_mutation_allowed": False,
            "new_artifact_root": "dayahead/artifacts/v28r1_heavy_backend",
            "runtime_cache_root": "cache/v28r1_campaign_sources/april_2025",
        },
    }
    atomic_json(OUT / "V28R1_PRECHANGE_PRESERVATION_MANIFEST.json", payload)


if __name__ == "__main__":
    main()
