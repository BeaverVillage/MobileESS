import unittest
import numpy as np
import pandas as pd
from scipy.stats import norm
from censor_proxy import asof_rows,weight,FEATURES
from study import choose,paired

class Contract(unittest.TestCase):
    def jobs(self):
        f=pd.DataFrame(dict(row_id=np.arange(4),job_id=['done','future','unknown','equal'],
            submit_time=pd.to_datetime(['2025-01-01']*4,utc=True),start_time=pd.to_datetime(['2025-01-01']*4,utc=True),
            end_time=pd.to_datetime(['2025-01-04','2025-01-06',None,'2025-01-05'],utc=True)))
        for c in FEATURES:f[c]=2. if c not in ['partition','qos','user','account'] else 'known'
        return f
    def test_strict_censor_semantics_and_null_retention(self):
        t=pd.Timestamp('2025-01-05',tz='UTC');f=asof_rows(self.jobs(),t).set_index('job_id')
        self.assertEqual(set(f.index),{'done','future','unknown','equal'})
        self.assertFalse(f.loc['done','right_censored']);self.assertEqual(f.loc['done','label_lower'],f.loc['done','label_upper'])
        for key in ['future','unknown','equal']:
            self.assertTrue(f.loc[key,'right_censored']);self.assertTrue(np.isinf(f.loc[key,'label_upper']));self.assertTrue(pd.isna(f.loc[key,'observed_end']))
    def test_future_end_mutation_cannot_change_training_view_or_weights(self):
        j=self.jobs();t=pd.Timestamp('2025-01-05',tz='UTC');a=asof_rows(j,t)
        j.loc[j.job_id.isin(['future','equal']),'end_time']=pd.Timestamp('2099-01-01',tz='UTC')
        j['runtime_seconds']=999999999;j['label_valid']=False
        b=asof_rows(j,t);pd.testing.assert_frame_equal(a,b)
        np.testing.assert_array_equal(weight(a,t)[0],weight(b,t)[0])
    def test_gpu_weight_sum_and_asof_long_factor(self):
        t=pd.Timestamp('2025-01-05',tz='UTC');f=asof_rows(self.jobs(),t);w,normalizer=weight(f,t)
        recency=np.exp(-np.log(2)/14*(t-f.observation_time).dt.total_seconds()/86400)
        self.assertAlmostEqual(w.sum(),recency.sum());self.assertGreater(normalizer,0)
    def test_aft_remaining_quantiles_without_scaling(self):
        median=3600.;q=np.exp(np.log(median)+norm.ppf([.5,.9,.95]))
        self.assertAlmostEqual(q[0],median);self.assertTrue((np.diff(q)>0).all())
    def table(self):
        return pd.DataFrame([dict(arm=a,role=r,coverage=.91,GPU_coverage=.92,long_under=.1,overreserved_GPUh=5.,requested_overreserved_GPUh=10.,reserve_vs_requested=.8 if a=='R2' else.9) for a in ['R1','R2','R3'] for r in ['DEVELOPMENT','CALIBRATION']])
    def test_selection_safety_both_splits_and_nan_fail_closed(self):
        f=self.table();self.assertEqual(choose(f)[0],'R2');f.loc[f.role.eq('CALIBRATION'),'GPU_coverage']=.89;self.assertEqual(choose(f)[0],'R0')
        f=self.table();f.loc[0,'long_under']=np.nan
        with self.assertRaises(AssertionError):choose(f)
    def test_paired_identical_bounds_zero_differences(self):
        f=pd.DataFrame(dict(job_issue_id=['a','b'],issue_time=pd.to_datetime(['2025-01-01','2025-01-02'],utc=True),actual_seconds=[1800.,18000.],runtime_seconds=[20000.,36000.],bound_seconds=[900.,10000.],num_gpus_req=[4.,2.],requested_seconds=[3600.,43200.],elapsed_seconds=[0.,18000.]))
        for r in paired(f,f,1):
            self.assertEqual(r['estimate'],0.);self.assertEqual(r['CI95_low'],0.);self.assertEqual(r['CI95_high'],0.)

if __name__=='__main__':unittest.main()
