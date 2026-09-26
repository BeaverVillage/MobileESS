"""Request-state authority audit and fail-closed as-of contract.

The supplied accounting extract is NOT an authenticated request-version log.
This module does not infer request availability from submit_time, fit a model,
or create a real feature matrix. Its CLI reads schemas/provenance only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import zipfile
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parent
BASE = ROOT.parent / "cc4_v2_hourly_future_workload"
EXPECTED_RAW_SHA256 = "3a90f9ac40991712f8718c686fa7b05d7a303a44a87ed1a8f21b403c11efd26f"
REQUEST_FIELDS = ["gpus_requested", "wallclock_req", "partition", "qos"]
AUTHORITY_COLUMNS = ["request_version_id", "request_effective_at", "request_observed_at"]
REQUIRED_ATTESTATIONS = [
    "original_submission_identity_verified",
    "request_version_history_complete",
    "request_effective_times_verified",
    "request_observed_times_verified",
    "source_capture_provenance_verified",
]


class RequestStateAuthorityError(RuntimeError):
    """A requested feature cannot be assigned a justified historical time."""


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def source_record(path, purpose):
    path = Path(path).resolve()
    return dict(path=str(path), sha256=sha(path), bytes=path.stat().st_size, purpose=purpose)


def require_request_state_authority(audit):
    """Only an independently audited complete version log may pass this gate.

    Column presence, a field called 'requested', issue-stamped reconstructions,
    and successful audits of hashes do not constitute as-of authority.
    """
    if audit.get("REQUEST_STATE_AUTHORITY_VERIFIED") is not True:
        raise RequestStateAuthorityError("BLOCKED_AUTHORITY: request-state version/effective/observed times are unverified")
    if audit.get("status") != "VERIFIED_ASOF_REQUEST_VERSIONS":
        raise RequestStateAuthorityError("BLOCKED_AUTHORITY: unsupported source authority status")
    attested = audit.get("attestations", {})
    missing = [name for name in REQUIRED_ATTESTATIONS if attested.get(name) is not True]
    if missing or not audit.get("verified_source_manifest_sha256"):
        raise RequestStateAuthorityError("BLOCKED_AUTHORITY: incomplete audited capture/version provenance: " + ", ".join(missing))
    return True


def verified_request_state_at_issue(versions, issue_time, authority_audit):
    """Reusable selection contract for a future authenticated version source.

    Only synthetic tests exercise its positive path in this study. Actual raw
    rows fail the authority gate before any requested values are consumed.
    No timestamp is filled from another timestamp. Effective and observed
    times must both be no later than issue, and future submissions are absent.
    """
    require_request_state_authority(authority_audit)
    needed = ["id", "submit_time", *REQUEST_FIELDS, *AUTHORITY_COLUMNS]
    missing = [name for name in needed if name not in versions.columns]
    if missing:
        raise RequestStateAuthorityError("MISSING_REQUEST_AUTHORITY_COLUMNS: " + ", ".join(missing))
    frame = versions[needed].copy()
    if frame[needed].isna().any().any():
        raise RequestStateAuthorityError("UNKNOWN_REQUEST_VALUE_OR_VERSION_TIME")
    cutoff = pd.Timestamp(issue_time)
    if cutoff.tzinfo is None:
        raise RequestStateAuthorityError("ISSUE_TIMEZONE_UNKNOWN")
    cutoff = cutoff.tz_convert("UTC")
    for name in ["submit_time", "request_effective_at", "request_observed_at"]:
        parsed = []
        for value in frame[name]:
            timestamp = pd.Timestamp(value)
            if pd.isna(timestamp) or timestamp.tzinfo is None:
                raise RequestStateAuthorityError("UNKNOWN_OR_NAIVE_VERSION_TIME: " + name)
            parsed.append(timestamp.tz_convert("UTC"))
        frame[name] = pd.DatetimeIndex(parsed)
    if frame.duplicated(["id", "request_version_id"]).any():
        raise RequestStateAuthorityError("AMBIGUOUS_REQUEST_VERSION_ID")
    if frame.duplicated(["id", "request_effective_at", "request_observed_at"]).any():
        raise RequestStateAuthorityError("AMBIGUOUS_REQUEST_VERSION_ORDER")
    available = (frame.submit_time <= cutoff) & (frame.request_effective_at <= cutoff) & (frame.request_observed_at <= cutoff)
    observed = frame[available].sort_values(["id", "request_effective_at", "request_observed_at"])
    return observed.drop_duplicates("id", keep="last").reset_index(drop=True)


def inventory_archive(raw_path):
    """Read every Parquet footer/schema; never materialize request/outcome rows."""
    partitions = []
    with zipfile.ZipFile(raw_path) as archive:
        names = sorted(name for name in archive.namelist() if name.endswith(".parquet"))
        other_files = sorted(name for name in archive.namelist() if not name.endswith("/") and not name.endswith(".parquet"))
        for name in names:
            with archive.open(name) as stream:
                parquet = pq.ParquetFile(stream)
                schema = parquet.schema_arrow
                fields = {field.name: str(field.type) for field in schema}
                metadata = parquet.metadata.metadata or {}
                provenance_fields = [field for field in fields if re.search(r"observ|ingest|snapshot|version|effective|valid_from|valid_to|modified|updated|restart|requeue", field, re.I)]
                partitions.append(dict(
                    member=name, rows=parquet.metadata.num_rows, row_groups=parquet.metadata.num_row_groups,
                    columns=fields, field_metadata_present=any(bool(field.metadata) for field in schema),
                    file_metadata_keys=sorted(key.decode("utf-8", errors="replace") for key in metadata),
                    provenance_field_candidates=provenance_fields,
                    missing_authority_columns=[field for field in AUTHORITY_COLUMNS if field not in fields],
                    schema_sha256=hashlib.sha256(schema.serialize().to_pybytes()).hexdigest(),
                ))
    require(partitions, "NO_PARQUET_AUTHORITY")
    return dict(partitions=partitions, parquet_partitions=len(partitions), total_rows=sum(row["rows"] for row in partitions),
                nonparquet_files=other_files, data_rows_read=0, outcome_metrics_computed=False)


def snapshot_inventory(snapshot_root):
    """Read only provenance keys and input Parquet schemas in the 31 B0 snapshots."""
    records, sources = [], []
    for path in sorted(Path(snapshot_root).glob("2025-05-*/B0/dayahead/ml/ML_SNAPSHOT.json")):
        snapshot = read_json(path)
        row = dict(path=str(path.resolve()), sha256=sha(path), schema=snapshot.get("schema"),
                   issue_time=snapshot.get("issue_time"),
                   original_submission_provenance_verified=snapshot.get("original_submission_provenance_verified"),
                   provenance_assumption=snapshot.get("provenance_assumption"))
        reference = snapshot.get("input_authority", {}).get("pending_features_source", {})
        table = Path(reference.get("path", "__MISSING__"))
        if table.is_file():
            digest = sha(table)
            require(digest == reference.get("sha256"), "FROZEN_SNAPSHOT_INPUT_DRIFT")
            schema = pq.ParquetFile(table).schema_arrow
            names = schema.names
            row["pending_feature_source"] = dict(path=str(table.resolve()), sha256=digest,
                                                  columns={field.name: str(field.type) for field in schema},
                                                  missing_authority_columns=[field for field in AUTHORITY_COLUMNS if field not in names])
            sources.append(source_record(table, "Frozen retrospective Pending feature table; schema inspected only"))
        else:
            row["pending_feature_source"] = dict(status="NOT_PRESENT", recorded_path=str(table))
        records.append(row)
        sources.append(source_record(path, "Frozen ML snapshot provenance fields only; no prediction or outcome arrays inspected"))
    return records, sources


def make_authority_audit(base=BASE, snapshot_root=None, runtime_root=None):
    base = Path(base)
    authority = read_json(base / "SOURCE_MANIFEST.json")
    raw_source = next(row for row in authority["sources"] if row["purpose"] == "raw Job authority, all parquet partitions")
    raw_path = Path(raw_source["path"])
    require(sha(raw_path) == raw_source["sha256"] == EXPECTED_RAW_SHA256, "RAW_ARCHIVE_HASH_DRIFT")
    datacard = raw_path.parent / "datacard.md"
    document = datacard.read_text(encoding="utf-8")
    # These establish provenance of this particular local authority. They do
    # not promote prose descriptions into field-level availability evidence.
    required_document_clauses = ["periodically running", "sacct", "Raw Slurm", "JSONB", "not publicly released"]
    require(all(clause in document for clause in required_document_clauses), "DATACARD_CONTRACT_CHANGED_REVIEW_REQUIRED")
    schema_inventory = inventory_archive(raw_path)
    paths = [source_record(raw_path, "Exact inherited accounting archive; hash verified"),
             source_record(datacard, "NLR dataset datacard; periodic accounting collection and omitted internal/raw sources"),
             source_record(base / "SOURCE_MANIFEST.json", "PR63 immutable raw-source authority"),
             source_record(base / "FEATURE_CONTRACT.json", "Existing logical event-time limitation")]
    snapshots, snapshot_sources = snapshot_inventory(snapshot_root) if snapshot_root is not None else ([], [])
    paths.extend(snapshot_sources)
    runtime = {}
    if runtime_root is not None:
        runtime_root = Path(runtime_root)
        protocol_path = runtime_root / "PROTOCOL.json"
        protocol = read_json(protocol_path)
        runtime = {name: protocol.get(name) for name in ["feature_version_provenance", "optional_survival"]}
        paths.append(source_record(protocol_path, "Runtime-vNext explicit unverified request-version provenance"))
        for name in ["README.md", "INTERPRETATION_CONTRACT.md"]:
            paths.append(source_record(runtime_root / name, "Runtime authority limitations reviewed; no model execution"))
    columns = sorted(set().union(*(set(row["columns"]) for row in schema_inventory["partitions"])))
    requested = {field: dict(present_partitions=sum(field in row["columns"] for row in schema_inventory["partitions"]),
                             arrow_types=sorted({row["columns"][field] for row in schema_inventory["partitions"] if field in row["columns"]}),
                             submission_time_value_proven=False, feature_available_time=None)
                 for field in ["submit_time", *REQUEST_FIELDS]}
    candidates = sorted(set().union(*(set(row["provenance_field_candidates"]) for row in schema_inventory["partitions"])))
    # A changed schema may require another source-specific audit, never an
    # automatic approval merely because a plausibly named column appears.
    findings = [
        "The archive is a parent-job accounting extract collected periodically with sacct, not a declared immutable submission-event log.",
        "Requested GPU/walltime/partition/QoS columns exist, but their original submission values and subsequent version histories are not established.",
        "No row-level request version, effective timestamp, or collector observation timestamp is supplied in the audited raw schemas.",
        "The datacard excludes raw Slurm JSONB and job-step tables and states the internal loading/preprocessing functions are unavailable.",
        "An issue_time on a retrospective generated snapshot does not establish when the scheduler originally exposed each request value.",
        "Previously frozen request-state proxies explicitly do not verify original submission provenance; their labels and hashes cannot repair missing acquisition/version authority.",
        "All-job submit-count features inherited from PR69 retain their previous event-time proxy limitation; they are not new proof of request-state availability.",
    ]
    audit = dict(
        time=pd.Timestamp.now(tz="UTC").isoformat(), PASS=True, REQUEST_STATE_AUTHORITY_VERIFIED=False,
        status="BLOCKED_AUTHORITY", performance_stop_rule="NOT_EVALUABLE", feature_matrix_created=False,
        model_fitting_performed=False, threshold_changed=False, target_changed=False,
        columns=columns, field_assessment=requested,
        missing_authority=AUTHORITY_COLUMNS + ["original_submission_event_or_requeue_identity", "complete_request_change_history", "collector_capture_provenance"],
        source_provenance_column_candidates=candidates, findings=findings,
        next_required_authority="Authenticated original submission events plus complete request changes with per-version effective and observed times, or independently validated immutable submission fields with capture provenance; no submit-time imputation of unknown availability.",
        raw_archive=dict(path=str(raw_path.resolve()), sha256=EXPECTED_RAW_SHA256, bytes=raw_path.stat().st_size),
        datacard=dict(path=str(datacard.resolve()), sha256=sha(datacard), url="https://data.nlr.gov/submissions/302"),
        sourcehashes=paths, partition_count=schema_inventory["parquet_partitions"], total_schema_rows=schema_inventory["total_rows"],
        partition_schema_inventory="REQUEST_STATE_SCHEMA_INVENTORY.json",
        historical_snapshot_count=len(snapshots), historical_snapshot_inventory=snapshots,
        historical_snapshots_with_verified_original_submission=sum(row["original_submission_provenance_verified"] is True for row in snapshots),
        runtime_authority_declarations=runtime,
        primary_documentation=[
            dict(url="https://slurm.schedmd.com/scontrol.html", section="JOBS - SPECIFICATIONS FOR UPDATE COMMAND / TimeLimit",
                 finding="Official Slurm documentation permits changing a job time limit; this establishes mutability risk, not that any particular archived job was changed."),
            dict(url="https://slurm.schedmd.com/sacct.html", section="Submit",
                 finding="Official sacct documentation says requeue resets Submit and obtaining the original requires duplicate records; the extract provides no certified original-event reconstruction."),
        ],
        documentation_scope="Online command documentation consulted as a general risk explanation, not proof of the historical cluster version or actual per-job changes.",
        inspected_data_scope="All raw Parquet schemas/footers and narrow stored provenance metadata; no raw request/outcome row values used for feature/model decisions.",
        script_sha256=sha(Path(__file__)),
    )
    return audit, schema_inventory


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", type=Path, default=BASE)
    parser.add_argument("--snapshot-root", type=Path, default=Path("D:/ChatGPT/Mobile ESS 2/CC4_FORENSIC_20260922/evidence/V41R4_May2025_raw/frozen_artifacts/v41r4_may/loop_wall_v4"))
    parser.add_argument("--runtime-root", type=Path, default=Path("D:/ChatGPT/Mobile ESS 2/runtime_vnext_causal_tail_pr/docs/runtime_vnext_causal_tail"))
    parser.add_argument("--output", type=Path, default=ROOT)
    args = parser.parse_args()
    audit_path = args.output / "REQUEST_STATE_AUTHORITY_AUDIT.json"
    inventory_path = args.output / "REQUEST_STATE_SCHEMA_INVENTORY.json"
    require(not audit_path.exists() and not inventory_path.exists(), "IMMUTABLE_AUTHORITY_AUDIT_EXISTS")
    audit, inventory = make_authority_audit(args.base, args.snapshot_root, args.runtime_root)
    args.output.mkdir(parents=True, exist_ok=True)
    with inventory_path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(inventory, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    audit["partition_schema_inventory_sha256"] = sha(inventory_path)
    with audit_path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(audit, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps(dict(PASS=True, REQUEST_STATE_AUTHORITY_VERIFIED=False, status=audit["status"],
                          partitions=audit["partition_count"], snapshots=audit["historical_snapshot_count"],
                          real_feature_matrix_created=False)), flush=True)


if __name__ == "__main__":
    main()
