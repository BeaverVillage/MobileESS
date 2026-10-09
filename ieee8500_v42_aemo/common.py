import csv
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "docs/ieee8500_v42_aemo_voltage_rebuild"
DATA = ROOT / "ieee8500_v42_aemo/data"
PR193 = ROOT / "docs/ieee8500_v42_single_case"
MAPPING = PR193 / "joint_selection_v3/score_selection/JOINT_SERVICE_MAPPING.csv"
DAY = "2025-05-01"
PR193_SHA = "7d2253c1c9cd6db0720e5930692e55352141a878"
LATEST_SHA = "625bbcb8b9a54a00c1660c26d96f7737c2f75457"
PR62_SHA = "cf6d0c86c877e73db09e09eec903f176486d2df1"
MAPPING_SHA = "4a70fd13bf08c8512d30f74e48dfafb46fdddd4e112a3aee92a8191f22cad016"
BG_SCALE = 0.552


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def write(path, value):
    path = Path(path)
    assert path.resolve().is_relative_to(ROOT), "EXTERNAL_WRITES_FORBIDDEN"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def table(path, rows):
    rows = list(rows)
    assert rows, "EMPTY_AUDIT_TABLE"
    path = Path(path)
    assert path.resolve().is_relative_to(ROOT)
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(dict.fromkeys(k for row in rows for k in row))
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def rows(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def receipt(path):
    path = Path(path)
    return {"path": str(path.resolve()), "sha256": sha(path), "bytes": path.stat().st_size}


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT)


def resolve(record):
    from v42_capacity.common import resolve as original_resolve
    return original_resolve(record)
