import unittest,tempfile,types,os
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
import numpy as np
import scipy.sparse as sp
from v44_iteration2 import config as c,performance as p,resume,recovery
from v44_iteration2.io import read,atomic,record

class Performance(unittest.TestCase):
 def test_complete_graph_allowance_is_reserved_for_an_actual_objective_plateau(self):
  module=SimpleNamespace(MAX_COLUMNS_PER_CLASS=20000);seen=[];state=SimpleNamespace()
  def original(self,*args):seen.append(module.MAX_COLUMNS_PER_CLASS);return args[0]
  apply=p.promotion_wrapper(original,module)
  with tempfile.TemporaryDirectory(dir=c.ROOT) as d:
   folder=Path(d)
   for value in ['3/5','1/2','1/2']:
    atomic(folder/'FULL_PRICING_RESULT.json',dict(active_objective_upper=value));apply(state,[{}],None,None,folder,None)
   self.assertEqual(seen,[0,0,20000]);self.assertEqual(module.MAX_COLUMNS_PER_CLASS,20000)

 def test_all31_new_A_stages_use_the_existing_bounded_promotion(self):
  for day in c.DAYS:
   for stage in ('A3','A4'):self.assertTrue(p.selected(dict(day=day,stage='A2',iteration_stage=stage,arm='B3')))
  for arm,stage in [('B1','A3'),('B3','M2'),('B3','ACTUAL')]:self.assertFalse(p.selected(dict(day=c.DAYS[0],stage='A2',iteration_stage=stage,arm=arm)))
  self.assertLessEqual(11*15725,p.MAX_TOTAL_COLUMNS);self.assertGreaterEqual(p.MAX_COLUMNS_PER_CLASS,15725)

 def test_real_expansion_promotes_15725_columns_on_repeat_and_enforces_limits(self):
  from v44_iteration2.bootstrap import base
  from v44_recovery_r031 import p1_expansion as e
  from v42_a_stage_domain_v2 import domain
  graph=lambda sha:SimpleNamespace(sha=sha,events={},states={},compatible={},physical={},transfers={},fixed=None)
  active=graph('active');full=graph('full');snapshot=SimpleNamespace(matrix=SimpleNamespace(shape=(1,15725)),fingerprint=lambda:'snapshot')
  candidate=dict(class_id='klass',graph=active,support_sha256='active')
  want=dict(class_id='klass',complete_native_primitive_columns=15725,complete_graph_sha256='full',external_full_block_cache={})
  data=(None,None,None,None,None,{'uid':active},None,dict(classes={'klass':['uid']}))
  with tempfile.TemporaryDirectory(dir=c.ROOT) as d,patch.object(e,'MAX_CLASSES',p.MAX_CLASSES),patch.object(e,'MAX_COLUMNS_PER_CLASS',p.MAX_COLUMNS_PER_CLASS),patch.object(e,'MAX_TOTAL_COLUMNS',p.MAX_TOTAL_COLUMNS),patch.object(domain,'graph_content_hash',lambda g:g.sha):
   expansion=e.Expansion();loader=lambda w:dict(graph=full,snapshot=snapshot)
   self.assertEqual(expansion.apply([candidate],data,dict(records=[want]),Path(d),loader)[0]['graph'].sha,'active')
   self.assertEqual(expansion.apply([candidate],data,dict(records=[want]),Path(d),loader)[0]['graph'].sha,'full')
   self.assertEqual(expansion.columns,15725)
   self.assertEqual(expansion.apply([candidate],data,dict(records=[want]),Path(d),loader)[0]['graph'].sha,'active')

 def test_matrix_links_round_trip_exactly_and_overwriting_one_is_copy_on_write(self):
  with tempfile.TemporaryDirectory(dir=c.ROOT) as d:
   root=Path(d);storage=p.MatrixStorage(root);save=storage.saver(sp.save_npz);matrix=sp.csr_matrix([[1.,0.],[2.,3.]])
   a=root/'STATIC/NATIVE/A/MATRIX.npz';b=root/'STATIC/NATIVE/B/MATRIX.npz';a.parent.mkdir(parents=True);b.parent.mkdir(parents=True)
   save(a,matrix);save(b,matrix.copy());self.assertEqual(a.read_bytes(),b.read_bytes());self.assertEqual(a.stat().st_ino,b.stat().st_ino)
   old=record(a);changed=matrix.copy();changed.data[0]=9.;save(b,changed)
   self.assertEqual(record(a),old);self.assertEqual(sp.load_npz(a)[0,0],1.);self.assertEqual(sp.load_npz(b)[0,0],9.)
   self.assertEqual(storage.links,1);self.assertGreater(storage.saved_bytes,0)

 def test_indexed_pricing_keeps_every_native_call_and_exact_certificate(self):
  from v44_iteration2.bootstrap import base
  from v42_a_stage_canary import pricing
  from v42_a_stage_domain_v2.lexstage import LinearSnapshot,Objective
  from fractions import Fraction
  original=pricing.full_pricing;newcode=p.pricing_code(original)
  full=LinearSnapshot(sp.csr_matrix([[1.]]),np.zeros(1),np.array([10.]),np.array(['=']),np.array([1.]),np.array(['C']),(Objective('rho',()),))
  master=LinearSnapshot(sp.csr_matrix([[1.,1.,1.],[0.,1.,0.],[0.,0.,1.]]),np.zeros(3),np.full(3,10.),np.array(['<','=','=']),np.array([10.,1.,1.]),np.full(3,'C'),(Objective('rho',((0,Fraction(1)),)),))
  records=[dict(class_id=k,full_physical_STAY=1,full_physical_migration=0,full_compact_blocks=1) for k in ('a','b')]
  cache=dict(snapshot=full,B=sp.csr_matrix([[1.]]),graph=SimpleNamespace(sha='g'))
  with tempfile.TemporaryDirectory(dir=c.ROOT) as d:
   root=Path(d);atomic(root/'BLOCK_PRICING_ORACLE_VERIFICATION.json',dict(records=records));outputs=[];callsets=[]
   for code in (original.__code__,newcode):
    ns=dict(original.__globals__,HISTORY=root,load_cache=lambda w:cache,validate_coverage=lambda *a:None)
    fn=types.FunctionType(code,ns,'full_pricing',original.__defaults__);fn.__kwdefaults__=original.__kwdefaults__
    calls=[]
    def solve(snapshot,folder,component):
     calls.append((snapshot.fingerprint(),component));return dict(status=2,native_seconds=1.),dict(X=np.ones(1),Pi=np.array([.1]),RC=np.zeros(1))
    native=SimpleNamespace(remaining=lambda:100,solve=solve)
    out=fn(native,master,None,dict(X=np.array([.5,1.,1.]),Pi=np.array([-.1,.1,.1])),None,None,None,None,{'g':0},1,[0],{'a':[1],'b':[2]},{2:'b',1:'a'},root/str(len(outputs)))
    out[0].pop('pricing_wall_seconds');outputs.append(out);callsets.append(calls)
   self.assertEqual(outputs[0],outputs[1]);self.assertEqual(callsets[0],callsets[1]);self.assertEqual(len(callsets[1]),2)

 def test_only_a_sealed_non_native_maintenance_stop_can_be_requeued(self):
  from tests_iteration2.test_iteration2_p1repair import RecoveryAccounts
  with tempfile.TemporaryDirectory(dir=c.ROOT) as d:
   parent,old,row,ops=RecoveryAccounts().fixture(Path(d));(parent/'RESULT.json').unlink()
   stop=Path(d)/'STOP.json';value=dict(Native_call_interrupted=False,ledger=row['ledger'],request=row['old_request'],parent_core=str(parent))
   atomic(stop,value);row['maintenance_stop']=record(stop);permit=Path(d)/'REPAIR_PERMIT.json'
   def seal():
    atomic(permit,dict(resumable_A_stages=[row],scientific_equations_domain_and_acceptance_unchanged=True,Native_budget_reset=False));atomic(ops/'AUTHORIZATION.json',dict(repair_permit=record(permit)))
   seal();state=dict(jobs=[dict(day=old['day'],status='PLANNING_INTERRUPTED',stages=dict(A3=dict(root=str(parent.parent),status='MAINTENANCE_STOPPED',PASS=False)))])
   with patch.object(c,'OPS',ops):
    self.assertEqual(resume.repair_source_bridge(parent,old,old),row);recovery.requeue(state);self.assertEqual(state['jobs'][0]['status'],'REPAIR_QUEUED')
    value['Native_call_interrupted']=True;atomic(stop,value);row['maintenance_stop']=record(stop);seal()
    with self.assertRaisesRegex(PermissionError,'NON_NATIVE_BOUNDARY'):resume.repair_source_bridge(parent,old,old)

if __name__=='__main__':unittest.main()
