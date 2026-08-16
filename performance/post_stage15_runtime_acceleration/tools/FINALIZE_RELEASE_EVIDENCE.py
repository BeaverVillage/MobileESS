#!/usr/bin/env python3
"""Freeze package, exact patch, and release SHA manifests without running science."""
from __future__ import annotations

import argparse
import hashlib
import subprocess
from pathlib import Path


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def regular_files(root: Path, excluded: set[Path]) -> list[Path]:
    return sorted(
        path for path in root.rglob("*")
        if path.is_file()
        and path not in excluded
        and "__pycache__" not in path.parts
        and path.suffix != ".pyc"
    )


def write_manifest(path: Path, files: list[Path], relative_to: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "".join(f"{digest(item)}  {item.relative_to(relative_to).as_posix()}\n" for item in files)
    path.write_text(text, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--mode", choices=("prepare", "finalize"), required=True)
    args = parser.parse_args()
    repo = Path(args.repo).resolve()
    root = repo / "performance/post_stage15_runtime_acceleration"
    package = root / "package"
    package_manifest = package / "SHA256SUMS.txt"
    write_manifest(package_manifest, regular_files(package, {package_manifest}), package)
    if args.mode == "prepare":
        print(f"PACKAGE_SHA256SUMS={package_manifest}")
        return 0

    patch_path = root / "PERFORMANCE_RESULT/FINAL/EXACT_SOURCE_PATCH.diff"
    patch = subprocess.check_output([
        "git", "-C", str(repo), "diff", "--cached", "--binary",
        "06a94bccc0a232ae7ea09cbc7b00962162c10f4d", "--",
        "science/main.py", "performance/post_stage15_runtime_acceleration",
        ":(exclude)performance/post_stage15_runtime_acceleration/PERFORMANCE_RESULT/FINAL/EXACT_SOURCE_PATCH.diff",
        ":(exclude)performance/post_stage15_runtime_acceleration/PERFORMANCE_RESULT/FINAL/FINAL_SHA256SUMS.txt",
        ":(exclude)performance/post_stage15_runtime_acceleration/SHA256SUMS.txt",
    ])
    if not patch:
        raise RuntimeError("staged source patch is empty")
    patch_path.write_bytes(patch)

    root_manifest = root / "SHA256SUMS.txt"
    final_manifest = root / "PERFORMANCE_RESULT/FINAL/FINAL_SHA256SUMS.txt"
    excluded = {root_manifest, final_manifest}
    write_manifest(root_manifest, regular_files(root, excluded), root)
    final_files = regular_files(final_manifest.parent, {final_manifest}) + [
        root_manifest,
        package / "A_TO_B_10_W02_4POLICY_PRODUCTION_BINDING.json",
        package / "STATIC_VALIDATION.json",
    ]
    write_manifest(final_manifest, sorted(set(final_files)), root)
    print(f"EXACT_SOURCE_PATCH={patch_path}")
    print(f"ROOT_SHA256SUMS={root_manifest}")
    print(f"FINAL_SHA256SUMS={final_manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
