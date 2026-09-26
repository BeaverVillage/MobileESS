"""Pure causal-feature contracts; no fitting or evaluation-metric inspection."""
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

import causal_features as feature


class CausalFeatures(unittest.TestCase):
    def setUp(self):
        self.day = "2024-04-10"
        self.issue = feature.modeled_issue(self.day)
        self.past = np.zeros((336, 8), dtype=np.float32)
        self.past[:, 0] = 1
        self.past[:, 1] = 10
        self.past[:, 2] = 1
        self.past[:, 3] = 2
        self.days = np.array(["2024-04-01", "2024-04-02", "2024-04-07", self.day])
        self.y = np.zeros((4, 24))
        self.y[0, 3] = 1000
        self.y[1, 4] = 2000
        self.availability = pd.to_datetime(["2024-04-02T15:00:00Z", "2024-04-03T15:00:00Z", self.issue.isoformat(), "2024-04-12T00:00:00Z"], utc=True)
        self.splits = np.array(["TRAIN"] * 4)

    def calculate(self, **overrides):
        inputs = dict(past=self.past, target_day=self.day, issue_time=self.issue, labels=self.y,
                      label_days=self.days, label_matured_at=self.availability, label_splits=self.splits)
        inputs.update(overrides)
        x, names, receipt, specs = feature.issue_features(**inputs)
        return x, {name: x[:, i] for i, name in enumerate(names)}, receipt, specs

    def test_windows_are_hourly_pairs_and_explicit_missing(self):
        past = self.past.copy()
        past[-1, 2] = 0
        past[-1, 1] = 999999
        _, columns, receipt, _ = self.calculate(past=past)
        self.assertEqual(columns["burst_work_6h_mature_hours"][0], 5)
        self.assertEqual(columns["burst_work_6h_sum"][0], 100)
        self.assertEqual(columns["burst_work_6h_mean"][0], 20)
        self.assertEqual(columns["burst_arrivals_6h_sum"][0], 12)
        self.assertNotIn(167, receipt["strictly_mature_complete_hour_indices"])
        self.assertEqual(receipt["past_halfhour_end_exclusive"], self.issue.isoformat())

    def test_unavailable_workload_is_not_observed_zero(self):
        past = self.past.copy()
        past[-12:, 2] = 0
        past[-12:, 1] = np.nan
        _, columns, _, _ = self.calculate(past=past)
        self.assertEqual(columns["burst_work_6h_missing"][0], 1)
        self.assertEqual(columns["burst_work_6h_mature_hours"][0], 0)
        self.assertEqual(columns["burst_work_6h_acceleration_valid"][0], 0)
        self.assertEqual(columns["burst_work_6h_ratio_valid"][0], 0)
        self.assertEqual(columns["burst_arrivals_6h_sum"][0], 12)

    def test_equal_maturity_is_not_strictly_available(self):
        past = self.past.copy()
        past[-1, 3] = 0
        _, columns, receipt, _ = self.calculate(past=past)
        self.assertEqual(columns["burst_work_6h_mature_hours"][0], 5)
        self.assertEqual(receipt["historical_full_day_indices"], [0, 1])

    def test_future_values_removal_and_maturity_postponement_invariant(self):
        baseline, _, _, _ = self.calculate()
        changed = self.y.copy()
        changed[2:] = np.nan
        postponed = self.availability.to_numpy().copy()
        postponed[2:] = pd.Timestamp("2026-01-01T00:00Z")
        actual, _, _, _ = self.calculate(labels=changed, label_matured_at=postponed)
        np.testing.assert_array_equal(actual, baseline)
        removed, _, _, _ = self.calculate(labels=self.y[:2], label_days=self.days[:2],
                                          label_matured_at=self.availability[:2], label_splits=self.splits[:2])
        np.testing.assert_array_equal(removed, baseline)

    def test_hidden_recent_outcomes_invariant(self):
        past = self.past.copy()
        past[-4:, 2] = 0
        before, _, _, _ = self.calculate(past=past)
        past[-4:, 1] = [1e20, np.nan, 1000, 30000]
        past[-4:, 3] = 0
        after, _, _, _ = self.calculate(past=past)
        np.testing.assert_array_equal(after, before)

    def test_burst_counts_and_recency_use_observed_complete_hours(self):
        past = self.past.copy()
        past[-6:-4, 1] = 500
        _, columns, receipt, _ = self.calculate(past=past)
        self.assertEqual(columns["burst_count_6h"][0], 1)
        self.assertEqual(columns["burst_time_since_recent_burst_hours"][0], 2)
        self.assertEqual(columns["burst_time_since_last_observed_burst_hours"][0], 2)
        self.assertEqual(receipt["latest_recent_burst_hour_index"], 165)

    def test_purge_and_current_calendar_frequency(self):
        _, columns, receipt, _ = self.calculate(label_splits=np.array(["PURGE", "TRAIN", "TRAIN", "TRAIN"]))
        self.assertEqual(receipt["historical_full_day_indices"], [1])
        self.assertEqual(columns["burst_target_hour_frequency"][4], 1)
        self.assertEqual(columns["burst_target_hour_support_hours"][4], 1)
        self.assertEqual(columns["burst_target_hour_frequency"][3], 0)

    def test_no_support_and_observed_zero_distinguishable(self):
        past = self.past.copy()
        past[:, 1] = 0
        _, columns, _, _ = self.calculate(past=past)
        self.assertEqual(columns["burst_work_6h_denominator_observed_zero"][0], 1)
        self.assertEqual(columns["burst_work_6h_missing"][0], 0)
        self.assertEqual(columns["burst_work_6h_ratio_valid"][0], 0)

    def test_all_443_actual_issues_asof_invariant(self):
        root = Path(__file__).resolve().parent
        base = root.parent / "cc4_v2_hourly_future_workload"
        ledger = pd.read_csv(base / "DAY_LEDGER.csv")
        with np.load(base / "DATA.npz", allow_pickle=False) as source:
            past, labels, days, original = (source[key].copy() for key in ["past", "y", "days", "X"])
        days = days.astype(str)
        with np.load(root / "FEATURES.npz", allow_pickle=False) as artifact:
            expected = artifact["X_extended"].copy()
        self.assertEqual(len(days), 443)
        np.testing.assert_array_equal(expected[:, :, :71], original)
        available = pd.to_datetime(ledger.label_matured_at, utc=True)
        issues = pd.to_datetime(ledger.issue_time, utc=True)
        ends = pd.DatetimeIndex(pd.to_datetime(days)).tz_localize(feature.TZ).tz_convert("UTC") + pd.Timedelta(days=1)
        splits = ledger.split.to_numpy()
        for i, day in enumerate(days):
            with self.subTest(target_day=day):
                hidden = past[i].copy()
                mature = (hidden[:, 2] == 1) & (hidden[:, 3] > 0)
                hidden[~mature, 1] = np.nan
                known = (available < issues.iloc[i]).to_numpy() & (ends < issues.iloc[i]) & (splits != "PURGE")
                unknown_labels = labels.copy()
                unknown_labels[~known] = np.nan
                postponed = available.copy()
                postponed.iloc[np.flatnonzero(~known)] = issues.iloc[i] + pd.Timedelta(days=365)
                changed, _, receipt, _ = feature.issue_features(
                    hidden, day, issues.iloc[i], unknown_labels, days, postponed, splits)
                np.testing.assert_array_equal(changed, expected[i, :, 71:])
                self.assertLessEqual(pd.Timestamp(receipt["feature_available_time"]), issues.iloc[i])
                removed, _, _, _ = feature.issue_features(
                    hidden, day, issues.iloc[i], labels[known], days[known], available[known], splits[known])
                np.testing.assert_array_equal(removed, expected[i, :, 71:])


if __name__ == "__main__":
    unittest.main()
