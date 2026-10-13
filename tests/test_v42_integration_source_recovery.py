from copy import deepcopy
import unittest

from v42_integration.source_recovery import PR79_LEDGER_SHA, episode_id, scoped_prior_check


class SourceRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.issue = 1746000000
        self.observed = dict(job_uid="8568682", submit_time="2025-04-23T11:12:28+00:00",
                             elapsed_seconds=588699., GPU_gang=4, state="RUNNING")
        self.base = dict(job_uid="8568682", episode_id=episode_id("8568682",1745406748),
            submit_seconds=1745406748, known_start_seconds=1745411301., state_at_issue="RUNNING",
            source_record_hash="source", boundary_status="RESOLVED", reference_AIDC_site="AIDC03",
            reference_rack="AIDC03_LP01", requested_GPU=4, snapshot_sha256="snapshot",
            capacity_feasible=True, rack_compatible=True, grid_information_used=False,
            policy_output_used=False, future_outcome_used=False, day_reference_ready=False,
            assignment_day="2025-04-27", reference_site_origin="NEW_SYNTHETIC_ASSIGNMENT",
            issue_seconds=self.issue-4*86400)
        self.prior = [dict(self.base,issue_seconds=self.issue-i*86400,
            reference_site_origin="NEW_SYNTHETIC_ASSIGNMENT" if i==4 else "INHERITED_EPISODE_REFERENCE")
            for i in (4,3,2,1)]
        self.fixed = [dict(GPU_gang=41,current_site_if_running="AIDC03")]
        self.caps = {"AIDC03":80}
        self.racks = [dict(rack_pool_id="AIDC03_LP01",aidc_id="AIDC03",compatibility_GPU_limit=80)]

    def check(self, prior=None, fixed=None):
        return scoped_prior_check(self.observed,self.prior if prior is None else prior,
            self.fixed if fixed is None else fixed,self.caps,self.racks,issue_seconds=self.issue,
            canonical_receipt=dict(path="canonical",sha256=PR79_LEDGER_SHA),source_record_hash="source")

    def test_scoped_pin_does_not_promote_failed_whole_reference(self):
        report,pin=self.check()
        self.assertTrue(report["PASS"])
        self.assertEqual(report["current_site_GPU_after"],45)
        self.assertFalse(report["PR79_global_ready"])
        self.assertFalse(report["KESTREL_OBSERVED_SITE"])
        self.assertFalse(report["SOURCE18R_NUMERICALLY_IDENTICAL"])
        self.assertEqual(pin["site"],"AIDC03")

    def test_prior_pending_site_is_not_proof_running_execution(self):
        prior=[dict(r,state_at_issue="PENDING",known_start_seconds=None) for r in self.prior]
        report,pin=self.check(prior)
        self.assertFalse(report["PASS"])
        self.assertIsNone(pin)

    def test_future_outcome_and_other_policy_are_rejected(self):
        for field in ("future_outcome_used","policy_output_used","grid_information_used"):
            prior=deepcopy(self.prior);prior[0][field]=True
            report,pin=self.check(prior)
            self.assertFalse(report["PASS"],field)
            self.assertIsNone(pin)

    def test_continuity_or_source_record_change_rejected(self):
        for field,value in (("known_start_seconds",1745411302.),("source_record_hash","another"),
                            ("reference_AIDC_site","AIDC02")):
            prior=deepcopy(self.prior);prior[1][field]=value
            report,pin=self.check(prior)
            self.assertFalse(report["PASS"],field)
            self.assertIsNone(pin)

    def test_current_capacity_not_old_row_flag_controls_acceptance(self):
        report,pin=self.check(fixed=[dict(GPU_gang=77,current_site_if_running="AIDC03")])
        self.assertFalse(report["PASS"])
        self.assertIsNone(pin)

    def test_gap_in_observed_episode_not_filled(self):
        report,pin=self.check(self.prior[:1]+self.prior[2:])
        self.assertFalse(report["PASS"])
        self.assertIsNone(pin)


if __name__ == "__main__":
    unittest.main()
