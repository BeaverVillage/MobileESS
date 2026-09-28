import unittest
from study import *
class Contracts(unittest.TestCase):
    def test_known_additive_and_scaled_residual(self):
        y=np.full((len(c.DAYS),8),6.);q=np.empty((len(c.DAYS),8,2));q[...,0]=2;q[...,1]=4
        for method in ['HORIZON_ADD','HORIZON_LOCAL_SCALE']:
            cf=coefficients(y,q,np.arange(26),method);pred=correct(q[30],6,cf,method)
            np.testing.assert_array_equal(pred[:,1],np.full(8,6.));np.testing.assert_array_equal(pred[:,0],q[30,:,0])
    def test_ordering_not_upper_cap(self):
        q=np.tile([2.,4.],(8,1));a=correct(q,6,[-10]*4,'HORIZON_ADD');b=correct(q,6,[100]*4,'HORIZON_ADD')
        np.testing.assert_array_equal(a[:,1],np.full(8,2.));np.testing.assert_array_equal(b[:,1],np.full(8,104.))
    def test_full_bank_maturity(self):
        p=pd.read_csv(ROOT/'CALIBRATION_CAUSAL_PROOF.csv');known=p.latest_maturity_ns.notna()
        self.assertTrue((p.loc[known,'latest_maturity_ns']<p.loc[known,'issue_ns']).all());self.assertTrue((p['count']<=26).all());self.assertTrue((p.used==(p['count']>=20)).all())
    def test_identical_paired_draws(self):
        y=np.full((8,8),3.);q=np.stack([y,y+1],axis=-1);a=previous_report.daystats(y,q,1,2)
        for r in previous_report.paired(a,a):self.assertEqual(r['delta'],0);self.assertEqual(r['CI_low'],0);self.assertEqual(r['CI_high'],0)
    def test_finalists_no_evaluation_selection(self):
        f=read(ROOT/'FINALIST_FREEZE.json');self.assertFalse(f['May_used']);self.assertFalse(f['evaluation_used']);self.assertLessEqual(len(f['finalists']),2)
        b=pd.read_csv(ROOT/'MODEL_STAGE_B_CALIBRATION_METRICS.csv')
        for arm,v in f['finalists'].items():
            r,band=choose(b[b.arm.eq(arm)&b.role.eq('CALIBRATION')]);self.assertEqual(r.method,v['method']);self.assertEqual(band,v['CAL_nominal_band_met'])
if __name__=='__main__':unittest.main(verbosity=2)
