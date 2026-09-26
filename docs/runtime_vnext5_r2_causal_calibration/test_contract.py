import unittest
import numpy as np
import pandas as pd
import study as s
class Contract(unittest.TestCase):
    def catalog(self):
        return pd.DataFrame(dict(job_id=['a','a','b','c','d','e'],job_issue_id=['a0','a1','b0','c0','d0','e0'],issue_time=pd.to_datetime(['2025-01-01','2025-01-02','2025-01-01','2025-01-01','2025-01-05','2025-01-01'],utc=True),end_time=pd.to_datetime(['2025-01-03','2025-01-03','2025-01-05','2025-01-06','2025-01-06','2025-01-03'],utc=True),label_valid=[True,True,True,True,True,False],raw_Q90=[100.,200.,300.,400.,500.,600.],num_gpus_req=[1.,1.,2.,2.,4.,1.]))
    def test_strict_maturity_then_latest_job_dedup_source_residual(self):
        f,n=s.pool_at(self.catalog(),pd.Timestamp('2025-01-05',tz='UTC'))
        self.assertEqual(n,2);self.assertEqual(f.job_issue_id.tolist(),['a1']);self.assertEqual(f.residual_seconds.iloc[0],86400-200)
        self.assertTrue(f.job_id.is_unique)
    def test_future_label_changes_do_not_change_current_pool(self):
        f=self.catalog();a,n=s.pool_at(f,pd.Timestamp('2025-01-05',tz='UTC'));f.loc[f.job_id.isin(['b','c','d']),'end_time']=pd.Timestamp('2099-01-01',tz='UTC');b,m=s.pool_at(f,pd.Timestamp('2025-01-05',tz='UTC'))
        pd.testing.assert_frame_equal(a,b);self.assertEqual(n,m)
    def test_inverse_ecdf_exact_unweighted_and_gpu_rank(self):
        self.assertEqual(s.inverse_ecdf(np.arange(1,11),np.ones(10)),9)
        self.assertEqual(s.inverse_ecdf([1.,3.,7.],[1.,1.,8.]),7.)
        self.assertEqual(s.inverse_ecdf([1.,3.,7.],[9.,.5,.5]),1.)
        with self.assertRaises(AssertionError):s.inverse_ecdf([1,2],[1,0])
        with self.assertRaises(AssertionError):s.inverse_ecdf([1,np.nan],[1,1])
    def test_support_after_dedup_and_one_sided_without_scaling(self):
        p=pd.DataFrame({'residual_seconds':np.full(99,10.),'num_gpus_req':np.ones(99)})
        self.assertEqual(s.corrections(p),{'R1':0.,'R2':0.,'R3':0.})
        p=pd.DataFrame({'residual_seconds':np.full(100,-10.),'num_gpus_req':np.ones(100)})
        self.assertEqual(s.corrections(p),{'R1':0.,'R2':0.,'R3':0.})
        p.residual_seconds=10.;self.assertEqual(s.corrections(p),{'R1':0.,'R2':10.,'R3':10.})
    def table(self):
        return pd.DataFrame([dict(role=role,arm=arm,coverage=.91,GPU_coverage=.91,long_under=.1,pinball_Q90=100.,overreserved_GPUh=2.,requested_overreserved_GPUh=1.,reserve_vs_requested=2.) for role in s.PRE for arm in s.ARMS])
    def test_selection_pinball_margin_and_preferred_not_hard_reserve(self):
        f=self.table();self.assertEqual(s.choose(f)[0],'R2')
        f.loc[f.arm.eq('R2')&f.role.eq('CALIBRATION'),'pinball_Q90']=103.;self.assertEqual(s.choose(f)[0],'R3')
        f.loc[f.arm.eq('R3')&f.role.eq('DEVELOPMENT'),'GPU_coverage']=.89;self.assertEqual(s.choose(f)[0],'R1')
        f.loc[f.arm.eq('R2'),'coverage']=np.nan
        with self.assertRaises(AssertionError):s.choose(f)
        f=self.table();f.loc[f.arm.eq('R1'),'pinball_Q90']=np.inf
        with self.assertRaises(AssertionError):s.choose(f)
    def test_paired_identity_and_total_long_definition(self):
        f=pd.DataFrame(dict(job_issue_id=['a','b'],issue_time=pd.to_datetime(['2025-01-01','2025-01-02'],utc=True),actual_seconds=[3600.,7200.],bound_seconds=[1800.,9000.],runtime_seconds=[18000.,7200.],requested_seconds=[30000.,30000.],elapsed_seconds=[14400.,0.],num_gpus_req=[4.,1.]))
        self.assertEqual(s.stats(f)['long_under'],1.)
        for r in s.paired(f,f,1):
            self.assertEqual(r['estimate'],0.);self.assertEqual(r['CI95_low'],0.);self.assertEqual(r['CI95_high'],0.)
if __name__=='__main__':unittest.main()
