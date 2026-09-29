import unittest
import numpy as np
from cc416 import state

class CC4PastStateTests(unittest.TestCase):
    def test_strict_future_poison_and_prefix(self):
        times=np.array([0.,3600.,7200.]);codes=np.array([[1,2,3],[4,5,6],[7,8,9]])
        baseline=state(times,codes,3600.)
        poison=codes.copy();poison[1:]=-999
        np.testing.assert_array_equal(baseline,state(times,poison,3600.))
        np.testing.assert_array_equal(baseline,state(times,codes,3600.,True)[:len(baseline)])
        self.assertEqual(len(baseline),312)
        changed=codes.copy();changed[0,0]=2
        self.assertFalse(np.array_equal(baseline,state(times,changed,3600.)))

    def test_empty_and_missing_are_finite(self):
        times=np.array([0.]);codes=np.array([[17,17,17]])
        self.assertTrue(np.isfinite(state(times,codes,-1.)).all())
        self.assertTrue(np.isfinite(state(times,codes,1.)).all())
        self.assertFalse(np.array_equal(state(times,codes,1.),state(times,np.zeros_like(codes),1.)))

if __name__=='__main__':unittest.main(verbosity=2)
