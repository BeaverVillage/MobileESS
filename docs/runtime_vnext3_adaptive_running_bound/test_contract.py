import unittest
import numpy as np
import pandas as pd
from study import features,eligible_history,bound,select_threshold,paired

class Contract(unittest.TestCase):
    def sample(self):
        return pd.DataFrame(dict(job_id=['a','b'],job_issue_id=['a@1','b@2'],state=['RUNNING']*2,
            issue_time=pd.to_datetime(['2025-01-01','2025-01-02'],utc=True),end_time=pd.to_datetime(['2025-01-03','2025-01-04'],utc=True),
            actual_seconds=[1800.,18000.],runtime_seconds=[1800.,36000.],Q90=[900.,21000.],Q95=[1900.,23000.],
            elapsed_seconds=[600.,18000.],requested_seconds=[3600.,43200.],num_gpus_req=[4.,1.],partition=['a100','h100'],qos=['normal','standby'],risk_probability=[.2,.8]))
    def test_exact_quantile_assignment_and_elapsed_features(self):
        f=self.sample();r=bound(f,'R3',.5);self.assertEqual(r.bound_seconds.tolist(),[900.,23000.])
        x=features(f);f.elapsed_seconds+=600;self.assertFalse(np.array_equal(x,features(f)))
    def test_features_ignore_outcome_columns(self):
        f=self.sample();x=features(f);f.actual_seconds=987654321;f.runtime_seconds=987654321;f.end_time=pd.NaT
        np.testing.assert_array_equal(x,features(f))
    def test_maturity_strict_and_latest_job(self):
        f=self.sample();self.assertEqual(len(eligible_history(f,pd.Timestamp('2025-01-03',tz='UTC'))),0)
        old=f.iloc[[0]].copy();old.issue_time-=pd.Timedelta(hours=1);old.job_issue_id='earlier'
        got=eligible_history(pd.concat([old,f]),pd.Timestamp('2025-01-05',tz='UTC'))
        self.assertEqual(got.job_issue_id.tolist(),['a@1','b@2'])
    def table(self):
        return pd.DataFrame([dict(role=r,threshold=t,coverage=.91,GPU_coverage=.91,long_under=.1,
            overreserved_GPUh=5,requested_overreserved_GPUh=10,reserve_vs_requested=1-t/10)
            for r in ['DEVELOPMENT','CALIBRATION'] for t in [.1,.2]])
    def test_selection_reserve_and_nan_fail_closed(self):
        f=self.table();self.assertEqual(select_threshold(f)[0]['threshold'],.2)
        for column in ['coverage','GPU_coverage','long_under','overreserved_GPUh','requested_overreserved_GPUh','reserve_vs_requested']:
            g=f.copy();g.loc[0,column]=np.nan
            with self.assertRaises(AssertionError):select_threshold(g)
    def test_fallback_min_safety_deficit(self):
        f=self.table();f.loc[f.threshold.eq(.1),'coverage']=.85;f.loc[f.threshold.eq(.2),'coverage']=.89
        winner,_=select_threshold(f);self.assertEqual(winner['threshold'],.2);self.assertFalse(winner['safety_pass'])
    def test_paired_identical_bound_ratios_zero(self):
        f=bound(self.sample(),'R1')
        for r in paired(f,f,1):
            self.assertEqual(r['estimate'],0.)
            self.assertEqual(r['CI95_low'],0.);self.assertEqual(r['CI95_high'],0.)

if __name__=='__main__':unittest.main()
