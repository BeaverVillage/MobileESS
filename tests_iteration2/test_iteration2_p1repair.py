import unittest,tempfile
from pathlib import Path
from types import SimpleNamespace
from contextvars import ContextVar
from unittest.mock import patch
import numpy as np
import scipy.sparse as sp
from v44_iteration2 import config as c,p1_interval,numerical
from v44_iteration2.io import atomic,read,record

class P1IntervalRepair(unittest.TestCase):
 def compiled(self,root,closed_after):
  from v44_iteration2.bootstrap import base
  from v42_a_stage_canary import phase
  from v44_recovery_r029 import p1_acceleration
  calls=[];prices=[]
  snapshot=SimpleNamespace(matrix=sp.csr_matrix((1,1)),rhs=np.zeros(1),fingerprint=lambda:'same-matrix')
  point=np.zeros(1);master=SimpleNamespace(snapshot=snapshot,artificial_rows=[],weights=[])
  state=dict(grows=[],compact=snapshot,prior_compact=point,axes={},reference=snapshot,metas={},data=None,domains=None,ledger=None,n=0)
  def pricing(*args):
   path=args[-1];index=len(prices)
   result=dict(no_negative_omitted_block_certified=index>=closed_after,full_domain_phase1_lower_bound='1',negative_blocks=0,
    min_stay_rc='-1/100000',complete_STAY_and_migration_coverage=True)
   atomic(path/'FULL_PRICING_RESULT.json',result);prices.append((snapshot,p1_interval.LEVEL.get()));return result,[]
  native=SimpleNamespace(remaining=lambda:100,admit_p1=lambda s,p:None)
  def solve(s,folder,component):
   calls.append((s,p1_interval.LEVEL.get(),component));return dict(status=2,native_seconds=3,Work=0,objective=1),dict(X=point,Pi=point,RC=point)
  native.solve=solve
  ns=dict(vars(phase),OUT=root,elastic_master=lambda *a:master,artificial_point=lambda *a:point,
   verify_zero=lambda *a:dict(PASS=True),expanded_point=lambda *a:point,primal_replay=lambda *a:dict(PASS=True),
   verify_sign_convention=lambda *a:dict(PASS=True),partition=lambda *a:({},{}),full_pricing=pricing,
   activate=lambda *a,**kw:(_ for _ in ()).throw(AssertionError('NO_FAKE_NEGATIVE_DIRECTION_ALLOWED')))
  run=p1_interval.compiler(p1_acceleration.compile_p1)(phase.run,ns)
  return lambda:run(native,state,'2025-05-01',certified_zero_point=point),calls,prices,snapshot

 def test_real_original_P1_source_retries_same_matrix_and_requires_full_closure(self):
  with tempfile.TemporaryDirectory(dir=c.ROOT) as d:
   run,calls,prices,snapshot=self.compiled(Path(d),1);result=run()
   self.assertTrue(result[-1]['no_negative_omitted_block_certified'])
   self.assertEqual([x[1] for x in calls],[0,1]);self.assertEqual([x[1] for x in prices],[0,1])
   self.assertTrue(all(x[0] is snapshot for x in calls));self.assertEqual(p1_interval.LEVEL.get(),0)

 def test_unresolved_bound_cannot_become_PASS_after_refinement_limit(self):
  with tempfile.TemporaryDirectory(dir=c.ROOT) as d:
   run,calls,prices,snapshot=self.compiled(Path(d),99)
   with self.assertRaisesRegex(ValueError,'EXHAUSTED_WITHOUT_CERTIFICATE'):run()
   self.assertEqual([x[1] for x in calls],[0,1,2]);self.assertEqual(len(prices),3)
   self.assertFalse((Path(d)/'2025-05-01/P1_RESULT.json').exists());self.assertEqual(p1_interval.LEVEL.get(),0)

 def test_existing_closure_needs_no_extra_solve(self):
  with tempfile.TemporaryDirectory(dir=c.ROOT) as d:
   run,calls,prices,_=self.compiled(Path(d),0);run();self.assertEqual(len(calls),1)

 def test_real_Gurobi_models_accept_precision_without_optimize_or_integer_policy_change(self):
  import gurobipy as gp
  with tempfile.TemporaryDirectory(dir=c.ROOT) as d,gp.Env(empty=True) as env:
   env.setParam('OutputFlag',0);env.start()
   stable=SimpleNamespace(_solve=ContextVar('test_policy',default=None))
   def factory(fn):return lambda model,a,g:dict(Threads=model.Params.Threads,MIPGap=model.Params.MIPGap)
   apply=numerical.policy_wrapper(factory,stable)(None)
   for component in ('ORIGINAL_P1','LOCAL_PRICING','PHASE_I','INTEGER_CONTROL'):
    with gp.Model(env=env) as model:
     model.Params.Threads=1;model.Params.MIPGap=.005
     token=stable._solve.set(dict(component=component,folder=Path(d),repair=False))
     try:apply(model,{},gp)
     finally:stable._solve.reset(token)
     self.assertEqual(model.Params.FeasibilityTol,1e-6 if component=='INTEGER_CONTROL' else 1e-9)
     self.assertEqual((model.Params.Threads,model.Params.MIPGap),(1,.005))

