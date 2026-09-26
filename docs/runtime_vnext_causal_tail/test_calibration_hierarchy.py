import unittest
import numpy as np,pandas as pd
from experiment import calibrate

def fixture():
 rows=[]
 for day in range(7):
  t=pd.Timestamp('2025-01-01T08:00Z')+pd.Timedelta(days=day)
  for j in range(155):
   rows.append(dict(job_id=f'{day}_{j}',job_issue_id=f'{day}_{j}@{t}',issue_time=t,end_time=t+pd.Timedelta(hours=1),
    state='PENDING',partition='gpu-h100' if j<150 else 'gpu-a100',qos='normal',requested_seconds=3600.,num_gpus_req=4.,
    actual_seconds=100.,point=80.,Q50=80.,Q90=80.,Q95=80.,Q99=80.))
 return pd.DataFrame(rows)

class Hierarchy(unittest.TestCase):
 def test_sufficient_child_and_sparse_parent(self):
  f=fixture();q,proof=calibrate(f,'hierarchical');last=q[q.issue_time==q.issue_time.max()]
  self.assertTrue(last.loc[last.partition.eq('gpu-h100'),'calibration_route'].str.count(r'\|').eq(3).all())
  self.assertTrue(last.loc[last.partition.eq('gpu-a100'),'calibration_route'].eq('root').all())
  np.testing.assert_array_equal(last.Q90,np.full(155,100.))
  self.assertLess(pd.Timestamp(proof[-1]['pool_latest_end']),pd.Timestamp(proof[-1]['issue_time']))
 def test_current_outcomes_do_not_change_current_calibration(self):
  f=fixture();q,_=calibrate(f,'hierarchical');t=f.issue_time.max();f.loc[f.issue_time.eq(t),'actual_seconds']=1e9
  changed,_=calibrate(f,'hierarchical');np.testing.assert_array_equal(q.loc[q.issue_time.eq(t),'Q90'],changed.loc[changed.issue_time.eq(t),'Q90'])

if __name__=='__main__':unittest.main()
