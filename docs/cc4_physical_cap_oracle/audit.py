"""Read frozen May CC4 authority; no model/project imports or fitting/solver calls."""
import argparse
import hashlib
import json
import math
from datetime import timezone, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--forensic-root', type=Path, required=True,
                    help='Extracted CC4_FORENSIC_20260922 directory, including evidence manifests')
parser.add_argument('--output-dir', type=Path, required=True,
                    help='New directory for recalculated audit outputs')
args = parser.parse_args()
OUT = args.output_dir.resolve()
FORENSIC = args.forensic_root.resolve()
if OUT.exists():
    parser.error('--output-dir must be a new directory to preserve existing evidence')
if not (FORENSIC / 'evidence/V41R4_May2025_raw/FINAL_RESULT_INDEX.json').is_file():
    parser.error('--forensic-root is missing the frozen FINAL_RESULT_INDEX.json')
OUT.mkdir(parents=True)
ROOT = FORENSIC / 'evidence/V41R4_May2025_raw'
TARGET = 0.85
TZ = timezone(timedelta(hours=10))
sources = {}
archive_manifest = {}
for manifest in FORENSIC.glob('*evidence_manifest.json'):
    entries = json.loads(manifest.read_text(encoding='utf-8'))
    if isinstance(entries, dict):
        for key, value in entries.items():
            if isinstance(value, dict) and 'sha256' in value:
                archive_manifest[key.replace('\\', '/')] = value


def source(path):
    path = path.resolve()
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if str(path) in sources:
        assert sources[str(path)]['sha256'] == digest, f'Input changed: {path}'
    key = 'V41R4_May2025_raw/' + path.relative_to(ROOT).as_posix()
    expected = archive_manifest.get(key)
    assert expected, f'Missing archive extraction hash: {path}'
    assert digest == expected['sha256'], f'Archive digest mismatch: {path}'
    sources[str(path)] = dict(sha256=digest, bytes=path.stat().st_size,
                              archive_extraction_hash_verified=bool(expected))
    return path


def read(path):
    return json.loads(source(path).read_text(encoding='utf-8'))


def parquet(path):
    return pd.read_parquet(source(path))


def resolve(original):
    return ROOT / 'frozen_artifacts' / original.replace('\\', '/').split('/frozen_artifacts/', 1)[1]


def save(name, data):
    (OUT / name).write_text(json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False), encoding='utf-8')


def equal(a, b, message):
    assert np.array_equal(np.asarray(a), np.asarray(b)), message


