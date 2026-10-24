import unittest,tempfile,inspect
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch
from fractions import Fraction
from v44_iteration2 import integer_support as support,config as c
import numpy as np
import scipy.sparse as sp
from dataclasses import replace
from v44_iteration2.io import read,record,atomic
from contextlib import nullcontext


class IntegerSupport(unittest.TestCase):
 def test_batch_preserves_classes_and_does_not_drop_oversized_graph(self):
  required={k:dict(complete_graph_sha256='full_'+k,complete_native_primitive_columns=n) for k,n in [('a',6000),('b',15000),('c',25000)]}
  state=dict(data=(None,None,None,None,None,{k:NS(sha='active_'+k) for k in required},None,dict(classes={k:[k] for k in required})))
  first=support.choose(required,state,dict(a=100,b=50,c=10),set())
  self.assertEqual(first,['a'])
  self.assertEqual(support.choose(required,state,dict(c=200),{'a','b'}),['c'])
  self.assertEqual(support.choose(required,state,{},set(required)),[])

 def test_small_restricted_gap_never_replaces_global_acceptance(self):
  search=object.__new__(support.Support);native=NS(remaining=lambda:4000)
  failed=[dict(acceptance=dict(PASS=False),gap=.00688)]
  self.assertTrue(search.need_more(failed,dict(status=2,MIPGap=.0003),native))
  self.assertFalse(search.need_more([dict(acceptance=dict(PASS=True))],dict(status=11),native))
  self.assertFalse(search.need_more([],dict(status=2),native))
  self.assertFalse(search.need_more(failed,dict(status=2),NS(remaining=lambda:0)))

 def test_incumbent_evidence_is_not_overwritten_after_enrichment(self):
  with tempfile.TemporaryDirectory(dir=c.ROOT) as folder:
   root=Path(folder);(root/'I').mkdir();(root/'I/V1.npz').write_bytes(b'original')
   self.assertEqual(support.unique_incumbent(root),root/'I/V2')
   self.assertEqual((root/'I/V1.npz').read_bytes(),b'original')

 def test_actual_inherited_compiler_keeps_original_checks_and_live_namespace(self):
  from v44_iteration2.bootstrap import base
  from v44_recovery_r029 import integer_repair
  from v42_may_campaign_native90 import a_stage
  with patch.object(a_stage,'_iteration2_integer_support',support,create=True):
   fn=base.live_compiler(support.compiler(integer_repair.compile_run))(a_stage.run)
   source=inspect.getsource(fn)
   self.assertIn('_iteration2_search.expand(state,typed,_point)',source)
   self.assertIn('contract(zero, closure, bound, candidate, verification)',source)
   self.assertIn('physical.verify(point)',source)
   self.assertIn('repair_conflict(native,typed',source)
   self.assertIn("native.solve(typed, _iteration2_search.folder(), 'INTEGER_CONTROL')",source)
   self.assertIs(fn.__globals__['_iteration2_integer_support'],support)

 def test_actual_A2_source_tree_includes_the_enrichment_instead_of_disk_body(self):
  from v44_iteration2.bootstrap import base
  from v44_recovery_r029 import integer_repair
  from v42_may_campaign_native90 import a_stage
  from v44.frozen.v43_a2 import adapter
  import ast
  with tempfile.TemporaryDirectory(dir=c.ROOT) as folder:
   request=dict(day=c.DAYS[0],iteration_stage='A3',root=folder,output=str(Path(folder)/'OUTPUT'))
   with patch.object(a_stage,'_iteration2_integer_support',support,create=True),patch.object(integer_repair,'compile_run',base.live_compiler(support.compiler(integer_repair.compile_run))):
    with integer_repair.install(),support.selective_scope(request):
     source=ast.unparse(adapter.source_tree(a_stage,'run'))
     self.assertIn('_iteration2_search.expand(state, typed, _point)',source)
     self.assertIn('repair_conflict(native, typed',source)
     self.assertTrue((Path(folder)/'ITERATION2_INTEGER_SUPPORT_BINDING.json').exists())
     self.assertFalse((Path(folder)/'OUTPUT').exists(),'Fresh prepare must start with an empty output directory')

 def test_cached_integer_types_require_exact_original_model_fingerprint(self):
  from v42_a_stage_domain_v2.lexstage import LinearSnapshot,Objective
  with tempfile.TemporaryDirectory(dir=c.ROOT) as folder:
   parent=Path(folder);out=parent/'OUTPUT';step=out/'P1/INTEGER_CONTROL';step.mkdir(parents=True)
   snapshot=LinearSnapshot(sp.csr_matrix([[1.]]),np.zeros(1),np.ones(1),np.array(['<']),np.ones(1),np.array(['C']),(Objective('rho',((0,Fraction(1)),)),))
   typed=replace(snapshot,vtypes=np.array(['I']))
   attributes=out/'ATTRIBUTES.npz';matrix=out/'MATRIX.npz'
   np.savez_compressed(attributes,vtypes=typed.vtypes);sp.save_npz(matrix,typed.matrix)
   identity=dict(original_snapshot_sha256=typed.fingerprint(),attributes=record(attributes),matrix=record(matrix))
   atomic(step/'MODEL_IDENTITY.json',identity);atomic(out/'ORIGINAL_INTEGER_TYPE_RESTORATION.json',dict(PASS=True))
   request=dict(_iteration2_integer_resume_parent=str(parent))
   answer,proof=support.restore_typed(dict(reference=snapshot),request,None)
   self.assertEqual(answer.fingerprint(),typed.fingerprint());self.assertTrue(proof['same_case_type_proof_reused'])
   np.savez_compressed(attributes,vtypes=snapshot.vtypes);identity['attributes']=record(attributes);atomic(step/'MODEL_IDENTITY.json',identity)
   with self.assertRaisesRegex(ValueError,'TYPED_SNAPSHOT_DRIFT'):support.restore_typed(dict(reference=snapshot),request,None)

 def test_maintenance_keeps_latest_account_and_approved_P1_checkpoint_separate(self):
  from v44_iteration2 import resume
  from v44_recovery_r046 import planning
  with tempfile.TemporaryDirectory(dir=c.ROOT) as folder:
   root=Path(folder);parent=root/'attempt014/A2';checkpoint=root/'attempt013/A2';ops=root/'OPS';ops.mkdir()
   permit=ops/'PERMIT.json';atomic(permit,dict(resumable_A_stages=[dict(parent_core=str(parent),integer_gap_continuation=True,integer_checkpoint_parent=str(checkpoint))]))
   atomic(ops/'AUTHORIZATION.json',dict(repair_permit=record(permit)))
   request={};receipt=dict(measured=564.853,remaining=4835.147)
   with patch.object(c,'OPS',ops),patch.object(resume,'admit',return_value=receipt) as admit,patch.object(resume,'phase_account',return_value=dict(used=50.998,calls=[])),patch.object(planning,'a1_scope',return_value=nullcontext()) as clock:
    with resume.a_scope(parent,request) as result:
     self.assertEqual(request['_iteration2_integer_resume_parent'],str(checkpoint))
     self.assertEqual(result['measured'],564.853);self.assertEqual(result['inherited_Phase_I_Native_seconds'],50.998)
    admit.assert_called_once_with(parent,request);clock.assert_called_once_with(parent)


if __name__=='__main__':unittest.main()
