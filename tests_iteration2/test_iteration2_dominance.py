import unittest,tempfile
from pathlib import Path
from types import SimpleNamespace
from contextvars import ContextVar
from unittest.mock import patch
from v44_iteration2 import config as c,numerical,p1_interval,resume
from v44_iteration2.io import read,atomic,record

class DominanceRepair(unittest.TestCase):
 def test_second_diagnosed_failure_must_match_the_sealed_exact_error(self):
  from tests_iteration2.test_iteration2_p1repair import RecoveryAccounts
  with tempfile.TemporaryDirectory(dir=c.ROOT) as d:
   parent,old,row,ops=RecoveryAccounts().fixture(Path(d));failure=parent/'RESULT.json'
   error="ValueError('R029_NUMERICAL_OPTIMALITY_OR_PRIOR_POINT_DOMINANCE_NOT_VERIFIED')";atomic(failure,dict(error=error))
   row.update(diagnosed_error=error,core_failure=record(failure));permit=Path(d)/'REPAIR_PERMIT.json'
   atomic(permit,dict(resumable_A_stages=[row],scientific_equations_domain_and_acceptance_unchanged=True,Native_budget_reset=False));atomic(ops/'AUTHORIZATION.json',dict(repair_permit=record(permit)))
   with patch.object(c,'OPS',ops):
    self.assertEqual(resume.repair_source_bridge(parent,old,old),row)
    atomic(failure,dict(error='other'))
    with self.assertRaisesRegex(PermissionError,'EXACT_DIAGNOSED'):resume.repair_source_bridge(parent,old,old)

 def test_real_Gurobi_repair_changes_algorithm_instead_of_overwriting_it(self):
  import gurobipy as gp
  with tempfile.TemporaryDirectory(dir=c.ROOT) as d,gp.Env(empty=True) as env:
   env.setParam('OutputFlag',0);env.start()
   stable=SimpleNamespace(_solve=ContextVar('dominance_policy',default=None))
   def factory(original):
    def apply(model,a,g):
     model.Params.Method=0 if stable._solve.get()['repair'] else 1
     return dict(Threads=model.Params.Threads,MIPGap=model.Params.MIPGap)
    return apply
   apply=numerical.policy_wrapper(factory,stable)(None)
   for repair,level,method,presolve in [(False,0,1,1),(True,0,0,1),(False,1,0,1),(False,2,1,0)]:
    with gp.Model(env=env) as model:
     model.Params.Threads=1;model.Params.MIPGap=.005
     a=stable._solve.set(dict(component='ORIGINAL_P1',repair=repair,folder=Path(d)));b=p1_interval.LEVEL.set(level)
     try:apply(model,{},gp)
     finally:p1_interval.LEVEL.reset(b);stable._solve.reset(a)
     self.assertEqual(model.Params.Method,method);self.assertEqual(model.Params.Presolve,presolve)
     self.assertEqual(model.Params.ScaleFlag,2);self.assertEqual(model.Params.FeasibilityTol,1e-9)
     self.assertEqual(model.Params.OptimalityTol,1e-9);self.assertEqual(model.Params.Quad,1)
     self.assertEqual(model.Params.PerturbValue,.0002)
     self.assertEqual((model.Params.Threads,model.Params.MIPGap),(1,.005))

 def test_twice_resumed_phase_account_keeps_new_phase_calls_after_historical_P1(self):
  with tempfile.TemporaryDirectory(dir=c.ROOT) as d:
   root=Path(d);parent=root/'A2'
   rows=[dict(component=k,Native_Runtime=t) for k,t in [('PHASE_I',1.),('LOCAL_PRICING',2.),('ORIGINAL_P1',4.),('LOCAL_PRICING',5.),('PHASE_I',6.),('LOCAL_PRICING',7.),('ORIGINAL_P1',8.)]]
   atomic(parent/'NATIVE_RUNTIME_LEDGER.json',dict(calls=rows,measured_Native_Runtime=33.))
   saved=dict(Native_seconds=16.,calls=[dict(label=k,Native_seconds=t) for k,t in [('INHERITED_PHASE_I',1.),('INHERITED_LOCAL_PRICING',2.),('PHASE_I',6.),('LOCAL_PRICING',7.)]])
   atomic(parent/'OUTPUT/PHASE_I_NATIVE_BUDGET.json',saved)
   self.assertEqual(resume.phase_account(parent)['used'],16.)
   saved['calls'][2]['Native_seconds']=6.01;atomic(parent/'OUTPUT/PHASE_I_NATIVE_BUDGET.json',saved)
   with self.assertRaisesRegex(ValueError,'CALL_NOT_IN_NATIVE_ACCOUNT'):resume.phase_account(parent)

 def test_repair_regression_native_costs_must_extend_exact_parent_prefix(self):
  from v44_iteration2.bootstrap import base
  from copy import deepcopy
  with tempfile.TemporaryDirectory(dir=c.ROOT) as d:
   root=Path(d);parent=root/'A2';diag=root/'DIAG';ops=root/'OPS'
   old=dict(calls=[dict(component='PHASE_I',Native_Runtime=1.,status='FINISHED')],inflight=None,Native_ceiling_seconds=5400.,measured_Native_Runtime=1.)
   atomic(parent/'NATIVE_RUNTIME_LEDGER.json',old)
   new=deepcopy(old);new['calls'].append(dict(component='ORIGINAL_P1',label='SAME_MATRIX_DOMINANCE_REPAIR_REGRESSION',Native_Runtime=2.,status='FINISHED'))
   new.update(parent_ledger=record(parent/'NATIVE_RUNTIME_LEDGER.json'),measured_Native_Runtime=3.)
   atomic(diag/'NATIVE_RUNTIME_LEDGER.json',new);atomic(diag/'RESULT.json',dict(PASS=True,matrix_bounds_objective_unchanged=True,acceptance_relaxed=False))
   row=dict(parent_core=str(parent),repaired_native_account=record(diag/'NATIVE_RUNTIME_LEDGER.json'),diagnostic_result=record(diag/'RESULT.json'))
   permit=root/'PERMIT.json';atomic(permit,dict(resumable_A_stages=[row]));atomic(ops/'AUTHORIZATION.json',dict(repair_permit=record(permit)))
   with patch.object(c,'OPS',ops):
    self.assertEqual(resume.budget_parent(parent),diag)
    new['calls'][0]['Native_Runtime']=0.;atomic(diag/'NATIVE_RUNTIME_LEDGER.json',new)
    row['repaired_native_account']=record(diag/'NATIVE_RUNTIME_LEDGER.json');atomic(permit,dict(resumable_A_stages=[row]));atomic(ops/'AUTHORIZATION.json',dict(repair_permit=record(permit)))
    with self.assertRaisesRegex(ValueError,'PREFIX_DRIFT'):resume.budget_parent(parent)

if __name__=='__main__':unittest.main()
