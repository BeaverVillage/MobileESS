"""Strict-authority and authorized-proxy contracts; no model fitting."""
import copy
import json
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from request_features import (
    AUTHORITY_COLUMNS, REQUIRED_ATTESTATIONS, RequestStateAuthorityError,
    require_request_state_authority, verified_request_state_at_issue,
    aggregate_request_rows, proxy_feature_vector, TZ,
)


class RequestAuthorityContracts(unittest.TestCase):
    def setUp(self):
        self.issue = pd.Timestamp("2025-01-01T18:00:00Z")
        self.verified_synthetic = dict(
            REQUEST_STATE_AUTHORITY_VERIFIED=True, status="VERIFIED_ASOF_REQUEST_VERSIONS",
            attestations={name: True for name in REQUIRED_ATTESTATIONS},
            verified_source_manifest_sha256="synthetic-test-only",
        )
        self.rows = pd.DataFrame([
            dict(id="synthetic-A", submit_time="2025-01-01T06:00:00Z", gpus_requested=1,
                 wallclock_req=3600, partition="synthetic", qos="normal", request_version_id="v1",
                 request_effective_at="2025-01-01T06:00:00Z", request_observed_at="2025-01-01T06:01:00Z"),
            dict(id="synthetic-A", submit_time="2025-01-01T06:00:00Z", gpus_requested=8,
                 wallclock_req=7200, partition="synthetic", qos="high", request_version_id="v2",
                 request_effective_at="2025-01-01T19:00:00Z", request_observed_at="2025-01-01T19:01:00Z"),
        ])

    def test_successful_file_audit_is_not_request_authority(self):
        with self.assertRaises(RequestStateAuthorityError):
            require_request_state_authority(dict(PASS=True, REQUEST_STATE_AUTHORITY_VERIFIED=False, status="BLOCKED_AUTHORITY"))

    def test_requested_names_and_submit_time_do_not_supply_version_time(self):
        accounting = self.rows.drop(columns=AUTHORITY_COLUMNS)
        with self.assertRaises(RequestStateAuthorityError):
            verified_request_state_at_issue(accounting, self.issue, self.verified_synthetic)

    def test_unverified_source_rejected_before_rows_consumed(self):
        with self.assertRaises(RequestStateAuthorityError):
            verified_request_state_at_issue(None, self.issue, dict(REQUEST_STATE_AUTHORITY_VERIFIED=False))

    def test_unknown_observation_is_not_filled_from_submit(self):
        rows = self.rows.copy()
        rows.loc[0, "request_observed_at"] = None
        with self.assertRaises(RequestStateAuthorityError):
            verified_request_state_at_issue(rows, self.issue, self.verified_synthetic)

    def test_future_change_cannot_replace_issue_known_value(self):
        result = verified_request_state_at_issue(self.rows, self.issue, self.verified_synthetic)
        self.assertEqual(result.gpus_requested.tolist(), [1])
        self.assertEqual(result.request_version_id.tolist(), ["v1"])
        altered = self.rows.copy()
        altered.loc[1, "gpus_requested"] = 1000000
        changed = verified_request_state_at_issue(altered, self.issue, self.verified_synthetic)
        pd.testing.assert_frame_equal(result, changed)

    def test_effective_but_late_observed_value_is_unavailable(self):
        rows = self.rows.copy()
        rows.loc[1, "request_effective_at"] = "2025-01-01T17:00:00Z"
        result = verified_request_state_at_issue(rows, self.issue, self.verified_synthetic)
        self.assertEqual(result.request_version_id.tolist(), ["v1"])

    def test_equal_boundary_allowed_without_using_future_submission(self):
        rows = self.rows.copy()
        rows.loc[1, "request_effective_at"] = self.issue.isoformat()
        rows.loc[1, "request_observed_at"] = self.issue.isoformat()
        result = verified_request_state_at_issue(rows, self.issue, self.verified_synthetic)
        self.assertEqual(result.request_version_id.tolist(), ["v2"])
        rows.loc[1, "submit_time"] = "2025-01-02T06:00:00Z"
        result = verified_request_state_at_issue(rows, self.issue, self.verified_synthetic)
        self.assertEqual(result.request_version_id.tolist(), ["v1"])

    def test_ambiguous_version_and_naive_timestamps_fail(self):
        rows = self.rows.copy()
        rows.loc[1, "request_version_id"] = "v1"
        with self.assertRaises(RequestStateAuthorityError):
            verified_request_state_at_issue(rows, self.issue, self.verified_synthetic)
        rows = self.rows.copy()
        rows.loc[0, "request_observed_at"] = "2025-01-01 06:00:00"
        with self.assertRaises(RequestStateAuthorityError):
            verified_request_state_at_issue(rows, self.issue, self.verified_synthetic)

    def test_each_missing_provenance_attestation_rejected(self):
        for name in REQUIRED_ATTESTATIONS:
            with self.subTest(attestation=name):
                authority = copy.deepcopy(self.verified_synthetic)
                authority["attestations"][name] = False
                with self.assertRaises(RequestStateAuthorityError):
                    require_request_state_authority(authority)


