import unittest
import numpy as np
import pandas as pd
from common12 import *
from regime12 import resolve,GLOBAL_STATS,META,prior_frame,make_prior,completed,materialize,ReplayState
from model12 import columns
from hazard10 import Hazard

class Contracts(unittest.TestCase):
    def test_fallback_not_zero_and_exact_support(self):
        base={c:np.ones(3) for c in GLOBAL_STATS}
        base.update(N=[20,300,0],tail_N=[1,30,0],ratio_N=[20,300,0],newest_age_seconds=[1,2,np.nan],oldest_age_seconds=[100,200,np.nan])
        a=pd.DataFrame(base);b=a.copy();b['N']=[800,0,0];b['ratio_N']=[800,0,0];b['tail_N']=[40,0,0];b['runtime_q90']=[1234,0,0]
        z=resolve([(a,200),(b,200)],GLOBAL_STATS)
        self.assertEqual(z.loc[0,'fallback_depth'],1)
        self.assertEqual(z.loc[0,'raw_N'],20)
        self.assertEqual(z.loc[0,'support_N'],800)
        self.assertEqual(z.loc[0,'runtime_q90'],1234)
        self.assertEqual(z.loc[1,'fallback_depth'],0)
        self.assertEqual(z.loc[2,'fallback_depth'],-1)
        self.assertTrue(pd.isna(z.loc[2,'runtime_q90']))

    def test_prior_is_not_available_to_earlier_train(self):
        t=pd.Timestamp('2024-03-01T00Z')
        prior=dict(stats={c:1 for c in GLOBAL_STATS},available_at=(t+pd.Timedelta(nanoseconds=1)).isoformat(),newest_end=t.isoformat(),oldest_end=(t-pd.Timedelta(days=1)).isoformat())
        z=prior_frame(prior,[t-pd.Timedelta(days=1),t,t+pd.Timedelta(seconds=1)])
        self.assertTrue(z.iloc[:2].isna().all().all())
        self.assertEqual(z.runtime_q90.iloc[2],1)

    def test_full_engine_future_cohort_and_current_outcome_invariance(self):
        t=pd.Timestamp('2024-03-01T00Z')
        ends=t+pd.to_timedelta(np.arange(220)*60,unit='s')
        history=pd.DataFrame(dict(job_id=[f'past_{i}' for i in range(220)],end_time=ends,
            start_time=ends-pd.Timedelta(seconds=20000),submit_time=ends-pd.Timedelta(seconds=21000),
            runtime=np.full(220,20000.),num_gpus_req=np.full(220,4.),requested_seconds=np.full(220,60000.),
            qos=['normal']*220,partition=['gpu']*220))
        time=t+pd.Timedelta(days=1);prior=make_prior(history,time)
        q=pd.DataFrame(dict(job_id=['current'],prediction_time=[time],partition=['gpu'],qos=['normal'],
            num_gpus_req=[4.],requested_seconds=[60000.]))
        expected=materialize(history,q,prior)
        future=history.iloc[:2].copy();future.job_id=['current','future'];future.end_time=[time,time+pd.Timedelta(days=1)]
        future.runtime=1e20;future.partition=['gpu','never_seen_future_category']
        augmented=pd.concat([history,future],ignore_index=True)
        pd.testing.assert_frame_equal(expected,materialize(augmented,q,prior),check_exact=True)
        q['runtime_seconds']=1e30;q['end_time']=pd.Timestamp('2099-01-01T00Z')
        pd.testing.assert_frame_equal(expected,materialize(history,q,prior),check_exact=True)
        state=ReplayState(history,prior)
        with self.assertRaises(ValueError):state.append_completed(future,time)

    def test_ablation_removes_derived_features(self):
        c=['g7__runtime_q90','g7__gt4h_rate','g7__tail_N','c_qos_14__ratio_q50','c_qos_14__ratio_N','trend__q90_7_minus_30','trend__ratio_14_minus_30']
        a=columns('EXPANDING_R3',['requested_seconds'],c,'A')
        self.assertNotIn('trend__q90_7_minus_30',a)
        b=columns('EXPANDING_R3',[],c,'B');self.assertNotIn('g7__tail_N',b)
        cc=columns('EXPANDING_R3',[],c,'C');self.assertFalse(any('ratio_' in name for name in cc))
        self.assertEqual(columns('EXPANDING_R0',['requested_seconds'],c),['requested_seconds'])

    def test_positive_distribution_and_extreme_log_survival(self):
        m=Hazard(dict(edges=[0,15,900,14400,86400],tail_exponential_rate=None),None)
        p=np.array([[1e-9,1e-8,1e-7,1e-6],[.1,.01,.001,.001]])
        q=np.column_stack([m.inverse_logsf(p,np.log1p(-a)) for a in [.5,.9]])
        self.assertTrue((q[:,1]>q[:,0]).all())
        for t in [0,1,900,1e8]:
            dh=m.interval_hazard(p,np.maximum(t-.5,0),np.full(2,t+.5))
            ll=m.logsf(p,np.maximum(t-.5,0))+np.log(-np.expm1(-dh))
            self.assertTrue(np.isfinite(ll).all())
        elapsed=np.array([1e8,1e8]);remaining=m.inverse_logsf(p,m.logsf(p,elapsed)+np.log(.1))-elapsed
        self.assertTrue((remaining>0).all())
        np.testing.assert_allclose(m.logsf(p,elapsed+remaining)-m.logsf(p,elapsed),np.log(.1),rtol=1e-10)

if __name__=='__main__':unittest.main()
