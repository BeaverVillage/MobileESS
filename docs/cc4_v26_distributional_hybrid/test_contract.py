import unittest
import numpy as np
from scipy.stats import lognorm
import distribution as d
import study as s


class Contract(unittest.TestCase):
    def test_zero_mass(self):
        np.testing.assert_array_equal(d.quantiles([0,.1,.5],[1,1,1],2),[[0,0],[0,0],[0,d.quantiles([.5],[1],2)[0,1]]])
    def test_exact_distribution_inverse(self):
        p=np.array([.15,.4,.8,1.]);mu=np.array([-3,1,4,8.]);sigma=2.7
        q=d.quantiles(p,mu,sigma)
        for k,tau in enumerate([.5,.9]):
            mask=tau>1-p
            np.testing.assert_allclose(q[mask,k],lognorm.ppf((tau-1+p[mask])/p[mask],s=sigma,scale=np.exp(mu[mask])),rtol=1e-14)
            np.testing.assert_allclose(d.cdf(q[:,k],p,mu,sigma)[mask],tau,atol=1e-14)
    def test_cdf_distribution(self):
        yy=np.r_[-1,0,np.geomspace(.0001,1e9,100)]
        f=d.cdf(yy,.7,2.,1.5)
        self.assertTrue((np.diff(f)>=0).all());self.assertEqual(f[0],0);self.assertAlmostEqual(f[1],.3);self.assertAlmostEqual(f[-1],1)
    def test_invalid_parameters_fail(self):
        for p,mu,sigma in [(1.1,0,1),(-.1,0,1),(.5,np.inf,1),(.5,0,0),(.5,0,np.nan)]:
            with self.assertRaises(ValueError):d.quantiles(p,mu,sigma)
    def test_nonfinite_not_capped(self):
        with self.assertRaises((ValueError,FloatingPointError)):d.quantiles(1.,1000.,1.)
    def test_no_normal_hour_change(self):
        base=np.array([[2.,4.],[3.,6.]]);tail=np.array([[20.,40.],[30.,60.]])
        np.testing.assert_array_equal(d.hybrid(base,tail,np.array([.09,.2]),.1),[[2,4],[30,60]])
    def test_quantile_ensemble_order(self):
        base=np.array([[0,4],[3,6.]]);deep=np.array([[20,40],[1,2.]])
        for w in s.WEIGHTS:
            q=d.ensemble(base,deep,w);self.assertTrue((q[:,1]>=q[:,0]).all())
        with self.assertRaises(ValueError):d.ensemble(base,deep,1.1)
    def test_burst_survival(self):
        np.testing.assert_allclose(d.burst_probability(10,np.array([.1,.8]),[1.,3.],2),1-d.cdf(10,[.1,.8],[1.,3.],2),atol=1e-15)
    def test_exact_causal_membership(self):
        for i in s.OOS:
            tr=s.membership(i);self.assertTrue((s.AV.iloc[tr]<s.ISS.iloc[i]).all());self.assertTrue((s.ISS.iloc[tr]<s.ISS.iloc[i]).all())
            self.assertNotIn(i,tr);self.assertFalse(s.L.iloc[tr].split.eq('PURGE').any())
    def test_decay_policy(self):
        i=s.OOS[-1];tr=s.membership(i);w=s.weights(tr,i)
        self.assertTrue(((w>0)&(w<=1)).all());self.assertAlmostEqual(w[0]/w[30],.5)
    def test_seed_mean_order(self):
        for q in s.reused().values():self.assertTrue((q[s.OOS,:,1]>=q[s.OOS,:,0]).all())
    def test_daily_sufficient_metrics(self):
        y=np.arange(96).reshape(4,24)*100.;q=np.stack([y*.7,y*1.1],-1)
        m=s.metric(y,q);v=s.values(s.daily_sums(y,q).sum(0))
        np.testing.assert_allclose(v,[m[k] for k in s.CI_METRICS])
    def test_paired_bootstrap_identity(self):
        y=np.arange(96).reshape(4,24)*100.;q=np.stack([y*.7,y*1.1],-1)
        for row in s.bootstrap(y,{a:q for a in s.ARMS},'synthetic'):
            self.assertEqual(row['delta'],0);self.assertEqual(row['low'],0);self.assertEqual(row['high'],0)
    def test_zero_denominator_ci_fail_closed(self):
        y=np.zeros((2,24));q=np.ones((2,24,2))
        rows=s.bootstrap(y,{a:q for a in s.ARMS},'synthetic')
        for r in rows:
            if r['metric']=='requirement_ratio':self.assertEqual(r['invalid_draws'],2000);self.assertTrue(np.isnan(r['low']))


if __name__=='__main__':unittest.main()
