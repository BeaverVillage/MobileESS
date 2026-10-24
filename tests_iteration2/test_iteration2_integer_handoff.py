import unittest,tempfile,pickle,gzip,os
from pathlib import Path
from types import SimpleNamespace as NS
from dataclasses import replace
from fractions import Fraction
import numpy as np
import scipy.sparse as sp
from v44_iteration2 import config as c,integer_support as support
from v44_iteration2.io import atomic,record,read


class IntegerHandoff(unittest.TestCase):
 def fixture(self,root,round_=3):
  from v44_iteration2.bootstrap import base
  from v42_a_stage_domain_v2.lexstage import LinearSnapshot,Objective
  reference=LinearSnapshot(sp.csr_matrix([[1.]]),np.zeros(1),np.ones(1),np.array(['<']),np.ones(1),np.array(['C']),(Objective('rho',((0,Fraction(1)),)),))
  typed=replace(reference,vtypes=np.array(['I']))
  state=dict(reference=reference,data=(dict(day=c.DAYS[0]),dict(job='complete original job')),atlas=dict(node_names=['n.1'],unused='LP row atlas'),
   _campaign=dict(input_receipts={}),domains=dict(all_original_options=['STAY','MIGRATE']),metas=dict(large_LP_only_block=True),compact=reference)
  search=object.__new__(support.Support);search.output=root/'OUTPUT';search.round=round_;search.lp_point=np.zeros(1)
  search.history=[dict(round=3,classes=['full'])];search.promoted={'full'};search.checkpoint=None;search.checkpoint_round=None;search.checkpoint_payload=True;search.typed_sha=None
  return search,state,typed,NS(state=state)

 def test_expanded_checkpoint_links_losslessly_and_all_options_rehydrate(self):
  with tempfile.TemporaryDirectory(dir=c.ROOT) as folder:
   root=Path(folder);search,state,typed,physical=self.fixture(root)
   source=root/'APPROVED.pkl.gz'
   with gzip.open(source,'wb') as f:pickle.dump(dict(state=state,round=3,history=search.history,promoted=search.promoted,lp_point=search.lp_point),f)
   search.checkpoint=record(source);search.checkpoint_round=3
   search.persist(state,typed)
   self.assertTrue(os.path.samefile(source,search.output/'STATIC/INTEGER_SEARCH_STATE.pkl.gz'))
   data=state['data'];search.offload(state,typed,physical)
   self.assertIs(state['data'],data);self.assertIs(physical.state,state)
   self.assertEqual(set(state),{'data','atlas','_campaign','_iteration2_offloaded'})
   self.assertFalse(read(search.output/'INTEGER_WORKING_STATE.json')['scientific_option_deletion'])
   search.restore(state,typed)
   self.assertEqual(state['domains']['all_original_options'],['STAY','MIGRATE'])
   self.assertTrue(state['metas']['large_LP_only_block'])
   self.assertEqual(replace(state['reference'],vtypes=typed.vtypes).fingerprint(),typed.fingerprint())

 def test_initial_integer_search_uses_existing_complete_P1_checkpoint(self):
  with tempfile.TemporaryDirectory(dir=c.ROOT) as folder:
   search,state,typed,physical=self.fixture(Path(folder),0)
   checkpoint=search.output/'STATIC/P1_CLOSED_STATE.pkl.gz';checkpoint.parent.mkdir(parents=True)
   with gzip.open(checkpoint,'wb') as f:pickle.dump(state,f)
   search.offload(state,typed,physical)
   self.assertFalse(search.checkpoint_payload)
   search.restore(state,typed)
   self.assertIn('MIGRATE',state['domains']['all_original_options'])

 def test_current_native_snapshot_drift_is_rejected_before_rehydration(self):
  with tempfile.TemporaryDirectory(dir=c.ROOT) as folder:
   search,state,typed,physical=self.fixture(Path(folder),0)
   checkpoint=search.output/'STATIC/P1_CLOSED_STATE.pkl.gz';checkpoint.parent.mkdir(parents=True)
   with gzip.open(checkpoint,'wb') as f:pickle.dump(state,f)
   search.offload(state,typed,physical)
   with self.assertRaisesRegex(ValueError,'CURRENT_INTEGER_SNAPSHOT_DRIFT'):search.restore(state,replace(typed,rhs=np.array([2.])))


if __name__=='__main__':unittest.main()
