import unittest
import numpy as np
import pandas as pd
from calibrate import choose_alpha,rolling_cal
from common import metrics
from evaluate import nondominated

class DurationTests(unittest.TestCase):
    def test_lowest_duration_meeting_90(self):
        f=pd.DataFrame(dict(runtime_seconds=[5.]*9+[10.],q50=[0.]*10,q90=[10.]*10))
        chosen,_,unattainable=choose_alpha(f,np.arange(21)/20)
        self.assertEqual(chosen['alpha'],.5);self.assertFalse(unattainable)
    def test_unattainable_never_relaxes_target(self):
        f=pd.DataFrame(dict(runtime_seconds=[20.,30.],q50=[1.,2.],q90=[10.,15.]))
        c,_,u=choose_alpha(f,np.arange(21)/20)
        self.assertTrue(u);self.assertEqual(c['coverage'],0);self.assertEqual(c['alpha'],0)
    def test_unattainable_chooses_highest_coverage(self):
        f=pd.DataFrame(dict(runtime_seconds=[5.,30.],q50=[1.,2.],q90=[10.,15.]))
        c,_,u=choose_alpha(f,np.arange(21)/20)
        self.assertTrue(u);self.assertEqual(c['coverage'],.5);self.assertEqual(c['alpha'],.45)
    def test_gpu_weights_cannot_change_primary(self):
        f=pd.DataFrame(dict(runtime_seconds=[3.,9.],q50=[2.,4.],q90=[5.,15.]))
        before=metrics(f);choice=choose_alpha(f,np.arange(21)/20)[0]
        f['num_gpus_req']=[1e100,0.];f['gpu']=[0.,1e200]
        self.assertEqual(metrics(f),before);self.assertEqual(choose_alpha(f,np.arange(21)/20)[0],choice)
    def test_seconds_ratio_not_mean_job_ratio(self):
        f=pd.DataFrame(dict(runtime_seconds=[1.,100.],q50=[10.,100.],q90=[20.,200.]))
        self.assertAlmostEqual(metrics(f)['TIME_RATIO_Q50'],110/101)
        self.assertNotEqual(metrics(f)['TIME_RATIO_Q50'],5.5)
    def test_zero_runtime_retained_without_division(self):
        f=pd.DataFrame(dict(runtime_seconds=[0.,10.],q50=[3.,5.],q90=[4.,12.]))
        m=metrics(f);self.assertEqual(m['zero_runtime_N'],1);self.assertEqual(m['TIME_RATIO_Q50'],.8)
    def test_alpha_endpoints(self):
        a=np.array([0,3,7.]);b=np.array([2,3,12.])
        np.testing.assert_array_equal(a+0*(b-a),a);np.testing.assert_array_equal(a+1*(b-a),b)
    def test_future_cal_label_cannot_change_earlier_shift(self):
        f=pd.DataFrame(dict(submit_time=pd.to_datetime(['2024-10-18T00Z']*200+['2024-10-19T00Z','2024-10-20T00Z']),end_time=pd.to_datetime(['2024-10-18T12Z']*200+['2024-10-20T00Z','2024-10-21T00Z']),event=[True]*202,runtime_seconds=[20.]*202))
        q=np.tile([1.,2.,3.,10.,11.],(202,1));original,_=rolling_cal(f,q)
        f.loc[201,'runtime_seconds']=1e20;changed,audit=rolling_cal(f,q)
        np.testing.assert_array_equal(original,changed)
        self.assertEqual(audit[1]['residual_N'],200);self.assertEqual(audit[2]['residual_N'],200)
        self.assertEqual(original[200,1],20.)
    def test_pareto_strict_dominance_and_ties(self):
        f=pd.DataFrame([[1,.9,.9,.8,2],[2,.8,.8,.7,3],[1,.9,.9,.8,2]],columns=['Q50_MAE_hours','OP_coverage','min_fold_OP_coverage','GT12H_OP_coverage','TIME_RATIO_OP'])
        self.assertEqual(nondominated(f),[True,False,True])
if __name__=='__main__':unittest.main(verbosity=2)
