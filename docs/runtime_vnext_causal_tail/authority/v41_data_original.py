"""Projected causal Kestrel inputs for V41. Future labels never leave the scanner."""
from __future__ import annotations
from datetime import timezone, timedelta
import hashlib
import json
from pathlib import Path
import re
import zipfile

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from dayahead.v37.aidc_materializer import KESTREL_ARCHIVE, KESTREL_ARCHIVE_SHA256
from dayahead.v40s5.common import FEATURES, CLOCK
from .preflight import ROOT, record
from .reserve import require

RUNTIME = ROOT / 'frozen_artifacts/v41r3_scale'
SOURCE_REPO = Path('C:/codex_mobileess_workspace/MobileESS_v40a_bounded_iterative_coopt')
SLOT_NS = 900_000_000_000
HISTORY_LOWER = pd.Timestamp('2025-01-29T00:00:00Z')
MEM_RE = re.compile(r'^([\d.]+)([KMGTPkmgtp]?)[nN]?$')
MEM_UNITS = {'K': 1/1024, 'M': 1, 'G': 1024, 'T': 1024**2, 'P': 1024**3, '': 1}


def memory_mib(value):
    # Exact pinned hpc_oda_commons _memory_slurm_to_mb normalization.
    if value is None:
        return None
    match = MEM_RE.match(str(value).strip())
    if not match:
        return None
    return float(match.group(1)) * MEM_UNITS[match.group(2).upper()]


def issue_time(day):
    return pd.Timestamp(day, tz=timezone(timedelta(hours=10))).tz_convert('UTC') - pd.Timedelta(hours=6)


def normalize(raw):
    frame = pd.DataFrame(index=raw.index)
    frame['job_id'] = raw.id.astype(str)
    frame['job_uid'] = frame.job_id
    frame['submit_time'] = pd.to_datetime(raw.submit_time, utc=True)
    frame['requested_seconds'] = raw.wallclock_req.dt.total_seconds().astype(float)
    for source, target in [('gpus_requested', 'num_gpus_req'), ('nodes_req', 'num_nodes_req'),
                           ('processors_req', 'num_cores_req')]:
        frame[target] = pd.to_numeric(raw[source], errors='coerce')
    frame['requested_memory_mib'] = raw.memory_req.map(memory_mib)
    for name in ('partition', 'qos'):
        frame[name] = raw[name]
    frame['submit_hour'] = frame.submit_time.dt.hour.astype(float)
    frame['submit_dow'] = frame.submit_time.dt.dayofweek.astype(float)
    return frame


def pending_features(day):
    path = SOURCE_REPO / 'dayahead/artifacts/v37_r4a_per_day_aidc/days' / day / 'V37_R4A_D1_SNAPSHOT.parquet'
    columns = ['id', 'submit_time', 'wallclock_req', 'gpus_requested', 'nodes_req', 'processors_req',
               'memory_req', 'partition', 'qos', 'state_at_issue']
    raw = pq.read_table(path, columns=columns, filters=[('state_at_issue', '==', 'PENDING')]).to_pandas()
    require(raw.submit_time.le(issue_time(day)).all(), 'PENDING_SUBMISSION_AFTER_ISSUE')
    f = normalize(raw)
    require(not f.job_uid.duplicated().any(), 'DUPLICATE_PENDING_UID')
    require(not set(['start_time', 'end_time', 'runtime_seconds']) & set(f.columns), 'PENDING_LABEL_COLUMN_LEAKAGE')
    return f, record(path)


def atomic_json(path, value):
    from dayahead.paper_analysis.storage import write_json
    write_json(Path(path), value)


def parquet_index(frame):
    """Parquet retains every timestamp but has no DatetimeIndex.freq field.

    Normalize only that nonserialized metadata before writing so the strict
    full read-back comparison remains enabled, including timestamp equality.
    """
    if isinstance(frame.index, pd.DatetimeIndex):
        frame = frame.copy()
        frame.index = frame.index.copy(deep=True)
        frame.index.freq = None
    return frame


def parquet_bins(frame):
    """Normalize mixed raw timestamp units without changing any event instant."""
    result=parquet_index(frame)
    for column in ('max_observed_end','modeled_end_max'):
        original=result[column]
        normalized=pd.to_datetime(original,utc=True).astype('datetime64[ns, UTC]')
        require(original.isna().equals(normalized.isna()),'CAUSAL_TIMESTAMP_NULL_DRIFT')
        require(all(pd.Timestamp(a)==b for a,b in zip(original,normalized) if pd.notna(a)),
                'CAUSAL_TIMESTAMP_VALUE_DRIFT')
        result[column]=normalized
    return result