def main():
    index = read(ROOT / 'FINAL_RESULT_INDEX.json')
    expected_days = pd.date_range('2025-05-01', '2025-05-31').strftime('%Y-%m-%d').tolist()
    assert len(index) == 124
    assert {(e['day'], e['policy']) for e in index} == {(d, p) for d in expected_days for p in ('B0', 'B1', 'B2', 'B3')}
    daily = {}
    policy_checks = []
    for entry in sorted(index, key=lambda e: (e['day'], e['policy'])):
        day, policy = entry['day'], entry['policy']
        joint_path = resolve(entry['accepted_joint_original_path'])
        joint = read(joint_path)
        assert sources[str(joint_path.resolve())]['sha256'] == entry['accepted_joint_sha256']
        original = ROOT / f'frozen_artifacts/v41r4_may/loop_wall_v4/{day}/{policy}/dayahead'
        snap_path = original / 'ml/ML_SNAPSHOT.json'
        snap = read(snap_path)
        snap_sha = sources[str(snap_path.resolve())]['sha256']
        pred_path = original / 'ml/H4_WINDOW_PREDICTIONS.parquet'
        pred = parquet(pred_path)
        common = ROOT / entry['final_actual'].replace('/replays/', '/common_inputs/')
        score_path = common / 'H4_SCORE.json'
        score = read(score_path)
        ready = read(common / 'READY.json')
        assert ready['decision_SHA'] == joint['decision_SHA']
        assert score['future_scheduling_calls'] == 0
        selected = joint_path.parent
        plan = read(selected / 'PLANNING_RESULT.json')
        assert plan['ML_snapshot_SHA'] == snap_sha
        opt_path = selected / 'H4_OPTIMIZER_WINDOWS.parquet'
        if not opt_path.exists():
            opt_path = resolve(plan['H4_window_persistence']['path'])
        opt = parquet(opt_path) if opt_path.exists() else None
        assert opt is not None, f'Missing optimizer authority: {day} {policy}'
        assert sources[str(opt_path.resolve())]['sha256'] == plan['H4_window_persistence']['sha256']
        begin = pd.Timestamp(day, tz=TZ).tz_convert('UTC')
        starts = pd.date_range(begin, periods=81, freq='15min')
        assert len(pred) == 81 and snap['target_day'] == day
        equal(pd.DatetimeIndex(pred.window_start), starts, 'Window starts')
        equal(pd.DatetimeIndex(pred.window_end), starts + pd.Timedelta(hours=4), 'Window ends')
        assert pd.Timestamp(snap['issue_time']) == begin - pd.Timedelta(hours=6)
        assert (pred.service_level == TARGET).all()
        assert snap['H4_registered_service_level_metadata_only'] == TARGET

        cap = np.asarray(snap['future_service_capacity_gpu'], float)
        sites = snap['future_service_eligible_sites']
        assert cap.shape == (96, len(sites)) and len(set(sites)) == len(sites)
        assert np.isfinite(cap).all() and (cap >= 0).all()
        # Same window-specific eligible-capacity calculation as reserve.py, no hardcoded cap.
        physical = 0.25 * np.lib.stride_tricks.sliding_window_view(cap.sum(axis=1), 16).sum(axis=1)
        historical = np.repeat(float(snap['H4_CAP_HIST']), 81)
        raw = np.asarray(snap['H4_RAW_R85_B2_GPUh'], float)
        actionable = np.asarray(snap['H4_ACTIONABLE_RESERVE_GPUh'], float)
        y = np.asarray(score['realized_H4_GPUh'], float)
        assert y.shape == (81,) and np.isfinite(y).all() and (y >= 0).all()
        equal(physical, snap['H4_CAP_PHYS'], 'Reconstructed physical cap')
        equal(actionable, np.minimum(raw, np.minimum(physical, historical)), 'Actionable cap composition')
        columns = dict(PHYS_CAP_GPUh=physical, HIST_CAP_GPUh=historical,
                       RAW_R85_B2_GPUh=raw, ACTIONABLE_H4_GPUh=actionable)
        for column, values in columns.items():
            equal(pred[column], values, f'Prediction {column}')
            if opt is not None:
                equal(opt[column], values, f'Optimizer {column}')
        if opt is not None:
            equal(pd.DatetimeIndex(opt.window_start), starts, 'Optimizer window starts')
            assert (opt.snapshot_hash == snap_sha).all()
        phys_binds = (physical == actionable) & (actionable < raw)
        hist_binds = (historical == actionable) & (actionable < raw)
        equal(pred.phys_cap_binding, phys_binds, 'Physical binding flags')
        equal(pred.hist_cap_binding, hist_binds, 'Historical binding flags')
        frame = pd.DataFrame(dict(date=day, window_index=np.arange(81, dtype=np.int64),
            window_start=[t.tz_convert(TZ).isoformat() for t in starts],
            window_end=[(t + pd.Timedelta(hours=4)).tz_convert(TZ).isoformat() for t in starts],
            Y_k_GPUh=y, C_phys_k_GPUh=physical, C_hist_k_GPUh=historical,
            uncapped_prediction_GPUh=raw, actionable_prediction_GPUh=actionable,
            physical_oracle_covered=y <= physical, historical_oracle_covered=y <= historical,
            uncapped_covered=y <= raw, actionable_covered=y <= actionable,
            physical_prediction_cap_binding=phys_binds, historical_prediction_cap_binding=hist_binds))
        if day in daily:
            pd.testing.assert_frame_equal(frame, daily[day]['frame'], check_exact=True)
        else:
            daily[day] = dict(frame=frame, Y_source=str(score_path.resolve()),
                capacity_source=str(snap_path.resolve()), prediction_source=str(pred_path.resolve()),
                eligible_sites=sites, eligibility_authority=snap['future_service_eligibility_authority'])
        policy_checks.append(dict(date=day, policy=policy, selected_plan=str(selected / 'PLANNING_RESULT.json'),
            snapshot_sha256=snap_sha, optimizer_table_present=opt is not None,
            accepted_joint_hash_matches=True, physical_recomputed_exact=True))

    contributor_checks = []
    for day in expected_days:
        entry = next(e for e in index if e['day'] == day and e['policy'] == 'B0')
        common = ROOT / entry['final_actual'].replace('/replays/', '/common_inputs/')
        contrib = common.parent / 'workload/REALIZED_WORKLOAD_CONTRIBUTORS.parquet'
        if not contrib.exists():
            matches = sorted((ROOT / f'frozen_artifacts/v41r4_may/loop_wall_v4/{day}').glob('*/actual/authority/ACTUAL_WORKLOAD_CONTRIBUTORS.parquet'))
            contrib = matches[0] if matches else None
        if contrib is None:
            contributor_checks.append(dict(date=day, status='STORED_FINAL_H4_SCORE_AUTHORITY_ONLY'))
            continue
        cf = parquet(contrib)
        begin = pd.Timestamp(day, tz=TZ).tz_convert('UTC')
        submit = pd.to_datetime(cf.submit_time, utc=True)
        assert cf.id.is_unique and submit.ge(begin).all() and submit.lt(begin + pd.Timedelta(days=1)).all()
        weight = cf.gpus_requested.to_numpy(float) * (pd.to_datetime(cf.end_time, utc=True) - pd.to_datetime(cf.start_time, utc=True)).dt.total_seconds().to_numpy() / 3600
        slots = ((submit - begin).dt.total_seconds() // 900).astype(int)
        rebuilt = np.lib.stride_tricks.sliding_window_view(np.bincount(slots, weights=weight, minlength=96), 16).sum(axis=1)
        error = float(np.max(np.abs(rebuilt - daily[day]['frame'].Y_k_GPUh.to_numpy())))
        assert error <= 1e-8
        contributor_checks.append(dict(date=day, status='RECONSTRUCTED_AND_MATCHED', source=str(contrib.resolve()), max_abs_error_GPUh=error))

    all_rows = pd.concat([daily[d]['frame'] for d in expected_days], ignore_index=True)
    assert len(all_rows) == 2511 and not all_rows.duplicated(['date', 'window_index']).any()
    n = len(all_rows)
    count = lambda col: int(all_rows[col].sum())
    physical_n = count('physical_oracle_covered')
    historical_n = count('historical_oracle_covered')
    raw_n = count('uncapped_covered')
    actionable_n = count('actionable_covered')
    summary = dict(N=n, count_Y_le_C_phys=physical_n, count_Y_gt_C_phys=n-physical_n,
        physical_cap_oracle_coverage=physical_n/n, TARGET_COVERAGE=TARGET,
        PHYSICAL_85PCT_ATTAINABLE=physical_n/n >= TARGET,
        current_uncapped_covered_count=raw_n, current_uncapped_coverage=raw_n/n,
        current_actionable_covered_count=actionable_n, current_actionable_coverage=actionable_n/n,
        gap_oracle_minus_uncapped=(physical_n-raw_n)/n,
        gap_oracle_minus_actionable=(physical_n-actionable_n)/n,
        required_covered_windows_for_85pct=math.ceil(TARGET*n),
        additional_covered_windows_required_from_current=math.ceil(TARGET*n)-actionable_n,
        physical_cap_values_GPUh=sorted(all_rows.C_phys_k_GPUh.unique().tolist()),
        historical_cap_values_GPUh=sorted(all_rows.C_hist_k_GPUh.unique().tolist()),
        historical_oracle=dict(N=n, count_Y_le_C_hist=historical_n, count_Y_gt_C_hist=n-historical_n,
            historical_cap_oracle_coverage=historical_n/n, HISTORICAL_85PCT_ATTAINABLE=historical_n/n >= TARGET),
        physical_prediction_cap_binding_windows=count('physical_prediction_cap_binding'),
        historical_prediction_cap_binding_windows=count('historical_prediction_cap_binding'),
        realized_physical_exceedance_and_prediction_cap_binding=int(((~all_rows.physical_oracle_covered)&all_rows.physical_prediction_cap_binding).sum()),
        realized_physical_exceedance_without_prediction_cap_binding=int(((~all_rows.physical_oracle_covered)&(~all_rows.physical_prediction_cap_binding)).sum()),
        physical_feasible_but_current_actionable_missed=int((all_rows.physical_oracle_covered & ~all_rows.actionable_covered).sum()),
        coverage_comparison='Exact <=, equality covered; no rounding or epsilon',
        cap_derivation='0.25 * rolling_16_sum(sum(snapshot.future_service_capacity_gpu, eligible site axis))',
        population='2025-05-01..2025-05-31 fixed UTC+10 modeled dates; 81 overlapping 4h windows/day; 15min stride; policies deduplicated after exact equality checks',
        target_definition='Full lifetime GPU service of jobs whose original submit time falls in the 4h window; same stored final CC4 evaluation target',
        model_fitting_calls=0, model_setting_changes=False)
    exceed = all_rows.loc[~all_rows.physical_oracle_covered, ['date','window_start','Y_k_GPUh','C_phys_k_GPUh']].copy()
    exceed['exceedance_GPUh'] = exceed.Y_k_GPUh - exceed.C_phys_k_GPUh
    assert (exceed.exceedance_GPUh > 0).all() and len(exceed) == n-physical_n
    all_rows.to_csv(OUT / 'CC4_ALL_MAY_WINDOWS.csv', index=False, encoding='utf-8-sig')
    exceed.to_csv(OUT / 'CC4_PHYSICAL_CAP_EXCEEDANCE_WINDOWS.csv', index=False, encoding='utf-8-sig')
    pd.testing.assert_frame_equal(pd.read_csv(OUT / 'CC4_ALL_MAY_WINDOWS.csv', float_precision='round_trip'), all_rows, check_exact=True)
    pd.testing.assert_frame_equal(pd.read_csv(OUT / 'CC4_PHYSICAL_CAP_EXCEEDANCE_WINDOWS.csv', float_precision='round_trip'), exceed.reset_index(drop=True), check_exact=True)
    # Check all consumed authority files are unchanged after the computation.
    for filename, metadata in sources.items():
        assert hashlib.sha256(Path(filename).read_bytes()).hexdigest() == metadata['sha256']
    save('SUMMARY.json', summary)
    save('VALIDATION.json', dict(status='PASS', policy_days=len(policy_checks), unique_windows=n,
        all_policy_labels_predictions_and_caps_exactly_equal=True, authority_inputs_unchanged=True,
        csv_exact_roundtrip=True, checks=policy_checks, contributor_checks=contributor_checks))
    save('SOURCE_MANIFEST.json', dict(authority_root=str(ROOT.resolve()), files=sources,
        per_day={day: {k:v for k,v in value.items() if k != 'frame'} for day, value in daily.items()}))
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
