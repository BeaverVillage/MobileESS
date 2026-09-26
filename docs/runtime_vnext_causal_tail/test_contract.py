import unittest
import experiment as e
import pandas as pd,numpy as np

class Contract(unittest.TestCase):
 def test_end_boundary_and_full_membership(self):
  t=pd.Timestamp('2025-03-22T08:00Z')
  for w in ['120','180','expanding']:
   f=e.member(w,t);self.assertTrue(f.end_time.lt(t).all())
   if w!='expanding':self.assertTrue(f.end_time.ge(t-pd.Timedelta(days=int(w))).all())
 def test_query_label_projection(self):
  q=e.query(pd.Timestamp('2025-03-22T08:00Z'));self.assertFalse(set(['end_time','runtime_seconds','actual_seconds','start_time'])&set(q))
  self.assertTrue((q.elapsed_seconds[q.state.eq('RUNNING')]>0).all())
 def test_landmark_remaining(self):
  f=e.landmarks(e.member('120',pd.Timestamp('2025-03-22T08:00Z')))
  np.testing.assert_array_equal(f.remaining_seconds+f.elapsed_seconds,f.runtime_seconds)
  self.assertTrue(f.remaining_seconds.gt(0).all());self.assertTrue(f.job_id.is_unique)
 def test_calibration_boundary(self):
  self.assertEqual(e.residual_quantile(np.arange(100),.9),90.)
  with self.assertRaises(AssertionError):e.residual_quantile(np.arange(5),.99)
 def test_serialized_preprocessing_order(self):
  f=e.member('120',pd.Timestamp('2025-03-22T08:00Z'));p=e.Preprocess('2025-03-22T08:00Z').fit(f)
  a=p.transform(f.iloc[:100]);p.medians=dict(sorted(p.medians.items()));np.testing.assert_array_equal(a,p.transform(f.iloc[:100]))
 def test_future_label_mutation_has_no_query_effect(self):
  e.data();original=e.P;first=e.query(pd.Timestamp('2025-03-22T08:00Z'))
  try:
   e.P=e.P.copy();e.P['runtime_seconds']=-1;e.P['actual_seconds']=1e15;e.P['end_time']=pd.Timestamp('2100-01-01',tz='UTC')
   pd.testing.assert_frame_equal(first,e.query(pd.Timestamp('2025-03-22T08:00Z')))
  finally:e.P=original

if __name__=='__main__':unittest.main()