class RecoveryAccounts(unittest.TestCase):
 def fixture(self,root):
  parent=root/'2025-05-01/B3/attempt002/A2';request=dict(day='2025-05-01',iteration_stage='A3',source_sha='old')
  atomic(parent/'request.json',request);atomic(parent/'RESULT.json',dict(error="ValueError('P1_UNRESOLVED_INTERVAL_WITHOUT_NEGATIVE_SUPPORT')"))
  calls=[dict(component=k,Native_Runtime=t,status='FINISHED') for k,t in [('PHASE_I',1.),('LOCAL_PRICING',2.),('ORIGINAL_P1',4.),('LOCAL_PRICING',5.)]]
  atomic(parent/'NATIVE_RUNTIME_LEDGER.json',dict(Native_ceiling_seconds=5400.,measured_Native_Runtime=12.,calls=calls,costs=[],wall_seconds=100.,inflight=None))
  atomic(parent/'RECONCILIATION.json',dict(inflight=None));atomic(parent/'OUTPUT/PHASE_I_NATIVE_BUDGET.json',dict(Native_seconds=3.,calls=[dict(label='PHASE_I',Native_seconds=1.),dict(label='LOCAL_PRICING',Native_seconds=2.)]))
  row=dict(day=request['day'],stage='A3',parent_core=str(parent),old_source_sha='old',old_request=record(parent/'request.json'),ledger=record(parent/'NATIVE_RUNTIME_LEDGER.json'),reconciliation=record(parent/'RECONCILIATION.json'),phase_budget=record(parent/'OUTPUT/PHASE_I_NATIVE_BUDGET.json'))
  permit=root/'REPAIR_PERMIT.json';atomic(permit,dict(resumable_A_stages=[row],scientific_equations_domain_and_acceptance_unchanged=True,Native_budget_reset=False))
  ops=root/'OPS';atomic(ops/'AUTHORIZATION.json',dict(repair_permit=record(permit)))
  return parent,request,row,ops

 def test_phase_I_continuation_includes_its_local_pricing_but_excludes_original_P1(self):
  from v44_iteration2.resume import phase_account
  with tempfile.TemporaryDirectory(dir=c.ROOT) as d:
   parent,_,_,_=self.fixture(Path(d));account=phase_account(parent)
   self.assertEqual(account['used'],3.);self.assertEqual(len(account['calls']),2)
   saved=read(parent/'OUTPUT/PHASE_I_NATIVE_BUDGET.json');saved['Native_seconds']=1.;atomic(parent/'OUTPUT/PHASE_I_NATIVE_BUDGET.json',saved)
   with self.assertRaisesRegex(ValueError,'ACCOUNT_DRIFT'):phase_account(parent)

 def test_source_bridge_rejects_unapproved_stage_or_changed_old_ledger(self):
  from v44_iteration2.resume import repair_source_bridge
  with tempfile.TemporaryDirectory(dir=c.ROOT) as d:
   parent,old,row,ops=self.fixture(Path(d))
   with patch.object(c,'OPS',ops):
    self.assertEqual(repair_source_bridge(parent,old,old),row)
    with self.assertRaises(PermissionError):repair_source_bridge(parent,old,dict(old,iteration_stage='A4'))
    with (parent/'NATIVE_RUNTIME_LEDGER.json').open('ab') as f:f.write(b' ')
    with self.assertRaises(ValueError):repair_source_bridge(parent,old,old)

 def test_failed_stage_is_requeued_only_once_and_original_failure_is_retained(self):
  from v44_iteration2.recovery import requeue
  with tempfile.TemporaryDirectory(dir=c.ROOT) as d:
   parent,old,row,ops=self.fixture(Path(d));item=dict(status='FAILED',PASS=False,root=str(parent.parent),error='original')
   state=dict(jobs=[dict(day=old['day'],status='PLANNING_FAILED',stages=dict(A3=item),error='original')])
   with patch.object(c,'OPS',ops):requeue(state);requeue(state)
   job=state['jobs'][0];self.assertEqual(job['status'],'REPAIR_QUEUED');self.assertFalse(item['PASS']);self.assertEqual(len(job['repair_history']),1)
   self.assertEqual(job['repair_history'][0]['original_failure']['status'],'FAILED');self.assertFalse(job['repair_history'][0]['Native_budget_reset'])

 def test_actual_continuation_scope_carries_both_accounts_without_any_solve(self):
  from v44_iteration2 import resume
  from v44_iteration2.bootstrap import base
  from v44_recovery_r029 import phase_limit
  from v42_may_campaign_native90 import budget
  with tempfile.TemporaryDirectory(dir=c.ROOT) as d:
   root=Path(d);parent,old,row,ops=self.fixture(root)
   with patch.object(c,'OPS',ops),patch.object(resume,'admit',return_value=dict(remaining=5388.)),resume.a_scope(parent,{}) as proof:
    account=budget.DateBudget(root/'NEW/NATIVE_RUNTIME_LEDGER.json',native_limit=5400.)
    self.assertEqual(account.used(),12.);self.assertEqual(account.remaining(),5388.)
    with phase_limit.phase_scope(SimpleNamespace(remaining=lambda:5388),root/'NEW/OUTPUT') as limited:
     self.assertEqual(limited.context['used'],3.);self.assertEqual(limited.remaining(),1497.)
    self.assertEqual(proof['inherited_Phase_I_Native_seconds'],3.)
   self.assertTrue(read(root/'NEW/NATIVE_RUNTIME_LEDGER.json')['resumed_same_stage_budget'])

if __name__=='__main__':unittest.main()
