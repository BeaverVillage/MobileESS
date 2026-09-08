"""Adversarial authority and case-identity regressions; no scientific execution."""
import copy
import unittest
from .authority import classify,aggregate,deduplicate_raw
from .forensic import PRE,AUTH,MISS,CONFLICT,guard

class AuthorityTests(unittest.TestCase):
    def evidence(self,**changes):
        e={'uid':'1','case_id':'2025-05-01/B0','adjudicated':True,'source_hash_verified':True,
           'source_path':'raw.json','source_sha256':'a'*64,'row_key':'/jobs/0',
           'domain':'CURRENT_CASE_EXECUTION','actual_start':'2025-05-01T01:00:00+10:00',
           'actual_end':'2025-05-01T02:00:00+10:00','actual_site':'AIDC01',
           'site_origin':'DIRECT_EXECUTION_ALLOCATION','complete_timing':True,'full_active_interval_site_coverage':True}
        return {**e,**changes}
    def result(self,rows):return classify('2025-05-01/B0','1','2025-05-01T00:00:00+10:00',rows)['classification']
    def test_direct_allocation(self):self.assertEqual(self.result([self.evidence()]),AUTH)
    def test_pre_day_actual_timestamps(self):
        self.assertEqual(self.result([self.evidence(actual_start='2025-04-30T20:00:00+10:00',actual_end='2025-04-30T23:59:59+10:00',actual_site=None,site_origin=None)]),PRE)
    def test_equal_boundary_no_service_overlap(self):
        self.assertEqual(self.result([self.evidence(actual_start='2025-04-30T23:00:00+10:00',actual_end='2025-05-01T00:00:00+10:00')]),PRE)
    def test_planning_site_rejected(self):self.assertEqual(self.result([self.evidence(site_origin='PLANNING')]),MISS)
    def test_inferred_site_rejected(self):self.assertEqual(self.result([self.evidence(site_origin='INFERRED')]),MISS)
    def test_physical_node_is_not_aidc(self):self.assertEqual(self.result([self.evidence(site_origin='PHYSICAL_NODE_UNMAPPED')]),MISS)
    def test_observed_pending_end_not_counterfactual_end(self):
        self.assertEqual(self.result([self.evidence(domain='KESTREL_HISTORY',actual_start='2025-04-30T10:00:00+10:00',actual_end='2025-04-30T11:00:00+10:00')]),MISS)
    def test_wrong_case(self):self.assertEqual(self.result([self.evidence(case_id='2025-05-01/B1')]),MISS)
    def test_wrong_uid(self):self.assertEqual(self.result([self.evidence(uid='2')]),MISS)
    def test_naive_timestamp(self):self.assertEqual(self.result([self.evidence(actual_start='2025-05-01T01:00:00')]),MISS)
    def test_reverse_chronology(self):self.assertEqual(self.result([self.evidence(actual_end='2025-04-30T00:00:00+10:00')]),MISS)
    def test_hash_verification_required(self):self.assertEqual(self.result([self.evidence(source_hash_verified=False)]),MISS)
    def test_candidate_self_assertion_not_trusted(self):self.assertEqual(self.result([self.evidence(adjudicated=False)]),MISS)
    def test_incomplete_interval_coverage(self):self.assertEqual(self.result([self.evidence(full_active_interval_site_coverage=False)]),MISS)
    def test_timing_conflict_before_precomplete(self):
        a=self.evidence(actual_start='2025-04-30T20:00:00+10:00',actual_end='2025-04-30T21:00:00+10:00')
        b=self.evidence(actual_start=a['actual_start'],actual_end='2025-05-01T02:00:00+10:00',source_sha256='b'*64)
        self.assertEqual(self.result([a,b]),CONFLICT)
    def test_site_conflict(self):self.assertEqual(self.result([self.evidence(),self.evidence(actual_site='AIDC02',source_sha256='b'*64)]),CONFLICT)
    def test_case_count_conservation(self):
        self.assertEqual(aggregate([PRE,PRE]),PRE);self.assertEqual(aggregate([PRE,MISS]),MISS)
        self.assertEqual(aggregate([PRE,AUTH]),AUTH);self.assertEqual(aggregate([MISS,CONFLICT]),CONFLICT)
    def test_same_uid_different_case_kept_separate(self):
        self.assertEqual(len({('d/B0','1'),('d/B1','1')}),2)
    def test_duplicate_raw_conflict(self):
        a={'uid':'1','domain':'KESTREL','actual_start':'a','actual_end':'b','nodes':['n1'],'gpus_requested':4}
        groups,conflicts=deduplicate_raw([a,{**a,'actual_end':'c'}]);self.assertEqual(len(groups),1);self.assertEqual(len(conflicts),1)
    def test_duplicate_raw_identical_corroboration(self):
        a={'uid':'1','domain':'KESTREL','actual_start':'a','actual_end':'b'}
        self.assertFalse(deduplicate_raw([a,copy.deepcopy(a)])[1])
    def test_v40l_guard(self):
        for path in ['C:/x/dayahead/v40l/data.json','C:/x/V40L_TEST.txt']:
            with self.assertRaises(ValueError):guard(path)

if __name__=='__main__':unittest.main()
