import inspect,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch
import numpy as np
from v44_iteration2 import config as c,integer_support as support
from v44_iteration2.io import atomic,read,record


class PhysicalCallbackRepair(unittest.TestCase):
 def test_factorized_rejection_keeps_raw_and_next_valid_candidate(self):
  physical=NS(snapshot=NS(fingerprint=lambda:'original'),verify=lambda x:dict(PASS=True))
  point=np.array([0.,1.,.55]);original=point.copy()
  with tempfile.TemporaryDirectory(dir=c.ROOT) as folder:
   with patch.object(physical,'verify',side_effect=ValueError("NONPHYSICAL_FACTORIZED_STATE:link_bytes:('LOSAng--SNVAng', 47)")):
    rejected=support.verify_candidate(physical,point,folder)
    self.assertFalse(rejected['PASS']);self.assertFalse(rejected['candidate_accepted'])
    self.assertFalse(rejected['tolerance_relaxed'])
    with np.load(rejected['point']['path']) as raw:np.testing.assert_array_equal(raw['X'],original)
    second=support.verify_candidate(physical,point,folder)
    self.assertNotEqual(second['point']['path'],rejected['point']['path'])
   self.assertTrue(support.verify_candidate(physical,point,folder)['PASS'])
   np.testing.assert_array_equal(point,original)
   self.assertFalse((Path(folder)/'VALIDATED_INTEGER_INCUMBENTS.json').exists())

 def test_other_exceptions_still_fail_visibly(self):
  for error in (ValueError('OTHER_PHYSICAL_IMPLEMENTATION_ERROR'),RuntimeError('failure')):
   physical=NS(verify=lambda _:None)
   with patch.object(physical,'verify',side_effect=error):
    with self.assertRaises(type(error)):support.verify_candidate(physical,np.array([0.]),'unused')

 def test_actual_compiler_routes_rejection_before_original_acceptance(self):
  from v44_iteration2.bootstrap import base
  from v44_recovery_r029.integer_repair import compile_run
  from v42_may_campaign_native90 import a_stage
  with patch.object(a_stage,'_iteration2_integer_support',support,create=True):
   source=inspect.getsource(base.live_compiler(support.compiler(compile_run))(a_stage.run))
  self.assertEqual(source.count('verify_candidate(physical,point,output)'),1)
  self.assertIn("if not verification['PASS']:",source)
  self.assertIn('invalid_replays.append(verification)',source)
  self.assertIn('contract(zero, closure, bound, candidate, verification)',source)
  self.assertLess(source.index('verify_candidate(physical,point,output)'),source.index('contract(zero, closure, bound, candidate, verification)'))

 def test_resume_requires_exact_failure_and_strict_same_case_evidence(self):
  from v44_iteration2.resume import repair_source_bridge
  with tempfile.TemporaryDirectory(dir=c.ROOT) as folder:
   root=Path(folder);parent=root/'A2';ops=root/'OPS';parent.mkdir();ops.mkdir()
   old=dict(day=c.DAYS[0],iteration_stage='A3',source_sha='prior')
   error='TELEMETRY_CALLBACK_ERROR:ValueError: NONPHYSICAL_FACTORIZED_STATE:link_bytes:case'
   failure=dict(error=error,incumbent=dict(PASS=True))
   ledger=dict(inflight=None,measured_Native_Runtime=692.788,calls=[dict(component='INTEGER_CONTROL')])
   proof=dict(PASS=True,Native_calls=0,same_failed_case_verified=True,saved_incumbent_original_physical_PASS=True,
    known_factorized_rejection_tested=True,unexpected_errors_propagate=True,scientific_matrix_unchanged=True,
    candidate_not_accepted=True,tolerance_relaxed=False)
   for name,value in [('request',old),('RESULT',failure),('ledger',ledger),('proof',proof),('pass',dict(PASS=True))]:atomic(parent/(name+'.json'),value)
   row=dict(day=old['day'],stage='A3',parent_core=str(parent),old_source_sha='prior',integer_physical_callback_repair=True,integer_gap_continuation=True,
    diagnosed_error=error,old_request=record(parent/'request.json'),ledger=record(parent/'ledger.json'),reconciliation=record(parent/'pass.json'),phase_budget=record(parent/'pass.json'),
    core_failure=record(parent/'RESULT.json'),closed_state=record(parent/'pass.json'),repair_regression=record(parent/'proof.json'),certificates=dict(P1=record(parent/'pass.json')))
   def seal():
    atomic(ops/'PERMIT.json',dict(resumable_A_stages=[row],scientific_equations_domain_and_acceptance_unchanged=True,Native_budget_reset=False))
    atomic(ops/'AUTHORIZATION.json',dict(repair_permit=record(ops/'PERMIT.json')))
   seal()
   with patch.object(c,'OPS',ops):
    self.assertEqual(repair_source_bridge(parent,old,old),row)
    proof['tolerance_relaxed']=True;atomic(parent/'proof.json',proof);row['repair_regression']=record(parent/'proof.json');seal()
    with self.assertRaisesRegex(PermissionError,'STRICT_PHYSICAL_CALLBACK'):repair_source_bridge(parent,old,old)
    proof['tolerance_relaxed']=False;atomic(parent/'proof.json',proof);row['repair_regression']=record(parent/'proof.json')
    ledger['measured_Native_Runtime']=5400.;atomic(parent/'ledger.json',ledger);row['ledger']=record(parent/'ledger.json');seal()
    with self.assertRaisesRegex(PermissionError,'EXACT_PAID_INTEGER_PHYSICAL'):repair_source_bridge(parent,old,old)


if __name__=='__main__':unittest.main()
