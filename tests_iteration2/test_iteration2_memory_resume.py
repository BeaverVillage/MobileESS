import hashlib,json,unittest,tempfile
from pathlib import Path
from fractions import Fraction
from unittest.mock import patch
from v44_iteration2 import config as c
from v44_iteration2.performance import streaming_domain_digest
from v44_iteration2.io import atomic,record

class ExactDomainDigest(unittest.TestCase):
 def test_canonical_bytes_match_original_for_empty_nested_unicode_and_large_key_lists(self):
  values=[[],[('job',1,-0.0,'한글'),(2,3,Fraction(1,3))],{'nested':[1,2,{'x':'é'}]},[(i,i%96,'x') for i in range(10001)]]
  for value in values:
   expected=hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),default=str,allow_nan=False).encode()).hexdigest()
   original=json.dumps;seen=[]
   def bounded(v,*a,**kw):
    if type(v) is list:self.assertLessEqual(len(v),4096);seen.append(len(v))
    return original(v,*a,**kw)
   with patch.object(json,'dumps',bounded):self.assertEqual(streaming_domain_digest(value),expected)
  self.assertGreater(len(seen),1)
 def test_nonfinite_still_fails_and_changed_key_changes_SHA(self):
  with self.assertRaises(ValueError):streaming_domain_digest([float('nan')])
  self.assertNotEqual(streaming_domain_digest([(1,2)]),streaming_domain_digest([(1,3)]))

class ExactZeroNativeResume(unittest.TestCase):
 def test_only_exact_diagnosed_JSON_memory_failure_may_bridge_sources(self):
  from v44_iteration2.resume import repair_source_bridge
  with tempfile.TemporaryDirectory(dir=c.ROOT) as d:
   root=Path(d);parent=root/'A2';ops=root/'OPS';old=dict(day='2025-05-01',iteration_stage='A3',source_sha='old')
   for name in ('request','ledger','phase','reconciliation'):atomic(parent/(name+'.json'),{})
   trace='active_key_sha256=digest(sorted(self.active_keys))\nin encode\nMemoryError'
   atomic(parent/'RESULT.json',dict(error='MemoryError()',traceback=trace))
   row=dict(day=old['day'],stage='A3',parent_core=str(parent),old_source_sha='old',diagnosed_error='MemoryError()',
    old_request=record(parent/'request.json'),ledger=record(parent/'ledger.json'),phase_budget=record(parent/'phase.json'),reconciliation=record(parent/'reconciliation.json'),core_failure=record(parent/'RESULT.json'))
   policy=dict(resumable_A_stages=[row],exact_canonical_domain_digest_streaming=True,scientific_equations_domain_and_acceptance_unchanged=True,Native_budget_reset=False)
   atomic(ops/'permit.json',policy);atomic(ops/'AUTHORIZATION.json',dict(repair_permit=record(ops/'permit.json')))
   with patch.object(c,'OPS',ops):self.assertEqual(repair_source_bridge(parent,old,old)['diagnosed_error'],'MemoryError()')
   atomic(parent/'RESULT.json',dict(error='MemoryError()',traceback='unrelated matrix allocation'))
   with patch.object(c,'OPS',ops):
    with self.assertRaisesRegex(PermissionError,'ONLY_EXACT_DIAGNOSED'):repair_source_bridge(parent,old,old)

 def test_missing_phase_account_only_allowed_before_any_native_call(self):
  from v44_iteration2.resume import phase_account
  with tempfile.TemporaryDirectory(dir=c.ROOT) as d:
   root=Path(d);ledger=root/'NATIVE_RUNTIME_LEDGER.json'
   atomic(ledger,dict(calls=[],inflight=None,measured_Native_Runtime=0.))
   self.assertEqual(phase_account(root),dict(used=0.,calls=[]))
   atomic(ledger,dict(calls=[dict(Native_Runtime=.1)],inflight=None,measured_Native_Runtime=.1))
   with self.assertRaisesRegex(ValueError,'MISSING_PAID_PHASE_I_ACCOUNT'):phase_account(root)

if __name__=='__main__':unittest.main()
