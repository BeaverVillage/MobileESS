import unittest
import experiment as e
import numpy as np
import pandas as pd

class Contract(unittest.TestCase):
    def test_zero_mass_inverse(self):
        values=np.tile(e.GRID*100,(4,1));p=np.array([0.,.05,.5,1.])
        q=e.unconditional(p,values)
        np.testing.assert_allclose(q,[[0,0],[0,0],[0,80],[50,90]],atol=1e-10)

    def test_refit_maturity_and_history(self):
        cut=e.issue('2025-05-01').tz_convert('UTC')
        for policy in e.POLICIES:
            ids=e.membership(policy,cut)
            self.assertTrue((e.AV.iloc[ids]<cut).all())
            self.assertFalse((e.DAYS[ids]>='2025-05-01').any())
            if policy!='fixed':self.assertTrue(((e.DAYS[ids]>='2025-03-01')&(e.DAYS[ids]<='2025-04-30')).any())

    def test_fixed_baseline_exact(self):
        ids=e.DEV;tr=e.TRAIN
        q=e.tree_model('LGBM','fixed',e.issue('2024-09-01'),tr,ids,e.ROOT)
        old=np.load(e.BASE/'fits/LGBM_20260924/development_prediction.npy')
        np.testing.assert_array_equal(q,old)

    def test_residual_rank_and_support(self):
        y=np.tile(np.arange(26)[:,None],(1,24));d,rank=e.finite_residual(y,np.zeros_like(y))
        self.assertEqual(rank,25);np.testing.assert_array_equal(d,np.full(24,24))
        q=e.corrected(np.ones((24,2)),np.full(24,-100))
        self.assertTrue((q[:,1]>=q[:,0]).all())

    def test_mixture_reduces_to_single_expert(self):
        v=np.tile(e.GRID*100,(2,1));p=np.array([.5,1.])
        np.testing.assert_allclose(e.mixture_quantile(p,np.zeros(2),v,v*5),e.unconditional(p,v),atol=1e-9)

if __name__=='__main__':unittest.main()
