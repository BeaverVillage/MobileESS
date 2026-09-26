import unittest
import numpy as np
import study as s
class Contract(unittest.TestCase):
 def test_prior_odds(self):
  np.testing.assert_allclose(s.corrected_probability([0,.5,1],9),[0,.1,1])
 def test_probability_fail_closed(self):
  for p in [[np.nan],[np.inf],[-.1],[1.1]]:
   with self.assertRaises(AssertionError):s.corrected_probability(p,9)
 def test_no_missing_selection_metric(self):
  m=dict(detector_recall=.8,burst_coverage=.8,positive_coverage=.9,requirement_ratio=1.5,Q90_pinball=100,precision=.2,false_positive_rate=.1,PR_AUC=.3)
  self.assertTrue(s.criteria(m,dict(Q90_pinball=100))[0])
  for k in m:
   with self.assertRaises(AssertionError):s.criteria({**m,k:np.nan},dict(Q90_pinball=100))
 def test_hard_ratio_and_pinball(self):
  m=dict(detector_recall=.8,burst_coverage=.8,positive_coverage=.9,requirement_ratio=2.,Q90_pinball=100,precision=.2,false_positive_rate=.1,PR_AUC=.3)
  self.assertFalse(s.criteria(m,dict(Q90_pinball=100))[0])
  self.assertFalse(s.criteria({**m,'requirement_ratio':1.5,'Q90_pinball':103},dict(Q90_pinball=100))[0])
 def test_exact_temporal_weights(self):
  for i in s.OOS:
   tr=s.old.membership(i);self.assertTrue((s.AV.iloc[tr]<s.ISS.iloc[i]).all());self.assertEqual(len(s.old.weights(tr,i)),len(tr))
if __name__=='__main__':unittest.main()