class AuthorizedProxyContracts(unittest.TestCase):
    def setUp(self):
        self.day = "2025-01-02"
        self.issue = (pd.Timestamp(self.day, tz=TZ) - pd.Timedelta(hours=6)).tz_convert("UTC")
        self.rows = pd.DataFrame(dict(
            id=["cpu", "gpu", "unknown", "future"],
            submit_time=[self.issue-pd.Timedelta(hours=2), self.issue-pd.Timedelta(hours=1), self.issue-pd.Timedelta(minutes=30), self.issue],
            gpus_requested=[0.0, 4.0, np.nan, 100.0],
            wallclock_req=pd.to_timedelta([1, 5, 2, 99], unit="h"),
            partition=["cpu", "gpu", "gpu", "future-category"],
            qos=["normal", "normal", None, "future-qos"],
        ))
        self.vocab = dict(partition=["<MISSING>", "cpu", "gpu"], qos=["<MISSING>", "normal"])

    def bins(self, rows=None):
        result = aggregate_request_rows(self.rows if rows is None else rows)
        return result.reindex(pd.date_range(self.issue-pd.Timedelta(days=8), self.issue+pd.Timedelta(hours=1), freq="30min"), fill_value=0.0)

    def test_unknown_gpu_is_separate_from_cpu_zero(self):
        x, names, receipt = proxy_feature_vector(self.bins(), self.issue, self.day, self.vocab)
        value = dict(zip(names, x[0]))
        self.assertEqual(value["request_proxy_6h_jobs"], 3)
        self.assertEqual(value["request_proxy_6h_cpu_zero"], 1)
        self.assertEqual(value["request_proxy_6h_gpu_missing"], 1)
        self.assertEqual(value["request_proxy_6h_gpu_positive"], 1)
        self.assertEqual(value["request_proxy_6h_product_known_sum"], 20)
        self.assertEqual(value["request_proxy_6h_gpu_ge4"], 1)
        self.assertEqual(value["request_proxy_6h_gpu_wall_gt4h"], 1)
        self.assertEqual(receipt["request_version_provenance"], "UNVERIFIED")

    def test_future_request_and_issue_equality_are_excluded(self):
        expected, _, _, = proxy_feature_vector(self.bins(), self.issue, self.day, self.vocab)
        removed, _, _ = proxy_feature_vector(self.bins(self.rows.iloc[:3]), self.issue, self.day, self.vocab)
        np.testing.assert_array_equal(removed, expected)
        changed = self.rows.copy()
        changed.loc[3, "gpus_requested"] = 1e9
        altered, _, _ = proxy_feature_vector(self.bins(changed), self.issue, self.day, self.vocab)
        np.testing.assert_array_equal(altered, expected)

    def test_all_outcome_columns_are_ignored(self):
        expected = aggregate_request_rows(self.rows)
        changed = self.rows.copy()
        changed["start_time"] = self.issue+pd.Timedelta(days=900)
        changed["end_time"] = self.issue-pd.Timedelta(days=900)
        changed["actual_runtime"] = [np.nan, 1e100, -10, 0]
        changed["state"] = ["COMPLETED", "FAILED", "RUNNING", "PENDING"]
        pd.testing.assert_frame_equal(aggregate_request_rows(changed), expected)

    def test_arrow_microsecond_and_nanosecond_submit_resolutions_match(self):
        micros, nanos = self.rows.copy(), self.rows.copy()
        micros["submit_time"] = pd.to_datetime(micros.submit_time, utc=True).dt.as_unit("us")
        nanos["submit_time"] = pd.to_datetime(nanos.submit_time, utc=True).dt.as_unit("ns")
        pd.testing.assert_frame_equal(aggregate_request_rows(micros), aggregate_request_rows(nanos))

    def test_walltime_missing_does_not_become_observed_zero(self):
        changed = self.rows.copy()
        changed.loc[1, "wallclock_req"] = pd.NaT
        x, names, _ = proxy_feature_vector(self.bins(changed), self.issue, self.day, self.vocab)
        value = dict(zip(names, x[0]))
        self.assertEqual(value["request_proxy_6h_gpu_wall_known"], 0)
        self.assertEqual(value["request_proxy_6h_gpu_wall_unknown"], 1)
        self.assertEqual(value["request_proxy_6h_product_support_empty"], 1)
        self.assertEqual(value["request_proxy_6h_product_support"], 0)

    def test_all_443_real_issues_event_membership_and_future_removal(self):
        root = Path(__file__).resolve().parent
        base = root.parent / "cc4_v2_hourly_future_workload"
        bins = pd.read_parquet(root / "REQUEST_BINS.parquet")
        vocab = json.loads((root / "REQUEST_CATEGORY_VOCABULARY.json").read_text(encoding="utf-8"))["vocabulary"]
        ledger = pd.read_csv(base / "DAY_LEDGER.csv")
        issues = pd.to_datetime(ledger.issue_time, utc=True)
        with np.load(root / "FEATURES.npz", allow_pickle=False) as archive:
            x = archive["X"].copy()
        with np.load(base / "DATA.npz", allow_pickle=False) as archive:
            np.testing.assert_array_equal(x[:, :, :71], archive["X"])
        manifest = json.loads((root / "REQUEST_EVENT_INDEX_MANIFEST.json").read_text(encoding="utf-8"))
        submissions = []
        for item in manifest["files"]:
            with np.load(root / item["path"], allow_pickle=False) as source:
                self.assertEqual(len(source["job_id"]), item["rows"])
                self.assertEqual(len(np.unique(source["source_row_index"])), item["rows"])
                submissions.append(source["submit_ns"].copy())
        times = np.sort(np.concatenate(submissions))
        self.assertEqual(len(ledger), 443)
        for i, row in ledger.iterrows():
            with self.subTest(target_day=row.target_day):
                issue = issues.iloc[i]
                removed = bins[bins.index+pd.Timedelta(minutes=30) <= issue]
                replay, _, receipt = proxy_feature_vector(removed, issue, row.target_day, vocab)
                np.testing.assert_array_equal(replay, x[i, :, 71:])
                for window in receipt["windows"]:
                    start = pd.Timestamp(window["submit_start_inclusive"]).value
                    end = pd.Timestamp(window["submit_end_exclusive"]).value
                    count = int(np.searchsorted(times, end, side="left")-np.searchsorted(times, start, side="left"))
                    self.assertEqual(count, window["jobs"])


if __name__ == "__main__":
    unittest.main()
