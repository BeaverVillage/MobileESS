import unittest,tempfile,types,os
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
import numpy as np
import scipy.sparse as sp
from v44_iteration2 import config as c,performance as p,resume,recovery
from v44_iteration2.io import read,atomic,record

class Performance(unittest.TestCase):
 def test_real_original_P1_compiler_calls_the_direct_binding(self):
  from tests_iteration2.test_iteration2_p1repair import P1IntervalRepair
  from v44_iteration2.adapters import ACTIVE
  with tempfile.TemporaryDirectory(dir=c.ROOT) as d:
   root=Path(d);request=dict(day=c.DAYS[0],arm='B3',stage='A2',iteration_stage='A3',output=str(root));token=ACTIVE.set(request)
   try:
    with patch.object(p,'bind_pricing',wraps=p.bind_pricing) as observed:
     P1IntervalRepair().compiled(root,0);observed.assert_called_once()
     self.assertTrue(read(root/'ITERATION2_PERFORMANCE_BINDING.json')['PASS'])
   finally:ACTIVE.reset(token)

 def test_actual_compiler_binds_even_when_the_legacy_stage_stack_is_empty(self):
  from v44_iteration2.adapters import ACTIVE
  from v44_iteration2.bootstrap import base
  from v44_recovery_r031 import p1_expansion as e
  with tempfile.TemporaryDirectory(dir=c.ROOT) as d:
   root=Path(d);atomic(root/'BLOCK_PRICING_ORACLE_VERIFICATION.json',dict(records=[]));calls=[]
   def original(*args,**kwargs):
    calls.append(args);value=dict(active_objective_upper='1/2');atomic(Path(args[13])/'FULL_PRICING_RESULT.json',value);return value,[]
   ns=dict(full_pricing=original);request=dict(day=c.DAYS[0],arm='B3',stage='A2',iteration_stage='A3',output=str(root))
   token=ACTIVE.set(request)
   try:
    with patch.object(e.Expansion,'apply',p.promotion_wrapper(e.Expansion.apply,e)):
     p.bind_pricing(ns);bound=ns['full_pricing']
     # The stage installs a profiling wrapper AFTER compilation.
     ns['full_pricing']=lambda *a,**kw:bound(*a,**kw)
     args=[None]*14;args[2]=None;args[13]=root/'P1/S0';ns['full_pricing'](*args)
     self.assertTrue(read(root/'ITERATION2_PERFORMANCE_BINDING.json')['PASS'])
     self.assertTrue((root/'P1/S0/ITERATION2_P1_PLATEAU_ACCELERATION.json').exists());self.assertEqual(len(calls),1)
     old=ns['full_pricing'];p.bind_pricing(ns);self.assertIs(ns['full_pricing'],old)
   finally:ACTIVE.reset(token)

 def test_complete_graph_allowance_is_reserved_for_an_actual_objective_plateau(self):
  module=SimpleNamespace(MAX_COLUMNS_PER_CLASS=20000);seen=[];state=SimpleNamespace()
  def original(self,*args):seen.append(module.MAX_COLUMNS_PER_CLASS);return args[0]
  apply=p.promotion_wrapper(original,module)
  with tempfile.TemporaryDirectory(dir=c.ROOT) as d:
   folder=Path(d)
   for value in ['3/5','1/2','1/2']:
    atomic(folder/'FULL_PRICING_RESULT.json',dict(active_objective_upper=value));apply(state,[{}],None,None,folder,None)
   self.assertEqual(seen,[0,0,8000]);self.assertEqual(module.MAX_COLUMNS_PER_CLASS,20000)

 def test_all31_new_A_stages_use_the_existing_bounded_promotion(self):
  for day in c.DAYS:
   for stage in ('A3','A4'):self.assertTrue(p.selected(dict(day=day,stage='A2',iteration_stage=stage,arm='B3')))
  for arm,stage in [('B1','A3'),('B3','M2'),('B3','ACTUAL')]:self.assertFalse(p.selected(dict(day=c.DAYS[0],stage='A2',iteration_stage=stage,arm=arm)))
  from v44_iteration2.bootstrap import base
  from v44_recovery_r031 import p1_expansion as original
  self.assertEqual((p.MAX_CLASSES,p.MAX_COLUMNS_PER_CLASS,p.MAX_TOTAL_COLUMNS),(original.MAX_CLASSES,original.MAX_COLUMNS_PER_CLASS,original.MAX_TOTAL_COLUMNS))

 def test_oversize_whole_graph_is_not_promoted_and_negative_direction_stays_available(self):
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
   self.assertEqual(expansion.apply([candidate],data,dict(records=[want]),Path(d),loader)[0]['graph'].sha,'active')
   self.assertEqual(expansion.columns,0)
   self.assertEqual(expansion.apply([candidate],data,dict(records=[want]),Path(d),loader)[0]['graph'].sha,'active')

 def test_original_real_expansion_keeps_every_direction_and_enforces_total_column_budget(self):
  from v44_iteration2.bootstrap import base
  from v44_recovery_r031 import p1_expansion as e
  from v42_a_stage_domain_v2 import domain
  graph=lambda sha:SimpleNamespace(sha=sha,events={},states={},compatible={},physical={},transfers={},fixed=None)
  active=graph('active');full=graph('full');snapshot=SimpleNamespace(matrix=SimpleNamespace(shape=(1,8000)),fingerprint=lambda:'snapshot')
  keys=['a','b','c','d'];candidates=[dict(class_id=k,graph=active,support_sha256='active') for k in keys]
  required=[dict(class_id=k,complete_native_primitive_columns=8000,complete_graph_sha256='full') for k in keys]
  data=(None,None,None,None,None,{k:active for k in keys},None,dict(classes={k:[k] for k in keys}))
  loaded=[]
  def load(w):loaded.append(w['class_id']);return dict(graph=full,snapshot=snapshot)
  with tempfile.TemporaryDirectory(dir=c.ROOT) as d,patch.object(e,'MAX_CLASSES',p.MAX_CLASSES),patch.object(e,'MAX_COLUMNS_PER_CLASS',p.MAX_COLUMNS_PER_CLASS),patch.object(e,'MAX_TOTAL_COLUMNS',p.MAX_TOTAL_COLUMNS),patch.object(domain,'graph_content_hash',lambda g:g.sha):
   expansion=e.Expansion();expansion.apply(candidates,data,dict(records=required),Path(d),load)
   result=expansion.apply(candidates,data,dict(records=required),Path(d),load)
   self.assertEqual([r['class_id'] for r in result],keys)
   self.assertEqual([r['graph'].sha for r in result],['full','full','active','active'])
   self.assertEqual(loaded,['a','b']);self.assertEqual(expansion.columns,16000)

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
