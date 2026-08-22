"""Stable source identity for January scientific-result reuse."""

from __future__ import annotations

import hashlib
from pathlib import Path


def scientific_implementation_files(repo: Path) -> tuple[Path, ...]:
    repo = repo.resolve()
    files = sorted((repo / "pfr").glob("*.py"))
    files.append(repo / "pfr" / "tools" / "run_pfr_matrix.py")
    missing = [path for path in files if not path.is_file()]
    if missing:
        raise RuntimeError(f"scientific implementation source is missing: {missing}")
    return tuple(files)


def scientific_implementation_fingerprint(repo: Path) -> str:
    repo = repo.resolve()
    digest = hashlib.sha256()
    for path in scientific_implementation_files(repo):
        relative = path.relative_to(repo).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(8 << 20), b""):
                digest.update(block)
    return digest.hexdigest()
