import inspect,tempfile,unittest
from types import CodeType
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch
from v44_iteration2 import config as c
from v44_iteration2.io import read,atomic,record


class IntegerRuntime(unittest.TestCase):
 def model(self,n=3298802,integer=400):
  model=NS(NumVars=n,NumIntVars=integer,Params=NS(MemLimit=float('inf'),SoftMemLimit=float('inf'),Presolve=-1,Method=2,Threads=1,FeasibilityTol=1e-6,IntFeasTol=1e-5))
  model.setParam=lambda k,v:setattr(model.Params,k,v)
  return model

 def test_global_gap_callback_controls_search_without_restricted_early_exit(self):
  from v44_iteration2.integer_native import configure
  with tempfile.TemporaryDirectory(dir=c.ROOT) as folder:
   model=self.model();settings=configure(model,folder)
   self.assertEqual(settings['MIPGap'],0);self.assertEqual(settings['MIPGapAbs'],0)
   self.assertEqual((model.Params.Presolve,model.Params.Method,model.Params.Threads),(-1,2,1))
   self.assertEqual((model.Params.FeasibilityTol,model.Params.IntFeasTol),(1e-6,1e-5))
   self.assertEqual((model.Params.PreSparsify,model.Params.AggFill),(1,0))
   self.assertEqual(model.Params.MemLimit,float('inf'))
   proof=read(Path(folder)/'ITERATION2_INTEGER_SOLVER_POLICY.json')
   self.assertFalse(proof['tolerance_relaxed']);self.assertEqual(proof['global_gap_target'],.005)
   self.assertFalse(proof['restricted_MIP_bound_used_as_global'])

 def test_continuous_P1_and_pricing_are_untouched(self):
  from v44_iteration2.integer_native import configure
  model=self.model(integer=0)
  with patch.object(model,'setParam',side_effect=AssertionError('continuous policy changed')):
   self.assertEqual(configure(model,Path('unused')),{} )

 def test_native_compiler_preserves_persistence_account_and_independent_model_check(self):
  from v44_iteration2.bootstrap import base
  from v44_iteration2.integer_native import compiled,configure
  from v42_a_stage_acceptance.native import Native
  from v42_may_campaign_native90.a_routing import routed_optimize
  fn=compiled(Native.solve);body=inspect.getsource(fn)
  self.assertIn("if not actual['PASS']:",body)
  self.assertIn('del compiled,delta,expected',body)
  self.assertIn('self.budget.charge(used or 0.)',body)
  self.assertIn("solver_policy_unchanged=not (effective.get('iteration2_global_integer_target',False)",body)
  self.assertIn('model.dispose();self.live_model=None',body)
  routed=routed_optimize(fn,dict(fn.__globals__))
  self.assertIs(routed.__globals__['_iteration2_integer_configure'],configure)
  self.assertIn("if component=='INTEGER_CONTROL':effective.update",inspect.getsource(routed))

 def test_stage_numerical_policy_remains_live_after_integer_scope_binding(self):
  from v44_iteration2.bootstrap import base
  from v44_iteration2.integer_native import scope
  from v42_a_stage_acceptance import native
  previous=native.Native.solve;marker=object()
  with scope():
   self.assertIs(native.Native.solve.__globals__,previous.__globals__)
   with patch.object(native,'apply_policy',marker):self.assertIs(native.Native.solve.__globals__['apply_policy'],marker)
  self.assertIs(native.Native.solve,previous)

 def test_source_guard_retains_receipts_without_pinning_obsolete_graph_state(self):
  from v44_iteration2.bootstrap import base
  from v44_iteration2.integer_native import native_factory
  from v42_may_campaign_native90 import a_stage
  function=native_factory(a_stage._native)
  guard=next(code for code in function.__code__.co_consts if isinstance(code,CodeType) and code.co_name=='verify')
  self.assertNotIn('state',guard.co_freevars)
  self.assertIn('_iteration2_inputs',guard.co_freevars)
  body=inspect.getsource(function)
  self.assertIn('if record(receipt[',body)
  self.assertIn('A_FROZEN_SOURCE_OR_INPUT_SHA_DRIFT',body)
  self.assertIs(function.__globals__,a_stage._native.__globals__)

 def test_actual_A2_factory_also_drops_only_obsolete_state_reference(self):
  from v44_iteration2.bootstrap import base
  from v44_iteration2.integer_support import selective_scope
  from v44.frozen.v43_a2 import adapter
  from v42_may_campaign_native90 import a_stage
  import ast
  with selective_scope({}):
   tree=adapter.source_tree(a_stage,'_native')
  namespace=dict(a_stage.__dict__);exec(compile(ast.fix_missing_locations(ast.Module(body=[tree],type_ignores=[])),'<integer_factory_test>','exec'),namespace)
  guard=next(code for code in namespace['_native'].__code__.co_consts if isinstance(code,CodeType) and code.co_name=='verify')
  self.assertNotIn('state',guard.co_freevars);self.assertIn('_iteration2_inputs',guard.co_freevars)

 def test_expanded_resume_uses_latest_point_without_repeating_promotion(self):
  from v44_iteration2.bootstrap import base
  from v44_iteration2 import integer_support as support
  from v44_recovery_r029.integer_repair import compile_run
  from v42_may_campaign_native90 import a_stage
  with patch.object(a_stage,'_iteration2_integer_support',support,create=True):
   body=inspect.getsource(base.live_compiler(support.compiler(compile_run))(a_stage.run))
  self.assertIn("if _iteration2_search.resumed_support or request.get('_iteration2_retry_same_support'):_warm=_iteration2_initial",body)
  self.assertIn("if acceptance['PASS'] and native.live_model is not None:",body)
  self.assertIn('_iteration2_search.persist(state,typed)',body)

 def test_integer_OOM_admission_rejects_unpaid_or_relaxed_repair(self):
  from v44_iteration2.resume import repair_source_bridge
  with tempfile.TemporaryDirectory(dir=c.ROOT) as folder:
   root=Path(folder);parent=root/'A2';ops=root/'OPS';parent.mkdir();ops.mkdir()
   request=dict(day=c.DAYS[0],iteration_stage='A3',source_sha='prior')
   failure=dict(error="RuntimeError('GurobiError: Out of memory')",classification='IMPLEMENTATION_FAILURE',incumbent=dict(PASS=True))
   ledger=dict(inflight=None,measured_Native_Runtime=3807.321,calls=[dict(component='INTEGER_CONTROL',error='Out of memory')])
   proof=dict(PASS=True,Native_calls=0,exact_failed_integer_snapshot_restored=True,scientific_matrix_unchanged=True,tolerance_relaxed=False,integer_policy_regression_PASS=True)
   for name,value in [('request',request),('RESULT',failure),('ledger',ledger),('proof',proof),('pass',dict(PASS=True))]:atomic(parent/(name+'.json'),value)
   row=dict(day=c.DAYS[0],stage='A3',parent_core=str(parent),old_source_sha='prior',integer_gap_continuation=True,integer_memory_repair=True,
    old_request=record(parent/'request.json'),ledger=record(parent/'ledger.json'),reconciliation=record(parent/'pass.json'),phase_budget=record(parent/'pass.json'),
    core_failure=record(parent/'RESULT.json'),closed_state=record(parent/'pass.json'),repair_regression=record(parent/'proof.json'),
    integer_search_checkpoint=record(parent/'pass.json'),integer_model_identity=record(parent/'pass.json'),integer_typeproof=record(parent/'pass.json'),certificates=dict(P1=record(parent/'pass.json')))
   def seal():
    atomic(ops/'PERMIT.json',dict(resumable_A_stages=[row],scientific_equations_domain_and_acceptance_unchanged=True,Native_budget_reset=False))
    atomic(ops/'AUTHORIZATION.json',dict(repair_permit=record(ops/'PERMIT.json')))
   seal()
   with patch.object(c,'OPS',ops):
    self.assertEqual(repair_source_bridge(parent,request,request),row)
    ledger['measured_Native_Runtime']=5400;atomic(parent/'ledger.json',ledger);row['ledger']=record(parent/'ledger.json');seal()
    with self.assertRaisesRegex(PermissionError,'EXACT_PAID_INTEGER_OOM'):repair_source_bridge(parent,request,request)
    ledger['measured_Native_Runtime']=3807.321;atomic(parent/'ledger.json',ledger);row['ledger']=record(parent/'ledger.json')
    proof['tolerance_relaxed']=True;atomic(parent/'proof.json',proof);row['repair_regression']=record(parent/'proof.json');seal()
    with self.assertRaisesRegex(PermissionError,'EXACT_INTEGER_REPAIR_REGRESSION'):repair_source_bridge(parent,request,request)


if __name__=='__main__':unittest.main()
