import unittest,tempfile,json
from pathlib import Path
from types import SimpleNamespace
from contextvars import ContextVar
from unittest.mock import patch
import numpy as np
import scipy.sparse as sp
from v44_iteration2 import config as c,numerical
from v44_iteration2.elastic import artificial_point,replay_with_exact
from v44_iteration2.io import atomic,read

class ExactElasticWitness(unittest.TestCase):
 def fixture(self,sense='='):
  from v42_a_stage_domain_v2.lexstage import LinearSnapshot,Objective
  from v42_a_stage_phase1.core import elastic_master
  original=LinearSnapshot(sp.csr_matrix([[1.,1.]]),np.zeros(2),np.full(2,np.inf),np.array([sense]),np.array([70.17601209252096]),np.array(['C','C']),(Objective('rho',()),))
  return elastic_master(original,[0]),np.array([22575448186.073494,0.])
 def test_real_cancellation_reconstructs_only_auxiliaries_and_keeps_original_tolerance(self):
  from v42_a_stage_phase1 import core
  raw=core.primal_replay;master,x=self.fixture()
  with patch.object(core,'primal_replay',replay_with_exact(raw)):
   lifted,proof=artificial_point(master,x)
  self.assertTrue(proof['PASS']);self.assertEqual(proof['tolerance'],1e-6)
  np.testing.assert_array_equal(lifted[:2],x)
  self.assertTrue(np.all(lifted[2:]>=0))
 def test_true_violation_or_bound_violation_cannot_be_accepted(self):
  from v42_a_stage_phase1.core import primal_replay
  master,x=self.fixture();check=replay_with_exact(primal_replay)
  point=np.r_[x,np.zeros(len(master.artificial_rows))]
  self.assertFalse(check(master.snapshot,point)['PASS'])
  point[0]=-1.;self.assertFalse(check(master.snapshot,point)['PASS'])
 def test_original_physical_replay_is_never_replaced(self):
  master,x=self.fixture();sentinel=dict(PASS=False,max_row_violation=2.,max_bound_violation=0.)
  observed=[]
  def original(*args):observed.append(args);return sentinel
  self.assertIs(replay_with_exact(original)(master.original,x),sentinel)
  self.assertEqual(len(observed),1)
 def test_hard_row_failure_cannot_acquire_an_artificial(self):
  from v42_a_stage_phase1 import core
  master,x=self.fixture();master=SimpleNamespace(original=master.original,snapshot=master.original,artificial_rows=[],artificial_signs=[])
  with self.assertRaisesRegex(ValueError,'HARD_ROW'):artificial_point(master,x)

class LargeLPPolicy(unittest.TestCase):
 def test_large_P1_retains_r043_auto_presolve_and_barrier_without_relaxing_precision(self):
  with tempfile.TemporaryDirectory(dir=c.ROOT) as d:
   context=ContextVar('largeLP',default=None);stable=SimpleNamespace(_solve=context)
   apply=numerical.policy_wrapper(lambda original:lambda m,a,g:{},stable)(None)
   for component,size in [('ORIGINAL_P1',17107557),('ORIGINAL_P1',2000),('LOCAL_PRICING',17107557)]:
    values={};model=SimpleNamespace(NumNZs=size,setParam=lambda k,v:values.update({k:v}))
    token=context.set(dict(component=component,folder=Path(d),repair=False))
    try:apply(model,{},None)
    finally:context.reset(token)
    self.assertEqual(values['Presolve'],-1);self.assertEqual(values['Method'],2)
    self.assertEqual(values['LPWarmStart'],2);self.assertEqual(values['FeasibilityTol'],1e-9)
    self.assertNotIn('Threads',values);self.assertNotIn('MIPGap',values)

class LosslessPersistence(unittest.TestCase):
 def test_compact_atomic_keeps_unicode_nonfinite_rules_and_every_audit_row(self):
  with tempfile.TemporaryDirectory(dir=c.ROOT) as d:
   path=Path(d)/'ledger.json';value=dict(label='측정',calls=[dict(i=i,time=i/1000) for i in range(100)])
   atomic(path,value);self.assertEqual(read(path),value)
   self.assertLess(path.stat().st_size,len(json.dumps(value,ensure_ascii=False,indent=2).encode()))
   with self.assertRaises(ValueError):atomic(path,dict(value=float('nan')))
   self.assertEqual(read(path),value)

class ImmutableFreeze(unittest.TestCase):
 def test_controller_update_preserves_freeze_but_evidence_change_still_fails(self):
  from v44_iteration2 import supervisor
  from v44_iteration2.io import record
  with tempfile.TemporaryDirectory(dir=c.ROOT) as d:
   root=Path(d);physical=root/'physical.json';atomic(physical,{})
   ref=root/'reference.json';atomic(ref,dict(identity=dict(physical=record(physical))))
   acore=root/'A.json';atomic(acore,dict(AIDC_reference=record(ref)))
   mcore=root/'M.json';atomic(mcore,{})
   checkpoint=root/'checkpoint.json';atomic(checkpoint,{})
   job=dict(day='2025-05-01',stages={})
   for stage in c.STAGES:
    file=root/(stage+'.json');atomic(file,dict(core_result=record(acore if stage.startswith('A') else mcore),checkpoint=record(checkpoint)))
    job['stages'][stage]=dict(result=record(file))
   with patch.object(c,'ROOT',root),patch.object(supervisor,'full_m',return_value=dict(case_sha='case',plan_sha='plan')),patch.object(supervisor,'full_a'),patch.object(supervisor.authority,'validate',return_value=dict(commit_sha='old')):
    supervisor.freeze(job);original=job['M4_freeze']
   with patch.object(c,'ROOT',root),patch.object(supervisor,'full_m',return_value=dict(case_sha='case',plan_sha='plan')),patch.object(supervisor,'full_a'),patch.object(supervisor.authority,'validate',return_value=dict(commit_sha='new')):
    supervisor.freeze(job);self.assertEqual(job['M4_freeze'],original)
    with patch.object(supervisor,'full_m',return_value=dict(case_sha='changed',plan_sha='plan')):
     with self.assertRaisesRegex(ValueError,'FROZEN_M4_DRIFT'):supervisor.freeze(job)

if __name__=='__main__':unittest.main()