def causal_history(day):
    """Expanding all positive-GPU raw history, no rolling-window/decay restriction.

    The dated cache contains only mature labels and censored historical event
    bins. Its receipt seals the issue and source archive, and all files are hashed.
    """
    issue = issue_time(day)
    folder = RUNTIME / 'inputs' / day
    receipt_path = folder / 'CAUSAL_INPUT_RECEIPT.json'
    if receipt_path.exists():
        receipt = json.loads(receipt_path.read_text(encoding='utf-8'))
        require(receipt['issue_time'] == issue.isoformat() and receipt['archive_sha256'] == KESTREL_ARCHIVE_SHA256,
                'CAUSAL_CACHE_SCOPE_DRIFT')
        for entry in receipt['files'].values():
            require(record(entry['path']) == entry, 'CAUSAL_CACHE_HASH_DRIFT')
        return (pd.read_parquet(folder / 'runtime_history.parquet'), pd.read_parquet(folder / 'bins.parquet'),
                pd.read_parquet(folder / 'mature_work_jobs.parquet'), receipt)
    folder.mkdir(parents=True, exist_ok=True)
    with KESTREL_ARCHIVE.open('rb') as stream:
        require(hashlib.file_digest(stream, 'sha256').hexdigest() == KESTREL_ARCHIVE_SHA256, 'KESTREL_ARCHIVE_HASH_DRIFT')
    histories = []; binparts = []; workparts = []; source_rows = []; seen = set()
    cols = ['id', 'submit_time', 'start_time', 'end_time', 'wallclock_req', 'gpus_requested',
            'nodes_req', 'processors_req', 'memory_req', 'partition', 'qos']
    with zipfile.ZipFile(KESTREL_ARCHIVE) as archive:
        # Accounting partitions can contain earlier submissions. Do not inherit
        # V37's old month<=May enumeration cutoff (June carries May submissions).
        members = sorted(name for name in archive.namelist()
                         if re.search(r'year=\d{4}/month=\d{1,2}/.*\.parquet$', name))
        for name in members:
            # Predicate pushdown before Python row materialization. The raw
            # future END is used only as a boolean event-maturity predicate.
            with archive.open(name) as stream:
                table = pq.read_table(stream, columns=cols, filters=[('submit_time', '<=', issue.to_pydatetime())])
            if not table.num_rows:
                continue
            end = table['end_time']; start = table['start_time']; gpu = table['gpus_requested']
            cutoff = pa.scalar(issue.to_pydatetime(), type=end.type)
            mature = pc.fill_null(pc.and_(pc.less(end, cutoff), pc.greater(end, start)), False)
            positive_gpu = pc.fill_null(pc.greater(gpu, 0), False)
            take = pc.and_(mature, positive_gpu)
            raw = table.filter(take).to_pandas()
            if len(raw):
                f = normalize(raw)
                f['start_time'] = pd.to_datetime(raw.start_time, utc=True)
                f['end_time'] = pd.to_datetime(raw.end_time, utc=True)
                f['runtime_seconds'] = (f.end_time - f.start_time).dt.total_seconds()
                f = f[np.isfinite(f.runtime_seconds) & f.runtime_seconds.gt(0) & f[CLOCK].notna().all(axis=1)].copy()
                require(not set(f.job_uid) & seen and f.job_uid.is_unique, 'DUPLICATE_RAW_RUNTIME_UID')
                seen.update(f.job_uid)
                histories.append(f)
            lower = pa.scalar(HISTORY_LOWER.to_pydatetime(), type=table['submit_time'].type)
            recent = table.filter(pc.greater_equal(table['submit_time'], lower))
            if recent.num_rows:
                event = recent.select(['id', 'submit_time', 'end_time', 'start_time', 'gpus_requested'])
                # Censor exact not-yet-observed timestamps before conversion.
                for field in ('start_time', 'end_time'):
                    col = event[field]
                    allowed = pc.less_equal(col, pa.scalar(issue.to_pydatetime(), type=col.type))
                    event = event.set_column(event.schema.get_field_index(field), field,
                        pc.if_else(pc.fill_null(allowed, False), col, pa.scalar(None, type=col.type)))
                e = event.to_pandas()
                e['bin'] = e.submit_time.dt.floor('30min')
                e['unresolved'] = e.end_time.isna().astype('int64')
                e['gpu_unresolved'] = (e.gpus_requested.gt(0) & e.end_time.isna()).astype('int64')
                binparts.append(e.groupby('bin').agg(submit_count=('id', 'size'), max_observed_end=('end_time', 'max'),
                    unresolved_end_count=('unresolved', 'sum'), gpu_unresolved=('gpu_unresolved', 'sum')))
                valid = e.gpus_requested.gt(0) & np.isfinite(e.gpus_requested) & e.start_time.notna() & e.end_time.notna()
                valid &= e.end_time.gt(e.start_time) & e.start_time.ge(e.submit_time)
                w = e.loc[valid, ['id', 'submit_time', 'start_time', 'end_time', 'gpus_requested']].copy()
                w['work_GPUh'] = w.gpus_requested * (w.end_time - w.start_time).dt.total_seconds() / 3600
                if len(w):
                    workparts.append(w)
            source_rows.append({'member': name, 'causal_submissions': table.num_rows, 'mature_runtime_rows': len(raw)})
            print(f'V41 causal source {name}: mature GPU jobs {len(raw):,}', flush=True)
    history = pd.concat(histories, ignore_index=True).sort_values(['end_time', 'job_uid'], kind='mergesort').reset_index(drop=True)
    require(history.end_time.lt(issue).all() and history.job_uid.is_unique, 'RUNTIME_MEMBERSHIP_CAUSALITY')
    work = pd.concat(workparts, ignore_index=True)
    # Raw accounting partitions differ in timestamp unit; normalize before
    # concatenated event arithmetic (including partitions with no GPU jobs).
    for column in ('submit_time', 'start_time', 'end_time'):
        work[column] = pd.to_datetime(work[column], utc=True)
    require(work.id.astype(str).is_unique, 'DUPLICATE_WORKLOAD_UID')
    bins = pd.concat(binparts).groupby(level=0).agg(submit_count=('submit_count', 'sum'),
        max_observed_end=('max_observed_end', 'max'), unresolved_end_count=('unresolved_end_count', 'sum'),
        gpu_unresolved=('gpu_unresolved', 'sum')).sort_index()
    coverage = pd.date_range(HISTORY_LOWER, issue.floor('30min'), freq='30min', inclusive='left')
    bins = bins.reindex(coverage)
    for col in ('submit_count', 'unresolved_end_count', 'gpu_unresolved'):
        bins[col] = bins[col].fillna(0).astype('int64')
    work['bin'] = work.submit_time.dt.floor('30min')
    modeled = work.groupby('bin').agg(work_GPUh=('work_GPUh', 'sum'), modeled_end_max=('end_time', 'max'))
    bins = bins.join(modeled); bins['work_GPUh'] = bins.work_GPUh.fillna(0.)
    bins = parquet_bins(bins)
    bins.index.name = 'arrival_bin'
    for name, frame in [('runtime_history', history), ('bins', bins), ('mature_work_jobs', work)]:
        path = folder / (name + '.parquet')
        require(not path.exists(), 'UNSEALED_CAUSAL_CACHE_REQUIRES_REVIEW:' + str(path))
        from dayahead.paper_analysis.storage import atomic
        with atomic(path) as stream: frame.to_parquet(stream,index=name=='bins')
        pd.testing.assert_frame_equal(frame,pd.read_parquet(path),check_exact=True)
    receipt = dict(issue_time=issue.isoformat(), archive_sha256=KESTREL_ARCHIVE_SHA256,
        runtime_training_N=len(history), training_membership='all eligible positive-GPU raw jobs with end < issue; no window or decay',
        training_min_end=history.end_time.min().isoformat(), training_max_end=history.end_time.max().isoformat(),
        future_label_rows_materialized=0, event_future_timestamps_censored=True, source_rows=source_rows,
        workload_history_coverage_begin=HISTORY_LOWER.isoformat(),
        files={name: record(folder / (name + '.parquet')) for name in ('runtime_history', 'bins', 'mature_work_jobs')})
    atomic_json(receipt_path, receipt)
    return history, bins, work, receipt


