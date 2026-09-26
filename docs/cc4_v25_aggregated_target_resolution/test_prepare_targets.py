"""Target-resolution identities and unchanged-feature contracts; no fitting."""
from pathlib import Path
import json
import tempfile
import unittest
import numpy as np
import pandas as pd
from prepare_targets import (ROOT, BASE, TZ, aggregate_targets, anchored_features,
                             train_thresholds, day_indices, eligible, reconstruct_hourly, write_once)


class TargetPreparationContracts(unittest.TestCase):
    def test_nonoverlap_mass_and_cumulative_first_differences(self):
        y = np.arange(72, dtype=float).reshape(3, 24)
        a = aggregate_targets(y)
        for key in ['H1', 'H3', 'H6']:
            np.testing.assert_array_equal(a[key].sum(1), y.sum(1))
        np.testing.assert_array_equal(a['CUM'][:, -1], y.sum(1))
        np.testing.assert_array_equal(np.diff(np.column_stack([np.zeros(3), a['CUM']]), axis=1), y)
        self.assertFalse(np.array_equal(a['CUM'].sum(1), y.sum(1)))

    def test_invalid_labels_fail_closed(self):
        for y in [np.zeros((2, 23)), np.full((2, 24), -1.), np.full((2, 24), np.nan)]:
            with self.assertRaises(AssertionError): aggregate_targets(y)

    def test_anchor_rows_are_exact_not_pooled(self):
        x = np.arange(2*24*71, dtype=np.float32).reshape(2, 24, 71)
        f = anchored_features(x)
        np.testing.assert_array_equal(f['H3'], x[:, 2::3])
        np.testing.assert_array_equal(f['H6'], x[:, 5::6])
        np.testing.assert_array_equal(f['CUM'], x)
        self.assertFalse(np.array_equal(f['H3'], x.reshape(2, 8, 3, 71).mean(2)))

    def test_thresholds_and_normalizer_ignore_nontrain_labels(self):
        y = np.arange(1, 121, dtype=float).reshape(5, 24)
        ledger = pd.DataFrame(dict(split=['TRAIN','TRAIN','DEVELOPMENT','MAY_HISTORICAL','TRAIN'], eligible=[True,True,True,True,False], target_day=[str(x) for x in range(5)]))
        a = train_thresholds(aggregate_targets(y), ledger)
        y[2:] = 1e15
        self.assertEqual(a, train_thresholds(aggregate_targets(y), ledger))
        self.assertEqual(len(a['CUM']), 24)
        self.assertEqual(a['TRAIN_day_indices'], [0, 1])

    def test_fixed_timezone_day_boundary_and_timestamp_units(self):
        times = pd.Series(pd.to_datetime(['2025-01-01T13:59:59Z','2025-01-01T14:00:00Z','2025-01-02T14:00:00Z'], utc=True))
        days = np.array(['2025-01-02'])
        np.testing.assert_array_equal(day_indices(times, days), [-1, 0, -1])
        np.testing.assert_array_equal(day_indices(times.dt.as_unit('us'), days), day_indices(times.dt.as_unit('ns'), days))

    def test_unresolved_gpu_preserves_full_day_unavailability(self):
        submit = pd.Timestamp('2025-01-01T15:00Z')
        work = pd.DataFrame(dict(id=['a'], submit_time=[submit], start_time=[submit], end_time=[submit+pd.Timedelta(hours=2)], gpus_requested=[2.], work_GPUh=[4.]))
        ledger = pd.DataFrame(dict(target_day=['2025-01-02'], issue_time=['2025-01-01T08:00Z'], split=['TRAIN'], eligible=[True]))
        y, jobs, daily = reconstruct_hourly(work, ledger, np.array([1]))
        self.assertEqual(y[0, 1], 4.)
        self.assertEqual(pd.Timestamp(daily.label_matured_at.iloc[0]), pd.Timestamp.max.tz_localize('UTC'))
        self.assertEqual(len(jobs), 1)

    def test_original_population_predicate_no_gpu_imputation(self):
        t = pd.Timestamp('2025-01-01T00:00Z')
        rows = pd.DataFrame(dict(gpus_requested=[1.,0.,np.nan,1.,1.], submit_time=[t]*5,
             start_time=[t,t,t,t,t-pd.Timedelta(hours=1)], end_time=[t+pd.Timedelta(hours=1)]*3+[pd.NaT,t+pd.Timedelta(hours=1)]))
        np.testing.assert_array_equal(eligible(rows), [True,False,False,False,False])

    def test_write_once_receipt_rejects_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'receipt.json'
            write_once(path, {'PASS': True})
            with self.assertRaises(FileExistsError): write_once(path, {'PASS': False})

    def test_all443_saved_targets_features_membership_and_maturity(self):
        with np.load(ROOT / 'TARGETS.npz', allow_pickle=False) as a, np.load(BASE / 'DATA.npz', allow_pickle=False) as b:
            self.assertEqual(len(a['days']), 443)
            np.testing.assert_array_equal(a['y_H1'], b['y'])
            expected = aggregate_targets(b['y'])
            for name, targets in expected.items():
                np.testing.assert_array_equal(a['y_'+name], targets)
                np.testing.assert_array_equal(a['X_'+name], b['X'][:, a['end_hour_'+name]])
            hourly = a['y_H1'].copy()
        jobs = pd.read_parquet(ROOT / 'RAW_TARGET_JOB_MEMBERSHIP.parquet')
        self.assertTrue(jobs.id.is_unique)
        self.assertFalse(jobs.duplicated(['archive_member_index', 'archive_row_index']).any())
        ledger = pd.read_csv(BASE / 'DAY_LEDGER.csv')
        daily = pd.read_csv(ROOT / 'DAILY_TARGET_AUDIT.csv')
        np.testing.assert_array_equal(pd.to_datetime(daily.label_matured_at, utc=True, format='mixed'), pd.to_datetime(ledger.label_matured_at, utc=True, format='mixed'))
        groups = jobs.groupby('day_index', sort=True).indices
        for i in range(443):
            selected = jobs.iloc[groups.get(i, np.array([], int))]
            replay = np.bincount(selected.hour.to_numpy(), weights=selected.work_GPUh.to_numpy(), minlength=24)
            np.testing.assert_array_equal(replay, hourly[i])
        thresholds = json.loads((ROOT / 'HIGH_LOAD_THRESHOLDS.json').read_text(encoding='utf-8'))
        self.assertEqual(thresholds, train_thresholds(aggregate_targets(hourly), ledger))


if __name__ == '__main__': unittest.main()
