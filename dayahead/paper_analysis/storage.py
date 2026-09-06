"""Atomic, precision-preserving storage shared by offline paper/Actual outputs."""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import tempfile

SCHEMA = "PAPER_ANALYSIS_SAVED_DATA_SCHEMA_V1"
MISSING = "MISSING_NOT_RECORDED"
STAGES = {"A0": "A1", "M1": "M1", "A1": "A2", "MF": "M2"}


def canonical(value):
    def convert(x):
        if hasattr(x, "tolist"):
            return x.tolist()
        if hasattr(x, "item"):
            return x.item()
        if isinstance(x, Path):
            return str(x)
        if hasattr(x, "isoformat"):
            return x.isoformat()
        raise TypeError(type(x).__name__)
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,
                       separators=(",", ":"), default=convert) + "\n").encode("utf-8")


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


@contextmanager
def atomic(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w+b") as stream:
            yield stream
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def write_json(path, value):
    with atomic(path) as f:
        f.write(canonical(value))


def write_parquet(path, frame):
    with atomic(path) as f:
        frame.to_parquet(f, index=False, compression="zstd")


def write_npz(path, **arrays):
    import numpy as np
    with atomic(path) as f:
        np.savez_compressed(f, **arrays)


def reference(path):
    p = Path(path).resolve()
    return {"path": str(p), "sha256": sha(p), "bytes": p.stat().st_size}


def seal(root, required, *, missing=(), metadata=None):
    """A complete write with explicitly absent historical fields is PARTIAL, never PASS."""
    root = Path(root)
    absent = [name for name in required if not (root / name).is_file()]
    if absent:
        write_json(root / "PERSISTENCE_STATUS.json", {
            "status": "RESULT_PERSISTENCE_FAIL", "absent_artifacts": absent})
        raise RuntimeError("RESULT_PERSISTENCE_FAIL:" + ",".join(absent))
    files = {p.relative_to(root).as_posix(): reference(p) for p in sorted(root.rglob("*"))
             if p.is_file() and p.name != "PERSISTENCE_STATUS.json" and not p.name.endswith(".tmp")}
    value = {"schema_id": SCHEMA, "status": "PARTIAL_HISTORICAL" if missing else "PASS",
             "missing_fields": list(missing), "files": files, **(metadata or {})}
    write_json(root / "PERSISTENCE_STATUS.json", value)
    return value


def verify_seal(root):
    root = Path(root)
    value = read(root / "PERSISTENCE_STATUS.json")
    if value["status"] not in ("PASS", "PARTIAL_HISTORICAL"):
        raise RuntimeError("RESULT_PERSISTENCE_FAIL")
    for name, item in value["files"].items():
        if sha(root / name) != item["sha256"]:
            raise RuntimeError("RESULT_PERSISTENCE_HASH_MISMATCH:" + name)
    return value