def fit_runtime(day, history, pending, directory):
    from dayahead.v40s5r1.common import Preprocess, ids
    from dayahead.v40s5r1.models import fit_one
    directory = Path(directory); directory.mkdir(parents=True, exist_ok=False)
    issue = issue_time(day)
    pre = Preprocess('P', issue).fit(history)
    records = []
    temporary=directory/'Q90.txt.gz.tmp'; target=directory/'Q90.txt.gz'
    model = fit_one(history, pre, history.runtime_seconds, 'L2', .90, temporary, records)
    from dayahead.paper_analysis.storage import atomic
    with atomic(target) as stream: stream.write(temporary.read_bytes())
    require(record(target)['sha256']==record(temporary)['sha256'],'MODEL_ATOMIC_PUBLICATION_DRIFT')
    temporary.unlink(); records[-1]['name']=target.name
    seconds = model.predict(pre.transform(pending), num_threads=1) if len(pending) else np.array([])
    require(np.isfinite(seconds).all() and (seconds > 0).all(), 'INVALID_Q90_NO_MANUAL_CORRECTION')
    slots = np.ceil(seconds / 900).astype('int64')
    from dayahead.v40s5r1.models import load_model
    reopened=load_model(target).predict(pre.transform(pending),num_threads=1) if len(pending) else np.array([])
    require(np.array_equal(reopened,seconds),'MODEL_REOPEN_PREDICTION_DRIFT')
    atomic_json(directory / 'preprocessing.json', pre.descriptor())
    authority = dict(runtime_model_id='ROLLING_Q90_TRACK_P_L2', runtime_training_N=len(history),
        runtime_training_membership_hash=ids(history.job_uid), PENDING_N=len(pending),
        PENDING_JOB_Q90_SECONDS=dict(zip(pending.job_uid, seconds.tolist())),
        PENDING_JOB_DURATION_SLOTS=dict(zip(pending.job_uid, slots.tolist())),
        fit_records=records, model=record(directory / 'Q90.txt.gz'), preprocessing=record(directory / 'preprocessing.json'),
        issue_time=issue.isoformat(), original_submission_provenance_verified=False,
        provenance_assumption='D1_SCHEDULER_REQUEST_STATE_PROXY_V1')
    atomic_json(directory / 'RUNTIME_AUTHORITY.json', authority)
    return authority
