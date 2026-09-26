import unittest
import numpy as np
import pandas as pd
import study as s


class Contract(unittest.TestCase):
    def test_no_gate_lowering(self):
        self.assertEqual(s.GATE, .01)
        self.assertGreater(s.GATE, .0025)

    def test_recency_membership_preserved(self):
        for i in s.OOS:
            train = s.prior.old.membership(i)
            self.assertTrue((s.AV.iloc[train] < s.ISS.iloc[i]).all())
            self.assertTrue(np.isfinite(np.asarray(s.prior.old.weights(train, i))).all())

    def test_recall_alone_cannot_select_detector(self):
        baseline = dict(PR_AUC=.20, precision=.15, detector_recall=.1, burst_coverage=.1, positive_coverage=.85, requirement_ratio=1.5, Q90_pinball=100.)
        candidate = dict(baseline, detector_recall=1., burst_coverage=.8, positive_coverage=.90)
        self.assertFalse(s.criteria(candidate, baseline)[0])
        candidate.update(PR_AUC=.22, precision=.17)
        self.assertTrue(s.criteria(candidate, baseline)[0])

    def test_ratio_strict_and_pinball_margin(self):
        baseline = dict(PR_AUC=.20, precision=.15, detector_recall=.1, burst_coverage=.1, positive_coverage=.85, requirement_ratio=1.5, Q90_pinball=100.)
        candidate = dict(baseline, PR_AUC=.22, precision=.17, detector_recall=.7, burst_coverage=.7, requirement_ratio=2.)
        self.assertFalse(s.criteria(candidate, baseline)[0])
        candidate.update(requirement_ratio=1.9, Q90_pinball=102.01)
        self.assertFalse(s.criteria(candidate, baseline)[0])

    def test_inclusive_meaningful_improvement_boundary(self):
        baseline = dict(PR_AUC=.20, precision=.15, detector_recall=.1, burst_coverage=.1, positive_coverage=.85, requirement_ratio=1.5, Q90_pinball=100.)
        candidate = dict(baseline, PR_AUC=.21, precision=.16, detector_recall=.6, burst_coverage=.6, Q90_pinball=102.)
        self.assertTrue(s.criteria(candidate, baseline)[0])
        candidate['PR_AUC'] = .21 - 1e-10
        self.assertFalse(s.criteria(candidate, baseline)[0])

    def test_missing_quality_fails_closed(self):
        values = dict(PR_AUC=np.nan, precision=.15, detector_recall=.6, burst_coverage=.6, positive_coverage=.85, requirement_ratio=1.5, Q90_pinball=100.)
        with self.assertRaises(AssertionError): s.criteria(values, values)

    def test_timestamp_serialization_is_exact_writer_representation(self):
        issue = pd.Timestamp('2025-05-01T08:00:00Z')
        self.assertEqual(s.clean([dict(issue=issue, weights=np.array([1., 2.]))]), [dict(issue=str(issue), weights=[1., 2.])])


if __name__ == '__main__': unittest.main()
