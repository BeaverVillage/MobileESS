import sys,unittest,copy
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).parent/'shared'))
from qsafe_shell import coarse_shells,correct_slot
RULE=dict(coarse_grid=dict(unit_coordinates=[0,.25,.5,.75,1]),local_refinement=dict(max_starts=4,maxiter=75,ftol=1e-10,finite_difference_step_kvar=.25))
def result(ok):return dict(v=np.array([1. if ok else 1.1]),ipu=np.array([.5]),kva=np.array([.5]),taps=[0],converged=True)
class Tests(unittest.TestCase):
 def test_domains(self):
  for n in (4,6):self.assertEqual(sum(len(qs) for _,qs in coarse_shells(-np.ones(n),np.ones(n),np.zeros(n),RULE['coarse_grid']['unit_coordinates'])),5**n)
 def test_complete_shell_tie_and_no_larger_shell(self):
  seen=[]
  def ev(q):seen.append(tuple(q));return result(np.sum(q*q)>=.25)
  q,r,e=correct_slot(ev,np.zeros(2),-np.ones(2),np.ones(2),rules=RULE,feasible=lambda r:r['v'][0]<=1.05,constraints=lambda r:np.array([1.05-r['v'][0]]),refine=False)
  self.assertEqual(tuple(q),(-.5,0.));self.assertEqual(e['shells'][-1]['candidates'],4)
  self.assertEqual(set(seen),{(0.,0.),(-.5,0.),(0.,-.5),(0.,.5),(.5,0.)})
 def test_refinement_separate_and_runs(self):
  q,r,e=correct_slot(lambda q:result(q[0]>=.2),np.zeros(1),-np.ones(1),np.ones(1),rules=RULE,feasible=lambda r:r['v'][0]<=1.05,constraints=lambda r:np.array([1.05-r['v'][0]]))
  self.assertGreater(e['refinement_starts'],0);self.assertGreater(e['refinement_evaluations'],0);self.assertIsNone(e['global_candidate_cap'])
 def test_disconnected_axis(self):
  shells=list(coarse_shells(np.array([-1.,0.]),np.array([1.,0.]),np.zeros(2),RULE['coarse_grid']['unit_coordinates']))
  self.assertEqual(sum(len(q) for _,q in shells),5)
  self.assertTrue(all(x[1]==0 for _,qs in shells for x in qs))
 def test_complete_six_domain_not_truncated_at_5000(self):
  _,_,e=correct_slot(lambda q:result(False),np.zeros(6),-np.ones(6),np.ones(6),rules=RULE,feasible=lambda r:False,constraints=lambda r:np.array([-1.]),refine=False)
  self.assertEqual(e['coarse_candidates'],15625)
  self.assertEqual(e['unique_Q_trials'],15625)
  self.assertIsNone(e['first_feasible_shell'])
 def test_worker_completion_order_does_not_change_choice(self):
  from concurrent.futures import ThreadPoolExecutor
  import time
  def ev(q):time.sleep(.001 if q[0]>0 else .004);return result(np.sum(q*q)>=.25)
  with ThreadPoolExecutor(4) as pool:
   q,_,e=correct_slot(ev,np.zeros(2),-np.ones(2),np.ones(2),rules=RULE,feasible=lambda r:r['v'][0]<=1.05,constraints=lambda r:np.array([1.05-r['v'][0]]),evaluate_many=lambda qs:list(pool.map(ev,qs)),refine=False)
  self.assertEqual(tuple(q),(-.5,0.));self.assertEqual(e['shells'][-1]['feasible_candidates'],4)
if __name__=='__main__':unittest.main()
