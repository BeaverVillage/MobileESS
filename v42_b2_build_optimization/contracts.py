"""Small deterministic identities for immutable source-input reuse."""
import hashlib
import json
import re


def require(value, message):
    if not value:
        raise ValueError(message)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def require_sha(value):
    require(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None, "SHA256_REQUIRED")
