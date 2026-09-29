import unittest
from common import *
from audit import pareto
def frame(y,q):return pd.DataFrame(dict(runtime_seconds=y,q50=q,q90=np.asarray(q)+100))
class AuditTests(unittest.TestCase):
    def test_ties_are_covered(self):
        m=metrics(frame([0,1,2,3],[0,1,1,4]));self.assertEqual(m['Q50_coverage'],.75);self.assertEqual(m['Q50_underprediction_fraction'],.25)
    def test_median_target_not_90(self):
        m=metrics(frame([1,3],[2,2]));self.assertEqual(m['Q50_coverage'],.5);self.assertEqual(m['Q50_calibration_error'],0)
    def test_zero_handling(self):
        f=frame([0,2],[4,2]);self.assertEqual(metrics(f)['Q50_time_ratio'],3);self.assertEqual(ratios(f)['median'],1);self.assertEqual(ratios(f)['zero_runtime_excluded_N'],1)
    def test_undefined_empty_and_zero_only_ratio(self):
        self.assertIsNone(metrics(frame([0],[4]))['Q50_time_ratio']);self.assertIsNone(metrics(frame([],[]))['Q50_coverage']);self.assertIsNone(ratios(frame([0],[4]))['median'])
    def test_aggregate_not_job_median(self):
        f=frame([1,1,100],[10,10,100]);self.assertEqual(ratios(f)['median'],10);self.assertAlmostEqual(metrics(f)['Q50_time_ratio'],120/102)
    def test_outcome_buckets_partition_boundaries(self):
        f=frame([0,1,900,901,3600,3601,14400,14401,43200,43201,86400,86401],[1]*12)
        counts=[int(((f.runtime_seconds>lo)&(f.runtime_seconds<=hi)).sum()) for _,lo,hi in BUCKETS]
        self.assertEqual(counts,[2,2,2,2,2,1]);self.assertEqual(sum(counts)+f.runtime_seconds.eq(0).sum(),12)
    def test_gpu_metadata_does_not_affect_primary(self):
        f=frame([1,20],[4,10]);m=metrics(f);f['gpu']=[1e100,0];self.assertEqual(m,metrics(f))
    def test_coverage_closeness_is_two_sided(self):
        low=metrics(frame([1,2,3,4],[0,0,0,0]));high=metrics(frame([1,2,3,4],[5]*4));self.assertEqual(low['Q50_calibration_error'],high['Q50_calibration_error'])
    def test_pareto_no_automatic_selection(self):
        self.assertEqual(pareto([[1,2,3],[2,3,4],[1,2,3],[3,1,2]]),[True,False,True,True])
if __name__=='__main__':unittest.main(verbosity=2)
