"""Meaningful fail-closed boundary controls, no model training."""
import unittest
from common import *
from prepare import history, eligible
from report import block_indices, bootstrap


class ContractTests(unittest.TestCase):
    def test_clock_and_twenty_four_leads(self):
        start=pd.Timestamp('2025-05-01',tz=TZ)
        origin=issue('2025-05-01')
        self.assertEqual(origin.hour,18)
        self.assertEqual(origin.day,30)
        self.assertEqual([(start+pd.Timedelta(hours=h)-origin).total_seconds()/3600 for h in range(24)],list(range(6,30)))

    def test_finite_sample_day_rank_and_no_upper_cap(self):
        y=np.repeat(np.arange(26)[:,None],24,axis=1).astype(float)+10000
        delta,rank=finite_residual(y,np.zeros_like(y))
        self.assertEqual(rank,25)
        self.assertTrue(np.all(delta==10024))
        q=corrected(np.zeros((1,24,2)),delta)
        self.assertTrue(np.all(q[...,1]>3120))
        with self.assertRaises(AssertionError):finite_residual(y[:2],y[:2])

    def test_signed_correction_preserves_quantile_order(self):
        q=np.zeros((24,2));q[:,0]=5;q[:,1]=10
        out=corrected(q,np.full(24,-100.))
        self.assertTrue(np.all(out==5))

    def test_future_runtime_is_masked(self):
        origin=pd.Timestamp('2024-08-31 08:00Z')
        ix=pd.DatetimeIndex([origin-pd.Timedelta(minutes=30)])
        b=pd.DataFrame(dict(submit_count=[2],max_observed_end=[origin+pd.Timedelta(hours=1)],
                            unresolved_end_count=[0],work_GPUh=[999999]),index=ix)
        before,_=history(b,ix,origin)
        b.max_observed_end=origin+pd.Timedelta(days=100)
        b.work_GPUh=1e30
        after,_=history(b,ix,origin)
        self.assertTrue(np.array_equal(before,after))
        self.assertEqual(before[0,1],0)
        self.assertEqual(before[0,2],0)

    def test_maturity_equality_and_future_bins(self):
        origin=pd.Timestamp('2024-08-31 08:00Z');ix=pd.DatetimeIndex([origin-pd.Timedelta(minutes=30)])
        b=pd.DataFrame(dict(submit_count=[1],max_observed_end=[origin],unresolved_end_count=[0],work_GPUh=[10]),index=ix)
        out,_=history(b,ix,origin)
        self.assertEqual(out[0,1],10)  # feature maturity <= issue; labels use strict < elsewhere
        with self.assertRaises(AssertionError):history(b,ix,origin-pd.Timedelta(minutes=1))

    def test_population_predicate(self):
        submit=pd.Timestamp('2024-01-01',tz='UTC')
        r=pd.DataFrame(dict(gpus_requested=[4,0,np.nan,4,4],submit_time=[submit]*5,
             start_time=[submit,submit,submit,submit,submit-pd.Timedelta(hours=1)],
             end_time=[submit+pd.Timedelta(hours=2.5),submit+pd.Timedelta(hours=1),submit+pd.Timedelta(hours=1),pd.NaT,submit]))
        self.assertEqual(eligible(r).tolist(),[True,False,False,False,False])
        self.assertEqual((r.loc[0,'end_time']-r.loc[0,'start_time']).total_seconds()/3600*r.loc[0,'gpus_requested'],10)

    def test_block_resampling_keeps_day_units(self):
        days=['2024-10-26','2024-10-27','2024-10-29','2024-10-30']
        ix=block_indices(days,np.random.default_rng(7),draws=20)
        self.assertEqual(ix.shape,(20,4))
        self.assertTrue((ix[:,:2]<2).all())
        self.assertTrue((ix[:,2:]>=2).all())

    def test_paired_identical_models_have_zero_uncertainty_delta(self):
        rows=[]
        for family in ['LGBM','TFT']:
            for day in pd.date_range('2025-01-01',periods=10):
                rows.append(dict(split='TEST',variant='calibrated',model=family,target_day=str(day.date()),
                    Q90_coverage=.9,Q90_pinball=float(day.day),Q90_sum_GPUh=200.,actual_GPUh=100.))
        result=bootstrap(pd.DataFrame(rows))
        self.assertEqual(len(result),3)
        self.assertTrue(np.all(result[['delta','CI95_low','CI95_high']].to_numpy()==0))


if __name__=='__main__':unittest.main()
