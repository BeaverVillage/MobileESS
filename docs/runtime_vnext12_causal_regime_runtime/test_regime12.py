import unittest
import numpy as np
import pandas as pd
from regime12 import window_stats,completed

class CausalityTests(unittest.TestCase):
    def test_ties_boundaries_future_and_current(self):
        t=pd.Timestamp('2024-10-10T00Z')
        events=pd.DataFrame(dict(end_time=[t-pd.Timedelta(days=7),t-pd.Timedelta(seconds=1),t,t,t+pd.Timedelta(seconds=1)],
            runtime=[2.,8.,1e8,2e8,3e8],num_gpus_req=[1.]*5,requested_seconds=[10.]*5))
        s=window_stats(events,[t,t],7)
        np.testing.assert_array_equal(s.N,[2,2])
        np.testing.assert_array_equal(s.runtime_q50,[5,5])
        self.assertEqual(s.oldest_age_seconds.iloc[0],7*86400)
        altered=events.copy();altered.loc[2:,'runtime']=1e20
        pd.testing.assert_frame_equal(s,window_stats(altered,[t,t],7))
        pd.testing.assert_frame_equal(s,window_stats(events.iloc[:2],[t,t],7))
    def test_bruteforce_and_empty(self):
        rng=np.random.default_rng(4012);origin=pd.Timestamp('2024-01-01T00Z')
        times=np.sort(rng.integers(0,100*86400,2000))
        e=pd.DataFrame(dict(end_time=origin+pd.to_timedelta(times,unit='s'),runtime=rng.integers(0,200000,2000).astype(float),
                            num_gpus_req=rng.integers(1,33,2000),requested_seconds=np.full(2000,86400.)))
        q=origin+pd.to_timedelta(np.sort(rng.integers(0,110*86400,100)),unit='s')
        for days in [7,14,30]:
            s=window_stats(e,q,days)
            for i,t in enumerate(q):
                f=e[e.end_time.lt(t)&e.end_time.ge(t-pd.Timedelta(days=days))]
                self.assertEqual(s.N.iloc[i],len(f))
                if len(f):
                    self.assertAlmostEqual(s.runtime_q90.iloc[i],f.runtime.quantile(.9))
                    self.assertAlmostEqual(s.gt4h_rate.iloc[i],(f.runtime>14400).mean())
                    self.assertAlmostEqual(s.total_GPUh.iloc[i],(f.runtime*f.num_gpus_req/3600).sum())
            z=window_stats(e.iloc[:0],q,days)
            self.assertTrue((z.N==0).all());self.assertTrue(z.runtime_q50.isna().all())
    def test_visibility_precedes_subtraction(self):
        t=pd.Timestamp('2024-01-01T00Z')
        f=pd.DataFrame(dict(job_id=['current','future','past'],submit_time=[t,t,t-pd.Timedelta(days=1)],
                            start_time=[t,t,t-pd.Timedelta(days=1)],end_time=[t,t+pd.Timedelta(days=1),t-pd.Timedelta(seconds=1)]))
        e=completed(f,t)
        self.assertEqual(list(e.job_id),['past'])

if __name__=='__main__':unittest.main()
