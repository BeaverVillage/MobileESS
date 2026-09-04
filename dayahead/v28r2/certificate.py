"""Canonical, disk-recomputed V28R2 certificate primitives."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Mapping

from .backend_contract import canonical_sha256, sha256_file
from .day_state import atomic_json


PLACEHOLDER_TOKENS = ("BOUND_IN_", "RECORDED_IN_", "V28_FINAL_LIGHTGBM_SHA256", "PLACEHOLDER")


def _reject_placeholders(value: object) -> None:
    if isinstance(value, str) and any(token in value for token in PLACEHOLDER_TOKENS):
        raise ValueError(f"V28R2_CERTIFICATE_PLACEHOLDER:{value}")
    if isinstance(value, Mapping):
        for key, item in value.items():
            _reject_placeholders(key)
            _reject_placeholders(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _reject_placeholders(item)


def file_references(paths: Mapping[str, Path]) -> dict[str, dict[str, object]]:
    result = {}
    for name, path in sorted(paths.items()):
        if not path.is_file():
            raise FileNotFoundError(f"V28R2_CERTIFICATE_REFERENCE_MISSING:{name}:{path}")
        result[name] = {
            "path": str(path.resolve()),
            "sha256": sha256_file(path),
            "bytes": path.stat().st_size,
        }
    return result


def _verify_embedded_file_manifest(path: Path) -> None:
    if path.suffix.lower() != ".json":
        return
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    if "code_tree_sha256" in payload:
        return
    files = payload.get("files")
    if isinstance(files, dict):
        for name, record in files.items():
            if not isinstance(record, dict) or "sha256" not in record:
                raise RuntimeError(f"V28R2_EMBEDDED_MANIFEST_SCHEMA:{path}:{name}")
            child = Path(str(record.get("path", path.parent / name)))
            if not child.is_file():
                child = path.parent / Path(str(name)).name
            if not child.is_file() or sha256_file(child) != record["sha256"]:
                raise RuntimeError(f"V28R2_EMBEDDED_MANIFEST_TAMPER:{path}:{name}")


def _verify_code_tree(payload: Mapping[str, object], references: Mapping[str, object]) -> None:
    repo_text = payload.get("repository_root")
    commit = payload.get("git_head")
    record = references.get("code_tree_manifest")
    if not isinstance(repo_text, str) or not isinstance(commit, str) or not isinstance(record, dict):
        return
    repo = Path(repo_text)
    manifest = json.loads(Path(str(record["path"])).read_text(encoding="utf-8"))
    files = manifest.get("files")
    if not isinstance(files, dict) or manifest.get("code_tree_sha256") != canonical_sha256(files):
        raise RuntimeError("V28R2_CODE_TREE_MANIFEST_SHA")
    subprocess.run(["git", "cat-file", "-e", f"{commit}^{{commit}}"], cwd=repo, check=True, capture_output=True)
    for relative, expected in files.items():
        content = subprocess.check_output(["git", "show", f"{commit}:{relative}"], cwd=repo)
        if hashlib.sha256(content).hexdigest() != expected:
            raise RuntimeError(f"V28R2_CODE_TREE_COMMIT_MISMATCH:{relative}")


def certificate_digest(payload: dict[str, object]) -> str:
    unsigned = {key: value for key, value in payload.items() if key != "certificate_sha256"}
    return canonical_sha256(unsigned)


def write_certificate(path: Path, payload: dict[str, object]) -> None:
    if "certificate_sha256" in payload:
        raise ValueError("V28R2_CERTIFICATE_CALLER_SUPPLIED_DIGEST")
    _reject_placeholders(payload)
    signed = dict(payload)
    signed["certificate_sha256"] = certificate_digest(signed)
    atomic_json(path, signed)


def verify_certificate(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    _reject_placeholders(payload)
    if payload.get("certificate_sha256") != certificate_digest(payload):
        raise RuntimeError("V28R2_CERTIFICATE_SHA_MISMATCH")
    references = payload.get("references")
    if references is not None:
        if not isinstance(references, dict) or not references:
            raise RuntimeError("V28R2_CERTIFICATE_REFERENCE_AXIS")
        for name, record in references.items():
            if not isinstance(record, dict) or set(record) != {"path", "sha256", "bytes"}:
                raise RuntimeError(f"V28R2_CERTIFICATE_REFERENCE_SCHEMA:{name}")
            reference = Path(str(record["path"]))
            if (
                not reference.is_file()
                or sha256_file(reference) != record["sha256"]
                or reference.stat().st_size != record["bytes"]
            ):
                raise RuntimeError(f"V28R2_CERTIFICATE_REFERENCE_TAMPER:{name}")
            _verify_embedded_file_manifest(reference)
        source = references.get("source_day_manifest")
        if isinstance(source, dict):
            from .source_manifest import verify_day_manifest

            source_path = Path(str(source["path"]))
            verify_day_manifest(json.loads(source_path.read_text(encoding="utf-8")), base_dir=source_path.parent)
        _verify_code_tree(payload, references)
    return payload
