import unittest
from core import *
from prepare import overlap,H
class Contracts(unittest.TestCase):
    def test_submit_lifetime_vs_execution(self):
        # 14:20, 4 GPUs, 2.5 hours: ten GPUh in submit bin, split execution.
        start=np.array([14*H+H//3]);end=start+int(2.5*H)
        y=overlap(start,end,np.array([4.]),np.arange(25)*H)
        self.assertAlmostEqual(y.sum(),10)
        self.assertAlmostEqual(y[14],8/3);self.assertAlmostEqual(y[15],4)
        self.assertAlmostEqual(y[16],10/3)
    def test_half_open_and_mass(self):
        y=overlap(np.array([-H,0,H]),np.array([0,H,2*H]),np.ones(3),np.arange(9)*(H//4))
        np.testing.assert_array_equal(y,np.full(8,.25))
    def test_baseline_replay(self):
        a=np.load(ROOT/'A0_PREDICTIONS.npz')['q'];b=np.load(P21/'predictions/LGBM_weighted_c1_s20260924.npz')['q']
        np.testing.assert_array_equal(a[OOS],b[OOS])
    def test_feature_arrays_and_unavailable_state(self):
        z=np.load(ROOT/'FEATURES.npz')
        for t in ['T0','T1','T2','T3']:
            x=np.repeat(X0,4,axis=1) if t=='T3' else X0
            for f in range(6):np.testing.assert_array_equal(z[f'{t}_F{f}'][...,:71],x)
            np.testing.assert_array_equal(z[t+'_F0'],z[t+'_F3'])
    def test_lags_and_issue_boundary(self):
        f=pd.read_parquet(ROOT/'FEATURE_CAUSAL_AVAILABILITY.parquet')
        self.assertTrue(f.valid.all());u=f[f.available&f.max_read_ns.notna()]
        self.assertTrue((u.max_read_ns<=u.issue_ns).all())
        for t in ['T0','T1']:
            # D-1 18:00 issue: same-clock previous-day 18..23 hours cannot be read.
            forbidden=f[f.target.eq(t)&f.feature.eq('same_clock_1d')&f.slot.ge(18)]
            self.assertFalse(forbidden.available.any())
        unavailable=f[~f.available];self.assertTrue((unavailable.value==0).all())
    def test_target_maturity_and_conservation(self):
        z=np.load(ROOT/'TARGETS.npz');np.testing.assert_array_equal(z['T0'],Y0)
        np.testing.assert_allclose(z['T3'].reshape(-1,24,4).mean(2),z['T2'],atol=1e-10,rtol=1e-13)
        for t in ['T0','T1','T2','T3']:
            self.assertTrue(np.isfinite(z[t]).all());self.assertTrue((z[t]>=0).all())
            end=np.array([(pd.Timestamp(str(x),tz=TZ)+pd.Timedelta(days=1)).value for x in DAYS])
            self.assertTrue((z['maturity_'+t].max(1)>=end).all())
    def test_frozen_roles(self):
        self.assertEqual(len(role_ids('OOS_EXTENSION')),63)
        self.assertFalse(L.loc[L.split.eq('OOS_EXTENSION'),'eligible'].any())
        self.assertEqual(len(DEV),58);self.assertEqual(len(CAL),26)
if __name__=='__main__':unittest.main(verbosity=2)
