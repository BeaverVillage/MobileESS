"""Reproduce strict QoS coverage and separately labeled PR75 proxy statistics."""
from pathlib import Path
import argparse
import csv
import gzip
import hashlib
import json
import time

from .qos import TrainingStatistics, TRAIN_CUTOFF


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def materialize(source, output, *, provenance_files=()):
    source, output = Path(source), Path(output)
    output.mkdir(parents=True, exist_ok=True)
    before = sha(source)
    started = time.perf_counter()
    def records():
        with gzip.open(source, "rt", encoding="utf-8-sig", newline="") as stream:
            yield from csv.DictReader(stream)
    strict = TrainingStatistics.from_records(records(), source_sha=before)
    proxy = TrainingStatistics.from_records(records(), source_sha=before, descriptive_only=True)
    if sha(source) != before:
        raise ValueError("FROZEN_TRAIN_SOURCE_CHANGED")
    source_receipt = dict(path=str(source.resolve()), sha256=before, bytes=source.stat().st_size)
    files = [dict(path=str(Path(p).resolve()), sha256=sha(p), bytes=Path(p).stat().st_size)
             for p in provenance_files]
    evidence = dict(policy_id="EMPIRICAL_QOS_Q90_REFERENCE_SLACK_V1", cutoff=TRAIN_CUTOFF,
        source=source_receipt, provenance_sources=files, strict=strict.to_dict(include_uids=True),
        descriptive_proxy=proxy.to_dict(), issuer_uses="STRICT_ONLY",
        historical_request_versions="UNVERIFIED_IN_PR75_LEAKAGE_AUDIT",
        source_has_observation_timestamp=False, source_has_request_provenance=False,
        research_proxy_is_not_customer_SLA=True, May_used_for_thresholds=False,
        model_training_calls=0, solver_calls=0, wall_seconds=time.perf_counter()-started,
        status="UNSUPPORTED_AUTHORITY_COVERAGE" if not strict.accepted_uids else "SUPPORTED_STRICT_COHORTS")
    for name, value in (("QOS_EMPIRICAL_STATS.json", evidence),
                        ("QOS_EMPIRICAL_STATS_STRICT.json", strict.to_dict(include_uids=True)),
                        ("QOS_EMPIRICAL_STATS_DESCRIPTIVE_PROXY.json", proxy.to_dict())):
        (output/name).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    return evidence


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--provenance", action="append", default=[])
    args = parser.parse_args()
    result = materialize(args.source, args.output, provenance_files=args.provenance)
    print(json.dumps(dict(status=result["status"], strict_unique=result["strict"]["accepted_unique_uids"],
                          descriptive_unique=result["descriptive_proxy"]["accepted_unique_uids"],
                          wall_seconds=result["wall_seconds"], solver_calls=0)))


if __name__ == "__main__":
    main()
