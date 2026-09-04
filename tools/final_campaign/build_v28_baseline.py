#!/usr/bin/env python3
"""Create the immutable V28 pre-change preservation manifest."""

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


REPO = Path(__file__).resolve().parents[2]
ARTIFACTS = REPO / "dayahead" / "artifacts" / "v28_final_dayahead_actual"
RAW_ROOT = Path(
    os.environ.get(
        "V28_RAW_DATA_ROOT",
        r"C:\Users\kjw39\OneDrive\Desktop\4-2\Mobile ESS\raw데이터\데이터 센터",
    )
)


def run(*args: str) -> str:
    return subprocess.check_output(args, cwd=REPO, text=True, encoding="utf-8").strip()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def atomic_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    os.replace(temporary, path)


def tracked_tree() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for line in run("git", "ls-tree", "-r", "--long", "HEAD").splitlines():
        metadata, path = line.split("\t", 1)
        mode, kind, object_id, size = metadata.split()
        rows.append(
            {
                "path": path,
                "git_mode": mode,
                "git_object_type": kind,
                "git_object_sha": object_id,
                "size_bytes": None if size == "-" else int(size),
            }
        )
    return rows


def raw_inventory() -> tuple[list[dict[str, object]], str]:
    if not RAW_ROOT.exists():
        return [], "RAW_ROOT_MISSING"
    rows = []
    for path in sorted((p for p in RAW_ROOT.rglob("*") if p.is_file()), key=lambda p: p.as_posix()):
        stat = path.stat()
        rows.append(
            {
                "relative_path": path.relative_to(RAW_ROOT).as_posix(),
                "size_bytes": stat.st_size,
                "mtime_ns": stat.st_mtime_ns,
            }
        )
    canonical = json.dumps(rows, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return rows, sha256_bytes(canonical)


def packages() -> list[dict[str, str]]:
    return sorted(
        ({"name": dist.metadata["Name"], "version": dist.version} for dist in importlib.metadata.distributions()),
        key=lambda item: (item["name"].lower(), item["version"]),
    )


def optional_version(module_name: str, attribute: str = "__version__") -> str:
    try:
        module = __import__(module_name)
        return str(getattr(module, attribute, "INSTALLED_VERSION_UNAVAILABLE"))
    except Exception as exc:  # environment evidence, never a functional dependency
        return f"UNAVAILABLE:{type(exc).__name__}"


def main() -> None:
    tracked = tracked_tree()
    raw, raw_fingerprint = raw_inventory()
    branch_lines = run("git", "branch", "--all", "--format=%(refname) %(objectname)").splitlines()
    worktree_lines = run("git", "worktree", "list", "--porcelain").splitlines()
    artifact_roots = {
        name: run("git", "rev-parse", f"HEAD:{name}")
        for name in (
            "dayahead/artifacts/v17_candidate",
            "dayahead/artifacts/v21_pre_science_integration",
            "dayahead/artifacts/v22s_r1_final_operating_scale",
            "dayahead/artifacts/v27m_safe_flex_r1",
        )
    }
    payload = {
        "artifact_id": "V28_PRECHANGE_PRESERVATION_MANIFEST_V1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "baseline": {
            "branch": run("git", "branch", "--show-current"),
            "head": run("git", "rev-parse", "HEAD"),
            "tree": run("git", "rev-parse", "HEAD^{tree}"),
            "expected_head": "a9f75e603a74cd3f938aa7eb7dfa537fd4ea0662",
        },
        "repository": {
            "tracked_file_count": len(tracked),
            "files": tracked,
            "historical_artifact_tree_sha": artifact_roots,
        },
        "raw_sources": {
            "root": str(RAW_ROOT),
            "exists": RAW_ROOT.exists(),
            "file_count": len(raw),
            "total_bytes": sum(int(item["size_bytes"]) for item in raw),
            "metadata_inventory_sha256": raw_fingerprint,
            "files": raw,
            "content_sha256_authority": "V24T/V22SR1 source manifests plus V28 final source inventory at May freeze",
            "mutated_by_v28": False,
        },
        "branch_topology": branch_lines,
        "worktree_topology": worktree_lines,
        "environment": {
            "python": sys.version,
            "python_executable": sys.executable,
            "platform": platform.platform(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "cpu_count": os.cpu_count(),
            "timezone_contract": "FIXED_AEST_UTC_PLUS_10_NO_DST",
            "gurobipy": optional_version("gurobipy"),
            "opendssdirect": optional_version("opendssdirect"),
            "packages": packages(),
        },
        "preservation_contract": {
            "V17_through_V27_immutable": True,
            "V22SR1_immutable": True,
            "V24T_accepted_artifacts_immutable_on_import": True,
            "historical_output_overwrite_allowed": False,
            "heavy_output_root_separate": True,
        },
    }
    atomic_json(ARTIFACTS / "V28_PRECHANGE_PRESERVATION_MANIFEST.json", payload)


if __name__ == "__main__":
    main()
