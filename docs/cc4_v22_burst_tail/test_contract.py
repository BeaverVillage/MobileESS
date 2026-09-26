import unittest
import numpy as np
import study as s
class Contract(unittest.TestCase):
 def test_q90_tail_mass(self):
  p=np.array([.1,.2,1.]);v=np.tile([110,125,150,175,190],(3,1))
  np.testing.assert_allclose(s.tail_bound(p,v,100),[100,150,190])
 def test_finite_rank(self):
  self.assertEqual(s.residual_delta(np.arange(50)),45.)
  self.assertEqual(s.residual_delta(-np.arange(1,51)),0.)
 def test_equality_not_mature(self):
  for i in s.OOS:
   tr=s.membership(i);self.assertTrue((s.AV.iloc[tr]<s.ISS.iloc[i]).all());self.assertFalse(s.L.split.iloc[tr].eq('PURGE').any())
 def test_selection_rejects_pinball_tradeoff(self):
  self.assertFalse(s.eligible(dict(positive_coverage=.99,burst_coverage=.99,Q90_pinball=101),dict(Q90_pinball=100)))
 def test_paired_identity(self):
  y=np.tile(np.arange(24)*100.,(10,1));q=y+4
  for row in s.uncertainty(y,q,q,7):self.assertEqual(row['delta'],0);self.assertEqual(row['CI95_low'],0);self.assertEqual(row['CI95_high'],0)
if __name__=='__main__':unittest.main()
