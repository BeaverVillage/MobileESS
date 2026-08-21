"""Build a source-hashed H100 utilization-power envelope without throughput claims."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import statistics
import zipfile


BINS = (0.0, 0.25, 0.5, 0.75, 1.0)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def quantile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    if not ordered:
        raise RuntimeError("empty utilization bin")
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def build(source: Path) -> dict:
    bins: list[list[float]] = [[] for _ in BINS]
    members = []
    unique_member_hashes: set[str] = set()
    row_count = 0
    with zipfile.ZipFile(source) as archive:
        names = sorted(
            name for name in archive.namelist()
            if name.lower().endswith(".csv") and "/h100/" in name.lower()
        )
        if not names:
            raise RuntimeError("no H100 CSV members found")
        for name in names:
            payload = archive.read(name)
            member_sha256 = sha256_bytes(payload)
            included = member_sha256 not in unique_member_hashes
            members.append({
                "path": name,
                "sha256": member_sha256,
                "bytes": len(payload),
                "included_in_statistics": included,
            })
            if not included:
                continue
            unique_member_hashes.add(member_sha256)
            reader = csv.DictReader(io.StringIO(payload.decode("utf-8-sig")))
            required = {
                *(f"gpu{i}_utilization_percent" for i in range(8)),
                *(f"gpu{i}_power_W" for i in range(8)),
            }
            if not required.issubset(reader.fieldnames or ()):
                raise RuntimeError(f"H100 member schema missing utilization/power fields: {name}")
            for row in reader:
                util = sum(float(row[f"gpu{i}_utilization_percent"]) for i in range(8)) / 800.0
                power = sum(float(row[f"gpu{i}_power_W"]) for i in range(8)) / 8.0 / 1000.0
                if not 0.0 <= util <= 1.0 or power < 0.0:
                    raise RuntimeError("measured utilization or power lies outside physical domain")
                index = min(range(len(BINS)), key=lambda i: abs(util - BINS[i]))
                bins[index].append(power)
                row_count += 1
    raw_median = [statistics.median(values) for values in bins]
    raw_p95 = [quantile(values, 0.95) for values in bins]
    envelope = []
    for value in raw_p95:
        envelope.append(max(value, envelope[-1] if envelope else 0.0))
    return {
        "stage": "PFR9_PREPARATION",
        "status": "PASS",
        "gpu_type": "H100",
        "source_sha256": sha256_file(source),
        "source_members": members,
        "h100_path_member_count": len(members),
        "h100_unique_content_member_count": len(unique_member_hashes),
        "duplicate_path_member_count": len(members) - len(unique_member_hashes),
        "duplicate_content_weighting": False,
        "measured_row_count": row_count,
        "utilization_fraction": list(BINS),
        "raw_per_gpu_power_kw_median": raw_median,
        "raw_per_gpu_power_kw_p95": raw_p95,
        "per_gpu_power_kw_p95_envelope": envelope,
        "curve_interpolation": "piecewise_linear",
        "work_fraction_semantics": "NORMALIZED_FULL_UTILIZATION_H100_EQUIVALENT_NOT_MEASURED_THROUGHPUT",
        "optimizer_role": "power mapping for normalized compute-rate fraction",
        "prohibited_claims": ["FLOP throughput", "token throughput", "measured checkpoint behavior"],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build(args.source)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "rows": result["measured_row_count"], "output": str(args.output)}))


if __name__ == "__main__":
    main()
