"""Canonical certificate hashing primitives; production binding is added later."""

from __future__ import annotations

import json
from pathlib import Path

from .backend_contract import canonical_sha256
from .day_state import atomic_json


def certificate_digest(payload: dict[str, object]) -> str:
    unsigned = {key: value for key, value in payload.items() if key != "certificate_sha256"}
    return canonical_sha256(unsigned)


def write_certificate(path: Path, payload: dict[str, object]) -> None:
    if "certificate_sha256" in payload:
        raise ValueError("V28R2_CERTIFICATE_CALLER_SUPPLIED_DIGEST")
    signed = dict(payload)
    signed["certificate_sha256"] = certificate_digest(signed)
    atomic_json(path, signed)


def verify_certificate(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("certificate_sha256") != certificate_digest(payload):
        raise RuntimeError("V28R2_CERTIFICATE_SHA_MISMATCH")
    return payload

