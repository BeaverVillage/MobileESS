import unittest,tempfile
from pathlib import Path
from types import SimpleNamespace
from contextvars import ContextVar
from fractions import Fraction
import numpy as np
import scipy.sparse as sp
from v44_iteration2 import config as c,numerical,p1_basis,p1_interval

def snapshot(matrix,lower=None,upper=None,rhs=None):
 from v44_iteration2.bootstrap import base
 from v42_a_stage_domain_v2.lexstage import LinearSnapshot,Objective
 A=sp.csr_matrix(matrix,dtype=float);m,n=A.shape
 return LinearSnapshot(A,np.zeros(n) if lower is None else np.array(lower),np.full(n,np.inf) if upper is None else np.array(upper),
  np.full(m,'<'),np.ones(m) if rhs is None else np.array(rhs),np.full(n,'C'),(Objective('rho',((0,Fraction(1)),)),))

class P1BasisTransfer(unittest.TestCase):
 def old(self):
  s=snapshot([[1,2],[0,1]])
  return dict(snapshot=s,labels=['x','y'],basis=(np.array([0,-1]),np.array([-1,0])),fingerprint='old',folder='old')
 def test_expanded_and_permuted_axes_retain_exact_nonsingular_basic_minor(self):
  old=self.old();new=snapshot([[0,1,4],[2,0,0],[1,1,7]])
  basis,reason=p1_basis.extended_basis(old,new,['y','x','new'])
  self.assertEqual(reason,'EXACT_BASIC_MINOR_EXTENDED');vb,cb=basis
  self.assertEqual(vb.tolist(),[-1,0,-1]);self.assertEqual(cb.tolist(),[-1,0,0])
  B=np.hstack((new.matrix[:,vb==0].toarray(),np.eye(3)[:,cb==0]))
  self.assertEqual(np.linalg.matrix_rank(B),3)
 def test_changed_basic_minor_missing_role_or_ambiguous_role_declines_reuse(self):
  for matrix,labels in [([[2,2],[0,1]],['x','y']),([[1,2],[0,1]],['other','y']),([[1,2],[0,1]],['x','x'])]:
   basis,_=p1_basis.extended_basis(self.old(),snapshot(matrix),labels)
   self.assertIsNone(basis)
 def test_same_snapshot_uses_only_last_accepted_complete_basis(self):
  cache=p1_basis.Bases();s=self.old()['snapshot']
  self.assertIsNone(cache.start(s,None,'s')['basis'])
  self.assertFalse(cache.remember(s,None,'s',dict(VBasis=[0,0],CBasis=[0,0]),Path('bad')))
  raw=dict(VBasis=[0,-1],CBasis=[-1,0]);self.assertTrue(cache.remember(s,None,'s',raw,Path('good')))
  raw['VBasis'][0]=-1
  start=cache.start(s,None,'s');self.assertEqual(start['reason'],'EXACT_SAME_SNAPSHOT');self.assertEqual(start['basis'][0][0],0)
  self.assertIsNone(cache.start(s,None,'different')['basis'])
 def test_physical_column_roles_survive_offsets_and_new_graph_variables(self):
  def state(offset,new=False):
   unit=dict(id='job_STAY',v=dict(y={('site',1):('v',0),**({('site',2):('v',1)} if new else {})}))
   return dict(n=1,compact=SimpleNamespace(matrix=sp.csr_matrix((1,offset+3))),metas=dict(k=dict(offset=offset,units=[unit])))
  before=p1_basis.column_labels(state(1));after=p1_basis.column_labels(state(2,True))
  self.assertEqual(before[0],after[0]);self.assertEqual(before[1],after[2]);self.assertNotEqual(after[2],after[3])
 def test_all31_dates_share_normal_policy_and_complete_P1_basis_handoff(self):
  import gurobipy as gp
  from v44_iteration2.bootstrap import base
  from v44_recovery_r029 import phase_stability as stable
  with tempfile.TemporaryDirectory(dir=c.ROOT) as d,gp.Env(empty=True) as env:
   env.setParam('OutputFlag',0);env.start()
   def original(m,a,g):m.Params.Method=2;return {}
   apply=numerical.policy_wrapper(stable.policy,stable)(original)
   for day in c.DAYS:
    with gp.Model(env=env) as model:
     x=model.addVar(lb=0);model.addConstr(x<=1);model.setObjective(x);model.update()
     # This pending objective change must be committed before setting a basis.
     model.setObjective(2*x)
     start=dict(basis=(np.array([-1]),np.array([0])),used=False)
     a=stable._solve.set(dict(component='ORIGINAL_P1',repair=False,folder=Path(d)/day,seed=None,basis=None));b=p1_basis.START.set(start)
     try:apply(model,{},gp);model.update()
     finally:p1_basis.START.reset(b);stable._solve.reset(a)
     self.assertTrue(start['used']);self.assertEqual(model.getAttr('VBasis'),[-1]);self.assertEqual(model.getAttr('CBasis'),[0])
     self.assertEqual((model.Params.Method,model.Params.Presolve,model.Params.LPWarmStart),(2,-1,2))
     self.assertEqual((model.Params.FeasibilityTol,model.Params.OptimalityTol),(1e-9,1e-9))
 def test_real_compiled_P1_receives_current_state_for_each_refinement(self):
  from tests_iteration2.test_iteration2_p1repair import P1IntervalRepair
  states=[]
  with tempfile.TemporaryDirectory(dir=c.ROOT) as d:
   run,calls,prices,s= P1IntervalRepair().compiled(Path(d),1,states.append)
   run();self.assertEqual(len(calls),2);self.assertEqual(len(prices),2)
   self.assertEqual(len(states),2);self.assertTrue(all(state['compact'] is s for state in states))

 def test_new_stage_instance_has_no_other_dates_basis(self):
  s=self.old()['snapshot'];raw=dict(VBasis=[0,-1],CBasis=[-1,0]);seen=[]
  class Parent:
   def __init__(self):self.p1_seed=dict(snapshot_sha='same')
   def solve(self,snapshot,folder,component):
    start=p1_basis.START.get();seen.append(start['basis'] is not None)
    return dict(status=2),raw
  with tempfile.TemporaryDirectory(dir=c.ROOT) as d:
   Native=p1_basis.native_class(Parent);first=Native();second=Native()
   first.solve(s,Path(d)/'day01_S0','ORIGINAL_P1');first.solve(s,Path(d)/'day01_S1','ORIGINAL_P1')
   second.solve(s,Path(d)/'day02_S0','ORIGINAL_P1')
  self.assertEqual(seen,[False,True,False]);self.assertIsNone(p1_basis.START.get())

if __name__=='__main__':unittest.main()
