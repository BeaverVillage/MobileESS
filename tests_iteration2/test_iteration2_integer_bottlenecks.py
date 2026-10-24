import inspect,math,tempfile,unittest
from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch
import numpy as np
import scipy.sparse as sp
from v44_iteration2 import config as c,integer_native as policy,integer_support as support
from v44_iteration2.io import read,atomic,record


class IntegerBottlenecks(unittest.TestCase):
 def model(self,size=2712308,integer=10):
  model=NS(NumVars=size,NumIntVars=integer,Params=NS(MemLimit=float('inf'),SoftMemLimit=float('inf'),
   Presolve=-1,Method=2,Threads=1,MIPFocus=3,PrePasses=-1,FeasibilityTol=1e-6))
  model.setParam=lambda k,v:setattr(model.Params,k,v)
  return model

 def test_presolve_pass_limit_is_only_for_large_integer_models(self):
  for size,passes,focus in [(119899,-1,3),(2712308,3,1),(3298802,3,1)]:
   with tempfile.TemporaryDirectory(dir=c.ROOT) as folder:
    m=self.model(size);policy.configure(m,folder)
    self.assertEqual((m.Params.PrePasses,m.Params.MIPFocus),(passes,focus))
    self.assertEqual((m.Params.Presolve,m.Params.Method,m.Params.Threads),(-1,2,1))
    self.assertEqual(m.Params.FeasibilityTol,1e-6)

 def test_restricted_bound_only_schedules_superset_search(self):
  gp=NS(GRB=NS(Callback=NS(MIP=3,MIP_OBJBND=4)))
  model=NS(cbGet=lambda _:0.5578,terminate=lambda:stopped.append(True));stopped=[]
  native=NS(_iteration2_target=Fraction('0.5541383715571461')/Fraction('.995'))
  with tempfile.TemporaryDirectory(dir=c.ROOT) as folder:
   policy.support_exhausted(native,model,3,gp,folder)
   self.assertEqual(stopped,[True])
   proof=read(Path(folder)/'RESTRICTED_SUPPORT_ENLARGEMENT.json')
   self.assertFalse(proof['restricted_bound_is_global_certificate'])
   self.assertTrue(proof['prior_graphs_and_incumbent_retained'])
   self.assertNotIn('PASS',proof)

 def test_target_needs_finite_bound_strictly_above_target(self):
  gp=NS(GRB=NS(Callback=NS(MIP=3,MIP_OBJBND=4)))
  for bound in (math.nan,-math.inf,.55,.556):
   model=NS(cbGet=lambda _,v=bound:v,terminate=lambda:self.fail('premature enlargement'))
   policy.support_exhausted(NS(_iteration2_target=Fraction('.556')),model,3,gp,Path('unused'))
  policy.support_exhausted(NS(),model,3,gp,Path('unused'))

 def snapshot(self):
  from v44_iteration2.bootstrap import base
  from v42_a_stage_domain_v2.lexstage import LinearSnapshot,Objective
  return LinearSnapshot(sp.csr_matrix([[-1.,.5]]),np.zeros(2),np.ones(2),np.array(['<']),np.zeros(1),
   np.array(['C','I']),(Objective('rho',((0,Fraction(1)),)),)).require()

 def test_conflicting_candidate_is_quarantined_without_clipping_or_acceptance(self):
  snapshot=self.snapshot();point=np.array([.5-1e-7,1.]);native=NS(live_model=None)
  with tempfile.TemporaryDirectory(dir=c.ROOT) as folder:
   self.assertTrue(support.defer_bound_conflict(native,snapshot,point,Fraction(float(point[0])),Fraction(1,2),folder))
   proof=native._iteration2_bound_conflict
   self.assertFalse(proof['candidate_accepted']);self.assertFalse(proof['lower_bound_modified'])
   with np.load(proof['point']['path']) as raw:np.testing.assert_array_equal(raw['X'],point)
   self.assertFalse((Path(folder)/'VALIDATED_INTEGER_INCUMBENTS.json').exists())
   with self.assertRaisesRegex(ValueError,'A_CERTIFIED_LB_UB_CONFLICT'):
    support.defer_bound_conflict(native,snapshot,point,Fraction('.49'),Fraction('.5'),folder)
   native._iteration2_conflict_polished=True
   with self.assertRaisesRegex(ValueError,'A_CERTIFIED_LB_UB_CONFLICT'):
    support.defer_bound_conflict(native,snapshot,point,Fraction(float(point[0])),Fraction('.5'),folder)

 def test_exact_integer_candidate_still_gets_continuous_polish_after_conflict(self):
  snapshot=self.snapshot();point=np.array([.5-1e-7,1.]);seen=[]
  native=NS(_iteration2_bound_conflict=dict(candidate_accepted=False),incumbent_callback=None,warm_point=point,warm_basis=None)
  def solve(fixed,folder,component):
   self.assertTrue(policy.POLISH.get());self.assertEqual(component,'INTEGER_CONTROL')
   self.assertEqual((fixed.matrix-snapshot.matrix).nnz,0)
   np.testing.assert_array_equal(fixed.lower,[0.,1.]);np.testing.assert_array_equal(fixed.upper,[1.,1.])
   self.assertTrue(np.all(fixed.vtypes=='C'));seen.append(True)
   folder.mkdir(parents=True);atomic(folder/'NATIVE_RESULT.json',dict(native_seconds=.1))
   return dict(native_seconds=.1,objective=.5),dict(X=np.array([.5,1.]))
  native.solve=solve
  with tempfile.TemporaryDirectory(dir=c.ROOT) as folder:
   rec,raw=support.repair_conflict(native,snapshot,point,Path(folder)/'repair',lambda *a:self.fail('old exact-integer early return'))
   self.assertEqual(seen,[True]);self.assertEqual(raw['X'][0],.5)
   self.assertTrue(read(Path(folder)/'repair/REPAIR_CERTIFICATE.json')['PASS'])
   self.assertFalse(policy.POLISH.get());self.assertTrue(native._iteration2_conflict_polished)

 def test_polish_changes_only_continuous_fixed_decision_numerics(self):
  token=policy.POLISH.set(True)
  try:
   with tempfile.TemporaryDirectory(dir=c.ROOT) as folder:
    m=self.model(integer=0);settings=policy.configure(m,folder)
    self.assertEqual(settings['FeasibilityTol'],1e-9);self.assertEqual(settings['Method'],0)
    with self.assertRaisesRegex(ValueError,'MUST_BE_CONTINUOUS'):policy.configure(self.model(),folder)
  finally:policy.POLISH.reset(token)
  with patch.object(m,'setParam',side_effect=AssertionError('ordinary LP changed')):self.assertEqual(policy.configure(m,'unused'),{})

 def test_actual_compiler_keeps_independent_contract_and_post_native_polish(self):
  from v44_iteration2.bootstrap import base
  from v44_recovery_r029.integer_repair import compile_run
  from v42_may_campaign_native90 import a_stage
  with patch.object(a_stage,'_iteration2_integer_support',support,create=True):
   source=inspect.getsource(base.live_compiler(support.compiler(compile_run))(a_stage.run))
  self.assertIn('contract(zero, closure, bound, candidate, verification)',source)
  self.assertIn('defer_bound_conflict(native,typed,point,upper,exact_lb,output)',source)
  self.assertIn('repair_conflict(native,typed',source)
  self.assertIn("native._iteration2_target=exact_lb/(1-Fraction(1,200))",source)

 def test_bound_conflict_resume_requires_exact_error_paid_account_and_strict_proof(self):
  from v44_iteration2.resume import repair_source_bridge
  with tempfile.TemporaryDirectory(dir=c.ROOT) as folder:
   root=Path(folder);parent=root/'A2';ops=root/'OPS';parent.mkdir();ops.mkdir()
   old=dict(day=c.DAYS[7],iteration_stage='A4',source_sha='prior')
   error='RuntimeError("TELEMETRY_CALLBACK_ERROR:[\'ValueError: A_CERTIFIED_LB_UB_CONFLICT\']")'
   failure=dict(error=error);ledger=dict(inflight=None,measured_Native_Runtime=14.988,calls=[dict(component='INTEGER_CONTROL')])
   proof=dict(PASS=True,Native_calls=0,same_failed_matrix_and_raw_point_verified=True,scientific_matrix_unchanged=True,candidate_not_accepted=True,lower_bound_modified=False,tolerance_relaxed=False)
   for name,value in [('request',old),('RESULT',failure),('ledger',ledger),('proof',proof),('pass',dict(PASS=True))]:atomic(parent/(name+'.json'),value)
   row=dict(day=old['day'],stage='A4',parent_core=str(parent),old_source_sha='prior',integer_conflict_repair=True,integer_gap_continuation=True,
    diagnosed_error=error,old_request=record(parent/'request.json'),ledger=record(parent/'ledger.json'),reconciliation=record(parent/'pass.json'),phase_budget=record(parent/'pass.json'),
    core_failure=record(parent/'RESULT.json'),closed_state=record(parent/'pass.json'),repair_regression=record(parent/'proof.json'),certificates=dict(P1=record(parent/'pass.json')))
   def seal():
    atomic(ops/'PERMIT.json',dict(resumable_A_stages=[row],scientific_equations_domain_and_acceptance_unchanged=True,Native_budget_reset=False))
    atomic(ops/'AUTHORIZATION.json',dict(repair_permit=record(ops/'PERMIT.json')))
   seal()
   with patch.object(c,'OPS',ops):
    self.assertEqual(repair_source_bridge(parent,old,old),row)
    proof['lower_bound_modified']=True;atomic(parent/'proof.json',proof);row['repair_regression']=record(parent/'proof.json');seal()
    with self.assertRaisesRegex(PermissionError,'STRICT_BOUND_CONFLICT'):repair_source_bridge(parent,old,old)
    proof['lower_bound_modified']=False;atomic(parent/'proof.json',proof);row['repair_regression']=record(parent/'proof.json')
    ledger['measured_Native_Runtime']=5400.;atomic(parent/'ledger.json',ledger);row['ledger']=record(parent/'ledger.json');seal()
    with self.assertRaisesRegex(PermissionError,'EXACT_PAID_INTEGER_BOUND'):repair_source_bridge(parent,old,old)


if __name__=='__main__':unittest.main()
