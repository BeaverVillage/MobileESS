"""Finish raw preparation in a NEW reproduction directory, never overwrite."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys
import datetime
import numpy as np
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    with path.open('rb') as stream: return hashlib.file_digest(stream, 'sha256').hexdigest()


def write(name, value):
    with (ROOT / name).open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False)


assert not (ROOT / 'PREPARATION_RECEIPT.json').exists()
assert not (ROOT / 'CODE_FREEZE.json').exists()
assert json.loads((ROOT / 'RAW_TARGET_AUDIT.json').read_text(encoding='utf-8'))['PASS']
assert (ROOT / 'target_preparation.log').exists()
arrays = np.load(ROOT / 'TARGETS.npz')
schema = pq.read_schema(ROOT / 'RAW_TARGET_JOB_MEMBERSHIP.parquet')
write('TARGET_SCHEMA.json', dict(arrays={name: dict(shape=list(arrays[name].shape), dtype=str(arrays[name].dtype)) for name in arrays.files},
    raw_target_job_columns={field.name: str(field.type) for field in schema},
    membership_key=['archive_member_index', 'archive_row_index'], independent_identifier='id and pinned_raw_work_row_index',
    work_GPUh_definition='gpus_requested * (end_time-start_time).total_seconds()/3600',
    timestamps='UTC nanosecond normalized; target-day clock fixed UTC+10', label_use_only=['start_time', 'end_time', 'work_GPUh'],
    features='X arrays are unchanged endpoint slices of base71; no raw completion values used to add or modify features'))
result = subprocess.run([sys.executable, '-m', 'unittest', 'test_prepare_targets', '-v'], cwd=ROOT, capture_output=True)
with (ROOT / 'target_preparation_tests.log').open('xb') as stream: stream.write(result.stdout + result.stderr)
assert result.returncode == 0, (result.stdout + result.stderr).decode(errors='replace')
write('TARGET_PREPARATION_TEST_RECEIPT.json', dict(PASS=True, returncode=0,
    log_sha256=sha(ROOT / 'target_preparation_tests.log'), source_sha256=sha(ROOT / 'test_prepare_targets.py')))
names = ['prepare_targets.py', 'test_prepare_targets.py', 'TARGETS.npz', 'HIGH_LOAD_THRESHOLDS.json',
    'RAW_TARGET_JOB_MEMBERSHIP.parquet', 'RAW_SOURCE_MEMBERS.json', 'DAILY_TARGET_AUDIT.csv',
    'TARGET_FEATURE_CONTRACT.json', 'RAW_TARGET_AUDIT.json', 'TARGET_SCHEMA.json',
    'TARGET_PREPARATION_TEST_RECEIPT.json', 'target_preparation.log', 'target_preparation_tests.log']
write('PREPARATION_RECEIPT.json', dict(PASS=True, time=datetime.datetime.now(datetime.timezone.utc).isoformat(),
    artifacts={name: sha(ROOT / name) for name in names}, frozen_prior_to_model_training=True,
    feature_contract='Unchanged71 endpoint anchors only', request_provenance='UNVERIFIED/UNOBSERVED inherited event-time proxy', models_fitted=0))
print('PREPARATION FINALIZED', len(names))
