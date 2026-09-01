"""Small deterministic IO and audit helpers for V24T."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
import sys
from importlib import import_module
from pathlib import Path
from typing import Any, Iterable


def sha256_file(path: Path, chunk_bytes: int = 8 * 1024 * 1024) -> str:
    """Return SHA256 for *path* without changing the source file."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(chunk_bytes):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, payload: Any) -> None:
    """Write stable UTF-8 JSON and create only the destination parent."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def command_output(args: list[str], cwd: Path | None = None) -> str | None:
    """Return stripped command output, or ``None`` when unavailable."""
    try:
        return subprocess.check_output(
            args, cwd=cwd, text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def package_versions(names: Iterable[str]) -> dict[str, str | None]:
    """Return installed package versions without importing optional failures."""
    result: dict[str, str | None] = {}
    for name in names:
        try:
            module = import_module(name)
            result[name] = str(getattr(module, "__version__", "installed"))
        except Exception:
            result[name] = None
    return result


def environment_audit() -> dict[str, Any]:
    """Describe the Python, OS, packages, and CUDA visibility used by V24T."""
    packages = package_versions(
        (
            "numpy",
            "pandas",
            "pyarrow",
            "scipy",
            "sklearn",
            "statsmodels",
            "xarray",
            "cfgrib",
            "eccodes",
            "requests",
            "herbie",
        )
    )
    return {
        "python": sys.version,
        "python_executable": sys.executable,
        "platform": platform.platform(),
        "processor": platform.processor(),
        "packages": packages,
        "dependency_source": "PyPI via pip; pinned in requirements-v24t.txt",
        "cuda_status": command_output(
            ["nvidia-smi", "--query-gpu=name,driver_version", "--format=csv,noheader"]
        ),
        "cpu_count": os.cpu_count(),
    }


def git_output(repo: Path, *args: str) -> str:
    """Return required Git output, raising if the repository is unavailable."""
    return subprocess.check_output(
        ["git", *args], cwd=repo, text=True, stderr=subprocess.STDOUT
    ).strip()
