"""Verify the published audit with no project imports, writes, or raw archive."""
import csv
import gzip
import hashlib
import json
import math
import statistics
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / 'docs/v41r4_cc4_forensic'


def load(name):
    return json.loads((DATA / name).read_text(encoding='utf-8'))


def close(actual, expected):
    assert math.isclose(actual, expected, rel_tol=1e-10, abs_tol=1e-7), (actual, expected)


def quantile(values, q):
    values = sorted(values)
    x = (len(values) - 1) * q
    i = int(x)
    return values[i] + (values[min(i + 1, len(values) - 1)] - values[i]) * (x - i)


def main():
    manifest = load('PACKAGE_MANIFEST.json')
    for record in manifest['files']:
        raw = (DATA / record['path']).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == record['sha256'], record['path']
        if 'decompressed_sha256' in record:
            raw = gzip.decompress(raw)
            assert len(raw) == record['decompressed_bytes']
            assert hashlib.sha256(raw).hexdigest() == record['decompressed_sha256']
    summary = load('CC4_HEADROOM_MISS_DELAY_SUMMARY.json')
    with (DATA / 'CC4_DAY_POLICY_AGGREGATION.csv').open(encoding='utf-8-sig', newline='') as f:
        daily = list(csv.DictReader(f))
    assert len({(r['day'], r['policy']) for r in daily}) == len(daily) == 124
    for policy in ('B0', 'B1', 'B2', 'B3'):
        rows = [r for r in daily if r['policy'] == policy]
        assert len(rows) == 31
        expected = summary['policy_statistics'][policy]
        close(sum(float(r['total_delay_seconds']) for r in rows), expected['total_delay_seconds'])
        close(sum(float(r['planned_migration_extra_postH_GPUh']) for r in rows), expected['planned_migration_extra_postH_GPUh'])
    with (DATA / 'CC4_HEADROOM_MISS_WINDOWS.csv').open(encoding='utf-8-sig', newline='') as f:
        windows = list(csv.DictReader(f))
    assert len(windows) == summary['cc4_total_windows'] == 2511
    assert set(Counter(r['day'] for r in windows).values()) == {81}
    lookup = {(r['day'], int(r['window_index'])): r for r in windows}
    assert len(lookup) == len(windows)
    positive = []
    for row in windows:
        error = float(row['H_actual_GPUh']) - float(row['R_k_GPUh'])
        close(error, float(row['forecast_miss_GPUh']))
        assert (error > 0) == (row['miss_flag'] == 'True')
        for policy in ('B1', 'B3'):
            close(float(row[f'xi_k_{policy}_GPUh']), max(0, float(row['R_k_GPUh']) - float(row[f'A_k_{policy}_GPUh'])))
        if error > 0:
            positive.append(error)
    assert len(positive) == summary['cc4_miss_windows'] == 466
    close(1 - len(positive) / len(windows), summary['actionable_coverage_recomputed'])
    for key, result in [('mean', statistics.mean(positive)), ('median', statistics.median(positive)), ('P90', quantile(positive, .9)), ('max', max(positive))]:
        close(result, summary['positive_miss_GPUh'][key])
    counts = Counter()
    unique = set()
    delays = {'B1': [], 'B3': []}
    weights = {'B1': [], 'B3': []}
    with gzip.open(DATA / 'CC4_MISS_JOB_DELAY_LINK.csv.gz', 'rt', encoding='utf-8-sig', newline='') as f:
        for row in csv.DictReader(f):
            policy = row['policy']
            key = (row['day'], policy, row['population'], row['job_uid'])
            assert key not in unique, key
            unique.add(key)
            if row['population'] == 'FUTURE_ARRIVAL_LABEL_ONLY':
                assert row['explicitly_replayed'] == 'False'
                for field in ('actual_start', 'start_delay_seconds', 'remaining_GPU_hours_at_H'):
                    assert row[field] == 'NOT_AVAILABLE'
                k = int(float(row['canonical_window']))
                window = lookup[row['day'], k]
                submit = datetime.fromisoformat(row['submit_time'])
                begin = datetime.fromisoformat(lookup[row['day'], 0]['window_start'])
                assert k == min(int((submit - begin).total_seconds() // 900), 80)
                assert datetime.fromisoformat(window['window_start']) <= submit < datetime.fromisoformat(window['window_end'])
                assert row['window_miss_flag'] == window['miss_flag']
                counts[policy, 'M' if row['window_miss_flag'] == 'True' else 'C'] += 1
            elif row['frozen_policy_admitted'] == 'True':
                delay = float(row['start_delay_seconds'])
                if delay > 0:
                    assert row['delay_reason'] == 'RESOURCE_CONTENTION_FROM_RUNTIME_OVERRUN'
                delays[policy].append(delay)
                weights[policy].append(float(row['requested_GPU']))
    assert len(unique) == 193624
    for policy in ('B1', 'B3'):
        expected = summary['policy_statistics'][policy]
        d, g = delays[policy], weights[policy]
        assert len(d) == expected['jobs'] == 46092
        assert sum(x > 0 for x in d) == expected['delayed_jobs']
        close(sum(d), expected['total_delay_seconds'])
        close(statistics.mean(d), expected['mean_delay_seconds'])
        close(quantile(d, .95), expected['P95_delay_seconds'])
        close(sum(x * y for x, y in zip(d, g)), expected['GPU_weighted_delay_GPU_seconds'])
        for group in ('M', 'C'):
            assert counts[policy, group] == summary['canonical_incoming_groups'][policy][group]['incoming_jobs']
    assert summary['cc4_miss_caused_delay'] == 'NOT_IDENTIFIABLE'
    assert summary['future_arrival_jobs_explicitly_replayed'] == summary['online_cc4_recourse_exists'] == 'NO'
    assert summary['missing_contributor_days'] == ['2025-05-21']
    for key in ('delayed_jobs_in_miss_windows', 'delayed_jobs_in_nonmiss_windows', 'mean_delay_miss_seconds', 'mean_delay_nonmiss_seconds'):
        assert summary[key] is None
    print('PASS: package hashes, lossless CSV, 2511 windows, 193624 unique job links, B1/B3 delay totals and attribution limits')


if __name__ == '__main__':
    main()
