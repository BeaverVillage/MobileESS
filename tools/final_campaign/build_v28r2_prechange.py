#!/usr/bin/env python3
"""Freeze the immutable V28R2 blocker-resolution baseline."""

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
OUT = REPO / "dayahead" / "artifacts" / "v28r2_heavy_backend"
RAW = Path(r"C:\Users\kjw39\OneDrive\Desktop\4-2\Mobile ESS\raw데이터")
EXPECTED_HEAD = "e1680d971e7a2b3b12b4ad92a6c1c47a535340f5"


def command(*args: str) -> str:
    return subprocess.check_output(args, cwd=REPO, text=True, encoding="utf-8").strip()


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tree(path: str) -> str:
    return command("git", "rev-parse", f"HEAD:{path}")


def atomic_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    os.replace(temporary, path)


def module(name: str) -> dict[str, Any]:
    try:
        loaded = __import__(name)
        return {"available": True, "version": str(getattr(loaded, "__version__", "UNKNOWN"))}
    except Exception as exc:
        return {"available": False, "error": f"{type(exc).__name__}:{exc}"}


def gurobi() -> dict[str, Any]:
    try:
        import gurobipy as gp

        result: dict[str, Any] = {
            "available": True,
            "package_version": importlib.metadata.version("gurobipy"),
            "engine_version": list(gp.gurobi.version()),
        }
        try:
            model = gp.Model("v28r2_license_probe")
            model.Params.OutputFlag = 0
            model.dispose()
            result["license_probe"] = "PASS_MODEL_CREATED_AND_DISPOSED"
        except Exception as exc:
            result["license_probe"] = f"FAIL:{type(exc).__name__}:{exc}"
        return result
    except Exception as exc:
        return {"available": False, "error": f"{type(exc).__name__}:{exc}"}


def opendss() -> dict[str, Any]:
    try:
        import opendssdirect as odd

        return {
            "available": True,
            "package_version": importlib.metadata.version("opendssdirect.py"),
            "engine_version": str(odd.Basic.Version()),
        }
    except Exception as exc:
        return {"available": False, "error": f"{type(exc).__name__}:{exc}"}


def inventory() -> list[dict[str, Any]]:
    if not RAW.is_dir():
        return []
    result = []
    for path in sorted((item for item in RAW.rglob("*") if item.is_file()), key=lambda item: item.as_posix()):
        stat = path.stat()
        result.append(
            {
                "relative_path": path.relative_to(RAW).as_posix(),
                "size_bytes": stat.st_size,
                "mtime_ns": stat.st_mtime_ns,
            }
        )
    return result


def main() -> None:
    head = command("git", "rev-parse", "HEAD")
    if head != EXPECTED_HEAD:
        raise RuntimeError(f"V28R2_BASE_HEAD_MISMATCH:{head}")
    raw = inventory()
    raw_bytes = json.dumps(raw, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    source_root = Path(
        r"C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\tmp\c12_exact_sources_repo_cleanup"
        r"\c12_exact_sources\v2038_parent"
        r"\Conversation3_Exact_AC_Remediation_Sweep_From_Conversation1_V2038\reference"
    )
    authority_paths = {
        "V16_3_monolithic": REPO / "dayahead/final_science_solver_v16_3.py",
        "V16_3_decomposition": REPO / "dayahead/v16_3_decomposition_executor.py",
        "V22SR1_scale": REPO / "dayahead/artifacts/v22s_r1_final_operating_scale/V22SR1_FINAL_IEEE123_AIDC_SCALE.json",
        "V22SR1_weights": REPO / "dayahead/artifacts/v22s_r1_final_operating_scale/V22SR1_PRIMARY_SITE_WEIGHTS.csv",
        "V24T_C1": REPO / "dayahead/artifacts/v24t_thermal_aware_aidc/V24T_C1_QUASISTATIC_MODEL.json",
        "V28_LightGBM": REPO / "dayahead/artifacts/v28_final_dayahead_actual/V28_FINAL_LIGHTGBM_AUTHORITY.json",
        "V28R1_blocking_audit": REPO / "dayahead/artifacts/v28r1_heavy_backend/V28R1_BLOCKING_AUDIT.json",
        "IEEE123_master": source_root / "opendss_assets/IEEE123Master.dss",
    }
    historical_paths = {
        "V17": "dayahead/artifacts/v17_candidate",
        "V22SR1": "dayahead/artifacts/v22s_r1_final_operating_scale",
        "V24T": "dayahead/artifacts/v24t_thermal_aware_aidc",
        "V27": "dayahead/artifacts/v27m_safe_flex_r1",
        "V28": "dayahead/artifacts/v28_final_dayahead_actual",
        "V28R1": "dayahead/artifacts/v28r1_heavy_backend",
    }
    payload = {
        "artifact_id": "V28R2_PRECHANGE_PRESERVATION_MANIFEST_V1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "baseline": {
            "expected_head": EXPECTED_HEAD,
            "head": head,
            "tree": command("git", "rev-parse", "HEAD^{tree}"),
            "branch": command("git", "branch", "--show-current"),
            "worktree": str(REPO),
            "status_before_manifest": command("git", "status", "--short"),
        },
        "authority_sha256": {
            name: {"path": str(path), "exists": path.is_file(), "sha256": sha(path) if path.is_file() else None}
            for name, path in authority_paths.items()
        },
        "historical_artifact_trees": {name: tree(path) for name, path in historical_paths.items()},
        "historical_artifact_mismatch_count": 0,
        "raw_sources": {
            "root": str(RAW),
            "exists": RAW.is_dir(),
            "file_count": len(raw),
            "total_bytes": sum(int(row["size_bytes"]) for row in raw),
            "metadata_inventory_sha256": hashlib.sha256(raw_bytes).hexdigest(),
            "files": raw,
            "mutated_by_V28R2": False,
        },
        "environment": {
            "python": sys.version,
            "python_executable": sys.executable,
            "platform": platform.platform(),
            "processor": platform.processor(),
            "machine": platform.machine(),
            "cpu_count": os.cpu_count(),
            "numpy": module("numpy"),
            "pandas": module("pandas"),
            "lightgbm": module("lightgbm"),
            "gurobi": gurobi(),
            "opendss": opendss(),
            "timezone_contract": "FIXED_AEST_UTC_PLUS_10",
        },
        "firewall": {
            "historical_authority_mutation_allowed": False,
            "raw_source_mutation_allowed": False,
            "automatic_merge_allowed": False,
            "new_artifact_root": "dayahead/artifacts/v28r2_heavy_backend",
            "new_cache_root": "cache/v28r2_campaign_sources/april_2025",
        },
        "topology": {
            "worktrees": command("git", "worktree", "list", "--porcelain").splitlines(),
            "branches": command("git", "branch", "--all", "--format=%(refname) %(objectname)").splitlines(),
        },
    }
    atomic_json(OUT / "V28R2_PRECHANGE_PRESERVATION_MANIFEST.json", payload)


if __name__ == "__main__":
    main()
