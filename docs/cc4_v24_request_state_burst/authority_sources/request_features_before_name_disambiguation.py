"""Request-state authority audit, strict contract and explicitly authorized proxy.

The supplied accounting extract is NOT an authenticated request-version log.
The strict verified-source path still rejects that extract. An explicit user
authorization permits a separately labeled offline request-state proxy, using
archive request values at submit event time without claiming version accuracy.
No model is fitted and no future completion field is loaded in either path.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import zipfile
from pathlib import Path

import numpy as np
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


PROXY_ID = "D1_SCHEDULER_REQUEST_STATE_PROXY_V1"
REQUEST_INPUT_COLUMNS = ["id", "submit_time", "gpus_requested", "wallclock_req", "partition", "qos"]
TZ = "Etc/GMT-10"
HALFHOUR_NS = 1_800_000_000_000
DAY_NS = 86_400_000_000_000
COUNT_FIELDS = ["jobs", "gpu_missing", "gpu_invalid", "cpu_zero", "gpu_positive", "gpu_1", "gpu_2to3", "gpu_ge4",
                "wall_missing", "wall_invalid", "wall_zero", "wall_gt4h_all", "gpu_wall_known", "gpu_wall_unknown", "gpu_wall_gt4h", "large_gpu_long_wall"]
MOMENT_FIELDS = [prefix + suffix for prefix in ["gpu", "wall", "product"] for suffix in ["_sum", "_squares", "_maximum"]]


def write_once_json(path, value):
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write("\n")


def proxy_authorization(output):
    path = Path(output) / "REQUEST_STATE_PROXY_AUTHORIZATION.json"
    authority_path = Path(output) / "REQUEST_STATE_AUTHORITY_AUDIT.json"
    audit = read_json(authority_path)
    require(audit["REQUEST_STATE_AUTHORITY_VERIFIED"] is False, "AUTHORITY_STATUS_UNEXPECTED")
    record = dict(
        experiment_status="AUTHORIZED_OFFLINE_PROXY", proxy_id=PROXY_ID,
        authorization="User explicitly instructed continuing the offline experiment using the inherited V40S4 D1 scheduler request-state proxy despite absent certified request-version history.",
        REQUEST_STATE_AUTHORITY_VERIFIED=False, request_version_provenance="UNVERIFIED", request_change_history="UNOBSERVED",
        availability_assumption="For submitted archive rows only, requested GPU, walltime, partition and QoS are assumed scheduler-visible request proxies at their recorded submit_time. Actual version/effective/observed times are not certified.",
        no_claims=["historically exact request state", "immutable requests", "zero request changes", "authenticated ingestion at submit time"],
        production_readiness="FAIL_CLOSED", production_promoted=False,
        authority_audit_preserved_sha256=sha(authority_path),
        original_audit_source_sha256=sha(Path(output) / "authority_sources" / "request_features_before_proxy_authorization.py"),
        feature_constants=dict(windows_hours=[6, 12, 24], long_reference_hours=168, large_GPU_inclusive=4,
                               long_walltime_seconds_exclusive=14400, category_vocabulary="TRAIN eligible arrival days only"),
    )
    if path.exists():
        require(read_json(path) == record, "PROXY_AUTHORIZATION_DRIFT")
    else:
        write_once_json(path, record)
    return record


def aggregate_request_rows(rows):
    """Aggregate only the six explicit request-proxy columns; ignore outcomes."""
    require(set(REQUEST_INPUT_COLUMNS).issubset(rows.columns), "REQUEST_PROXY_COLUMNS_MISSING")
    r = rows[REQUEST_INPUT_COLUMNS]
    submit = pd.to_datetime(r.submit_time, utc=True)
    require(submit.notna().all() and r.id.notna().all(), "REQUEST_EVENT_ID_OR_TIME_UNKNOWN")
    gpu = pd.to_numeric(r.gpus_requested, errors="coerce").to_numpy(dtype=float)
    wall = pd.to_timedelta(r.wallclock_req).dt.total_seconds().to_numpy(dtype=float)
    gpu_valid = np.isfinite(gpu) & (gpu >= 0) & (gpu == np.floor(gpu))
    positive = gpu_valid & (gpu > 0)
    wall_valid = np.isfinite(wall) & (wall >= 0)
    joint = positive & wall_valid
    gv = np.where(positive, gpu, 0.0)
    wv = np.where(joint, wall / 3600, 0.0)
    product = np.where(joint, gpu * wall / 3600, 0.0)
    fields = dict(jobs=np.ones(len(r)), gpu_missing=np.isnan(gpu), gpu_invalid=~np.isnan(gpu) & ~gpu_valid,
                  cpu_zero=gpu_valid & (gpu == 0), gpu_positive=positive, gpu_1=positive & (gpu == 1),
                  gpu_2to3=positive & (gpu > 1) & (gpu < 4), gpu_ge4=positive & (gpu >= 4),
                  wall_missing=np.isnan(wall), wall_invalid=~np.isnan(wall) & ~wall_valid,
                  wall_zero=wall_valid & (wall == 0), wall_gt4h_all=wall_valid & (wall > 14400),
                  gpu_wall_known=joint, gpu_wall_unknown=positive & ~wall_valid,
                  gpu_wall_gt4h=joint & (wall > 14400), large_gpu_long_wall=joint & (gpu >= 4) & (wall > 14400))
    for name, value in [("gpu", gv), ("wall", wv), ("product", product)]:
        fields[name + "_sum"] = value
        fields[name + "_squares"] = value ** 2
        fields[name + "_maximum"] = value
    b = pd.DatetimeIndex(submit.dt.floor("30min"))
    frame = pd.DataFrame(fields, index=b).astype(float)
    rules = {name: "max" if name.endswith("_maximum") else "sum" for name in frame.columns}
    grouped = frame.groupby(level=0, sort=True).agg(rules)
    categories = []
    for field in ["partition", "qos"]:
        value = r[field].astype("string").fillna("<MISSING>").to_numpy(dtype=str)
        count = pd.DataFrame({"bin": b, "category": value, "all": 1.0, "gpu": positive.astype(float)})
        for kind in ["all", "gpu"]:
            wide = count.groupby(["bin", "category"], sort=True)[kind].sum().unstack(fill_value=0)
            wide.columns = ["cat::" + field + "::" + kind + "::" + str(name) for name in wide.columns]
            categories.append(wide)
    return pd.concat([grouped, *categories], axis=1).fillna(0.0)


def proxy_feature_vector(bins, issue_time, target_day, vocab):
    """Fixed request features under the authorized submit-event proxy only."""
    issue_time = pd.Timestamp(issue_time).tz_convert("UTC")
    require(issue_time == (pd.Timestamp(str(target_day), tz=TZ) - pd.Timedelta(hours=6)).tz_convert("UTC"), "PROXY_ISSUE_CLOCK")
    # Complete bins end at or before issue. Events exactly at issue belong to
    # its following bin and cannot enter this as-of view.
    history = bins[bins.index + pd.Timedelta(minutes=30) <= issue_time]
    require(len(history) > 0, "NO_ARCHIVED_REQUEST_HISTORY")
    values, names = [], []

    def add(name, value):
        names.append("request_proxy_" + name)
        values.append(np.broadcast_to(np.asarray(value, float), (24,)).copy())

    def section(hours, offset=0):
        end = issue_time - pd.Timedelta(hours=offset)
        begin = end - pd.Timedelta(hours=hours)
        result = history[(history.index >= begin) & (history.index < end)]
        require(len(result) == 2 * hours, "REQUEST_WINDOW_SOURCE_COVERAGE")
        return result

    long = section(168)
    long_rates = {name: float(long[name].sum()) / 168 for name in ["jobs", "gpu_sum", "product_sum"]}
    category_columns = {}
    for field in ["partition", "qos"]:
        for kind in ["all", "gpu"]:
            prefix = "cat::" + field + "::" + kind + "::"
            category_columns[(field, kind)] = [name for name in bins.columns if name.startswith(prefix)]
    for hours in [6, 12, 24]:
        part = section(hours)
        previous = section(hours, hours)
        total = part.sum()
        for name in COUNT_FIELDS:
            add(f"{hours}h_{name}", float(total[name]))
        for name, support_name in [("gpu", "gpu_positive"), ("wall", "gpu_wall_known"), ("product", "gpu_wall_known")]:
            count = float(total[support_name])
            mass = float(total[name + "_sum"])
            mean = mass / count if count else 0.0
            variance = max(0.0, float(total[name + "_squares"]) / count - mean * mean) if count else 0.0
            add(f"{hours}h_{name}_known_sum", mass)
            add(f"{hours}h_{name}_known_mean", mean)
            add(f"{hours}h_{name}_known_variance", variance)
            add(f"{hours}h_{name}_known_maximum", float(part[name + "_maximum"].max()))
            add(f"{hours}h_{name}_support", count)
            add(f"{hours}h_{name}_missing", float(count == 0))
        jobs = float(total.jobs)
        positive = float(total.gpu_positive)
        add(f"{hours}h_GPU_field_known_fraction", float((total.cpu_zero + positive) / jobs) if jobs else 0.0)
        add(f"{hours}h_request_product_known_fraction_of_GPU_jobs", float(total.gpu_wall_known / positive) if positive else 0.0)
        add(f"{hours}h_no_arrivals", float(jobs == 0))
        for field in ["jobs", "gpu_sum", "product_sum"]:
            rate = float(total[field]) / hours
            before = float(previous[field].sum()) / hours
            add(f"{hours}h_{field}_per_hour", rate)
            add(f"{hours}h_{field}_acceleration", rate - before)
            add(f"{hours}h_{field}_to_168h_ratio", rate / long_rates[field] if long_rates[field] > 0 else 0.0)
            add(f"{hours}h_{field}_ratio_valid", float(long_rates[field] > 0))
        prior_jobs = float(previous.jobs.sum())
        prior_gpu = float(previous.gpu_positive.sum())
        add(f"{hours}h_previous_GPU_known_fraction", float((previous.cpu_zero.sum() + prior_gpu) / prior_jobs) if prior_jobs else 0.0)
        add(f"{hours}h_previous_product_known_fraction", float(previous.gpu_wall_known.sum()) / prior_gpu if prior_gpu else 0.0)
        for field in ["partition", "qos"]:
            for kind, denominator in [("all", jobs), ("gpu", positive)]:
                prefix = "cat::" + field + "::" + kind + "::"
                recognized = [prefix + category for category in vocab[field]]
                counts = [float(total.get(name, 0.0)) for name in recognized]
                other = sum(float(total.get(name, 0.0)) for name in category_columns[(field, kind)] if name not in recognized)
                for index, count in enumerate(counts + [other]):
                    add(f"{hours}h_{field}_{kind}_category{index:03d}_count", count)
                    add(f"{hours}h_{field}_{kind}_category{index:03d}_share", count / denominator if denominator else 0.0)
    for field in ["jobs", "gpu_sum", "product_sum"]:
        add(f"168h_{field}_per_hour", long_rates[field])
    add("168h_GPU_field_known_fraction", float((long.cpu_zero.sum() + long.gpu_positive.sum()) / long.jobs.sum()) if long.jobs.sum() else 0.0)
    add("168h_product_known_fraction_of_GPU_jobs", float(long.gpu_wall_known.sum() / long.gpu_positive.sum()) if long.gpu_positive.sum() else 0.0)
    # Causal request intensity, never actual-runtime burst labels. Only fully
    # covered historical clock hours contribute; first partial hour is omitted.
    hour_groups = history.groupby(history.index.floor("h"))
    hourly = hour_groups[["jobs", "gpu_sum", "product_sum", "gpu_positive", "gpu_ge4", "gpu_wall_known", "gpu_wall_gt4h"]].sum()
    hourly = hourly[hour_groups.size().eq(2)]
    local = hourly.index.tz_convert(TZ)
    weekday = pd.Timestamp(str(target_day)).weekday()
    for scope in ["target_hour", "target_weekday", "target_hour_weekday"]:
        arrays = {name: [] for name in ["hours", "jobs_per_hour", "GPU_per_hour", "known_requested_GPUh_per_hour", "large_GPU_fraction", "longwall_GPU_fraction", "GPU_support", "GPU_wall_support"]}
        for hour in range(24):
            mask = np.ones(len(hourly), bool)
            if "hour" in scope:
                mask &= local.hour == hour
            if "weekday" in scope:
                mask &= local.dayofweek == weekday
            h = hourly[mask]
            n = len(h)
            gpu_n = float(h.gpu_positive.sum())
            joint_n = float(h.gpu_wall_known.sum())
            item = [n, float(h.jobs.sum()) / n if n else 0.0, float(h.gpu_sum.sum()) / n if n else 0.0,
                    float(h.product_sum.sum()) / n if n else 0.0,
                    float(h.gpu_ge4.sum()) / gpu_n if gpu_n else 0.0,
                    float(h.gpu_wall_gt4h.sum()) / joint_n if joint_n else 0.0, gpu_n, joint_n]
            for name, value in zip(arrays, item):
                arrays[name].append(value)
        for name, value in arrays.items():
            add(scope + "_" + name, value)
    feature = np.stack(values, axis=1).astype(np.float32)
    require(np.isfinite(feature).all() and len(set(names)) == len(names), "PROXY_FEATURES_NONFINITE_OR_DUPLICATE")
    receipt = dict(target_day=str(target_day), issue_time=issue_time.isoformat(), assumed_feature_available_time=issue_time.isoformat(),
                   availability_authority=PROXY_ID, request_version_provenance="UNVERIFIED", request_changes="UNOBSERVED",
                   windows=[dict(hours=hours, submit_start_inclusive=(issue_time-pd.Timedelta(hours=hours)).isoformat(),
                                 submit_end_exclusive=issue_time.isoformat(), jobs=int(section(hours).jobs.sum()),
                                 positive_GPU_jobs=int(section(hours).gpu_positive.sum())) for hours in [6, 12, 24, 168]],
                   historical_submit_start_inclusive=history.index.min().isoformat(), historical_submit_end_exclusive=issue_time.isoformat(),
                   historical_jobs=int(history.jobs.sum()), exact_source_membership="Filter compressed event indices by the stated submit intervals; each entry records archive member, original row index, job ID and submit timestamp.")
    return feature, names, receipt


def prepare_authorized_proxy(base=BASE, output=ROOT):
    base, output = Path(base), Path(output)
    targets = ["FEATURES.npz", "FEATURE_NAMES.json", "FEATURE_MEMBERSHIP.json", "FEATURE_AVAILABILITY_AUDIT.json", "REQUEST_BINS.parquet", "REQUEST_EVENT_INDEX_MANIFEST.json", "REQUEST_CATEGORY_VOCABULARY.json"]
    require(not any((output / name).exists() for name in targets), "IMMUTABLE_PROXY_FEATURE_OUTPUT_EXISTS")
    authorization = proxy_authorization(output)
    raw_source = next(row for row in read_json(base / "SOURCE_MANIFEST.json")["sources"] if row["purpose"] == "raw Job authority, all parquet partitions")
    raw_path = Path(raw_source["path"])
    require(sha(raw_path) == EXPECTED_RAW_SHA256, "PROXY_RAW_SOURCE_DRIFT")
    ledger = pd.read_csv(base / "DAY_LEDGER.csv")
    issues = pd.to_datetime(ledger.issue_time, utc=True)
    with np.load(base / "DATA.npz", allow_pickle=False) as data:
        original, days = data["X"].copy(), data["days"].astype(str)
    require(np.array_equal(days, ledger.target_day.astype(str)), "BASELINE_DAYS_CHANGED")
    train_days = days[(ledger.split.eq("TRAIN") & ledger.eligible).to_numpy()]
    train_ordinals = np.asarray(train_days, dtype="datetime64[D]").astype(np.int64)
    vocab = {name: {"<MISSING>"} for name in ["partition", "qos"]}
    aggregated, event_sources, train_category_sources = [], [], []
    index_dir = output / "request_event_index"
    index_dir.mkdir(parents=True, exist_ok=True)
    inventory = read_json(output / "REQUEST_STATE_SCHEMA_INVENTORY.json")["partitions"]
    with zipfile.ZipFile(raw_path) as archive:
        for member_index, record in enumerate(inventory):
            member = record["member"]
            # Partition names are not used as submit-time authority. Footer
            # submit statistics only skip wholly future partitions; row masks
            # enforce the actual strict final issue bound after decoding.
            with archive.open(member) as stream:
                parquet = pq.ParquetFile(stream)
                column = parquet.schema_arrow.names.index("submit_time")
                minima = [parquet.metadata.row_group(i).column(column).statistics.min for i in range(parquet.metadata.num_row_groups)
                          if parquet.metadata.row_group(i).column(column).statistics is not None and parquet.metadata.row_group(i).column(column).statistics.has_min_max]
                if minima and len(minima) == parquet.metadata.num_row_groups and min(pd.Timestamp(value).tz_convert("UTC") for value in minima) >= issues.max():
                    continue
                table = parquet.read(columns=REQUEST_INPUT_COLUMNS, use_threads=False).to_pandas()
            submit = pd.to_datetime(table.submit_time, utc=True)
            require(submit.notna().all(), "RAW_SUBMIT_UNKNOWN")
            keep = (submit < issues.max()).to_numpy()
            if not keep.any():
                continue
            source_rows = np.flatnonzero(keep).astype(np.int32)
            rows = table.loc[keep, REQUEST_INPUT_COLUMNS].copy()
            rows["submit_time"] = submit[keep].to_numpy()
            epochs = pd.to_datetime(rows.submit_time, utc=True).astype("int64").to_numpy()
            local_day = (epochs + 36_000_000_000_000) // DAY_NS
            training = np.isin(local_day, train_ordinals)
            for field in vocab:
                vocab[field].update(rows.loc[training, field].astype("string").fillna("<MISSING>").tolist())
            path = index_dir / f"member_{member_index:02d}.npz"
            require(not path.exists(), "EVENT_INDEX_EXISTS")
            np.savez_compressed(path, source_row_index=source_rows, job_id=rows.id.astype(str).to_numpy(dtype="S"), submit_ns=epochs)
            event_sources.append(dict(member=member, member_index=member_index, path=str(path.relative_to(output)),
                                      sha256=sha(path), rows=len(rows), submit_min_ns=int(epochs.min()), submit_max_ns=int(epochs.max())))
            train_category_sources.append(dict(member=member, training_arrival_rows=int(training.sum())))
            aggregated.append(aggregate_request_rows(rows))
            print("REQUEST_SOURCE", member_index, len(rows), flush=True)
    combined = pd.concat(aggregated, axis=0, sort=False).fillna(0.0)
    rules = {name: "max" if name in ["gpu_maximum", "wall_maximum", "product_maximum"] else "sum" for name in combined.columns}
    bins = combined.groupby(level=0, sort=True).agg(rules)
    index = pd.date_range(bins.index.min(), issues.max() - pd.Timedelta(minutes=30), freq="30min")
    bins = bins.reindex(index, fill_value=0.0).sort_index()
    require(bins.index.min() <= issues.min() - pd.Timedelta(days=7), "INSUFFICIENT_REQUEST_HISTORY")
    vocab = {field: sorted(values) for field, values in vocab.items()}
    names_base = read_json(base / "FEATURE_CONTRACT.json")["feature_names"]
    derived, memberships, names_new = [], [], None
    for i, day in enumerate(days):
        features, names, receipt = proxy_feature_vector(bins, issues.iloc[i], day, vocab)
        require(names_new is None or names == names_new, "PROXY_SCHEMA_DRIFT")
        names_new = names
        derived.append(features)
        memberships.append(receipt)
    extended = np.concatenate([original, np.stack(derived)], axis=2)
    require(extended.dtype == np.float32 and np.array_equal(extended[:, :, :71], original), "BASE_FEATURES_CHANGED")
    names = names_base + names_new
    bins.to_parquet(output / "REQUEST_BINS.parquet")
    np.savez_compressed(output / "FEATURES.npz", X=extended, days=days)
    write_once_json(output / "FEATURE_NAMES.json", names)
    write_once_json(output / "FEATURE_MEMBERSHIP.json", memberships)
    write_once_json(output / "REQUEST_EVENT_INDEX_MANIFEST.json", dict(raw_archive_sha256=EXPECTED_RAW_SHA256,
                    source_columns=REQUEST_INPUT_COLUMNS, strict_max_submit_exclusive=issues.max().isoformat(),
                    membership_recipe="Per issue/window select every indexed row where start<=submit_ns<issue; historical intensity uses all indexed earlier rows. Source member and original row index identify exact immutable raw records.",
                    files=event_sources, total_indexed_rows=sum(row["rows"] for row in event_sources)))
    write_once_json(output / "REQUEST_CATEGORY_VOCABULARY.json", dict(vocabulary=vocab, extra_last_category="<OTHER>",
                    training_target_days=train_days.tolist(), training_row_sources=train_category_sources,
                    missing_category="<MISSING> (predeclared support bucket)", future_unseen_category="<OTHER>",
                    selection_rule="Category values from archive rows whose modeled UTC+10 submit day is an eligible TRAIN target day only; no evaluation vocabulary fitting"))
    audit = dict(PASS=True, experiment_status=authorization["experiment_status"], REQUEST_STATE_AUTHORITY_VERIFIED=False,
                 proxy_id=PROXY_ID, request_version_provenance="UNVERIFIED", request_change_history="UNOBSERVED",
                 feature_shape=list(extended.shape), new_feature_count=len(names_new), original_71_exact=True,
                 feature_sha256=sha(output / "FEATURES.npz"), array_sha256=hashlib.sha256(extended.tobytes()).hexdigest(),
                 feature_source_sha256=sha(Path(__file__)), raw_archive_sha256=EXPECTED_RAW_SHA256,
                 source_columns=REQUEST_INPUT_COLUMNS, future_completion_fields_loaded=False, actual_runtime_values_loaded=False,
                 assumed_available_time_rule="Use archived request values only for rows with submit_time strictly before issue; this is an explicitly authorized scheduler-state proxy, not authenticated version-time reconstruction",
                 request_missingness="Known CPU zero, positive integer GPU request, missing GPU and invalid GPU are separate. Wall/product moments include only positive-GPU rows with finite nonnegative walltime; unknown values never count as observed zero and support/missingness is explicit.",
                 wall_units="hours", product_units="requested GPU*h proxy, never actual GPU*h",
                 moments="Exact sums/squared sums/maxima of known request values; variance=max(0,E[x^2]-E[x]^2) for floating-point roundoff only",
                 temporal_windows="6/12/24h and immediately preceding equal windows;168h relative reference; all windows end no later than issue",
                 historical_frequency="Known target hour/weekday conditional archived request intensity and large-GPU/long-wall proportions using all strictly earlier complete request hours; no actual-work burst labels",
                 existing_authority_audit_sha256=sha(output / "REQUEST_STATE_AUTHORITY_AUDIT.json"),
                 proxy_authorization_sha256=sha(output / "REQUEST_STATE_PROXY_AUTHORIZATION.json"),
                 feature_membership_sha256=sha(output / "FEATURE_MEMBERSHIP.json"),
                 source_membership_manifest_sha256=sha(output / "REQUEST_EVENT_INDEX_MANIFEST.json"),
                 category_vocabulary_sha256=sha(output / "REQUEST_CATEGORY_VOCABULARY.json"),
                 bins_sha256=sha(output / "REQUEST_BINS.parquet"), models_fitted=0, evaluation_metrics_used_for_features=False,
                 production_replacement_supported=False, optimizer_integration_ready=False)
    write_once_json(output / "FEATURE_AVAILABILITY_AUDIT.json", audit)
    print(json.dumps(dict(PASS=True, experiment_status="AUTHORIZED_OFFLINE_PROXY", shape=list(extended.shape),
                          indexed_jobs=sum(row["rows"] for row in event_sources), feature_sha256=audit["feature_sha256"])), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", type=Path, default=BASE)
    parser.add_argument("--snapshot-root", type=Path, default=Path("D:/ChatGPT/Mobile ESS 2/CC4_FORENSIC_20260922/evidence/V41R4_May2025_raw/frozen_artifacts/v41r4_may/loop_wall_v4"))
    parser.add_argument("--runtime-root", type=Path, default=Path("D:/ChatGPT/Mobile ESS 2/runtime_vnext_causal_tail_pr/docs/runtime_vnext_causal_tail"))
    parser.add_argument("--output", type=Path, default=ROOT)
    parser.add_argument("--prepare-authorized-proxy", action="store_true")
    args = parser.parse_args()
    if args.prepare_authorized_proxy:
        prepare_authorized_proxy(args.base, args.output)
        return
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
